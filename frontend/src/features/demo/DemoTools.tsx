/* 시연 도구 (5차 gp-core.js modeBox·jump·reset·agent-log) — 로그인한 계정의 서버 기록만 바꾼다.
   '에이전트 동작 보기'는 시연·디버그 전용이라 누가 호출했든 모든 계정의 호출을 보여 준다(직원·관리자 화면 공통 · 2026-10-26).
   VITE_DEMO_TOOLS가 명시적 on이고 서버도 demoMode:true를 알릴 때만 표시한다. 서버 조회 실패·구버전 응답은 숨긴다. */
import { useState } from 'react';
import { legacyToPath, paths } from '@/app/paths';
import { aiApi, demoApi, type AgentLogEntry } from '@/api/endpoints/account';
import { reloadWorkspace } from '@/features/draft/draftSync';
import { addDays, md, ymd } from '@/features/home/ganttCalc';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { canUseDemo } from '@/shared/lib/demoAccess';
import { ai, ping, PROV, resetConn, setDemoMock, setFailSim, useAi, useAiMode } from '@/shared/state/ai';
import { isoDay, setDemoDay, useDemoDay } from '@/shared/state/demoClock';
import { dataReset } from '@/shared/state/events';
import { isSup, useMe } from '@/shared/state/session';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { updateWs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';

export const JUMPS: [string, string][] = [
  ['start', '처음부터'],
  ['details', '세부 사항부터'],
  ['quiz', '역량 테스트부터'],
  ['result', '점검 결과부터'],
  ['options', '로드맵 3안부터'],
  ['review', '확정 직전'],
  ['active', '로드맵 실행 중'],
  ['multi', '로드맵 2개 함께 진행'],
  ['comment', '코멘트 받은 뒤'],
  ['post', '사후 점검부터'],
  ['report', '결과 보고서'],
];

const FAILS: [string, string][] = [
  ['goal', '목표 후보 제안'],
  ['doc', '기획서 읽기(이미지·요약)'],
  ['quiz', '역량 테스트 문항 생성'],
  ['diag', '점검 결과(수준 진단)'],
  ['gen', '로드맵 3안 (Crash Course·Challenge Course)'],
  ['sup', '지원 조건 확인'],
  ['report', '결과 보고서'],
  ['reg', '사내 생활 도우미 답변'],
  ['rev', '수정안 작성'],
];

const LOG_TAG: Record<string, [string, string]> = {
  ollama: ['tag acc', 'RunPod-Ollama'],
  api: ['tag acc', 'OpenAI API'],
  mock: ['tag', '가데이터'],
  error: ['tag fail', '호출 오류 · 실패 안내'],
  sim: ['tag fail', '실패 시연'],
  off: ['tag fail', '모드 사용 불가 · 실패 안내'],
  stop: ['tag', '사용자가 멈춤'],
};

export async function showAgentLog(): Promise<void> {
  let L: AgentLogEntry[] = [];
  try {
    L = (await aiApi.log()).log || [];
  } catch {
    L = [];
  }
  openSheet({
    title: '에이전트 동작 기록',
    sub: '모든 계정의 최근 호출이 위에 보여요(시연·디버그용) · 서버 메모리에만 있어 서버를 다시 켜면 지워져요 (DB에는 처리 시간·결과 같은 기록만 남아요)',
    wide: true,
    body: () =>
      L.length ? (
        <div className="log">
          {L.map((e, i) => (
            <details className="logi" key={i}>
              <summary>
                <span className="muted small num">{e.at}</span>
                {e.employee ? <span className="small">{e.employee}</span> : null}
                <b>{e.agent}</b>
                <span className="grow small">
                  {e.task}
                  {e.model && e.mode !== 'mock' ? ` · ${e.model}` : ''}
                </span>
                {e.by ? <span className="tag">{e.by} 실행</span> : null}
                {LOG_TAG[e.mode] ? <span className={LOG_TAG[e.mode][0]}>{LOG_TAG[e.mode][1]}</span> : null}
                <span className="small muted num">{e.ms}ms</span>
              </summary>
              {e.error ? (
                <p className="small" style={{ color: 'var(--warn)', margin: '8px 0' }}>
                  {e.error}
                </p>
              ) : null}
              <p className="small muted" style={{ marginTop: 8 }}>
                입력
              </p>
              <pre>{e.input}</pre>
              <p className="small muted">출력</p>
              <pre>{e.output}</pre>
            </details>
          ))}
        </div>
      ) : (
        <p className="muted">아직 호출한 에이전트가 없어요.</p>
      ),
  });
}

/** 서버 설정 한 줄(.env 의 모델 연결 상태) — 직원·관리자 시연 도구 공통 */
function serverLine(status: { checked: boolean; server?: boolean }): string {
  if (!status.checked) return '확인 중…';
  if (!status.server) return '서버에 연결하지 못했어요';
  return `RunPod-Ollama ${ai.available('ollama') ? '설정됨' : '없음'} · OpenAI ${ai.available('api') ? '설정됨' : '없음'} (.env)`;
}

/** 관리자 화면의 시연 도구: 관리자에게 맞는 것만(모델 연결 상태 · 에이전트 동작 보기). 가데이터·실패 시연·단계 이동은 직원 계정 기능이라 뺀다 */
export function AdminDemoTools() {
  const status = useAi((s) => s.status);
  if (!canUseDemo(status.demoMode)) return null;
  return (
    <details className="demo">
      <summary>
        <Icon name="right" />
        시연 도구
      </summary>
      <div className="foot-lbl">모델 연결</div>
      <p className="small muted" style={{ margin: '2px 0 8px', fontSize: 11.5, lineHeight: 1.4 }}>
        {serverLine(status)}
      </p>
      <button className="btn line sm" onClick={() => void showAgentLog()}>
        <Icon name="cpu" />
        에이전트 동작 보기
      </button>
      <p className="small muted" style={{ margin: '2px 0 6px', fontSize: 11.5, lineHeight: 1.4 }}>
        모든 계정의 모델 호출을 보여요(관리자가 시작한 목표 후보 다시 만들기 포함) · 시연·디버그용이라 운영 빌드에는 없어요
      </p>
    </details>
  );
}

/** 로드맵 주차 계산의 오늘을 앞으로 옮겨 본다. 연도를 치는 중에 잠깐 생기는 과거 날짜는 적용하지 않고 입력칸에만 둔다 */
function DemoDay() {
  const demoDay = useDemoDay();
  const [rejected, setRejected] = useState<string | null>(null);
  const today = isoDay(new Date());
  const shown = demoDay ?? today;
  const step = (days: number) => setDemoDay(isoDay(addDays(ymd(shown)!, days)));
  return (
    <>
      <div className="foot-lbl" style={{ marginTop: 4 }}>
        기준 날짜
      </div>
      <input
        type="date"
        aria-label="로드맵 주차를 계산할 기준 날짜"
        min={today}
        max="9999-12-31"
        value={rejected ?? shown}
        onChange={(e) => {
          const picked = e.target.value;
          setRejected(picked >= today ? null : picked);
          if (picked >= today) setDemoDay(picked);
        }}
        onBlur={() => setRejected(null)}
      />
      <div className="demo-day-steps">
        <button className="btn line sm" onClick={() => step(1)}>
          +1일
        </button>
        <button className="btn line sm" onClick={() => step(7)}>
          +1주
        </button>
        <button className="btn line sm" disabled={!demoDay} onClick={() => setDemoDay(null)}>
          오늘로
        </button>
      </div>
      <p className="small muted" style={{ margin: '4px 0 8px', fontSize: 11.5, lineHeight: 1.4 }}>
        이 탭의 로드맵 주차 표시만 바뀌어요 · 서버 기록은 그대로예요 · 탭을 닫으면 실제 날짜로 돌아가요
      </p>
    </>
  );
}

export function DemoTools() {
  const me = useMe();
  const go = useGo();
  const { demo } = useAiMode();
  const status = useAi((s) => s.status);
  const failSim = useAi((s) => s.settings.failSim);
  const open = useWs((s) => s.demoOpen);
  const demoDay = useDemoDay();
  if (!canUseDemo(status.demoMode) || !me) return null;
  const fs = { ...ai.failSim(), ...failSim };
  const srv = serverLine(status);

  const jump = async (stage: string) => {
    if (stage === 'comment' && !me.mySupervisor) {
      toast('내 계획을 보는 부서장이 없는 계정이라 이 단계는 쓸 수 없어요');
      return;
    }
    toast('시연 데이터를 서버에 만드는 중이에요…');
    try {
      const r = await demoApi.jump(stage);
      await reloadWorkspace();
      updateWs((s) => void (s.demoOpen = true));
      dataReset();
      go(legacyToPath(r.entry), { force: true });
    } catch (err) {
      failToast(err, '단계로 이동하지 못했어요');
    }
  };

  const reset = () =>
    openSheet({
      title: '처음 상태로 초기화할까요?',
      body: () => (
        <>
          <p style={{ marginTop: 0 }}>
            <b>{me.name}</b> 님의 기록을 모두 지우고 처음 상태로 돌려요.
          </p>
          <ul className="plain-list small">
            <li>지우는 것: 확정한 로드맵(진행 중·지난 로드맵), 작성 중인 로드맵, 점검 응답·결과 보고서, 받은 코멘트 (서버 DB에서)</li>
            <li>그대로 두는 것: 내 정보(인사 정보·본인 입력)·목표 후보{isSup(me) ? ', 소속 직원의 로드맵과 기록' : ''}</li>
          </ul>
        </>
      ),
      foot: () => (
        <>
          <button className="btn line" onClick={closeSheet}>
            취소
          </button>
          <button
            className="btn pri"
            onClick={async () => {
              closeSheet();
              try {
                await demoApi.reset();
                await reloadWorkspace();
                dataReset();
                go(paths.home, { force: true });
                toast('내 기록을 처음 상태로 돌렸어요');
              } catch (err) {
                failToast(err, '초기화하지 못했어요');
              }
            }}
          >
            초기화
          </button>
        </>
      ),
    });

  return (
    <details className="demo" open={open} onToggle={(e) => updateWs((s) => void (s.demoOpen = (e.target as HTMLDetailsElement).open))}>
      <summary>
        <Icon name="right" />
        시연 도구{demoDay ? ` · ${md(ymd(demoDay)!)} 기준` : ''}
      </summary>
      <div className="foot-lbl">에이전트 데이터</div>
      <label className="radio">
        <input
          type="checkbox"
          name="gp-demomock"
          checked={demo}
          onChange={(e) => {
            const on = e.target.checked;
            setDemoMock(on)
              .then((saved) => {
                if (!saved) return;
                resetConn();
                toast(
                  on
                    ? '시연용 가데이터로 보여요'
                    : ai.off()
                      ? `${PROV[ai.choice()]}를 지금 쓸 수 없어요 · 가데이터로 자동 대체하지 않아요`
                      : `${PROV[ai.choice()]} 기준으로 돌아왔어요`,
                );
                if (ai.live()) void ping();
              })
              .catch((err) => failToast(err));
          }}
        />
        가데이터로 보기
      </label>
      <p className="small muted" style={{ margin: '2px 0 8px 24px', fontSize: 11.5, lineHeight: 1.4 }}>
        {srv}
        <br />
        사용자 모드는 좌측 ‘AI 모델’에서 골라요 · 서버가 가데이터 응답을 만들어요
      </p>
      <div className="foot-lbl" style={{ marginTop: 4 }}>
        생성 실패 시연
      </div>
      {FAILS.map(([k, l]) => (
        <label className="radio" key={k}>
          <input
            type="checkbox"
            name="gp-fail"
            value={k}
            checked={!!fs[k]}
            onChange={(e) => {
              const on = e.target.checked;
              setFailSim(k, on)
                .then((saved) => {
                  if (saved) toast(on ? '다음 생성의 첫 시도가 실패해요. 다시 시도하면 성공해요' : '실패 시연을 껐어요');
                })
                .catch((err) => failToast(err));
            }}
          />
          {l}
        </label>
      ))}
      <p className="small muted" style={{ margin: '2px 0 8px 24px', fontSize: 11.5, lineHeight: 1.4 }}>
        켜 두면 첫 시도만 실패해요
      </p>
      <DemoDay />
      <button className="btn line sm" onClick={() => void showAgentLog()}>
        <Icon name="cpu" />
        에이전트 동작 보기
      </button>
      <select
        aria-label="시연 단계로 이동 (내 기록만 바꿈)"
        value=""
        onChange={(e) => {
          if (e.target.value) void jump(e.target.value);
        }}
      >
        <option value="">단계로 바로 이동…</option>
        {JUMPS.map(([k, l]) =>
          k === 'comment' && !me.mySupervisor ? (
            <option key={k} value={k} disabled>
              {l} (부서장 없는 계정)
            </option>
          ) : (
            <option key={k} value={k}>
              {l}
            </option>
          ),
        )}
      </select>
      <p className="small muted" style={{ margin: '2px 0 6px', fontSize: 11.5, lineHeight: 1.4 }}>
        단계 이동·초기화는 로그인한 계정({me.name})의 서버 기록만 바꿔요
      </p>
      <button className="btn line sm" onClick={reset}>
        처음 상태로 초기화
      </button>
    </details>
  );
}
