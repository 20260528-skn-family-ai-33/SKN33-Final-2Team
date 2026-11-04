"""월간 개선 생성→별도 비교 평가→버전 확인→원자적 적용. 명시적 실행 전에는 동작하지 않는다."""
from copy import deepcopy
import json

from app import db
from app.agents import prompt_improvement as agent, roadmap, runtime
from app.services.prompt_improvement_evaluation import evaluate_gate
from app.services.prompt_selection_store import read_decisions


def current_prompts(transaction=None) -> dict:
    read = transaction.all if transaction else db.all_
    result = {}
    for course, agent_id in sorted(roadmap.TRACK_PROMPT_AGENTS.items()):
        rows = read('SELECT prompt_version_id,system_prompt FROM public.prompt_versions WHERE agent_id=:a AND is_active', a=agent_id)
        if len(rows) != 1:
            raise agent.ImprovementError('코스별 활성 프롬프트가 정확히 하나 필요합니다.')
        row = rows[0]
        result[course] = {'promptVersionId': str(row['prompt_version_id']), 'systemPrompt': agent._prompt_text(row['system_prompt'])}
    return result


def activate(expected: dict, approved: list[dict], period_key: str) -> dict:
    """통과한 안만 같은 트랜잭션으로 적용. 부모 버전과 평가 결과를 남기고 삭제하지 않는다."""
    if not approved:
        return {}
    with db.tx() as transaction:
        # 기존 수동 설치 경로와 같은 잠금 키를 사용해 경쟁 변경을 막는다.
        for agent_id in sorted(roadmap.TRACK_PROMPT_AGENTS.values()):
            transaction.val('SELECT pg_advisory_xact_lock(hashtext(:key))', key='prompt:' + agent_id)
        if current_prompts(transaction) != expected:
            raise agent.ImprovementError('평가 중 활성 프롬프트가 변경되어 적용하지 않습니다.')
        marker = 'monthly-prompt-improvement:' + period_key
        if transaction.one('SELECT 1 FROM public.prompt_versions WHERE change_reason LIKE :marker LIMIT 1', marker=marker + '%'):
            raise agent.ImprovementError('이 월간 실행은 이미 적용된 기록이 있습니다.')
        seen, prepared = set(), []
        for row in approved:
            course = row.get('course')
            if not isinstance(course, str) or course not in expected or course in seen:
                raise agent.ImprovementError('적용 대상 코스가 없거나 중복되었습니다.')
            if row.get('basePromptVersionId') != expected[course]['promptVersionId']:
                raise agent.ImprovementError('평가한 부모 프롬프트 버전이 다릅니다.')
            verdict = evaluate_gate(row.get('baselineEvaluation'), row.get('candidateEvaluation'))
            if not verdict['approved']:
                raise agent.ImprovementError('비교 평가를 통과한 프롬프트만 적용합니다.')
            text = agent.replacement_text(expected[course]['systemPrompt'], row.get('systemPrompt'))
            if text == expected[course]['systemPrompt']:
                raise agent.ImprovementError('기존과 동일한 프롬프트입니다.')
            seen.add(course)
            prepared.append((row, text, verdict))
        # 모든 검증을 마친 뒤에만 UPDATE/INSERT를 실행한다.
        versions = {}
        for row, text, verdict in prepared:
            course = row['course']
            agent_id = roadmap.TRACK_PROMPT_AGENTS[course]
            number = transaction.val('SELECT coalesce(max(version_num),0)+1 FROM public.prompt_versions WHERE agent_id=:a', a=agent_id)
            transaction.run('UPDATE public.prompt_versions SET is_active=false,deactivated_at=now() WHERE agent_id=:a AND is_active', a=agent_id)
            audit = {'reason': row['changeReason'], 'references': row['references'], 'evaluation': verdict,
                     'baseline': row['baselineEvaluation'], 'candidate': row['candidateEvaluation']}
            versions[course] = str(transaction.val('INSERT INTO public.prompt_versions(agent_id,version_num,system_prompt,is_active,parent_version_id,change_reason) VALUES(:a,:v,:p,true,CAST(:parent AS uuid),:reason) RETURNING prompt_version_id',
                a=agent_id, v=number, p=text, parent=row['basePromptVersionId'], reason=marker + '\n' + json.dumps(audit, ensure_ascii=False)))
    return versions


def run_cycle(period_key: str, evaluate, *, ctx=None, apply=True) -> dict:
    """평가기는 실제 동일 사례의 (기존 결과, 개선 결과)를 반환해야 한다. 자기 승인 사용 금지."""
    snapshot = current_prompts()
    context = ctx or runtime.Ctx(employee_id=0, provider='ollama', by='월간 프롬프트 개선')
    proposal = agent.run(context, snapshot, read_decisions())
    if proposal['status'] != 'proposed':
        return proposal
    accepted, results = [], []
    for change in proposal['changes']:
        try:
            before, after = evaluate(context, change['course'], snapshot[change['course']]['systemPrompt'], change['systemPrompt'])
            verdict = evaluate_gate(before, after)
        except Exception:
            # 오류 원문에는 평가 입력/모델 응답이 들어갈 수 있으므로 결과에 포함하지 않는다.
            results.append({'course': change['course'], 'approved': False, 'reason': '비교 평가 실행 실패'})
            continue
        results.append({'course': change['course'], **verdict})
        if verdict['approved']:
            accepted.append(dict(deepcopy(change), baselineEvaluation=deepcopy(before), candidateEvaluation=deepcopy(after)))
    versions = activate(snapshot, accepted, period_key) if apply and accepted else {}
    return {'status': 'applied' if versions else 'evaluated', 'model': proposal['model'], 'metrics': proposal['metrics'],
            'evaluations': results, 'appliedVersions': versions, 'approvedCount': len(accepted), 'dryRun': not apply}
