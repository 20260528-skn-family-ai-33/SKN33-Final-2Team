"""DB 정렬 환경이 달라도 같은 마스터 정보의 목표 후보 캐시를 재사용한다."""
import os
import unittest
from unittest.mock import Mock

os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
from app.agents import goals as agent
from app.services import goals, profile


class ProfileOrderTests(unittest.TestCase):
    def values(self, skills, certificates, personal=None):
        tx = Mock()
        tx.all.side_effect = lambda query, **_: (
            [{'title': x} for x in certificates] if 'public.certifications' in query
            else [{'name': x} for x in skills])
        state = {'profile': personal, 'certIds': [1, 2], 'unlisted': '직접 입력 B\n직접 입력 A', 'workDesc': '로그 분석'}
        return profile._team_values(tx, 1, state)

    def input_hash(self, values):
        return goals._hash(agent.goal_input(values))

    def test_master_order_and_input_hash_survive_database_collation_change(self):
        skills = ['자료구조', '운영체제', 'SQL 쿼리 튜닝']
        certs = ['정보처리기사', 'ADsP']
        before = self.values(skills, certs)
        after = self.values(list(reversed(skills)), list(reversed(certs)))
        self.assertEqual(before['tech'], ['SQL 쿼리 튜닝', '운영체제', '자료구조'])
        self.assertEqual(before['certs'], ['ADsP', '정보처리기사', '직접 입력 B', '직접 입력 A'])
        self.assertEqual(before, after)
        self.assertEqual(self.input_hash(before), self.input_hash(after))

    def test_personal_input_order_and_explicit_empty_override_are_preserved(self):
        values = self.values(['사내 스킬'], [], {'technology_experience': 'Python\nJava'})
        self.assertEqual(values['tech'], ['Python', 'Java'])
        empty = self.values(['사내 스킬'], [], {'technology_experience': ''})
        self.assertEqual(empty['tech'], [])

    def test_actual_skill_or_certificate_change_still_invalidates_cache(self):
        before = self.values(['SQL'], ['ADsP'])
        changed_skill = self.values(['SQL', 'Python'], ['ADsP'])
        changed_cert = self.values(['SQL'], ['ADsP', '정보처리기사'])
        self.assertNotEqual(self.input_hash(before), self.input_hash(changed_skill))
        self.assertNotEqual(self.input_hash(before), self.input_hash(changed_cert))


if __name__ == '__main__':
    unittest.main()
