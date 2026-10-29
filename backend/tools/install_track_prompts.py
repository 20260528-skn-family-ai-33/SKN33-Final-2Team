"""이슈 #38: Track 프롬프트 새 버전 등록. 이전 이력 보존 및 동일 내용 재실행 지원."""
from app import db
from app.agents import roadmap as rm

POLICIES = {
    'A1': '''Free Track: 무료 자료만 허용한다.
- catalog에서 cost가 정확히 0인 자료만 사용한다. 유료 및 비용 미확인(null) 자료는 금지한다.
- 목표에 맞는 무료 강좌를 우선하고 무료 공식 문서와 무료 도구로 직접 실습한다.
- 무료 자료가 부족하면 근거 있는 무료 자료와 실습으로 보완하고 부족한 범위는 scope에 명시한다. 유료 자료로 대체하지 않는다.
- 유료 자격시험, 유료 API 결제, 결제수단 등록이 필요한 실습을 요구하지 않는다. 유료인 필수 요청은 불가 이유를 scope/notes에 명시한다.
- 기간·주당 시간·예산·보안 조건을 지킨다. 무료 전용 규칙은 다른 요청 및 수정 요청보다 우선한다.''',
    'A2': '''Fast Track: 단기 집중 과정이다.
- 목표에 직접 필요한 핵심 내용과 최소 기능 결과물에 집중하여 총 학습 시간을 줄인다.
- 목표에 명시된 작업은 누락하지 않는다. 부가 학습은 줄이고 제외 범위는 scope에 설명한다.
- 짧은 강좌·핵심 공식 문서·작동 여부 검증 실습을 우선한다. 근거 없이 시간을 축소하거나 품질·보안 검증을 생략하지 않는다.
- 주당 시간·기간·예산 한도를 지킨다. 최소 범위 충족이 불가능하면 한계를 명시한다.''',
    'A3': '''Challenge Track: 고강도 실무 적용 과정이다.
- 업무 맥락의 프로젝트·직접 구현·테스트·평가·개선을 중심으로 도전적인 실무 훈련을 구성한다.
- 업무 적용 단계에 전체 시간의 절반 이상을 배정하되 사용자 수준·주당 시간·기간·예산 한도를 넘지 않는다.
- 과제마다 구체적인 결과물과 검증 가능한 완료 기준을 적는다. 난도만 높이려 무관한 기술이나 불필요한 과제를 넣지 않는다.
- 업무 데이터 사용 전 공개 범위·개인정보·보안을 확인한다. 허가되지 않은 데이터 대신 공개 샘플을 사용한다.
- 결과물을 테스트하고 문제점을 개선하는 과정을 포함한다.''',
}


def install():
    with db.tx() as t:
        for pid, agent in rm.TRACK_PROMPT_AGENTS.items():
            t.val('SELECT pg_advisory_xact_lock(hashtext(:key))', key='prompt:' + agent)
            values = dict(rm.D['perspectives'][pid], id=pid, rules=POLICIES[pid], focus=POLICIES[pid])
            generation = rm.R_SYS.format(**values) + '\n\n[최우선 Track 정책]\n' + POLICIES[pid]
            revision = rm.REV_SYS.format(**values) + '\n\n[최우선 Track 정책]\n' + POLICIES[pid]
            prompt = '### GENERATION\n' + generation + '\n### REVISION\n' + revision
            active = t.all('SELECT prompt_version_id,system_prompt FROM public.prompt_versions WHERE agent_id=:a AND is_active FOR UPDATE', a=agent)
            if len(active) > 1:
                raise RuntimeError('Multiple active prompts: ' + agent)
            if active and active[0]['system_prompt'] == prompt:
                print(agent, 'unchanged')
                continue
            version = t.val('SELECT coalesce(max(version_num),0)+1 FROM public.prompt_versions WHERE agent_id=:a', a=agent)
            parent = active[0]['prompt_version_id'] if active else None
            t.run('UPDATE public.prompt_versions SET is_active=false,deactivated_at=now() WHERE agent_id=:a AND is_active', a=agent)
            t.run('INSERT INTO public.prompt_versions(agent_id,version_num,system_prompt,is_active,parent_version_id,change_reason) VALUES(:a,:v,:p,true,:parent,:reason)',
                  a=agent, v=version, p=prompt, parent=parent,
                  reason='이슈 #38: ' + values['name'] + ' 생성·수정 프롬프트 DB 연결. 기존 이력 보존.')
            print(agent, 'version', version)


if __name__ == '__main__':
    install()