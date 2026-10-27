import unittest

from src.shared.catalog_scope import body_text, scoped_matches
from src.shared.instructional_content import teaching_text
from src.shared.skill_matching import SkillMatcher
from src.database.course_skill_corrections import validate_plan


class InstructionalContentTests(unittest.TestCase):
    def setUp(self):
        self.matcher = SkillMatcher([
            {'skill_id': 5, 'name': 'ETL & 데이터 파이프라인'},
            {'skill_id': 6, 'name': '데이터 웨어하우스 & OLAP'},
            {'skill_id': 9, 'name': 'MLOps & 모델 서빙'},
            {'skill_id': 15, 'name': '리눅스 환경 및 Bash 스크립팅'},
        ])

    def matches(self, text):
        return scoped_matches(self.matcher, {'syllabus_summary': text})

    def test_prerequisite_only_linux_is_not_taught(self):
        text = '학습대상\n- 학습자의 선수능력 : 리눅스 기초, SQL\n커리큘럼\n데이터 수집\n플럼(Flume)\n스쿱(Sqoop)'
        self.assertEqual(set(self.matches(text)), {5})
        self.assertIn('리눅스', text)

    def test_linux_curriculum_survives_prerequisite_section(self):
        text = '선수지식\nLinux 기초\n학습목표\nBash 스크립트 작성과 Linux 프로세스 관리를 실습한다.'
        self.assertIn(15, self.matches(text))

    def test_inline_prerequisite_removed_without_hiding_curriculum(self):
        text = '선수학습: Linux 기초\n학습 목표\n데이터 수집 파이프라인 실습과 Sqoop 활용'
        self.assertNotIn(15, self.matches(text))
        self.assertIn(5, self.matches(text))

    def test_beginner_promise_is_not_a_prerequisite_heading(self):
        text = '사전지식 없이 배우는 Linux 명령어 실습'
        self.assertEqual(teaching_text(text), text)
        self.assertIn(15, self.matches(text))

    def test_biography_and_references_not_taught(self):
        text = '강사 소개\nLinux 엔지니어 경력\n참고문헌\nMLOps 교재\n공개 단원\nHive 테이블 관리 실습'
        self.assertEqual(set(self.matches(text)), {6})

    def test_book_and_job_descriptions_preserved(self):
        text = '선수지식\nLinux\n강사 소개\nMLOps'
        self.assertEqual(body_text({'description': text}).strip(), text)

    def test_instructor_introduction_lesson_does_not_hide_following_lessons(self):
        text = '강의를 시작하며\n강사소개\n이번 강의에서 배울 내용 정리\n커리큘럼\nLinux 명령어 실습'
        self.assertIn(15, self.matches(text))
        # No explicit curriculum heading is also common in video lesson lists.
        self.assertIn(15, self.matches(text.replace('커리큘럼\n', '')))

    def test_legacy_prerequisite_paragraph_ends_before_actual_lessons(self):
        text = '선행지식\n\n\nPython 사전 학습을 권합니다.\n\n\nLinux 프로세스 관리 실습'
        self.assertIn(15, self.matches(text))
        self.assertNotIn('Python', body_text({'syllabus_summary': text}))

    def test_hadoop_alone_is_not_a_warehouse(self):
        for text in ('하둡 HDFS YARN MapReduce 설치 및 구현 실습',
                     'Hadoop 사용자 명령어 archive checknative classpath conftest credential',
                     '하둡 설치 방법을 학습한다. 참고문헌 hive 매뉴얼'):
            with self.subTest(text=text):
                self.assertNotIn(6, self.matches(text))

    def test_actual_warehouse_and_hive_teaching_retained(self):
        for text in ('데이터 웨어하우스 및 OLAP 실습', 'Data Warehouse 모델링 실습',
                     'Hive 테이블 관리 실습', '하이브를 활용한 데이터 분석',
                     '영화 평점 분석(Hive)', '하이브/피그를 학습하고 이해한다.'):
            with self.subTest(text=text):
                self.assertIn(6, self.matches(text))

    def test_ml_deployment_tracking_and_lifecycle_are_candidates(self):
        for text in ('Azure Machine Learning 모델 배포 및 모니터링',
                     '기계 학습 모델 버전 관리 및 수명 주기 관리',
                     'MLflow를 사용하여 메트릭과 모델 아티팩트를 추적한다.',
                     '머신러닝 모델 Server 배포', '기계 학습 모델을 프로덕션에 배포한다.'):
            with self.subTest(text=text):
                self.assertIn(9, self.matches(text))

    def test_non_ml_model_deployment_is_not_mlops(self):
        for text in ('데이터 모델 배포와 테이블 관리 실습', 'BIM 건축 모델 배포와 버전 관리',
                     'Linux 서버 배포 및 모니터링', '머신러닝 소개.\n일반 애플리케이션 배포'):
            with self.subTest(text=text):
                self.assertNotIn(9, self.matches(text))

    def test_plan_rejects_missing_evidence_duplicate_and_empty_links(self):
        row = dict(course_id='X', title='과정', before_skill_ids=[6], after_skill_ids=[5],
                   reason='실제 수집 단원', evidence=['Flume'], syllabus_sha256='a' * 64)
        self.assertEqual(validate_plan({'corrections': [row]}), [row])
        for rows in ([], [row, row], [{**row, 'evidence': []}],
                     [{**row, 'after_skill_ids': []}], [{**row, 'after_skill_ids': [5, 5]}]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    validate_plan({'corrections': rows})
