/* 시연 도구 (5차 gp-core.js modeBox·jump·reset·agent-log) — 로그인한 계정에 만든 시연 기록을 교체한다.
   '에이전트 동작 보기'는 시연·디버그 전용이라 누가 호출했든 모든 계정의 호출을 보여 준다(직원·관리자 화면 공통 · 2026-10-26).
   브라우저의 tools 설정(기본 VITE_DEMO_TOOLS)과 서버 시연 허용을 함께 확인한다. 서버 조회 실패·구버전 응답은 숨긴다. */
import { useState } from 'react';
import { legacyToPath, paths } from '@/app/paths';
import { demoApi } from '@/api/endpoints/account';
import { reloadWorkspace } from '@/features/draft/draftSync';
import { addDays, md, ymd } from '@/features/home/ganttCalc';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { canUseDemo } from '@/shared/lib/demoAccess';
import { D } from '@/shared/constants/data';
import { ai, ping, PROV, resetConn, setDemoMock, setFailSim, useAi, useAiMode } from '@/shared/state/ai';
import { isoDay, setDemoDay, useDemoDay } from '@/shared/state/demoClock';
import { dataReset } from '@/shared/state/events';
import { useMe } from '@/shared/state/session';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { updateWs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { showAgentLog } from './AgentLog';

export const JUMPS: [string, string][] = [
  ['start', '처음부터'],
  ['details', '세부 사항부터'],
  ['quiz', '역량 테스트부터'],
  ['result', '점검 결과부터'],
  ['options', '로드맵 3안부터'],
  ['review', '확정 직전'],
  ['active', '로드맵 실행 중'],
  ['multi', '로드맵 2개 함께 진행'],
  ['comment', '코멘트 예시 미리보기'],
  ['post', '사후 점검부터'],
  ['report', '결과 보고서'],
];

const FAILS: [string, string][] = [
  ['goal', '목표 후보 제안'],
  ['doc', '기획서 읽기(이미지·요약)'],
  ['quiz', '역량 테스트 문항 생성'],
  ['diag', '점검 결과(수준 진단)'],
  ['gen', '로드맵 3안 (Crash Course·Challenge Course)'],
  ['report', '결과 보고서'],
  ['reg', '사내 생활 도우미 답변'],
  ['rev', '수정안 작성'],
];

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
    if (stage === 'comment') {
      const sample = D.commentSample;
      openSheet({
        title: '코멘트 예시 미리보기',
        sub: '시연용 예시 · 화면에서만 표시해요',
        body: () => <><p>{sample.fitText}</p><p>{sample.levelText}</p><p>{sample.free}</p></>,
      });
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
      title: '시연 기록을 초기화할까요?',
      body: () => (
        <p>단계 이동으로 만든 {me.name} 님의 시연 초안·로드맵과 그 점검·보고서를 삭제해요. 부서장이 코멘트를 남긴 로드맵은 보존해요.</p>
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
                toast('시연 기록을 초기화했어요');
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
        aria-label="시연 단계로 이동"
        value=""
        onChange={(e) => {
          if (e.target.value) void jump(e.target.value);
        }}
      >
        <option value="">단계로 바로 이동…</option>
        {JUMPS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <p className="small muted" style={{ margin: '2px 0 6px', fontSize: 11.5, lineHeight: 1.4 }}>
        단계 이동·초기화는 {me.name} 님의 시연 기록에만 적용돼요.
      </p>
      <button className="btn line sm" onClick={reset}>
        시연 기록 초기화
      </button>
    </details>
  );
}
