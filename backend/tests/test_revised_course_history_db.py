"""팀 백업 복원본과 로컬 BGE-M3에서만 실행하는 수정안 이수 이력 회귀 검사."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')

from app import db
from app.agents import runtime
from app.agents.resource_recommendations import recommend_from_catalog
from app.services import plans
from app.services.course_recommendations import completed_course_ids


@unittest.skipUnless(os.getenv('GP_TEST_COURSE_HISTORY_DB'), '별도 복원 DB와 BGE-M3 필요')
class RevisedCourseHistoryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(db.val('SELECT current_database()'), os.environ['GP_TEST_COURSE_HISTORY_DB'])
        with db.tx() as t:
            self.employee = t.val("""INSERT INTO public.employees(name, employee_number)
                VALUES('QA 이수 이력', gen_random_uuid()::text) RETURNING employee_id""")
            self.project = t.val("""INSERT INTO public.projects(employee_id, project_name, status, draft_choices)
                VALUES(:e, 'QA 이수 이력', 'IN_PROGRESS', '{}') RETURNING project_id""", e=self.employee)
            self.round = t.val("""INSERT INTO public.diagnostic_rounds(project_id, round_number, project_snapshot)
                VALUES(:p, 1, '{}') RETURNING diagnostic_round_id""", p=self.project)
        self.addCleanup(self.clean_fixtures)

    def clean_fixtures(self):
        with db.tx() as t:
            t.run('DELETE FROM public.projects WHERE project_id = :p', p=self.project)
            t.run('DELETE FROM public.employees WHERE employee_id = :e', e=self.employee)

    def candidates(self, track):
        name = 'RAG & 생성형 AI 에이전트'
        pre = {'project': {'goal': 'RAG 문서 검색과 답변 근거 평가'},
               'selection': {'skills': [{'name': name, 'application': 'RAG 문서 검색'}]}}
        # 실제 검색 결과 중 첫 강좌를 고정 선택해 모델 변동 없이 비교한다.
        def select_first(ctx, system, payload, **kwargs):
            first = payload['skills'][0]['courses'][0]
            return {'skills': [{'name': name, 'courses': [{'key': first['choiceKey']}], 'books': []}]}

        with db.tx() as t:
            completed = completed_course_ids(t, self.employee)
        with patch.object(runtime, 'llm_json', side_effect=select_first):
            result = recommend_from_catalog(SimpleNamespace(live=True), pre, {'id': track}, completed=completed)
        candidates = {row['resourceId'] for row in result['retrieval']['matches']
                      if not row['resourceId'].startswith('book_')}
        selected = result['skills'][0]['selectedCourse']
        self.assertIn(selected, candidates)
        return selected, candidates

    def test_removed_completed_courses_stay_excluded_from_all_three_tracks(self):
        tracks = ('A1', 'A2', 'A3')
        before = {track: self.candidates(track) for track in tracks}
        finished = {selected for selected, _ in before.values()}
        all_candidates = set.union(*(ids for _, ids in before.values()))
        unfinished = sorted(all_candidates - finished)[0]
        acts = [dict(id=f'qa-{i}', stage=2, res=rid, title='QA 강좌', hours=1, wFrom=1, wTo=1)
                for i, rid in enumerate(sorted(finished) + [unfinished])]
        task = dict(id='task', stage=3, res=None, title='QA 과제', hours=1, wFrom=1, wTo=1)
        plan = {'opt': 'A3', 'name': 'Challenge Course', 'tagline': 'QA', 'version': 1,
                'acts': [*acts, task], 'prefs': {}, 'handoff': {}}
        with db.tx() as t:
            roadmap = plans.insert_roadmap(t, str(self.project), str(self.round), plan)
        for act in acts:
            plans.save_progress(self.employee, roadmap, act['id'], {'status': 'done'})
        plans.save_progress(self.employee, roadmap, acts[-1]['id'], {'status': 'doing'})

        revision = dict(label='강좌 제외', to=dict(plan, acts=[task]), prefsTo={}, handoff={})
        with db.tx() as t:
            rid = t.val("""INSERT INTO app_ext.roadmap_revisions(roadmap_id, request, result, status)
                VALUES(:r, '{}', :rev, 'ready') RETURNING revision_id""", r=roadmap, rev=db.J(revision))
        accepted = plans.accept_revision(self.employee, roadmap, str(rid))
        self.assertEqual([a['id'] for a in accepted['plan']['acts']], ['task'])
        with db.tx() as t:
            self.assertFalse(t.val("""SELECT EXISTS(SELECT 1 FROM public.roadmap_steps s
                JOIN public.roadmap_step_resources r USING (step_id)
                WHERE s.roadmap_id = :r AND r.course_id IS NOT NULL)""", r=roadmap))

        for track in tracks:
            with self.subTest(track=track):
                _, candidates = self.candidates(track)
                self.assertEqual(finished & candidates, set())
        with db.tx() as t:
            self.assertEqual(completed_course_ids(t, self.employee), finished)
            t.run("UPDATE public.projects SET draft_choices = :marker WHERE project_id = :p",
                  marker=db.J({'demoSeeded': True}), p=self.project)
            self.assertEqual(completed_course_ids(t, self.employee), frozenset())
