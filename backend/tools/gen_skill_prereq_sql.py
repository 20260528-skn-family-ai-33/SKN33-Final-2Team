"""스킬 선수 관계 초안 CSV로 팀 DB 추가용 SQL을 만든다.

입력: db/team_request/skill_prerequisites.csv — 목업 서버(app/skillmap.py)가 지금 읽는 원본. 열: skill_id, skill_name, prerequisite_skill_id, prerequisite_skill_name
출력: db/team_request/skill_prerequisites.sql — public.skill_prerequisites 표 만들기 + 행 넣기(여러 번 실행해도 됨)
번호(skill_id)는 팀 DB 판마다 달라질 수 있어 SQL은 스킬 이름(skill_tags.name, UNIQUE)으로 맞춰 넣는다. CSV의 번호 열은 사람이 읽기 위한 참고값이다.
CSV를 고치면 이 스크립트를 다시 돌려 SQL을 맞춘다(SQL을 직접 고치지 않는다).

실행: python tools/gen_skill_prereq_sql.py db/team_request/skill_prerequisites.csv db/team_request/skill_prerequisites.sql
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

HEAD = """-- GrowPath · 팀 DB 추가 요청안: 스킬 선수 관계 표 public.skill_prerequisites
-- 초안({n}행) · 아직 팀 DB에 없음 · tools/gen_skill_prereq_sql.py 가 skill_prerequisites.csv 에서 만든 파일(직접 고치지 말고 CSV를 고친 뒤 다시 만든다)
-- 관계는 Claude가 일반적인 학습 순서로 만든 가정이다. 팀 검토(추가·삭제) 뒤에 넣는다.
-- 뜻: prerequisite_skill_id 를 먼저 배우면 skill_id 를 배우기 쉽다(먼저 배울 스킬 → 다음 스킬). 순환(A→B→A)은 넣지 않는다(제약으로 막지는 않음).
-- 쓰는 곳: 5차 목업 검토·확정·내 로드맵 화면의 스킬 지도(GET /api/v1/skills/map). 표가 생기면 app/skillmap.py 가 CSV 대신 이 표를 읽게 바꾼다.
-- 번호는 DB 판마다 달라질 수 있어 스킬 이름으로 맞춰 넣는다. 여러 번 실행해도 된다(ON CONFLICT DO NOTHING).
BEGIN;

CREATE TABLE IF NOT EXISTS public.skill_prerequisites (
  skill_id integer NOT NULL REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE,
  prerequisite_skill_id integer NOT NULL REFERENCES public.skill_tags(skill_id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT skill_prerequisites_pkey PRIMARY KEY (skill_id, prerequisite_skill_id),
  CONSTRAINT skill_prerequisites_not_self CHECK (skill_id <> prerequisite_skill_id)
);
CREATE INDEX IF NOT EXISTS skill_prerequisites_prereq_idx ON public.skill_prerequisites (prerequisite_skill_id);
COMMENT ON TABLE public.skill_prerequisites IS '스킬 선수 관계: prerequisite_skill_id 를 먼저 배우면 좋은 skill_id';

CREATE TEMP TABLE _skill_prereq_draft (skill_name text NOT NULL, prerequisite_skill_name text NOT NULL) ON COMMIT DROP;
INSERT INTO _skill_prereq_draft (skill_name, prerequisite_skill_name) VALUES
"""

TAIL = """
INSERT INTO public.skill_prerequisites (skill_id, prerequisite_skill_id)
SELECT s.skill_id, p.skill_id
FROM _skill_prereq_draft v
JOIN public.skill_tags s ON s.name = v.skill_name
JOIN public.skill_tags p ON p.name = v.prerequisite_skill_name
ON CONFLICT DO NOTHING;

-- 확인 1: 지금 skill_tags 이름과 맞지 않아 빠진 행(0행이어야 한다)
SELECT v.skill_name, v.prerequisite_skill_name
FROM _skill_prereq_draft v
LEFT JOIN public.skill_tags s ON s.name = v.skill_name
LEFT JOIN public.skill_tags p ON p.name = v.prerequisite_skill_name
WHERE s.skill_id IS NULL OR p.skill_id IS NULL;
-- 확인 2: 표의 행 수
SELECT count(*) AS skill_prerequisites_rows FROM public.skill_prerequisites;

COMMIT;
"""


def sql_text(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def main(src: Path, dst: Path) -> None:
    with src.open(encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.DictReader(f)]
    if not rows:
        raise SystemExit(f'{src}: 행이 없어요')
    for i, r in enumerate(rows, 2):
        if not r.get('skill_name') or not r.get('prerequisite_skill_name') or r['skill_name'] == r['prerequisite_skill_name']:
            raise SystemExit(f'{src}:{i}: 스킬 이름이 비었거나 자기 자신을 선수로 적었어요')
    values = ',\n'.join(f"  ({sql_text(r['skill_name'])}, {sql_text(r['prerequisite_skill_name'])})" for r in rows) + ';\n'
    dst.write_text(HEAD.format(n=len(rows)) + values + TAIL, encoding='utf-8', newline='\n')
    print(f'{dst}: {len(rows)}행')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('사용법: python tools/gen_skill_prereq_sql.py <입력 CSV> <출력 SQL>')
    main(Path(sys.argv[1]), Path(sys.argv[2]))
