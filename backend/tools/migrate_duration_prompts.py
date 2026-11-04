"""#72 활성 프롬프트의 표시 계약만 버전 추가. 기본 읽기 전용, --apply / --rollback 기록.json."""
import argparse
import hashlib
import json
from pathlib import Path

from app import db
from app.agents.roadmap_display import with_display_contract

AGENTS = ('agent_certified', 'agent_fasttrack', 'agent_practical')
CHANGE_REASON = '이슈 #72: 자료 학습 기간·비용 표시 계약 v1 (기존 정책 보존)'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def transform(text):
    parts = text.split('\n### REVISION\n', 1)
    if len(parts) != 2 or not parts[0].startswith('### GENERATION\n'):
        raise ValueError('GENERATION/REVISION 구역 형식을 확인해 주세요.')
    generation = parts[0][len('### GENERATION\n'):]
    if not generation.strip() or not parts[1].strip():
        raise ValueError('비어 있는 프롬프트는 변경할 수 없습니다.')
    return '### GENERATION\n' + with_display_contract(generation) + '\n### REVISION\n' + with_display_contract(parts[1])


def migrate(apply=False):
    result = {'issue': 72, 'applied': apply, 'versions': []}
    with db.tx() as t:
        for agent in AGENTS:
            if apply:
                t.val('SELECT pg_advisory_xact_lock(hashtext(:key))', key='prompt:' + agent)
            rows = t.all('SELECT prompt_version_id,version_num,system_prompt FROM public.prompt_versions WHERE agent_id=:a AND is_active' + (' FOR UPDATE' if apply else ''), a=agent)
            if len(rows) != 1:
                raise ValueError('활성 프롬프트가 정확히 하나 필요합니다: ' + agent)
            current = rows[0]
            prompt = transform(current['system_prompt'])
            record = {'agent': agent, 'beforeId': str(current['prompt_version_id']),
                      'beforeVersion': current['version_num'], 'beforeHash': digest(current['system_prompt']),
                      'afterHash': digest(prompt), 'changed': prompt != current['system_prompt']}
            if apply and record['changed']:
                version = t.val('SELECT coalesce(max(version_num),0)+1 FROM public.prompt_versions WHERE agent_id=:a', a=agent)
                t.run('UPDATE public.prompt_versions SET is_active=false,deactivated_at=now() WHERE agent_id=:a AND is_active', a=agent)
                new_id = t.val('INSERT INTO public.prompt_versions(agent_id,version_num,system_prompt,is_active,parent_version_id,change_reason) VALUES(:a,:v,:p,true,:parent,:reason) RETURNING prompt_version_id',
                               a=agent, v=version, p=prompt, parent=current['prompt_version_id'], reason=CHANGE_REASON)
                record.update(afterId=str(new_id), afterVersion=version)
            result['versions'].append(record)
    return result


def rollback(manifest):
    if manifest.get('issue') != 72 or manifest.get('applied') is not True:
        raise ValueError('이슈 #72의 실제 적용 기록이 필요합니다.')
    records = manifest.get('versions') or []
    if sorted(row['agent'] for row in records) != sorted(AGENTS):
        raise ValueError('세 코스의 적용 기록을 모두 확인해 주세요.')
    restored = []
    with db.tx() as t:
        for row in records:
            if not row['changed']:
                continue
            agent = row['agent']
            t.val('SELECT pg_advisory_xact_lock(hashtext(:key))', key='prompt:' + agent)
            active = t.all('SELECT prompt_version_id,parent_version_id,system_prompt FROM public.prompt_versions WHERE agent_id=:a AND is_active FOR UPDATE', a=agent)
            if len(active) != 1 or str(active[0]['prompt_version_id']) != row['afterId'] or str(active[0]['parent_version_id']) != row['beforeId'] or digest(active[0]['system_prompt']) != row['afterHash']:
                raise ValueError('적용 후 프롬프트가 변경되어 자동 복구를 중단합니다: ' + agent)
            parent = t.one('SELECT system_prompt FROM public.prompt_versions WHERE agent_id=:a AND prompt_version_id=:id FOR UPDATE', a=agent, id=row['beforeId'])
            if not parent or digest(parent['system_prompt']) != row['beforeHash']:
                raise ValueError('부모 버전 원문이 적용 기록과 다릅니다: ' + agent)
            t.run('UPDATE public.prompt_versions SET is_active=false,deactivated_at=now() WHERE prompt_version_id=:id', id=row['afterId'])
            t.run('UPDATE public.prompt_versions SET is_active=true,deactivated_at=NULL WHERE prompt_version_id=:id', id=row['beforeId'])
            restored.append({'agent': agent, 'versionId': row['beforeId'], 'hash': row['beforeHash']})
    return {'issue': 72, 'restored': restored}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    report = rollback(json.loads(args.rollback.read_text(encoding='utf-8-sig'))) if args.rollback else migrate(args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
