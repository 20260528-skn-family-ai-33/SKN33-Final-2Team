"""진단 설문 풀(#225)을 스킬 태그마다 5문항씩 미리 만든다.

기본은 읽기 전용 점검(모델 호출·DB 쓰기 0회)이다. 실제 생성은 --apply 와 --provider 가 모두 있어야 하며
풀이 없는 스킬만 만든다(--force 는 이미 있는 풀도 다시 만든다). 스킬마다 모델 호출 1회·저장 1회이며,
한 스킬이 실패해도 앞서 저장한 스킬은 유지되므로 같은 명령을 다시 실행하면 남은 스킬만 이어서 만든다.

  python tools/generate_survey_pool.py                                  # 점검
  python tools/generate_survey_pool.py --apply --provider openai --max-calls 5 --skill Python
  python tools/generate_survey_pool.py --apply --provider openai --max-calls 300
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db, llm
from app.agents.runtime import parse_json
from app.services import survey_pool


def targets(t, names: list[str] | None, force: bool) -> tuple[list[dict], int]:
    """(만들 스킬 목록, 이미 있는 풀 수). 이름이 바뀐 스킬의 풀은 다시 만든다."""
    tags = t.all('SELECT skill_id, name FROM public.skill_tags ORDER BY skill_id')
    if names:
        known = {row['name'] for row in tags}
        missing = [name for name in names if name not in known]
        if missing:
            raise SystemExit(f'skill_tags 에 없는 스킬: {", ".join(missing)}')
        tags = [row for row in tags if row['name'] in set(names)]
    ready = set(survey_pool.load(t, [row['name'] for row in tags]))
    todo = tags if force else [row for row in tags if row['name'] not in ready]
    return todo, len(ready)


def generate_one(provider: str, skill: str) -> tuple[dict, str]:
    messages = [{'role': 'system', 'content': survey_pool.SYSTEM},
                {'role': 'user', 'content': json.dumps({'skill': skill}, ensure_ascii=False)}]
    res = llm.chat(provider, messages, json_mode=True)
    return survey_pool.clean(skill, parse_json(res['content'])), res.get('model') or llm.model_name(provider)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--skill', action='append', help='이 스킬만 만든다(여러 번 지정 가능)')
    parser.add_argument('--provider', choices=('openai', 'ollama'))
    parser.add_argument('--apply', action='store_true', help='실제로 모델을 호출하고 저장한다')
    parser.add_argument('--force', action='store_true', help='이미 있는 풀도 다시 만든다')
    parser.add_argument('--max-calls', type=int, default=0, help='--apply 때 허용할 최대 모델 호출 수(필수)')
    args = parser.parse_args(argv)
    with db.tx() as t:
        if not survey_pool.table_exists(t):
            parser.error('app_ext.skill_survey_pool 표가 없습니다. 먼저 db/migrate_survey_pool.sql 을 적용하세요.')
        todo, ready = targets(t, args.skill, args.force)
    summary = {'skills_to_generate': len(todo), 'already_pooled': ready, 'prompt_hash': survey_pool.PROMPT_HASH}
    if not args.apply:
        print(json.dumps(dict(summary, mode='preview', paid_api_calls=0, database_writes=0,
                              sample=[row['name'] for row in todo[:10]]), ensure_ascii=False))
        return 0
    if not args.provider:
        parser.error('--apply 에는 --provider 가 필요합니다. 모델·API 예산을 먼저 확인하세요.')
    if not llm.available(args.provider):
        parser.error(f'{args.provider} 모델 연결 설정이 없습니다.')
    if len(todo) > args.max_calls:
        parser.error(f'만들 스킬 {len(todo)}개가 --max-calls {args.max_calls} 를 넘습니다. 예산을 확인한 뒤 값을 올리세요.')
    saved, failed = 0, []
    for row in todo:
        try:
            item, model = generate_one(args.provider, row['name'])
        except Exception as err:  # 한 스킬 실패가 다른 스킬 저장을 막지 않게 하고 결과에 남긴다
            failed.append({'skill': row['name'], 'error': type(err).__name__, 'message': str(err)[:200]})
            continue
        with db.tx() as t:
            survey_pool.save(t, row['skill_id'], row['name'], item, model)
        saved += 1
    print(json.dumps(dict(summary, mode='apply', paid_api_calls=len(todo), saved=saved, failed=failed), ensure_ascii=False))
    return 0 if not failed else 2


if __name__ == '__main__':
    raise SystemExit(main())
