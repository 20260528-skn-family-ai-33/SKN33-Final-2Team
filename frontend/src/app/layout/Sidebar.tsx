/* 좌측 메뉴 (5차 gp-core.js sidebar · aiBox) — 직원 화면 공통 */
import { newIdToPath, paths } from '@/app/paths';
import { useState } from 'react';
import { NotificationBell } from '@/features/notifications/NotificationBell';
import { useGo } from '@/shared/hooks/useGo';
import { ai, canClearHiddenDemoSettings, clearDemoSettings, levelLabel, ping, PROV, resetConn, setChoice, setReasoning, useAi, useAiMode, type UiProvider } from '@/shared/state/ai';
import { logoutAndReset } from '@/features/auth/actions';
import { isSup, meLine, useMe } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { draftActive, newComments, recs, useWs } from '@/shared/state/workspace';
import { failToast } from '@/shared/lib/fail';
import { AimStatus } from '@/shared/ui/conn';
import { Icon } from '@/shared/ui/Icon';
import { Brand, NavLink, SideToggle } from '@/shared/ui/sideParts';

export function AiBox() {
  const { choice } = useAiMode();
  const showRecovery = useAi(canClearHiddenDemoSettings);
  const [clearing, setClearing] = useState(false);
  async function clearSettings() {
    setClearing(true);
    try {
      if (await clearDemoSettings()) {
        resetConn();
        toast('가데이터와 실패 시연을 해제했어요');
        if (ai.live()) void ping();
      }
    } catch (err) {
      failToast(err, '시연 설정을 해제하지 못했어요');
    } finally {
      setClearing(false);
    }
  }
  // 모델 상태(사용 가능 여부)·추론 정도는 ai.* 로 읽으므로, 바뀌면 다시 그리도록 구독만 한다(연결 확인 결과는 useAiMode 의 conn)
  const policy = useAi((s) => s.status.policy);
  useAi((s) => s.settings.reasoning);
  const pick = (p: UiProvider) => {
    setChoice(p)
      .then(() => {
        resetConn();
        toast(
          ai.demoMock()
            ? `${PROV[p]}로 바꿨어요 · 현재는 가데이터 설정이 적용돼요`
            : ai.available(p)
              ? `${PROV[p]}로 에이전트를 호출해요`
              : `${PROV[p]}를 지금 쓸 수 없어요 · 가데이터로 자동 대체하지 않아요`,
        );
        if (ai.live()) void ping();
      })
      .catch((err) => failToast(err));
  };
  const pickLevel = (p: UiProvider, level: string | null) => {
    setReasoning(p, level)
      .then(() => toast(`${PROV[p]} 추론 정도: ${level ? levelLabel(level) : '기본값'} · 다음 호출부터 적용돼요`))
      .catch((err) => failToast(err));
  };
  /** 고른 모드 바로 아래의 추론 정도. 단계는 모델마다 달라 그 모델이 받는 것만 보여 준다.
   *  RunPod-Ollama 는 모든 생성을 추론 없이 부르므로 고르는 칸 없이 그 사실만 적는다 */
  const effort = (p: UiProvider) => {
    if (choice !== p || !ai.available(p)) return null;
    if (p === 'ollama') return <div className="aim-effort"><small className="aim-effort-n">추론 없음</small></div>;
    const levels = ai.reasoningLevels(p);
    if (!levels.length) return null;
    const def = ai.reasoningDefault(p);
    const mine = ai.reasoning(p);
    const id = `aim-effort-${p}`;
    return (
      <div className="aim-effort">
        <label htmlFor={id}>추론 정도</label>
        <select id={id} value={mine && levels.includes(mine) ? mine : ''} onChange={(e) => pickLevel(p, e.target.value || null)}>
          <option value="">기본값 · {def ? levelLabel(def) : '모델 기본'}</option>
          {levels.map((l) => (
            <option key={l} value={l}>
              {levelLabel(l)}
            </option>
          ))}
        </select>
      </div>
    );
  };
  const opt = (p: UiProvider, l: string, sub: string) => (
    <label className="aim-o">
      <input type="radio" name="gp-prov" value={p} checked={choice === p} onChange={() => pick(p)} />
      <span>
        <b>{l}</b>
        <small>{ai.available(p) ? sub : '지금 쓸 수 없어요'}</small>
      </span>
    </label>
  );
  return (
    <div className="aim" role={policy && policy !== 'employee' ? 'group' : 'radiogroup'} aria-label="AI 모델">
      <span className="lbl">AI 모델</span>
      {policy && policy !== 'employee' ? (
        <p>관리자 지정 · {PROV[policy]} · {policy === 'openai' ? ai.openaiModel() : ai.ollamaInfo().model} · 추론 {policy === 'openai' ? levelLabel(ai.reasoning('api') || '기본값') : '없음'}</p>
      ) : <>
        {opt('ollama', 'RunPod-Ollama', '로컬 LLM·sLLM')}
        {effort('ollama')}
        {opt('api', 'OpenAI API', ai.openaiModel())}
        {effort('api')}
      </>}
      {showRecovery && <button type="button" className="btn line sm" disabled={clearing} onClick={() => void clearSettings()}>
        {clearing ? '해제 중…' : '가데이터·실패 시연 해제'}
      </button>}
      <div className="aim-st" id="aimSt" aria-live="polite">
        <AimStatus />
      </div>
    </div>
  );
}

