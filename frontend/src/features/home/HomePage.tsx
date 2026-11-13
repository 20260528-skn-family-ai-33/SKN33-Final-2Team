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
import { count, trackedActs } from '@/shared/lib/plan';
import { weekToneClass } from '@/features/roadmap/roadmapLearningData';
import { useState } from 'react';
import { monthDay, planStart, startsLater, weekNow } from './ganttCalc';
import { useClockRefresh } from '@/shared/state/demoClock';
import { useMe } from '@/shared/state/session';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { draftActive, recs, updateWs, useWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { useCatalog } from '@/shared/state/catalog';
import './homeSkills.css';
import { GanttAll } from './Gantt';
import { LearningSpace } from './LearningSpace';
import { sharedCourses } from './sharedCourses';

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
  /* 지우면 되돌릴 수 없어 한 번 확인한다(#224) */
  const askDiscard = () =>
    openSheet({
      title: '작성 중인 로드맵을 지울까요?',
      body: () => <p style={{ margin: 0 }}>지금까지 적은 목표·세부 사항과 역량 테스트 응답, 만들어 둔 로드맵 안이 모두 사라지고 되돌릴 수 없어요.</p>,
      foot: () => (
        <>
          <button className="btn line" onClick={closeSheet}>
            취소
          </button>
          <button className="btn pri" onClick={() => { closeSheet(); void discard(); }}>
            지우기
          </button>
        </>
      ),
    });
  return (
    <div className="card">
      <div className="sec-h">
        <h2 className="st">작성 중인 새 로드맵</h2>
        <button className="link quiet" onClick={askDiscard}>
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
  return (
    <div className="actions">
      <button className={c.done === c.t ? 'btn pri sm' : 'btn line home-show-all'} onClick={() => postStart(go, R.id)}>
        {c.done === c.t ? '사후 점검 시작' : '사후 점검·조기 종료'}
      </button>
    </div>
  );
}

export function StageCard({ R }: { R: PlanRecord }) {
  const pl = R.plan;
  const [expanded, setExpanded] = useState(false);
  useClockRefresh();
  const week = weekNow(R);
  const later = startsLater(R);
  const startText = monthDay(planStart(R));
  const resources = useCatalog(s => s.res);
  const shared = sharedCourses(pl.acts, resources);
  const sharedIds = new Set(shared.map(course => course.id));
  const skillNames = pl.def.learningSkills?.map(skill => skill.name) || [];
  const skillOf = (activity: PlanRecord['plan']['acts'][number]) => {
    const resource = activity.res ? resources[activity.res] : undefined;
    return activity.skill || activity.skills?.[0] || resource?.skills?.find(name => skillNames.includes(name)) || resource?.skills?.[0] || '기타 활동';
  };
  const bySkill = new Map<string, typeof pl.acts>();
  for (const activity of pl.acts) {
    const skill = skillOf(activity);
    bySkill.set(skill, [...(bySkill.get(skill) || []), activity]);
  }
  const orderedSkills = [...skillNames.filter(name => bySkill.has(name)), ...[...bySkill.keys()].filter(name => !skillNames.includes(name))];
  const skillInWeek = (skill: string, list: typeof pl.acts) => {
    const sharedCourse = shared.find(course => course.skills.includes(skill));
    if (sharedCourse) {
      const sharedGroupActs = pl.acts.filter(a => sharedCourse.skills.includes(a.skill || ''));
      const sharedDeliverables = sharedGroupActs.filter(a => !a.res);
      const from = sharedCourse.from;
      const to = sharedDeliverables.length ? Math.max(...sharedDeliverables.map(a => a.wTo)) : Math.max(...sharedGroupActs.map(a => a.wTo));
      return from <= week && week <= to;
    }
    const schedule = pl.def.materialSchedule?.find(row => row.skill === skill);
    const from = schedule?.startWeek ?? Math.min(...list.map(a => a.wFrom));
    const to = schedule?.endWeek ?? Math.max(...list.map(a => a.wTo));
    return from <= week && week <= to;
  };
  const currentSkills = new Set(orderedSkills.filter(skill => skillInWeek(skill, bySkill.get(skill)!)));
  const visibleSkills = expanded ? orderedSkills : orderedSkills.filter(skill => currentSkills.has(skill));
  const visibleShared = expanded ? shared : shared.filter(course => (course.from <= week && week <= course.to) || course.skills.some(skill => currentSkills.has(skill)));
  const groups = new Map<string, Map<string, typeof pl.acts>>();
  for (const skill of visibleSkills) {
    const categories = new Map<string, typeof pl.acts>();
    for (const activity of bySkill.get(skill)!) {
      if (activity.res && sharedIds.has(activity.res)) continue;
      if (!expanded && (activity.wFrom > week || activity.wTo < week)) continue;
      const resource = activity.res ? resources[activity.res] : undefined;
      const kind = !activity.res ? '과제' : resource?.type === 'book' || resource?.kind === '도서' ? '도서' : resource?.type === 'course' || resource?.kind === '강좌' ? '강좌' : '기타 자료';
      categories.set(kind, [...(categories.get(kind) || []), activity]);
    }
    if (categories.size) groups.set(skill, categories);
  }
  const hasHiddenActs = pl.acts.some(a => {
    if (a.res && sharedIds.has(a.res)) return false;
    return a.wFrom > week || a.wTo < week;
  });
  const hasHiddenShared = shared.some(course => course.to < week || course.from > week);
  const hasMore = hasHiddenActs || hasHiddenShared || orderedSkills.length > currentSkills.size;
  /* 묶음 강조(#101): 모든 활동(도서 제외)을 마친 묶음은 완료색, 펼친 '전체 활동'에서는 이번 주 묶음을 이번 주 색으로 칠한다.
     접힌 '이번 주차 활동'은 모두 이번 주라 이번 주 색은 쓰지 않는다 */
  const tone = (activities: typeof pl.acts, inThisWeek: boolean) => {
    const current = expanded && !later && inThisWeek;
    const className = weekToneClass(trackedActs(activities), R.progress, current);
    return { className, tags: <>{current ? <span className="tag week">이번 주</span> : null}{className === ' is-week-done' ? <span className="tag done">완료</span> : null}</> };
  };
  return (
    <div className="card">
      <div className="sec-h">
        <h2 className="st">
          {expanded ? '전체 활동' : later ? '시작 전' : '이번 주차 활동'}{later ? '' : ` · ${week}주차`}
        </h2>
        <span className="small muted" style={{ marginLeft: 'auto' }}>
          {hasMore && <button type="button" className="btn line home-show-all" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? '접기' : '모두 보기'}</button>}
        </span>
      </div>
      {!groups.size && !visibleShared.length && <p className="small muted">{later ? `${startText}부터 시작해요.` : '이번 주차에 예정된 활동이 없어요.'}{hasMore ? ' ‘모두 보기’에서 전체 활동을 확인할 수 있어요.' : ''}</p>}
      <div className="home-skill-groups">
        {visibleShared.map(course => { const t = tone(course.activities, course.from <= week && week <= course.to); return <section className={`home-skill-group${t.className}`} key={`shared:${course.id}`}>
          <h3>{course.skills.join(' · ')}{t.tags}</h3>
          <div className="home-material-group" data-kind="강좌">
            <h4>강좌<span>1개 · 공통</span></h4>
            {/* 같은 강좌라 한 줄만 보여 준다. 기록을 저장하면 다른 스킬의 활동에도 같이 저장된다 */}
            <ul className="acts"><ActRow a={course.activities[0]} R={R} /></ul>
          </div>
        </section>; })}
        {[...groups].map(([skill, categories]) => { const t = tone(bySkill.get(skill)!, currentSkills.has(skill)); return <section className={`home-skill-group${t.className}`} key={skill}>
        <h3>{skill}{t.tags}</h3>
        {['도서', '강좌', '과제', '기타 자료'].filter(kind => categories.has(kind)).map(kind => <div className="home-material-group" data-kind={kind} key={kind}>
          <h4>{kind}<span>{categories.get(kind)!.length}개</span></h4>
          <ul className="acts">{categories.get(kind)!.map(a => <ActRow key={a.id} a={a} R={R} />)}</ul>
        </div>)}
      </section>; })}</div>
      <PostCta R={R} />
    </div>
  );
}

