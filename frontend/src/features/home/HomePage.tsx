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
import { count } from '@/shared/lib/plan';
import { useState } from 'react';
import { monthDay, planStart, startsLater, weekNow } from './ganttCalc';
import { useClockRefresh } from '@/shared/state/demoClock';
import { useMe } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
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
  return (
    <div className="actions">
      <button className="btn line home-show-all" onClick={() => postStart(go, R.id)}>
        {c.done === c.t ? '사후 점검 시작' : '사후 점검·조기 종료'}
      </button>
    </div>
  );
}

function StageCard({ R }: { R: PlanRecord }) {
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
      {!groups.size && !visibleShared.length && <p className="small muted">{later ? `${startText}부터 시작해요.` : '이번 주차에 예정된 활동이 없어요.'} 모두 보기에서 전체 활동을 확인할 수 있어요.</p>}
      <div className="home-skill-groups">
        {visibleShared.map(course => <section className="home-skill-group" key={`shared:${course.id}`}>
          <h3>{course.skills.join(' and ')}</h3>
          <div className="home-material-group" data-kind="강좌">
            <h4>강좌<span>{course.activities.length}개</span></h4>
            <ul className="acts">{course.activities.map(activity => <ActRow key={activity.id} a={activity} R={R} />)}</ul>
          </div>
        </section>)}
        {[...groups].map(([skill, categories]) => <section className="home-skill-group" key={skill}>
        <h3>{skill}</h3>
        {['도서', '강좌', '과제', '기타 자료'].filter(kind => categories.has(kind)).map(kind => <div className="home-material-group" data-kind={kind} key={kind}>
          <h4>{kind}<span>{categories.get(kind)!.length}개</span></h4>
          <ul className="acts">{categories.get(kind)!.map(a => <ActRow key={a.id} a={a} R={R} />)}</ul>
        </div>)}
      </section>)}</div>
      <PostCta R={R} />
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
            ['역량 테스트', '1~5점 척도'],
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
        <LearningSpace />
      </>
    );
  }
  return (
    <>
      <p className="eyebrow">안녕하세요, {hello} 님</p>
      <h1 className="t">진행 중인 로드맵 {act.length}개</h1>
      <p className="lead">전체 일정을 먼저 보여 드리고, 로드맵마다 이번 주차 활동을 보여 드려요.</p>
      <GanttAll list={graphPlans} onMove={moveGraph} />
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
