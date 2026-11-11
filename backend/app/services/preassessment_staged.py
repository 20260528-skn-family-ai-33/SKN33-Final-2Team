"""설문 먼저 저장·노출 후 퀴즈 생성. 기존 초안 JSON과 세대 검증 사용."""
from copy import deepcopy
from app.errors import ApiError
from app.services import survey_store as store


def generate_for(employee_id, project_id):
    from app.routers import preassessment as api
    with api.generation_guard('draft', str(project_id)):
        me=api.profile.view(employee_id)
        if me is None:raise ApiError(404,'PROFILE_NOT_FOUND','개인 프로필을 찾을 수 없어요.')
        personal=api.profile_input(me)
        with api.db.tx() as t:
            project=api.project_input(t,employee_id,project_id)
            existing=store.read(t,employee_id,project_id)
        same=existing is not None and api.inputs_match(existing,project,personal)
        if same and existing.get('quizStatus') not in ('pending','failed'):return store.public_view(existing)
        ctx=api.runtime.context(employee_id,me)
        if not ctx.live:raise ApiError(503,'MODEL_REQUIRED','사용 가능한 모델을 선택해 주세요.')
        if same:selection=existing['selection']
        elif 'selectedSkills' in project:
            from app.services.preassessment_flow import checked_skills
            from app import catalog
            selection=checked_skills(project['selectedSkills'],catalog.skill_names())
        else:
            from app.learner_knowledge import from_profile,hr_context
            selection=api.select_from_catalog(ctx,dict(project,learnerKnowledge=from_profile(personal),hrContext=hr_context(personal)))
        def current(t):
            if api.project_input(t,employee_id,project_id)!=project or api.profile_input(api.profile.view(employee_id) or {})!=personal:
                raise ApiError(409,'SURVEY_INPUT_CHANGED','생성 중 입력이 변경됐어요. 다시 준비해 주세요.')
        def generate(phase):
            task='역량 테스트 설문 문항 생성' if phase=='surveys' else '역량 테스트 퀴즈 문항 생성'
            return api.generate_survey(project,selection,personal,api.runtime.model(ctx,'진단 에이전트',task),require_measurement=True,phase=phase)
        if not same:
            partial=generate('surveys')
            with api.db.tx() as t:
                store._owned(t,employee_id,project_id,lock=True);current(t)
                existing=store.save_generated(t,employee_id,project_id,project,selection,personal,partial,replace_generation_id=existing['generationId'] if existing else None,phase='surveys')
        gid=existing['generationId']
        try:
            with api.db.tx() as t:
                raw=store._owned(t,employee_id,project_id,lock=True);current(t)
                value=deepcopy(raw.get(store.KEY))
                if not value or value['generationId']!=gid:raise ApiError(409,'SURVEY_INPUT_CHANGED','문항이 변경됐어요.')
                value['quizStatus']='pending';store._write(t,employee_id,project_id,value)
            quizzes=generate('quizzes')
            with api.db.tx() as t:
                raw=store._owned(t,employee_id,project_id,lock=True);current(t)
                value=deepcopy(raw.get(store.KEY))
                if not value or value['generationId']!=gid:raise ApiError(409,'SURVEY_INPUT_CHANGED','문항이 변경됐어요.')
                combined=deepcopy(value['survey'])
                quiz_rows={g['skill']:g['quizzes'] for g in quizzes['groups']}
                for group in combined['groups']:group['quizzes']=quiz_rows[group['skill']]
                value['survey']=api.generate_survey(project,selection,personal,lambda *_:combined,require_measurement=True)
                value['quizStatus']='ready';store._write(t,employee_id,project_id,value)
                return store.public_view(value)
        except Exception:
            with api.db.tx() as t:
                raw=store._owned(t,employee_id,project_id,lock=True)
                value=deepcopy(raw.get(store.KEY))
                if value and value.get('generationId')==gid:
                    value['quizStatus']='failed';store._write(t,employee_id,project_id,value)
            raise
