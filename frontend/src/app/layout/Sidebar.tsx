/* 좌측 메뉴 (5차 gp-core.js sidebar · aiBox) — 직원 화면 공통 */
import { newIdToPath, paths } from '@/app/paths';
import { DemoTools } from '@/features/demo/DemoTools';
import { useGo } from '@/shared/hooks/useGo';
import { ai, ping, PROV, resetConn, setChoice, useAi, useAiMode, type UiProvider } from '@/shared/state/ai';
import { logoutAndReset } from '@/features/auth/actions';
import { isSup, meLine, useMe } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { draftActive, newComments, recs, useWs } from '@/shared/state/workspace';
import { failToast } from '@/shared/lib/fail';
import { AimStatus } from '@/shared/ui/conn';
import { Icon } from '@/shared/ui/Icon';
import { Brand, NavLink, ThemePicker } from '@/shared/ui/sideParts';

function AiBox() {
  const { choice } = useAiMode();
  // 모델 상태(사용 가능 여부)는 ai.* 로 읽으므로, 바뀌면 다시 그리도록 구독만 한다
  useAi((s) => s.status);
  const pick = (p: UiProvider) => {
    setChoice(p)
      .then(() => {
        resetConn();
        toast(
          ai.demoMock()
            ? `${PROV[p]}로 바꿨어요 · 지금은 시연 도구에서 가데이터로 보는 중이에요`
            : ai.available(p)
              ? `${PROV[p]}로 에이전트를 호출해요`
              : `${PROV[p]}를 지금 쓸 수 없어요 · 가데이터로 자동 대체하지 않아요`,
        );
        if (ai.live()) void ping();
      })
      .catch((err) => failToast(err));
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
    <div className="aim" role="radiogroup" aria-label="AI 모델">
      <span className="lbl">AI 모델</span>
      {opt('ollama', 'RunPod-Ollama', '로컬 LLM·sLLM')}
      {opt('api', 'OpenAI API', ai.openaiModel())}
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
  const items: [string, string, string, boolean?, string?][] = [
    [paths.home, '홈', 'home', newComment],
    [newIdToPath(lastNew), '새 로드맵 작성', 'pen', drafting, 'new'],
    [paths.roadmaps, '내 로드맵', 'map'],
    [paths.checks, '점검·보고서', 'chart'],
    [paths.me, '내 정보', 'user'],
  ];
  const keyOf = (to: string, key?: string) => key || ({ [paths.home]: 'home', [paths.roadmaps]: 'roadmap', [paths.checks]: 'checks', [paths.me]: 'me' } as Record<string, string>)[to];
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
      <AiBox />
      <div className="side-foot">
        <ThemePicker />
        <DemoTools />
        <button className="btn ghost sm logout" aria-label="로그아웃" onClick={() => void logoutAndReset(go)}>
          <Icon name="logout" />
          <span className="lbl">로그아웃</span>
        </button>
      </div>
    </>
  );
}
