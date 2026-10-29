"""Public outlines, portable cache evidence and bounded model handoff regression."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

from src.database.course_curriculum import VERSION, normalize, plain, repair_numbered_titles
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.catalog_evidence import CATALOG_BYTES, content_text, evidence, pack, packed_bytes


class CourseCurriculumTests(unittest.TestCase):
    def test_week_and_lesson_numbers_use_the_same_source_row_title(self):
        payload = {'summary': '<table><tr><th>주차</th><th>주제</th><th>차시</th><th>내용</th></tr>'
                   '<tr><td>WEEK 1</td><td>SW 배포체계</td><td>1-1</td><td>배포 위험</td></tr>'
                   '<tr><td>1-2</td><td>통합 배포 체계</td></tr></table>'}
        value = normalize('API_KMOOC', payload)
        self.assertEqual([r['title'] for r in value['items']], ['SW 배포체계', '통합 배포 체계'])
        self.assertEqual(value['items'][0]['section'], 'WEEK 1')
        self.assertEqual(value['items'][0]['description'], '1-1 / 배포 위험')
        self.assertEqual(value['items'][0]['original_title'], 'WEEK 1')
        self.assertEqual(value['items'][0]['original_description'], 'SW 배포체계 / 1-1 / 배포 위험')

    def test_restored_outline_repairs_without_original_cache_and_is_idempotent(self):
        import copy
        value = {'source': 'API_KMOOC', 'payload_sha256': 'preserved', 'item_count': 2,
                 'items': [{'title': '1 주차', 'section': '', 'description': 'SQL / SELECT'},
                           {'title': '트랜잭션', 'section': '', 'description': '격리 수준'}]}
        before = copy.deepcopy(value)
        fixed = repair_numbered_titles(value)
        self.assertEqual(value, before)
        self.assertEqual(fixed['payload_sha256'], value['payload_sha256'])
        self.assertEqual(fixed['item_count'], 2)
        self.assertEqual(fixed['items'][1], value['items'][1])
        self.assertEqual(fixed, repair_numbered_titles(fixed))

    def test_kocw_video_metadata_is_preserved_and_no_missing_title_is_invented(self):
        value = normalize('WEB_KOCW', {'lessons': [
            {'title': '1-2', 'chapter': '1.', 'description': '파이썬 기본 이론', 'video_listed': True},
            {'title': '2-1', 'description': ''}]})
        self.assertEqual(value['items'][0]['title'], '파이썬 기본 이론')
        self.assertEqual(value['items'][0]['section'], '1. / 1-2')
        self.assertTrue(value['items'][0]['video'])
        self.assertEqual(value['items'][1]['title'], '제목 미제공')
        self.assertEqual(value['items'][1]['original_title'], '2-1')
        self.assertTrue(value['items'][1]['title_missing'])
        self.assertEqual(value['coverage'], 'partial_outline')

    def test_entire_ai_catalog_budget_and_four_skill_limit(self):
        records=[{'id':str(i),'title':'SQL 강좌 '+str(i),'kind':'강좌','type':'course','format':'영상',
                  'skills':['SQL']*12,'hours':1,'timeStatus':'estimated','content':'한글 소개 '*1000,
                  'curriculum':{'items':[{'title':'SQL 조인','description':'한글 목차 '*1000}]*100}}
                 for i in range(28)]
        result=pack(records,['SQL 조인'])
        self.assertEqual(len(result),28)
        self.assertLessEqual(packed_bytes(result),CATALOG_BYTES)
        self.assertLessEqual(sum('curriculum' in r for r in result),4)
        self.assertTrue(all(len(r['skills'])==4 for r in result))
        self.assertTrue(all(r['timeStatus']=='estimated' for r in result))
        self.assertLessEqual(sum(len(str(v)) for r in evidence(records[0])['curriculum'] for v in r.values()),240)

    def test_huge_metadata_and_extra_candidates_cannot_bypass_catalog_budget(self):
        records=[{'id':str(i),'title':'긴 강좌명 '*1000,'kind':'강좌','type':'course',
                  'skills':['긴 스킬명 '*100]*30,'content':'내용'*10000} for i in range(60)]
        result=pack(records)
        self.assertGreater(len(result),0)
        self.assertLess(len(result),len(records))
        self.assertEqual(result[0]['id'],'0')
        self.assertLessEqual(packed_bytes(result),CATALOG_BYTES)

    def test_kmooc_table_keeps_later_topics_and_continuation_rows(self):
        payload={'summary':'<h2>소개</h2><table><tr><th>주차</th><th>차시목차</th><th>세부목차</th></tr>'
                 '<tr><td>1</td><td>SQL</td><td>SELECT</td></tr><tr><td>JOIN</td></tr>'
                 '<tr><td>2</td><td>트랜잭션</td><td>격리 수준</td></tr></table>'}
        value=normalize('API_KMOOC',payload)
        self.assertEqual([row['title'] for row in value['items']],['SQL','JOIN','트랜잭션'])
        self.assertEqual(value['items'][-1]['description'],'격리 수준')

    def test_assessment_week_labels_do_not_become_a_course_outline(self):
        value=normalize('API_KMOOC',{'summary':'<table><tr><td>구분</td><td>평가유형</td><td>평가시기</td></tr>'
                        '<tr><td>퀴즈</td><td>SQL 평가</td><td>1, 3, 5 주차</td></tr></table>'})
        self.assertEqual(value['coverage'],'description_only')
        self.assertEqual(value['items'],[])

    def test_opentutorials_full_ordered_outline_survives_restore_without_cache(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder)
            raw=b'<a class="depth_0" href="/course/1/11">First</a><a class="depth_1" href="/course/1/12">Second</a><a href="/course/1/11">Next</a>'
            (root/'course.html').write_bytes(raw)
            payload={'source_id':1,'html_path':'course.html','html_sha256':hashlib.sha256(raw).hexdigest(),
                     'url':'https://opentutorials.org/course/1','lessons':[{'title':'Sample'}]}
            value=normalize('WEB_OPENTUTORIALS',payload,source_root=root)
            self.assertEqual([row['title'] for row in value['items']],['First','Second'])
            (root/'course.html').unlink()
            self.assertEqual(normalize('WEB_OPENTUTORIALS',payload,previous=value,source_root=root),value)
            (root/'course.html').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'checksum'):
                normalize('WEB_OPENTUTORIALS',payload,source_root=root)

    def test_missing_cache_preserves_sample_status_and_never_claims_full_outline(self):
        value=normalize('WEB_OPENTUTORIALS',{'lessons':[{'title':'sample'}]})
        self.assertEqual(value['coverage'],'sample')
        self.assertEqual(normalize('API_MS_LEARN',{'units':['uid']})['coverage'],'description_only')

    def test_sample_upgrades_when_the_same_source_cache_becomes_available(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            raw = b'<a class="depth_0" href="/course/1/11">First</a><a class="depth_1" href="/course/1/12">Second</a>'
            payload = {'source_id': 1, 'html_path': 'course.html',
                       'html_sha256': hashlib.sha256(raw).hexdigest(), 'lessons': [{'title': 'Sample'}]}
            sample = normalize('WEB_OPENTUTORIALS', payload, source_root=root)
            self.assertEqual(sample['coverage'], 'sample')
            (root / 'course.html').write_bytes(raw)
            full = normalize('WEB_OPENTUTORIALS', payload, previous=sample, source_root=root)
            self.assertEqual(full['coverage'], 'public_outline')
            self.assertEqual([row['title'] for row in full['items']], ['First', 'Second'])
            self.assertEqual(full['payload_sha256'], sample['payload_sha256'])
            self.assertEqual(normalize('WEB_OPENTUTORIALS', payload, previous=full, source_root=root), full)
            (root / 'course.html').unlink()
            self.assertEqual(normalize('WEB_OPENTUTORIALS', payload, previous=full, source_root=root), full)

    def test_missing_outline_upgrades_from_verified_supplement_and_rejects_bad_hash(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            raw = b'<a class="unit-title" href="1">First</a><a class="unit-title" href="2">Second</a>'
            payload = {'units': ['first', 'second']}
            supplement = {'html_path': 'ms.html', 'html_sha256': hashlib.sha256(raw).hexdigest()}
            missing = normalize('API_MS_LEARN', payload, source_root=root, supplement=supplement)
            self.assertEqual(missing['coverage'], 'description_only')
            (root / 'ms.html').write_bytes(b'wrong source')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                normalize('API_MS_LEARN', payload, previous=missing, source_root=root, supplement=supplement)
            (root / 'ms.html').write_bytes(raw)
            full = normalize('API_MS_LEARN', payload, previous=missing, source_root=root, supplement=supplement)
            self.assertEqual(full['coverage'], 'public_outline')
            self.assertEqual(full['item_count'], 2)
            self.assertEqual(full['supplement_input_sha256'], missing['supplement_input_sha256'])

    def test_available_cache_does_not_replace_a_richer_partial_outline(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root = Path(folder)
            raw = b'<a class="unit-title" href="1">First</a>'
            payload = {'units': ['one', 'two', 'three'], 'html_path': 'ms.html',
                       'html_sha256': hashlib.sha256(raw).hexdigest()}
            description = '공개 단원\nFirst\nSecond'
            partial = normalize('API_MS_LEARN', payload, description, source_root=root)
            self.assertEqual(partial['item_count'], 2)
            (root / 'ms.html').write_bytes(raw)
            self.assertEqual(normalize('API_MS_LEARN', payload, description, previous=partial, source_root=root), partial)

    def test_changed_source_or_normalizer_version_rebuilds_the_cached_outline(self):
        payload = {'lessons': [{'title': 'Old', 'hasVideo': True}]}
        original = normalize('WEB_INFLEARN', payload)
        changed = normalize('WEB_INFLEARN', {'lessons': [{'title': 'New', 'hasVideo': True}]}, previous=original)
        self.assertEqual(changed['items'][0]['title'], 'New')
        stale_version = dict(original, version='old', items=[{'title': 'Stale'}])
        rebuilt = normalize('WEB_INFLEARN', payload, previous=stale_version)
        self.assertEqual(rebuilt['items'][0]['title'], 'Old')

    def test_ms_supplement_uses_public_titles_not_invented_uid_labels(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder);raw=b'<a class="unit-title" href="1-intro">Introduction</a>'
            (root/'ms.html').write_bytes(raw)
            supplement={'html_path':'ms.html','html_sha256':hashlib.sha256(raw).hexdigest(),'url':'https://learn.microsoft.com/test/'}
            value=normalize('API_MS_LEARN',{'units':['some.uid']},supplement=supplement,source_root=root)
            self.assertEqual(value['coverage'],'public_outline')
            self.assertEqual(value['items'][0]['title'],'Introduction')
            self.assertEqual(value['supplement_sha256'],supplement['html_sha256'])

    def test_untitled_source_entries_are_retained_as_partial_outline(self):
        value=normalize('WEB_INFLEARN',{'lessons':[{'title':'JOIN'},{'title':'','runtime':123}]})
        self.assertEqual(value['coverage'],'partial_outline')
        self.assertEqual(len(value['items']),2)
        self.assertTrue(value['items'][1]['title_missing'])

    def test_visual_transcription_requires_matching_image_and_survives_restore(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder);raw=b'original public image';(root/'outline.png').write_bytes(raw)
            supplement={'visual_transcription':{'image':{'path':'outline.png','sha256':hashlib.sha256(raw).hexdigest()},
                'method':'codex_visual_transcription','human_review':False,
                'items':[{'title':'SQL','description':'JOIN'}]}}
            value=normalize('API_KMOOC',{},supplement=supplement,source_root=root)
            self.assertEqual(value['items'][0]['description'],'JOIN')
            (root/'outline.png').unlink()
            self.assertEqual(normalize('API_KMOOC',{},previous=value,source_root=root),value)
            (root/'outline.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):
                normalize('API_KMOOC',{},supplement=supplement,source_root=root)

    def test_full_content_and_cleanup_preserve_meaningful_text_after_600_characters(self):
        source='id="course" class="cdt-card">\n'+'기초 내용\n'*150+'후반부 트랜잭션 격리 수준'
        for clean in (plain,content_text):
            result=clean(source)
            self.assertNotIn('class=',result)
            self.assertGreater(len(result),600)
            self.assertTrue(result.endswith('후반부 트랜잭션 격리 수준'))
            self.assertEqual(clean('<p>A &amp; B</p><script>hidden</script><p>C</p>'),'A & B\nC')

    def test_goal_relevant_tail_chapter_survives_model_budget_with_explicit_omission(self):
        rows=[{'title':f'기초 {i}','description':'기초 '*100} for i in range(100)]
        rows.append({'title':'PostgreSQL 트랜잭션 격리 수준','description':'MVCC'})
        r={'content':'기본 소개\n'*300+'PostgreSQL 트랜잭션 격리 수준',
           'curriculum':{'coverage':'public_outline','items':rows},'timeStatus':'estimated','timeNote':'가정'}
        value=evidence(r,['PostgreSQL 트랜잭션'])
        self.assertIn('PostgreSQL 트랜잭션 격리 수준',[x['title'] for x in value['curriculum']])
        self.assertGreater(value['curriculumOmitted'],0)
        self.assertTrue(value['contentTruncated'])
        self.assertLessEqual(sum(len(str(v)) for x in value['curriculum'] for v in x.values()),1800)
        self.assertEqual(value['timeStatus'],'estimated')

    def test_normalized_outline_does_not_change_existing_scope_input(self):
        from src.shared.catalog_scope import body_text
        fields={'course_id':'COURSE_FIXTURE','syllabus_summary':'학습 내용\nSQL 조인 실습'}
        original=body_text(fields)
        fields['curriculum']={'version':VERSION,'source_url':'https://example.invalid/python',
            'description':'새 목차 근거','items':[{'title':'머신러닝 배포'}]}
        self.assertEqual(body_text(fields),original)
        self.assertIn('관계형 데이터베이스',body_text({'curriculum':'관계형 데이터베이스'}))

    def test_relevant_term_after_a_long_single_line_is_kept_in_the_model_excerpt(self):
        value=evidence({'content':'기초 '*1000+'MVCC 구현',
            'curriculum':{'items':[{'title':'데이터베이스','description':'소개 '*1000+'MVCC 구현'}]}},['MVCC'])
        self.assertIn('MVCC',value['content'])
        self.assertIn('MVCC',value['curriculum'][0]['description'])


if __name__=='__main__':
    unittest.main()