export function Sidebar({ active }: { active: string }) {
  const me = useMe();
  const go = useGo();
  const newComment = useWs((s) => recs(s, 'active').some((R) => newComments(R).length > 0));
  const drafting = useWs((s) => draftActive(s));
  const lastNew = useWs((s) => s.lastNew);
  if (!me) return null;
  const sup = isSup(me);
  // 내 정보는 위 계정 칸(이름)으로만 들어간다. 주 메뉴에도 두면 같은 화면 진입점이 겹쳐서 뺐다(#104)
  const items: [string, string, string, boolean?, string?][] = [
    [paths.home, '홈', 'home', newComment],
    [newIdToPath(lastNew), '새 로드맵 작성', 'pen', drafting, 'new'],
    [paths.roadmaps, '내 로드맵', 'map'],
    [paths.checks, '점검·보고서', 'chart'],
  ];
  const keyOf = (to: string, key?: string) => key || ({ [paths.home]: 'home', [paths.roadmaps]: 'roadmap', [paths.checks]: 'checks' } as Record<string, string>)[to];
  return (
    <>
      <Brand />
      <a
        className={`me ${active === 'me' ? 'on' : ''}`}
        href={paths.me}
        aria-label={`내 정보 보기 · ${me.name}`}
        title="내 정보 보기"
        onClick={(e) => {
          e.preventDefault();
          go(paths.me);
        }}
      >
        <span className="avatar">{me.name.slice(1)}</span>
        <div className="grow">
          <b>
            {me.name}
            {sup ? <span className="me-sup">부서장</span> : null}
          </b>
          <small>{meLine(me)}</small>
        </div>
        <Icon name="right" cls="me-go" />
      </a>
      <nav className="nav" aria-label="주 메뉴">
        {items.map(([to, l, ic, dot, key]) => (
          <NavLink key={l} to={to} active={active === keyOf(to, key)} icon={ic} label={l} dot={!!dot} />
        ))}
      </nav>
      {sup ? (
        <nav className="nav nav-appx nav-sup" aria-label="부서장">
          <span className="lbl">부서장</span>
          <NavLink to={paths.team} active={active === 'm-list'} icon="users" label="소속 직원 계획" />
        </nav>
      ) : null}
      <nav className="nav nav-appx" aria-label="부록">
        <span className="lbl">부록</span>
        <NavLink to={paths.resources} active={active === 'resources'} icon="book" label="학습 자료" />
      </nav>
      <div className="side-foot">
        <NotificationBell />
        <button className="btn ghost sm logout" aria-label="로그아웃" onClick={() => void logoutAndReset(go)}>
          <Icon name="logout" />
          <span className="lbl">로그아웃</span>
        </button>
        <SideToggle />
      </div>
    </>
  );
}
