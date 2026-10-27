/* 앞 단계를 고쳤을 때 (5차 gp-app.js beforeGo·stale-go·stale-revert·staleNote·뒤 단계 화면 감싸기)
   앞으로 넘어갈 때만 묻는다(뒤로 가기·홈으로 가기는 그대로 두고, 나중에 뒤 단계 화면에 들어오면 그 화면에서 묻는다) */
import { useEffect, type ReactNode } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useLocation } from 'react-router';
import { draftsApi } from '@/api/endpoints/drafts';
import { NEW_ORDER } from '@/app/paths';
import { addNavGuard, useGo } from '@/shared/hooks/useGo';
import { me } from '@/shared/state/session';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { useWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Page } from '@/shared/ui/parts';
import { draftCall } from './draftSync';
import { DOWN, lossList, staleOf, stepOfPath, type Stale } from './model';
import { Stepper } from './Stepper';

function StaleText({ st }: { st: Stale }) {
  const s = useWs();
  return (
    <>
      <p style={{ margin: '0 0 8px' }}>{st.what} 바꿔서 아래를 새로 만들어요.</p>
      <ul className="plain-list">
        {lossList(s, st).map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      <p className="small muted" style={{ marginTop: 10 }}>
        {st.back ? '원래대로 되돌리면 이미 만든 결과를 그대로 써요. ' : ''}
        {st.kind === 'gen' ? '사전 점검 문항과 응답은 그대로예요.' : ''}
      </p>
    </>
  );
}

type Go = ReturnType<typeof useGo>;

export async function staleGo(go: Go, target: string): Promise<void> {
  const st = staleOf(ws().draft);
  closeSheet();
  if (st) {
    const r = await draftCall('바꾼 내용을 반영하지 못했어요', (id) => draftsApi.changesApply(id, st.kind));
    if (!r) return;
  }
  if (target && window.location.pathname !== target) go(target, { force: true });
}

export async function staleRevert(go: Go, target: string): Promise<void> {
  const st = staleOf(ws().draft);
  closeSheet();
  if (st && st.back) {
    const r = await draftCall('원래대로 되돌리지 못했어요', (id) => draftsApi.changesRevert(id, st.kind));
    if (!r) return;
    toast('원래대로 되돌렸어요');
  }
  if (target && window.location.pathname !== target) go(target, { force: true });
}

function StaleButtons({ st, target, go }: { st: Stale; target: string; go: Go }) {
  return (
    <>
      {st.back ? (
        <button className="btn line" onClick={() => void staleRevert(go, target)}>
          <Icon name="history" />
          원래대로 되돌리기
        </button>
      ) : null}
      <button className="btn pri" onClick={() => void staleGo(go, target)}>
        바꾼 내용으로 계속
      </button>
    </>
  );
}

export function openStaleSheet(go: Go, st: Stale, target: string): void {
  openSheet({ title: '바꾼 내용으로 계속할까요?', body: () => <StaleText st={st} />, foot: () => <StaleButtons st={st} target={target} go={go} /> });
}

/** 작성 단계 안에서 앞으로 넘어갈 때 확인 창을 띄우는 이동 가드(앱 틀에 한 번 단다) */
export function DraftNavGuard() {
  const go = useGo();
  useEffect(
    () =>
      addNavGuard((to, from) => {
        if (!me()) return true;
        const st = staleOf(ws().draft);
        if (!st) return true;
        const fi = NEW_ORDER.indexOf(from);
        const ti = NEW_ORDER.indexOf(to);
        if (fi < 0 || ti < 0 || ti <= fi || fi < NEW_ORDER.indexOf(st.input)) return true;
        openStaleSheet(go, st, to);
        return false;
      }),
    [go],
  );
  return null;
}

const NOTE: Record<string, string> = {
  quiz: '목표·기획서를 바꿨어요. 다음으로 넘어갈 때 사전 점검 문항부터 다시 만들지 확인해요.',
  cert: '자격증 계획을 바꿨어요. 사전 점검 문항에 쓰이는 조건이라, 다음으로 넘어갈 때 사전 점검 문항부터 다시 만들지 확인해요.',
  diag: '응답을 바꿨어요. 다음으로 넘어갈 때 점검 결과부터 다시 만들지 확인해요.',
  gen: '세부 사항을 바꿨어요. 다음으로 넘어갈 때 로드맵 3안을 다시 만들지 확인해요.',
};

/** 입력 화면 안내: 바꾼 내용이 있으면 미리 알려 주고 바로 되돌릴 수 있게 한다 */
export function StaleNote({ kind }: { kind: 'quiz' | 'cert' | 'diag' | 'gen' }) {
  const go = useGo();
  const st = useWs(useShallow((s) => staleOf(s.draft)));
  const show = !!st && (st.note || st.kind) === kind;
  return (
    <p className="note stale-note" data-stale={kind} hidden={!show}>
      <Icon name="info" />
      <span>
        {NOTE[kind]}{' '}
        <button type="button" className="link" hidden={!(st && st.back)} onClick={() => void staleRevert(go, '')}>
          원래대로 되돌리기
        </button>
      </span>
    </p>
  );
}

/** 앞 단계를 바꾼 채로 뒤 단계 화면에 들어오면(홈에서 이어서 작성·뒤로·앞으로·새로 고침) 그 화면 대신 확인 카드를 보여 준다.
    고르기 전에는 아무것도 지우거나 다시 만들지 않는다 */
export function StaleStepGuard({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const go = useGo();
  const st = useWs(useShallow((s) => staleOf(s.draft)));
  const hit = st && DOWN[st.kind].includes(loc.pathname) ? st : null;
  if (!hit) return <>{children}</>;
  return (
    <>
      <Stepper cur={stepOfPath(loc.pathname) || 'goal'} />
      <Page eyebrow="앞 단계를 바꿨어요" title="바꾼 내용으로 계속할까요?" foot={<StaleButtons st={hit} target={loc.pathname} go={go} />}>
        <div className="card">
          <StaleText st={hit} />
        </div>
      </Page>
    </>
  );
}
