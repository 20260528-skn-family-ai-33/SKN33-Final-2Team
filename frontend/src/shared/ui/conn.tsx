/* AI 연결 상태 표시 (5차 gp-core.js aimStatus · gp-app.js connView·connErr·connBox·connOps·coldOps)
   진단 에이전트 연결 상태: 가데이터 / 확인 중 / 연결됨 / 모델 대기 중(Ollama · 모델이 아직 GPU에 없음) / 연결 안 됨 */
import { ai, connFor, ping, PROV, unavailableWhyText, userText, userTodo, useAiMode, type Conn } from '@/shared/state/ai';
import { useAi } from '@/shared/state/ai';
import { Icon } from './Icon';
import { OpsBox, via } from './parts';

export const ConnOps = ({ c, cls }: { c: Conn; cls?: string }) => (
  <OpsBox items={[['', { text: c.error, hint: c.hint, raw: c.raw && c.raw !== c.error ? c.raw : '' }]]} cls={cls} />
);

export const ColdOps = ({ c, cls }: { c: Conn; cls?: string }) => (
  <OpsBox
    items={[['', { text: `모델이 아직 GPU에 올라가 있지 않음 (${(c.waiting || []).join(', ')})`, hint: '첫 호출 때 GPU에 올려요. 미리 올려 두려면 Pod에서 그 모델을 한 번 호출해 두세요' }]]}
    cls={cls}
  />
);

/** 좌측 'AI 모델' 아래 상태 */
export function AimStatus() {
  const { demo, conn } = useAiMode();
  if (demo)
    return (
      <>
        <i className="d off" />
        <span>시연 도구에서 가데이터로 보는 중</span>
      </>
    );
  if (!ai.live()) {
    const why = unavailableWhyText();
    return (
      <>
        <i className="d error" />
        <div className="aim-tx">
          지금 쓸 수 없어요
          <small>서버 연결과 모델 설정을 확인해 주세요. 자동 대체하지 않아요. 연결한 뒤 다시 시도해 주세요.</small>
          <OpsBox items={[['', { text: why, hint: '백엔드 설정(.env)을 고친 뒤 백엔드를 다시 켜 주세요. 가데이터로 보려면 시연 도구에서 직접 켜 주세요' }]]} cls="sm" />
        </div>
      </>
    );
  }
  const c = connFor('all', conn);
  const st = c.state === 'idle' ? 'checking' : c.state;
  const t = ({ ok: '연결됨', cold: '연결됨 · 모델 준비 중', checking: '연결 확인 중…', error: '연결 안 됨' } as Record<string, string>)[st];
  return (
    <>
      <i className={`d ${st}`} />
      <div className="aim-tx">
        {t}
        {st === 'error' ? (
          <>
            <small>{userText(c.kind)}</small>
            <ConnOps c={c} cls="sm" />
          </>
        ) : st === 'cold' ? (
          <>
            <small>첫 응답은 1~2분 걸릴 수 있어요</small>
            <ColdOps c={c} cls="sm" />
          </>
        ) : null}
      </div>
    </>
  );
}

export function ConnView() {
  const { demo, conn } = useAiMode();
  if (!ai.live())
    return (
      <span className="conn off">
        <i />
        {demo ? '가데이터 모드 · LLM에 연결하지 않아요' : `${PROV[ai.choice()]}를 지금 쓸 수 없어요 · 가데이터로 자동 대체하지 않아요`}
      </span>
    );
  const c = connFor('default', conn);
  const st = c.state === 'idle' ? 'checking' : c.state;
  const lbl = ({ ok: '연결됨', cold: '모델 준비 중', error: '연결 안 됨', checking: '연결 확인 중…' } as Record<string, string>)[st];
  return (
    <>
      <span className={`conn ${st}`}>
        <i />
        {lbl} · {via('default')}
      </span>
      {st === 'ok' && c.ms ? (
        <span className="small muted num">
          {c.via === 'ping' ? '확인' : '최근 응답'} {(c.ms / 1000).toFixed(1)}초{(c.loadMs || 0) > 500 ? ` · 모델 불러오기 ${((c.loadMs || 0) / 1000).toFixed(1)}초 포함` : ''}
        </span>
      ) : null}
      {st !== 'checking' ? (
        <button className="link quiet" onClick={() => void ping()}>
          <Icon name="retry" />
          다시 확인
        </button>
      ) : null}
    </>
  );
}

export function ConnErr() {
  const { conn } = useAiMode();
  const server = useAi((s) => s.status.server);
  /* 고른 모드를 쓸 수 없음(설계서 v1.7 그림 12): 가데이터로 바꾸지 않는다는 것과 할 일을 알린다 */
  if (ai.off())
    return (
      <div className="conn-err" role="alert">
        <Icon name="alert" />
        <div>
          <b>{userText('off')}.</b> {userTodo('off').join(' ')}
          <OpsBox
            items={[['', { text: ai.unavailableWhy(ai.choice()), hint: server ? '백엔드 설정(.env)을 고친 뒤 백엔드를 다시 켜 주세요' : '백엔드(docker compose)를 켜 주세요' }]]}
            cls="sm"
          />
        </div>
      </div>
    );
  if (!ai.live()) return null;
  const c = connFor('default', conn);
  if (c.state === 'cold')
    return (
      <div className="conn-err cold">
        <Icon name="info" />
        <div>
          <b>AI 모델을 준비하고 있어요.</b> 첫 문항 생성은 1~2분 걸릴 수 있어요.
          <ColdOps c={c} />
        </div>
      </div>
    );
  if (c.state !== 'error') return null;
  return (
    <div className="conn-err" role="alert">
      <Icon name="alert" />
      <div>
        <b>{userText(c.kind)}.</b> {userTodo(c.kind).join(' ')} 이대로 넘어가면 사전 점검 문항을 만들지 못할 수 있어요.
        <ConnOps c={c} />
      </div>
    </div>
  );
}

export const ConnBox = () => (
  <div className="connbox">
    <div className="cb-h">
      <Icon name="spark" />
      진단 에이전트
      <span className="conn-w" id="dConn" aria-live="polite">
        <ConnView />
      </span>
    </div>
    <div id="dConnErr">
      <ConnErr />
    </div>
  </div>
);
