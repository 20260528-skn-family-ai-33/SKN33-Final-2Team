/* 내 로드맵 공통 조각 (5차 actRow·commentAlert·repAlert·noPlan·planGuard·versions·pre-answers·post-start) */
import type { ReactNode } from 'react';
import { Navigate, useParams } from 'react-router';
import type { Activity, Comment, PlanRecord } from '@/api/types/plan';
import { newIdToPath, paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { hrs, won } from '@/shared/lib/format';
import { actMeta, st } from '@/shared/lib/plan';
import { ansLabel } from '@/shared/lib/prefs';
import { useCatalog } from '@/shared/state/catalog';
import { closeSheet, openSheet } from '@/shared/state/ui';
import { draftActive, newComments, planReports, recs, useWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { ActThumb, Hero, Note } from '@/shared/ui/parts';
import { openRecord } from './RecordSheet';

/** 활동 한 줄(홈·내 로드맵 진행 중). 줄 전체가 실행 기록 창을 여는 버튼이고, 상태는 보여 주기만 한다 */
export function ActRow({ a, R }: { a: Activity; R: PlanRecord }) {
  useCatalog((s) => s.res);
  const done = st(R.progress, a.id) === 'done';
  const memo = R.progress[a.id]?.memo;
  return (
    <li>
      <button className="act-row" aria-label={`${a.title}, ${done ? '완료' : '진행 중'}${memo ? ', 메모 있음' : ''}, 실행 기록 열기`} onClick={() => openRecord(R.id, a.id)}>
        <ActThumb a={a} />
        <span className="tx">
          {a.title}
          <small>
            {actMeta(a)} · {hrs(a.hours)}
            {memo ? ' · 메모 있음' : ''}
          </small>
        </span>
        {done ? (
          <span className="tag acc">
            <Icon name="check" />
            완료
          </span>
        ) : (
          <span className="tag">진행 중</span>
        )}
        <Icon name="right" cls="act-go" />
      </button>
    </li>
  );
}

export const cmBy = (c: Comment | undefined) => (c && c.by) || '부서장';

export function CommentAlert({ R }: { R: PlanRecord }) {
  const go = useGo();
  const nw = newComments(R);
  const n = nw.length;
  if (!n) return null;
  const edited = nw.every((c) => c.editedAt);
  return (
    <button className="alert" onClick={() => go(paths.comments(R.id))}>
      <Icon name="chat" />
      <span className="grow">
        <b>
          {cmBy(nw[nw.length - 1])} 님이 {edited ? '보낸 코멘트를 고쳤어요' : '이 로드맵에 코멘트를 남겼어요'}
          {n > 1 ? ` (${n}개)` : ''}
        </b>
        <br />
        <span className="small muted">평가가 아닌 계획 조정 의견이에요</span>
      </span>
      <Icon name="right" />
    </button>
  );
}

/** 결과 보고서가 나왔는데 아직 확인하지 않은 로드맵 */
export function RepAlert({ R }: { R: PlanRecord }) {
  const go = useGo();
  const r = useWs((s) => planReports(s, R).find((x) => !x.confirmed));
  if (!r) return null;
  return (
    <button className="alert" onClick={() => go(paths.report(r.id))}>
      <Icon name="chart" />
      <span className="grow">
        <b>결과 보고서가 나왔어요</b>
        <br />
        <span className="small muted">확인하면 이 로드맵을 마친 것으로 기록해요</span>
      </span>
      <Icon name="right" />
    </button>
  );
}

export function Alerts({ R }: { R: PlanRecord }) {
  const hasRep = useWs((s) => planReports(s, R).some((x) => !x.confirmed));
  if (!newComments(R).length && !hasRep) return null;
  return (
    <div className="stack hp-al">
      <CommentAlert R={R} />
      <RepAlert R={R} />
    </div>
  );
}

export function NoPlan() {
  const go = useGo();
  const active = useWs((s) => draftActive(s));
  const goal = useWs((s) => s.draft.goal);
  const lastNew = useWs((s) => s.lastNew);
  return active ? (
    <Hero
      title="작성 중인 로드맵이 있어요"
      lead={goal}
      foot={
        <button className="btn pri" onClick={() => go(newIdToPath(lastNew))}>
          이어서 작성하기
        </button>
      }
    />
  ) : (
    <Hero
      title="아직 확정한 로드맵이 없어요"
      lead="새 로드맵 작성에서 목표와 학습 여건을 적고 짧은 점검에 답하면 관점이 다른 3안을 받아볼 수 있어요."
      foot={
        <button className="btn pri" onClick={() => go(paths.newGoal)}>
          새 로드맵 작성
        </button>
      }
    />
  );
}

/** 로드맵 하나를 다루는 화면의 진입 조건(5차 P.planGuard): 그 로드맵이 있고(필요하면 진행 중) — 아니면 내 로드맵, 진행 중이 하나면 그것으로 */
export function PlanGate({ make, fallback, needActive, children }: { make: (pid: string) => string; fallback: string; needActive?: boolean; children: (R: PlanRecord) => ReactNode }) {
  const { pid } = useParams();
  const R = useWs((s) => (pid ? s.plans[pid] : undefined));
  const act = useWs((s) => recs(s, 'active').map((x) => x.id).join(','));
  if (R && (!needActive || R.status === 'active')) return <>{children(R)}</>;
  if (R) return <Navigate to={paths.roadmap(R.id)} replace />;
  const ids = act ? act.split(',') : [];
  return <Navigate to={ids.length === 1 ? make(ids[0]) : fallback} replace />;
}

export function openVersions(pid: string): void {
  const R = ws().plans[pid];
  if (!R) return;
  const vs = R.versions.slice().reverse();
  openSheet({
    title: '계획 버전 이력',
    sub: R.plan.goal,
    body: () => (
      <>
        <div className="list">
          {vs.map((v) => (
            <div className="li" key={v.version}>
              <span className={`idx ${v.version === R.plan.version ? 'on' : ''}`}>v{v.version}</span>
              <div className="tx">
                <b>{v.why}</b>
                <small>
                  {v.confirmedAt} · {v.weeks}주 · 주 {v.hours}시간 · {won(v.cost)}
                </small>
              </div>
            </div>
          ))}
        </div>
        <Note>계획을 고쳐 확정할 때마다 새 버전으로 쌓여요. 이전 버전은 지우지 않아요.</Note>
      </>
    ),
  });
}

export function openPreAnswers(pid: string): void {
  const R = ws().plans[pid];
  const pl = R && R.plan;
  const A = pl && pl.assess ? pl.assess : { questions: ws().draft.quiz?.questions || [], answers: ws().draft.answers };
  openSheet({
    title: '사전 점검 응답',
    sub: pl ? pl.goal : '',
    wide: true,
    body: () => (
      <>
        <div className="list">
          {A.questions.map((q) => (
            <div className="li" key={q.id}>
              <div className="tx">
                <small>{q.area}</small>
                <b style={{ fontWeight: 500 }}>{q.text}</b>
              </div>
              <span className="end">{ansLabel(A.answers[q.id])}</span>
            </div>
          ))}
        </div>
        <Note>처음 응답한 원본이에요. 진단 에이전트가 계산한 수준값은 사후 비교용으로 서버에만 저장하고 화면에 보여주지 않아요.</Note>
      </>
    ),
  });
}

/** 사후 점검 시작 (홈·내 로드맵·점검·보고서 모두 같은 규칙 · 10/14): 언제든 시작할 수 있고,
    '진행 중'인 활동이 남아 있으면 한 번 확인한다(이미 답하기 시작했으면 묻지 않음) */
export function postStart(go: ReturnType<typeof useGo>, pid: string): void {
  const R = ws().plans[pid];
  if (!R || R.status !== 'active') return;
  const left = R.plan.acts.filter((a) => st(R.progress, a.id) !== 'done').length;
  const begun = !!(R.post.goalSelf || Object.keys(R.post.answers || {}).length || R.post.fail);
  if (!left || begun) {
    closeSheet();
    go(paths.post(R.id));
    return;
  }
  openSheet({
    title: '사후 점검을 시작할까요?',
    sub: R.plan.goal,
    body: () => (
      <>
        <p style={{ marginTop: 0 }}>
          아직 ‘진행 중’인 활동이 <b>{left}개</b> 있어요.
        </p>
        <p className="small muted">지금 사후 점검을 하면 결과 보고서에 그 활동은 ‘진행 중’으로 남아요. 보고서를 확인하면 이 로드맵을 마친 것으로 기록해요.</p>
      </>
    ),
    foot: () => (
      <>
        <button className="btn line" onClick={closeSheet}>
          활동 더 하기
        </button>
        <button className="btn pri" onClick={() => go(paths.post(R.id))}>
          사후 점검 시작
        </button>
      </>
    ),
  });
}
