import { plansApi } from '@/api/endpoints/plans';
import { waitJob } from '@/api/jobs';
import { failToast } from '@/shared/lib/fail';
import { MaterialSkillTabs } from '@/features/draft/result/MaterialSkillTabs';
import { commentSkillNames } from './roadmapLearningData';
import { ReviewResourceCard, ReviewTaskCopy, type ReviewMaterials } from '@/features/draft/review/ReviewSkillBlocks';
import { planDescription } from '@/shared/lib/planDescription';
import { Stats } from '@/shared/ui/parts';
import { activityTime } from '@/shared/lib/resourceTime';
import { trackName } from '@/shared/constants/data';
/* 수정 요청 (10/14 · 5차 scr.revise · P.revForm·revCtl·revRow·goalRow·diffView)
   여러 항목을 함께 골라도 된다. 고른 항목과 요청 내용을 관점 에이전트가 함께 보고 수정안을 먼저 보여 준다. 확정하기 전까지 지금 로드맵은 그대로 */
import { useEffect, useId, useRef, useState } from 'react';
import { newIdToPath, paths } from '@/app/paths';
import type { PendingRevision, PlanContent, PlanRecord, RevForm } from '@/api/types/plan';
import { enterNewRoadmap } from '@/features/draft/startModeSheet';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { clone } from '@/shared/lib/format';
import { actMeta, diff, isBookActivity, st, stageName } from '@/shared/lib/plan';
import { prefText } from '@/shared/lib/prefs';
import { ai, cause, errText, PROV } from '@/shared/state/ai';
import { setAt } from '@/shared/state/bind';
import { useCatalog } from '@/shared/state/catalog';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { draftActive, emptyPrefs, freshDraft, updateWs, useWs } from '@/shared/state/workspace';
import { BCheckArr, BInput, BNum, BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { ActThumb, AgentRow, FailPage, Note, OpsBox, Page, runSub } from '@/shared/ui/parts';
import { ResPicker } from '@/shared/ui/ResPicker';
import { Skeleton } from '@/shared/ui/Skeleton';
import { CommentView, commentReq, CmTag } from './comments';
import { cmBy, PlanGate } from './parts';
import { acceptRevision, confirmReviseComment, confirmReviseSkillsExclusion, confirmSkillRevisionSingle, dropRevision, freshRev, pullPlan, REV_ITEMS, revise, revItemOk, revKey, revOk, usePlanWatch } from './planActions';


/** 수정안 비교 (5차 P.diffView) */
export function DiffView({ pd }: { pd: PendingRevision }) {
  useCatalog((s) => s.certById);
  const ch = diff(pd.from, pd.to, pd);
  const same = pd.from.opt === pd.to.opt;
  return (
    <>
      {pd.summary ? (
        <p className="rv-sum">
          <Icon name="spark" />
          <span>{planDescription(pd.summary)}</span>
        </p>
      ) : null}
      {pd.to.durationBasis === 'materials-only' && <Stats pl={pd.to} bare />}
      <div className="diff">
        {ch.length ? (
          ch.map((c, i) => (
            <div className="d" key={i}>
              <span className="k">{c.k}</span>
              <span className="ab">
                <s>{c.a}</s>
                <Icon name="arrow" />
                <span className="to">{c.b}</span>
              </span>
            </div>
          ))
        ) : (
          <div className="d">
            <span className="k">변경</span>
            <span>바뀌는 내용이 없어요</span>
          </div>
        )}
      </div>
      {pd.notes && pd.notes.length ? (
        <div className="callout soft rv-notes">
          <Icon name="info" />
          <div>
            <b>요청 중 반영하지 못한 것</b>
            <ul className="plain-list">
              {pd.notes.map((t, i) => (
                <li key={i}>{planDescription(t)}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      <p className="note">
        <Icon name="info" />
        <span>
          목표는 그대로예요.{same ? ` 관점(${trackName(pd.from.opt, pd.from.name)})도 그대로예요.` : ''} 같은 활동의 진행 기록(완료·메모)은 이어져요.
          {pd.request ? ` 요청 내용: “${pd.request}”` : ''}
        </span>
      </p>
    </>
  );
}

const curText = (k: string, pl: PlanContent): string => {
  const p = pl.prefs || emptyPrefs();
  if (k === 'hours') return `주 ${pl.hours}시간${+p.hours > 0 ? '' : ' (에이전트가 정함)'}`;
  if (['weeks', 'budget', 'format', 'etc'].includes(k)) return prefText(k as 'weeks', p);
  if (k === 'start') return `${pl.start}단계 ${stageName(pl.start)}`;
  if (k === 'pid') return `${trackName(pl.opt, pl.name)}`;
  return `활동 ${pl.acts.length}개`;
};

const REV_MISS: Record<string, string> = {
  hours: '0.5~40 사이로 적거나 비워 주세요',
  weeks: '1~52 사이로 적거나 비워 주세요',
  budget: '0 이상으로 적거나 비워 주세요',
  pid: '지금과 다른 관점을 골라 주세요',
  remove: '뺄 활동을 하나 이상 골라 주세요',
  replace: '바꿀 활동을 하나 이상 골라 주세요',
  add: '넣을 자료를 고르거나 과제를 적어 주세요',
};

function RevCtl({ k, R }: { k: string; R: PlanRecord }) {
  const pl = R.plan;
  const r = R.rev as RevForm;
  const base = `plans.${R.id}.rev.v`;
  const lab = REV_ITEMS.find((x) => x[0] === k)?.[1] || '';
  const num = (unit: string, min: number, max: number | undefined, step: number, ph: string, help: string) => (
    <>
      <div className="unit">
        <BNum path={`${base}.${k}`} min={min} max={max} step={step} placeholder={ph} ariaLabel={lab} />
        <span>{unit}</span>
      </div>
      <small className="muted">{help}</small>
    </>
  );
  const actList = (path: string) => (
    <div className="choices">
      {pl.acts.map((a) => (
        <label className="choice" key={a.id}>
          <BCheckArr path={path} value={a.id} />
          <ActThumb a={a} />
          <span className="tx">
            {a.title}
            <small>
              {a.stage}단계 · {actMeta(a)} · {activityTime(a).text}
              {st(R.progress, a.id) === 'done' && !isBookActivity(a) ? ' · 완료' : ''}
            </small>
          </span>
          <span className="ck">
            <Icon name="check" />
          </span>
        </label>
      ))}
    </div>
  );
  if (k === 'hours') return num('시간 / 주', 0.5, 40, 0.5, '알아서', '0.5~40시간. 비우면 관점과 기간에 맞게 에이전트가 정해요');
  if (k === 'weeks') return num('주 안에', 1, 52, 1, '없음', '1~52주. 비우면 기간을 정하지 않아요');
  if (k === 'budget') return num('원', 0, undefined, 10000, '알아서', '0을 넣으면 무료 자료만 써요. 비우면 알아서 골라요');
  if (k === 'format')
    return (
      <select className={`input df-sel ${r.v.format ? '' : 'empty'}`} aria-label={lab} value={r.v.format} onChange={(e) => setAt(`${base}.format`, e.target.value)}>
        <option value="">알아서</option>
        {D.formatOpts.map(([x, l]) => (
          <option value={x} key={x}>
            {l}
          </option>
        ))}
      </select>
    );
  if (k === 'etc')
    return <BText path={`${base}.etc`} className="textarea sm" maxLength={500} ariaLabel={lab} placeholder="예: 다음 달 둘째 주는 출장이 많아요. 평일 저녁에만 공부할 수 있어요." />;
  if (k === 'start')
    return (
      <div className="chips">
        {D.stages.map((s) => (
          <label className="chip" key={s.n}>
            <input type="radio" name="rv-start" value={s.n} checked={+r.v.start === s.n} onChange={() => setAt(`${base}.start`, s.n)} />
            {s.n}단계 {s.name}
            {s.n === pl.start ? ' (지금)' : ''}
          </label>
        ))}
      </div>
    );
  if (k === 'pid')
    return (
      <>
        <div className="chips">
          {D.optionOrder.map((id) => (
            <label className="chip" key={id}>
              <input type="radio" name="rv-pid" value={id} checked={r.v.pid === id} onChange={() => setAt(`${base}.pid`, id)} />
              {D.perspectives[id].name}
              {id === pl.opt ? ' (지금)' : ''}
            </label>
          ))}
        </div>
        <small className="muted">고른 관점의 하위 에이전트가 진단 내용과 바뀐 조건으로 로드맵을 새로 써요</small>
      </>
    );
  if (k === 'remove') return actList(`${base}.remove`);
  if (k === 'replace')
    return (
      <>
        {actList(`${base}.replace`)}
        <BInput path={`${base}.replaceHow`} maxLength={200} placeholder="어떻게 바꿀까요? (선택) 예: 영상 강의로, 더 짧은 자료로" ariaLabel="바꿀 방향" />
      </>
    );
  if (k === 'add') {
    const have = pl.acts.map((a) => a.res).filter(Boolean) as string[];
    return (
      <>
        <ResPicker path={`${base}.addRes`} exclude={have} />
        <BText
          path={`${base}.addTask`}
          className="textarea sm"
          maxLength={400}
          ariaLabel="직접 할 과제"
          placeholder={'직접 할 과제를 한 줄에 하나씩 적어 주세요 (선택)\n예: 부서 FAQ 20건으로 답변 품질 점검하기'}
        />
      </>
    );
  }
  return null;
}

function RevRow({ k, R }: { k: string; R: PlanRecord }) {
  const r = R.rev as RevForm;
  const lab = REV_ITEMS.find((x) => x[0] === k)?.[1] || '';
  const on = !!r.on[k];
  const toggle = () => updateWs((s) => void ((s.plans[R.id].rev as RevForm).on[k] = !on));
  return (
    <div className={`ef rv${on ? ' on' : ''}`}>
      <label className="ef-l rv-l">
        <input type="checkbox" checked={on} onChange={toggle} />
        <span>
          {lab}
          <small>지금: {curText(k, R.plan)}</small>
        </span>
      </label>
      <div className="ef-c">
        {on ? (
          <>
            <RevCtl k={k} R={R} />
            {REV_MISS[k] ? (
              <span className="miss" hidden={revItemOk(r, k, R.plan.opt)}>
                <Icon name="info" />
                {REV_MISS[k]}
              </span>
            ) : null}
          </>
        ) : (
          <div>
            <button type="button" className="link quiet rv-pick" onClick={toggle}>
              <Icon name="edit" />
              바꾸기
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function GoalRow({ R }: { R: PlanRecord }) {
  const go = useGo();
  const drafting = useWs((s) => draftActive(s));
  const lastNew = useWs((s) => s.lastNew);
  const pl = R.plan;
  return (
    <div className="ef rv">
      <div className="ef-l rv-l nock">
        <span>
          목표<small>지금: {pl.goal}</small>
        </span>
      </div>
      <div className="ef-c">
        <p className="small muted" style={{ margin: 0 }}>
          목표가 바뀌면 역량 테스트부터 다시 해야 해서 새 로드맵으로 만들어요. 지금 로드맵은 새 로드맵을 확정할 때까지 그대로예요.
        </p>
        <div>
          {drafting ? (
            <button type="button" className="btn line sm" onClick={() => go(newIdToPath(lastNew))}>
              <Icon name="pen" />
              작성 중인 새 로드맵 이어서 하기
            </button>
          ) : (
            <button
              type="button"
              className="btn line sm"
              onClick={() =>
                enterNewRoadmap(go, paths.newGoal, () => {
                  updateWs((s) => {
                    s.draft = { ...freshDraft(), startMode: s.draft.startMode };
                    s.draft.prefs = { ...emptyPrefs(), ...clone(pl.prefs || emptyPrefs()) };
                    s.draftId = null;
                    s.draftPlan = null;
                    s.plans[R.id].rev = null;
                  });
                  toast('지금 로드맵의 학습 여건을 채워 뒀어요. 새 목표를 적어 주세요');
                })
              }
            >
              <Icon name="pen" />
              지금 조건으로 새 로드맵 작성
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function RevForm({ R, settingsOnly = false }: { R: PlanRecord; settingsOnly?: boolean }) {
  const r = R.rev as RevForm;
  const grp = (g: 'cond' | 'plan' | 'acts', title: string) => (
    <div className="card rv-g">
      <h2 className="st">{title}</h2>
      <div className="efs">
        {REV_ITEMS.filter((x) => x[2] === g).map(([k]) => (
          <RevRow key={k} k={k} R={R} />
        ))}
        {g === 'plan' ? <GoalRow R={R} /> : null}
      </div>
    </div>
  );
  return (
    <>
      {grp('cond', '학습 여건')}
      {!settingsOnly && <>
      {grp('plan', '로드맵 구성')}
      {grp('acts', '활동')}
      <div className="card rv-g">
        <h2 className="st">
          요청 내용 <span className="small muted">선택 · 항목 없이 문장만 적어도 돼요</span>
        </h2>
        {r.fromComment ? (
          <p className="small muted" style={{ margin: '0 0 8px' }}>
            부서장 코멘트로 채웠어요. 반영하지 않을 부분은 지우고, 덧붙일 내용을 적어 주세요.
          </p>
        ) : null}
        <BText path={`plans.${R.id}.rev.note`} maxLength={600} ariaLabel="요청 내용" placeholder="예: 평일 저녁에만 시간이 나요. 실습을 늘려 주세요." />
      </div>
      </>}
    </>
  );
}

function SkillRevisionChoices({ pd, selected, onPick, retrying, onRetry, progress }: {
  pd: PendingRevision; selected: string[]; onPick: (skill: string, recommended: boolean) => void;
  retrying: string | null; onRetry: (skill: string) => void; progress?: PlanRecord['progress'];
}) {
  const allNames = commentSkillNames(pd.from);
  // 이미 완료된 강좌나 산출물이 있는 스킬은 수정안 선택 탭 및 고르는 버튼 자체를 제외 (#226)
  const isSkillDone = (name: string) =>
    pd.from.acts.some(
      (a) =>
        a.skill === name &&
        !isBookActivity(a) &&
        st(progress, a.id) === 'done',
    );
  const names = allNames.filter((name) => !isSkillDone(name));
  const [active, setActive] = useState('');
  const id = useId();
  const resources = useCatalog(state => state.res);
  const skill = names.includes(active) ? active : names[0];
  if (!skill) return <p className="small muted">모든 스킬에 완료된 활동이 있어 수정할 스킬이 없어요.</p>;
  return <div className="stack">
    {names.length > 1 && <MaterialSkillTabs names={names} active={skill} onChange={setActive} id={id} panelId={id + '-panel'} />}
    <div id={id + '-panel'} role={names.length > 1 ? 'tabpanel' : undefined} aria-label={skill} className="stack">
      {names.length === 1 && <h3 className="st">{skill}</h3>}
      {([['현재 계획', pd.from, false], ['새 제안', pd.to, true]] as const).map(([label, plan, recommended]) => {
        const report = plan.def.learningReport as ReviewMaterials | undefined;
        const saved = report?.recommendations?.skills.find(item => item.name === skill);
        const activities = plan.acts.filter(activity => activity.skill === skill &&
          !isBookActivity(activity) && !saved?.books.some(book => book.id === activity.res));
        const loading = recommended && retrying === skill;
        const disabled = recommended && (loading || !activities.length);
        return <section key={label} className={`card rv-pick-card${recommended ? ' rv-recommendation-new' : ''}`}
          data-selected={selected.includes(skill) === recommended} data-disabled={disabled}
          onClick={event => {
            if (disabled || (event.target instanceof Element && event.target.closest('a, button, input, label, summary'))) return;
            onPick(skill, recommended);
          }}>
          <div className="sec-h"><label className="st">
            <input type="radio" name={id + '-choice'} checked={selected.includes(skill) === recommended}
              disabled={disabled} onChange={() => onPick(skill, recommended)} /> {label}
          </label>{recommended && <button type="button" className="btn line sm" disabled={!!retrying}
            onClick={() => onRetry(skill)}>{retrying === skill ? '재요청 중…' : '재요청하기'}</button>}</div>
          {loading ? <div role="status" aria-label="새로운 강좌와 산출물 추천 중"><Skeleton kind="cards" count={2} /></div> : <div className="stack">
            <section aria-label="강좌">
              <h4 className="st">강좌</h4>
              <div className="stack">{activities.filter(activity => activity.res).map(activity => {
                const resourceId = activity.res!;
                const item = { ...activity, skill, how: activity.how || '' };
                const resource = saved?.courses.find(course => course.id === resourceId) || resources[resourceId];
                return <ReviewResourceCard key={activity.id} kind="강좌" activity={item}
                  resource={{ ...resource, id: resourceId, title: resource?.title || activity.title,
                    timeNote: resource?.timeNote ?? undefined, timeStatus: resource?.timeStatus ?? undefined }} />;
              })}</div>
              {!activities.some(activity => activity.res) && <p className="small muted">표시할 강좌가 없어요.</p>}
            </section>
            <section aria-label="산출물">
              <h4 className="st">산출물</h4>
              {activities.filter(activity => !activity.res).map(activity =>
                <div className="review-task" key={activity.id}>
                  <ReviewTaskCopy task={{ ...activity, skill, how: activity.how || '' }} />
                </div>)}
              {!activities.some(activity => !activity.res) && <p className="small muted">표시할 산출물이 없어요.</p>}
            </section>
          </div>}
        </section>;
      })}
    </div>
  </div>;
}

function Revise({ R }: { R: PlanRecord }) {
  const go = useGo();
  const [retrying, setRetrying] = useState<string | null>(null);
  const pd = R.pending;
  const revisionId = R.revision?.id;
  const allSkills = pd ? commentSkillNames(pd.from) : [];
  const activeSkills = pd
    ? allSkills.filter(
        (name) =>
          !pd.from.acts.some(
            (a) =>
              a.skill === name &&
              !isBookActivity(a) &&
              st(R.progress, a.id) === 'done',
          ),
      )
    : [];
  const [picks, setPicks] = useState<{ revisionId?: string; skills: string[] }>(() => ({
    revisionId,
    skills: activeSkills,
  }));
  const initializedRef = useRef<string | undefined>(pd ? revisionId : undefined);
  useEffect(() => {
    if (pd && revisionId && initializedRef.current !== revisionId) {
      initializedRef.current = revisionId;
      setPicks({ revisionId, skills: activeSkills });
    }
  }, [pd, revisionId, activeSkills]);
  usePlanWatch(R.id);
  const base = R.plan;
  const noForm = !R.rev || !R.rev.v;
  useEffect(() => {
    if (noForm) {
      updateWs((s) => {
        const init = (s.plans[R.id].revision?.request as RevForm | undefined) || freshRev(s.plans[R.id]);
        s.plans[R.id].rev = init;
      });
    }
  }, [noForm, R.id]);
  if (!R.rev || !R.rev.v) return null;
  const r = R.rev;
  const busy = !!r.running;
  const pid = r.on.pid && r.v.pid !== base.opt ? r.v.pid : base.opt;
  const agent = `${D.perspectives[pid].name}`;
  const cm = r.fromComment ? (R.comments || []).find((c) => c.id === r.fromComment) : undefined;
  /* 요청 내용을 채운 뒤 부서장이 코멘트를 고쳤으면(10/23 코멘트 수정) 알리고, 고친 내용으로 다시 채울 수 있게 한다 */
  const skillComment = cm?.skill;
  const activitySkills = new Set(base.acts.filter(a => !isBookActivity(a) && a.skill).map(a => a.skill));
  const completedSkills = new Set(base.acts.filter(a => !isBookActivity(a) && a.skill && st(R.progress, a.id) === 'done').map(a => a.skill));
  const settingsOnly = activitySkills.size > 0 && activitySkills.size === completedSkills.size;
  const mixed = !r.fromComment && !!base.def.learningReport && !settingsOnly;
  const selectedSkills = picks.revisionId === revisionId ? picks.skills : activeSkills;
  const confirmRevision = () => {
    if (!pd) return;
    if (mixed) {
      const activities = (plan: PlanContent, skill: string) => plan.acts
        .filter(activity => activity.skill === skill && !isBookActivity(activity))
        .map(activity => [activity.res || null, activity.title, activity.how || '', activity.stage, activity.hours]);
      const changed = selectedSkills.some(skill =>
        JSON.stringify(activities(pd.from, skill)) !== JSON.stringify(activities(pd.to, skill)));
      if (!changed) {
        toast('변경 점이 없습니다.');
        return;
      }
    }
    openSheet({
      title: '로드맵 확정',
      body: () => <p>선택한 수정안을 이 로드맵에 적용할까요?</p>,
      foot: () => <>
        <button type="button" className="btn pri" onClick={() => {
          closeSheet();
          void acceptRevision(go, R.id, mixed ? selectedSkills : undefined);
        }}>확정하기</button>
        <button type="button" className="btn line" onClick={closeSheet}>취소</button>
      </>,
    });
  };
  const retrySkill = async (skill: string) => {
    if (!revisionId || retrying || busy) return;
    setRetrying(skill);
    try {
      const job = await plansApi.revise(R.id, { retrySkill: skill, revisionId,
        rev: { on: {}, v: r.v, note: r.note, fromComment: false }, key: revKey(r) });
      await waitJob(job.jobId);
      await pullPlan(R.id);
    } catch (error) {
      failToast(error, '이 스킬의 새 제안을 만들지 못했어요');
    } finally {
      setRetrying(null);
    }
  };
  const startNew = () => {
    const hasDraft = draftActive(useWs.getState());
    openSheet({
      title: '새 로드맵 만들기',
      body: () => <><p>완전 새로운 로드맵을 생성하게 됩니다.</p>
        {hasDraft && <p>작성 중인 초안 대신 새 작성을 시작해요.</p>}</>,
      foot: () => <>
        <button type="button" className="btn pri" onClick={() => {
          updateWs(state => {
            state.draft = freshDraft();
            state.draftId = null;
            state.draftPlan = null;
          });
          go(paths.newGoal);
        }}>확인</button>
        <button type="button" className="btn line" onClick={closeSheet}>취소</button>
      </>,
    });
  };
  const stale = !!(cm && r.cmStamp && cm.stamp !== r.cmStamp);
  const fail = r.fail && 'cause' in r.fail && r.fail.cause ? cause(r.fail.cause) : null;
  const ok = revOk(R, settingsOnly && !r.fromComment) && !cm?.deleted && cm?.status !== 'applied';
  let out: React.ReactNode = null;
  if (busy)
    out = (
      <div className="agents">
        <AgentRow st="run" name={skillComment || mixed ? '새로운 강좌와 산출물 추천 중' : `${agent} · 수정안 작성`} sub={skillComment || mixed ? undefined : runSub('roadmap', '고른 항목과 요청 내용을 반영하고 있어요')} />
        <Skeleton kind="cards" count={2} />
      </div>
    );
  else if (fail)
    out = (
      <FailPage
        title="수정안을 만들지 못했어요"
        desc={`${agent} 에이전트가 수정안을 쓰지 못했어요. 지금 로드맵은 그대로이고, 고른 항목과 요청 내용도 그대로 남아 있어요.`}
        cause={errText(fail)}
        body={
          <div className="agents">
            <AgentRow st="fail" name={`${agent} · 수정안 작성`} sub={ai.live() ? `${PROV[ai.mode()]} · ${ai.modelName('roadmap')}` : ''} tag="오류 발생" tagCls="fail" />
          </div>
        }
        ops={<OpsBox items={[['', fail]]} />}
        foot={
          <button className="btn pri" disabled={!ok} onClick={() => (skillComment || r.fromComment ? confirmReviseComment(R, skillComment || undefined, () => void revise(R.id)) : confirmReviseSkillsExclusion(R, () => void revise(R.id, settingsOnly)))}>
            <Icon name="retry" />
            {skillComment ? '재요청하기' : '다시 시도하기'}
          </button>
        }
      />
    );
  else if (pd)
    out = (
      <>
        <div className="sec-h">
          <h2 className="st">수정안</h2>
          {pd.source && pd.source !== 'mock' ? <span className="tag acc">{PROV[pd.source] || 'API'} 작성</span> : <span className="tag">가데이터</span>}
        </div>
        {revKey(r) !== pd.key ? <Note>수정안을 만든 뒤 고른 항목이나 요청 내용을 바꿨어요. 바뀐 내용으로 보려면 ‘수정안 다시 만들기’를 눌러 주세요.</Note> : null}
        {skillComment ? <div className="stack">
          {([['기존 강좌와 산출물', pd.from, pd.to], ['새로 추천한 강좌와 산출물', pd.to, pd.from]] as const).map(([title, plan, other], index) => {
            const unchanged = new Set(other.acts.map(activity => activity.id));
            const rows = plan.acts.filter(activity => activity.skill === skillComment && !unchanged.has(activity.id));
            return <section className={`card${index ? ' rv-recommendation-new' : ''}`} key={title}>
              <div className="sec-h"><h3 className="st">{title}</h3><span className={`tag ${index ? 'acc' : 'line'}`}>{index ? '새 제안' : '현재 계획'}</span></div>
              <div className="stack">
                {plan.acts.filter(activity => activity.skill === skillComment && activity.res && st(R.progress, activity.id) === 'done').map(activity => (
                  <p className="small muted" key={'done-' + activity.id}>
                    <span className="tag ok">강좌 완료</span> {activity.title} (기존 유지)
                  </p>
                ))}
                {rows.map(activity => {
                const item = { ...activity, skill: skillComment, how: activity.how || '' };
                if (!activity.res) return <div className="review-task" key={activity.id}><ReviewTaskCopy task={item} /></div>;
                const report = plan.def.learningReport as ReviewMaterials | undefined;
                const saved = report?.recommendations?.skills.find(skill => skill.name === skillComment);
                const course = saved?.courses.find(course => course.id === activity.res) || useCatalog.getState().res[activity.res];
                return <ReviewResourceCard key={activity.id} kind="강좌" activity={item}
                  resource={{ ...course, id: activity.res, title: course?.title || activity.title, timeNote: course?.timeNote ?? undefined, timeStatus: course?.timeStatus ?? undefined }} />;
              })}</div>
            </section>;
          })}
        </div> : mixed ? <SkillRevisionChoices pd={pd} selected={selectedSkills} retrying={retrying} progress={R.progress} onRetry={skill => confirmSkillRevisionSingle(R, skill, () => void retrySkill(skill))} onPick={(skill, recommended) =>
          setPicks({ revisionId, skills: recommended ? [...new Set([...selectedSkills, skill])] : selectedSkills.filter(name => name !== skill) })
        } /> : <DiffView pd={pd} />}
      </>
    );
  const cmt = cm ? (
    <>
      <div className="callout soft rv-cmt">
        <Icon name="chat" />
        <div>
          <b>
            부서장 코멘트 · {cmBy(cm)} · {cm.at}
            {cm.editedAt ? ` · 수정됨 ${cm.editedAt}` : ''}
          </b>
          <br />
          <span className="small muted">
            {stale
              ? '이 수정 요청을 시작한 뒤 부서장이 코멘트를 고쳤어요. 아래가 고친 코멘트이고, ‘요청 내용’은 고치기 전 내용이에요.'
              : '아래 ‘요청 내용’에 채워 뒀어요. 반영할 부분만 남기고 수정안을 만들어 주세요.'}{' '}
            확정하면 이 코멘트가 ‘v{(base.version || 0) + 1}에 반영’으로 바뀌어요.
          </span>
          {stale && !busy ? (
            <div className="actions cm-act">
              <button
                className="btn line sm"
                onClick={() => {
                  updateWs((s) => {
                    const x = s.plans[R.id].rev as RevForm;
                    x.note = commentReq(cm);
                    x.cmStamp = cm.stamp;
                  });
                  toast('고친 코멘트로 요청 내용을 다시 채웠어요');
                }}
              >
                고친 코멘트로 요청 내용 다시 채우기
              </button>
            </div>
          ) : null}
        </div>
      </div>
      <CommentView c={cm} />
    </>
  ) : null;
  return (
    <Page
      back={r.fromComment ? paths.comments(base.rid || R.id) : paths.roadmap(base.rid || R.id)}
      eyebrow={<>{base.name} · v{base.version}<br />{base.goal}</>}
      title={skillComment ? '새로운 추천 강좌와 산출물입니다.' : mixed ? '스킬별 로드맵 수정안' : '무엇을 바꿀까요?'}
      lead={skillComment ? `${skillComment}의 기존 강좌·산출물과 새 제안을 비교해 보세요.` : mixed ? '스킬마다 현재 계획과 새 제안 중 하나를 골라 주세요.' : `여러 항목을 함께 골라도 돼요. 고른 항목과 요청 내용을 ${agent} 에이전트가 함께 보고 수정안을 먼저 보여 드려요. 확정하기 전까지 지금 로드맵은 그대로예요.`}
      foot={<>
        {mixed && <button type="button" className="btn line" onClick={startNew}>새 로드맵 만들기</button>}
        <button type="button" className="btn pri" disabled={!pd || busy || !!retrying || !!fail || (!!skillComment && (!ok || stale || revKey(r) !== pd.key))}
          onClick={confirmRevision}>
          확정하기
        </button>
        <button type="button" className="btn line" onClick={() => void dropRevision(go, R.id)}>취소</button>
      </>}
    >
      {cmt}
      {!skillComment && !mixed && <RevForm R={R} settingsOnly={settingsOnly && !r.fromComment} />}
      {fail && !busy ? null : (
        <div className="actions rv-act">
          <button className={`btn ${pd ? 'line' : 'pri'}`} disabled={!ok || !!retrying} onClick={() => (skillComment || r.fromComment ? confirmReviseComment(R, skillComment || undefined, () => void revise(R.id)) : confirmReviseSkillsExclusion(R, () => void revise(R.id, settingsOnly)))}>
            {busy ? '수정안을 만드는 중…' : mixed ? '전체 재요청' : skillComment ? '재요청하기' : pd ? '수정안 다시 만들기' : '수정안 만들기'}
          </button>
        </div>
      )}
      <p className="small muted rv-hint" hidden={busy || ok}>
        바꿀 항목을 고르거나 요청 내용을 적어 주세요. 고른 항목의 값이 맞는지도 확인해 주세요.
      </p>
      {out ? (
        <div className="sec" id="diffSec">
          {out}
        </div>
      ) : null}
    </Page>
  );
}

export function RevisePage() {
  return (
    <PlanGate make={paths.revise} fallback={paths.roadmaps} needActive>
      {(R) => <Revise R={R} />}
    </PlanGate>
  );
}

export { CmTag };
