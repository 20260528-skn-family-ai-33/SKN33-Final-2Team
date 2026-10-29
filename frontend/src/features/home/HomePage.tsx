/* 홈 (5차 scr.home · draftBox·stageCard·postCta·pastLink)
   진행 중인 로드맵이 하나면 그 로드맵 중심으로, 여럿이면 전체 일정을 먼저 보여 주고 로드맵마다 이번 단계 활동을 보여 준다(개수 제한 없음 · 10/14) */
import { draftsApi } from '@/api/endpoints/drafts';
import { ApiError } from '@/api/client';
import type { PlanRecord } from '@/api/types/plan';
import { newIdToPath, paths } from '@/app/paths';
import { takeDraft } from '@/features/draft/draftSync';
import { STEPS, SUB, type StepKey } from '@/features/draft/model';
import { Stepper } from '@/features/draft/Stepper';
import { ActRow, Alerts, postStart } from '@/features/roadmap/parts';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { count, curStage, range, stageActs, stageName } from '@/shared/lib/plan';
import { useMe } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { draftActive, recs, updateWs, useWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { GanttAll } from './Gantt';

function DraftBox() {
  const go = useGo();
  const goal = useWs((s) => s.draft.goal);
  const lastNew = useWs((s) => s.lastNew);
  const p = newIdToPath(lastNew);
  const k: StepKey = SUB[p] || (STEPS.find((s) => s[2] === p) || STEPS[0])[0];
  const discard = async () => {
    const id = ws().draftId;
    try {
      if (id) await draftsApi.remove(id);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404)) {
        failToast(err, '작성 중인 로드맵을 지우지 못했어요');
        return;
      }
    }
    takeDraft({ draftId: null, draft: null, draftPlan: null, lastNew: null });
    updateWs((s) => void (s.lastNew = null));
    toast('작성 중인 로드맵을 지웠어요');
  };
  return (
    <div className="card">
      <div className="sec-h">
        <h2 className="st">작성 중인 새 로드맵</h2>
        <button className="link quiet" onClick={() => void discard()}>
          지우기
        </button>
      </div>
      <p className="muted" style={{ margin: '-4px 0 14px' }}>
        {goal || '목표 입력 전'}
      </p>
      <Stepper cur={k} />
      <div className="actions" style={{ marginTop: 6 }}>
        <button className="btn line" onClick={() => go(p)}>
          이어서 작성하기
        </button>
      </div>
    </div>
  );
}

/** 모든 활동을 마치면 사후 점검 시작 버튼을 표시한다. */
function PostCta({ R }: { R: PlanRecord }) {
  const go = useGo();
  const c = count(R.plan, R.progress);
  return c.done === c.t ? (
    <div className="actions">
      <button className="btn pri" onClick={() => postStart(go, R.id)}>
        사후 점검 시작
      </button>
    </div>
  ) : null;
}

function StageCard({ R, multi }: { R: PlanRecord; multi?: boolean }) {
  const pl = R.plan;
  const cur = curStage(pl, R.progress);
  const acts = stageActs(pl, cur);
  return (
    <div className="card">
      <div className="sec-h">
        <h2 className="st">
          이번 단계 활동{multi ? ` · ${cur}단계 ${stageName(cur)}` : ''}
        </h2>
        <span className="small muted" style={{ marginLeft: 'auto' }}>
          {range(acts)}
        </span>
      </div>
      <ul className="acts" style={{ gap: 14 }}>
        {acts.map((a) => (
          <ActRow key={a.id} a={a} R={R} />
        ))}
      </ul>
    </div>
  );
}

function PastLink() {
  const go = useGo();
  const n = useWs((s) => recs(s).filter((R) => R.status !== 'active').length);
  if (!n) return null;
  return (
    <p className="small muted past-l">
      <button className="link" onClick={() => go(paths.roadmaps)}>
        지난 로드맵 보기 <Icon name="right" />
      </button>
    </p>
  );
}

export function HomePage() {
  const go = useGo();
  const me = useMe();
  const plans = useWs((s) => s.plans);
  const drafting = useWs((s) => draftActive(s));
  const act = recs({ plans }, 'active');
  const hello = (me?.name || '').slice(1);
  if (!act.length) {
    if (drafting)
      return (
        <>
          <p className="eyebrow">안녕하세요, {hello} 님</p>
          <h1 className="t lg">작성 중인 로드맵이 있어요</h1>
          <p className="lead">이어서 작성하면 마지막으로 작성하던 단계부터 이어가요.</p>
          <DraftBox />
          <PastLink />
        </>
      );
    return (
      <>
        <p className="eyebrow">안녕하세요, {hello} 님</p>
        <h1 className="t lg">어떤 역량을 키우고 싶나요?</h1>
        <p className="lead">목표와 학습 여건을 적고 짧은 점검에 답하면, 관점이 다른 로드맵 3안을 만들어 드려요.</p>
        <div className="actions">
          <button className="btn pri" onClick={() => go(paths.newGoal)}>
            새 로드맵 작성
          </button>
        </div>
        <PastLink />
        <div className="pstrip five" style={{ marginTop: 40 }}>
          {[
            ['목표 적기', '기획서는 선택'],
            ['세부 사항', '비워 두면 알아서'],
            ['사전 점검', '1~5점 척도'],
            ['3안 비교', '관점별 작성'],
            ['확정', '고친 뒤'],
          ].map(([a, b], i) => (
            <div key={a}>
              <b>
                {i + 1}. {a}
              </b>
              {b}
            </div>
          ))}
        </div>
      </>
    );
  }
  return (
    <>
      <p className="eyebrow">안녕하세요, {hello} 님</p>
      <h1 className="t">진행 중인 로드맵 {act.length}개</h1>
      <p className="lead">전체 일정을 먼저 보여 드리고, 로드맵마다 이번 단계 활동을 보여 드려요.</p>
      <GanttAll list={act} />
      {act.map((R) => (
        <section className="hp" key={R.id}>
          <div className="hp-h">
            <h2 className="hp-t">{R.plan.displayTitle || R.plan.goal}</h2>
            <button
              type="button"
              className="btn line sm hp-shortcut"
              aria-label={`${R.plan.displayTitle || R.plan.goal} 바로가기`}
              onClick={() => go(paths.roadmap(R.id))}
            >
              바로가기 <Icon name="right" />
            </button>
          </div>
          <Alerts R={R} />
          <StageCard R={R} multi />
          <PostCta R={R} />
        </section>
      ))}
      {drafting ? (
        <div className="sec">
          <DraftBox />
        </div>
      ) : null}
      <PastLink />
    </>
  );
}