/** 첫 화면의 단계 안내. 단계 이름은 작성 화면의 단계 표시줄(STEPS)을 그대로 쓴다(#74 · #224) */
const STEP_HINT: Record<StepKey, string> = {
  goal: '기획서는 선택',
  details: '비워 두면 AI가 제안',
  check: '적은 내용 훑어보기',
  quiz: '설문과 짧은 퀴즈',
  result: '답과 해설 확인',
  options: '세 코스 중 하나',
  materials: '',
  review: '산출물 과제 정하기',
};

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
  const [savedGraphOrders, setSavedGraphOrders] = useState<Record<string, string[]>>({});
  const graphKey = me?.id ? `growpath:home-graph-order:${me.id}` : '';
  let savedOrder = savedGraphOrders[graphKey];
  if (!savedOrder && graphKey) {
    try {
      const stored: unknown = JSON.parse(localStorage.getItem(graphKey) ?? '[]');
      if (Array.isArray(stored)) savedOrder = stored.filter((id): id is string => typeof id === 'string');
    } catch { /* Use the default order when storage is unavailable. */ }
  }
  const byId = new Map(act.map(plan => [plan.id, plan]));
  const graphPlans = [...new Set([...(savedOrder ?? []), ...byId.keys()])]
    .flatMap(id => { const plan = byId.get(id); return plan ? [plan] : []; });
  function moveGraph(id: string, offset: number) {
    const ids = graphPlans.map(plan => plan.id);
    const index = ids.indexOf(id);
    const next = index + offset;
    if (index < 0 || next < 0 || next >= ids.length) return;
    [ids[index], ids[next]] = [ids[next], ids[index]];
    setSavedGraphOrders(previous => ({ ...previous, [graphKey]: ids }));
    if (graphKey) {
      try { localStorage.setItem(graphKey, JSON.stringify(ids)); } catch { /* Keep the current session order. */ }
    }
  }
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
          <LearningSpace />
        </>
      );
    return (
      <>
        <p className="eyebrow">안녕하세요, {hello} 님</p>
        <h1 className="t lg">어떤 역량을 키우고 싶나요?</h1>
        <p className="lead">목표와 학습 여건을 적고 역량 테스트에 답하면, 방식이 다른 로드맵 3안을 만들어 드려요.</p>
        <div className="actions">
          <button className="btn pri" onClick={() => go(paths.newGoal)}>
            새 로드맵 작성
          </button>
        </div>
        <PastLink />
        <div className="pstrip steps" style={{ marginTop: 40 }}>
          {STEPS.map(([key, label], i) => (
            <div key={key}>
              <b>
                {i + 1}. {label}
              </b>
              {STEP_HINT[key]}
            </div>
          ))}
        </div>
        <LearningSpace />
      </>
    );
  }
  return (
    <>
      <p className="eyebrow">안녕하세요, {hello} 님</p>
      <h1 className="t">진행 중인 로드맵 {act.length}개</h1>
      <p className="lead">전체 일정을 먼저 보여 드리고, 로드맵마다 이번 주차에 할 일을 보여 드려요.</p>
      <GanttAll list={graphPlans} onMove={moveGraph} />
      {graphPlans.map((R) => (
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
          <StageCard R={R} />
        </section>
      ))}
      {drafting ? (
        <div className="sec">
          <DraftBox />
        </div>
      ) : null}
      <PastLink />
      <LearningSpace />
    </>
  );
}
