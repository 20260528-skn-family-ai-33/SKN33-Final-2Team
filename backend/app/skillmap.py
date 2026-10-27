"""스킬 지도 자료 — 검토·확정 화면과 확정한 내 로드맵 화면 (GET /api/v1/skills/map · 설계서 밖 추가 2026-10-23).

스킬 점(skill_tags 36개)·분야(category)·점 크기(그 스킬이 붙은 강좌·도서·자격 수)는 팀 DB에서 읽는다.
스킬 선수 관계는 아직 팀 DB에 표가 없어 db/team_request/skill_prerequisites.csv(Claude 초안 · 가정)를 읽는다(2026-10-23 사용자 결정: 지금은 파일 유지).
팀 DB에 public.skill_prerequisites(db/team_request/skill_prerequisites.sql)가 생기면 _prerequisites() 만 그 표를 읽게 바꾼다.
화면(web/assets/gp-skillmap.js)은 이 API 응답만 보므로 그대로 쓴다(prerequisiteSource 로 '초안'인지 'DB'인지 알린다).
"""
from __future__ import annotations

import csv
from pathlib import Path

from . import db
from .errors import ApiError

PREREQ_CSV = Path(__file__).resolve().parent.parent / 'db' / 'team_request' / 'skill_prerequisites.csv'


def _skills() -> list[dict]:
    # 같은 자료에 같은 스킬이 두 번 붙은 행은 한 번만 센다
    return db.all_("""WITH r AS (SELECT 'c' || course_id AS k, skill_id FROM public.course_skills
                                 UNION SELECT 'b' || isbn, skill_id FROM public.book_skills
                                 UNION SELECT 'x' || cert_id, skill_id FROM public.certification_skills)
                      SELECT t.skill_id AS id, t.name, coalesce(t.category, '') AS category, count(r.k)::int AS resources
                      FROM public.skill_tags t LEFT JOIN r ON r.skill_id = t.skill_id
                      GROUP BY t.skill_id, t.name, t.category ORDER BY t.skill_id""")


def _prerequisites(id_by_name: dict[str, int]) -> tuple[list[list[int]], list[dict]]:
    """[먼저 배울 스킬 id, 다음 스킬 id] 목록과, 지금 DB 스킬 이름과 맞지 않아 뺀 행.
    CSV 는 이름으로 맞춘다(팀 DB 판마다 번호가 달라질 수 있어서 · 번호 열은 참고값)."""
    if not PREREQ_CSV.exists():
        raise ApiError(500, 'SKILL_PREREQ_MISSING', '스킬 선수 관계 파일이 없어요', '5차 목업 폴더의 db/team_request/skill_prerequisites.csv 를 확인해 주세요')
    pairs, unmatched = [], []
    with PREREQ_CSV.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            a, b = id_by_name.get(row.get('prerequisite_skill_name', '')), id_by_name.get(row.get('skill_name', ''))
            if a and b and a != b:
                pairs.append([a, b])
            else:
                unmatched.append({'skill': row.get('skill_name', ''), 'prerequisite': row.get('prerequisite_skill_name', '')})
    return pairs, unmatched


def skill_map() -> dict:
    skills = _skills()
    pairs, unmatched = _prerequisites({s['name']: s['id'] for s in skills})
    return {'skills': skills, 'prerequisites': pairs, 'unmatched': unmatched, 'prerequisiteSource': 'draft'}
