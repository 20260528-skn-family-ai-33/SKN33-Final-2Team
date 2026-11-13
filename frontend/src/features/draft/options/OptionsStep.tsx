import { currentMaterialTotals } from './materialTotals';
import { planDescription } from '@/shared/lib/planDescription';
import { activityTime } from '@/shared/lib/resourceTime';
import { invalidateDraft, invalidateMaterialChoices } from '../invalidation';
import { materialPreparation, canRevealMaterials, initialMaterialPreparation, type MaterialStatus } from './materialPreparation';
import './courseSkills.css';
import './materialPanel.css';
import '../stepLayout.css';
import './optionsStep.css';
import { MaterialSkillTabs } from '../result/MaterialSkillTabs';
import { materialVersionKey } from '../result/materialVersion';
import { usePrepareMaterials, ResourceSelection, type ResourceSelectionHandle, type MaterialTotals } from '../result/ResultStep';
import { completeMaterialSelection } from '../materials/materialTransition';
import { OptionSummary } from './OptionSummary';
import { comparisonEvidence } from './comparisonEvidence';
import { trackName, trackTrait } from '@/shared/constants/data';
/* 6. 로드맵·자료 선택 (#224): ① 코스 카드(A1·A2·A3 순서 고정)에서 하나를 고르고 ② 그 코스의 강좌·도서를 정한다.
   마음에 들지 않는 코스는 바라는 점을 적어 그 코스만 다시 만들고(API-32 · 버전으로 쌓임), ‹ › 로 버전을 넘겨 본다 */
import { useCallback, useEffect, useId, useReducer, useRef, useState } from 'react';
import { draftsApi } from '@/api/endpoints/drafts';
import type { DraftDoc, OptionDef, RegenRequest } from '@/api/types/draft';
import type { PlanContent } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { buildPlan, planWeeklyHours } from '@/shared/lib/plan';
import { cause } from '@/shared/state/ai';
import { setAt } from '@/shared/state/bind';
import { resOf, useCatalog } from '@/shared/state/catalog';
import { failToast } from '@/shared/lib/fail';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { ActThumb, Note, OpsBox, Page } from '@/shared/ui/parts';
import { Skeleton } from '@/shared/ui/Skeleton';
import { syncGenCur, DraftSaveError, draftCall, flush, takeDraft } from '../draftSync';
import { STEPS } from '../model';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';
import { Wait } from '@/shared/ui/Wait';

/** 고른 안의 계획 계산 매개변수(진단 에이전트가 넘긴 학습 선호 기준) */
export function paramsOf(d: DraftDoc, opt?: OptionDef) {
  const h = d.handoff;
  return { start: h?.startStage || 1, hours: planWeeklyHours(h?.prefs.weeklyHours, opt?.weeklyHours), format: h?.prefs.formatKey || 'mixed', patch: {} };
}

export const optionIds = (d: DraftDoc): string[] => (d.gen ? D.optionOrder.filter((k) => d.gen?.options[k]) : []);
export const optsOf = (d: DraftDoc): PlanContent[] => optionIds(d).map((id) => buildPlan(d.gen!.options[id], paramsOf(d, d.gen!.options[id]), d.goal));

const regenBusy = (d: DraftDoc, pid: string) => !!(d.gen && d.gen.regenRun && d.gen.regenRun[pid]);
const regenErr = (d: DraftDoc, pid: string) => (d.gen && d.gen.regenErr && d.gen.regenErr[pid] ? cause(d.gen.regenErr[pid]) : null);

export async function choose(go: ReturnType<typeof useGo>, id: string, save:()=>Promise<boolean>): Promise<void> {
  try {
    await flush();
    takeDraft(await draftsApi.select(ws().draftId as string, id, comparisonEvidence(ws().draft.gen)));
    if(!await completeMaterialSelection(save,go))toast('자료 선택을 저장하지 못했어요. 선택은 유지됩니다. 다시 시도해 주세요.');
  } catch (err) {
    if (!(err instanceof DraftSaveError)) failToast(err, '안을 고르지 못했어요');
  }
}

async function ver(pid: string, dir: number, save?:()=>Promise<boolean>): Promise<void> {
  const d = ws().draft;
  const g = d.gen;
  if (!g || regenBusy(d, pid) || !(g.hist || {})[pid]) return;
  const owner=ws().owner, draftId=ws().draftId, version=materialVersionKey(g.options[pid]);
  if(save && !await save()){toast('자료 선택을 저장하지 못해 버전을 바꾸지 않았어요.');return;}
  if(ws().owner!==owner||ws().draftId!==draftId||materialVersionKey(ws().draft.gen?.options[pid])!==version)return;
  const list = g.hist![pid];
  const i = Math.min(list.length - 1, Math.max(0, ((g.cur || {})[pid] || 0) + dir));
  updateWs((s) => {
    const gg = s.draft.gen;
    if (!gg) return;
    gg.cur = gg.cur || {};
    gg.cur[pid] = i;
    gg.options[pid] = list[i];
    if (s.draft.chosen === pid && s.draft.v2Assessment) s.draft.v2Assessment={...s.draft.v2Assessment,materialsReady:false,activitiesReady:false,materialsKey:undefined};
    if (s.draftPlan && s.draftPlan.opt === pid) s.draftPlan = null;
  });
  try {
    await flush();
  } catch {
    /* 저장 실패는 이미 알렸고, 다음 입력이나 안 고르기 때 다시 저장한다 */
  }
}

/* 다시 만들기 요청 창: 바라는 점(문장) + 빠른 칩 + 활동별 그대로/빼기/바꾸기. 아무것도 고르지 않으면 활동 구성이 다른 안을 새로 쓴다.
   자료를 따로 고르는 흐름(v2Assessment)에서는 6단계에 활동을 보여 주지 않으므로 활동 목록을 뺀다 */
const QUICK = ['더 짧게', '실습 늘리기', '비용 줄이기', '영상 위주', '문서 위주', '업무 과제 늘리기'];
function RegenBody({ pl, showActs }: { pl: PlanContent; showActs: boolean }) {
  const q = useWs((s) => s.regenReq);
  if (!q) return null;
  return (
    <div className="rg">
      <div className="field">
        <label>
          바라는 점 <span className="muted small">선택</span>
        </label>
        <BText path="regenReq.note" className="textarea sm" maxLength={300} ariaLabel="바라는 점" placeholder="예: 평일 저녁에 맞게 짧은 자료로 바꿔 주세요" />
        <div className="chips rg-chips">
          {QUICK.map((c) => {
            const on = q.chips.includes(c);
            return (
              <button
                type="button"
                key={c}
                className={`chip${on ? ' on' : ''}`}
                aria-pressed={on}
                onClick={() => setAt('regenReq.chips', on ? q.chips.filter((x) => x !== c) : [...q.chips, c])}
              >
                {c}
              </button>
            );
          })}
        </div>
      </div>
      {showActs ? <div className="field">
        <label>
          빼거나 바꿀 활동 <span className="muted small">선택</span>
        </label>
        <div className="rg-acts">
          {pl.acts.map((a) => (
            <div className="rg-act" key={a.id}>
              <ActThumb a={a} size="xs" />
              <span className="tx">
                {a.title}
                <small>
                  {a.stage}단계 · {a.task ? '직접 수행 과제' : resOf(a.res)?.kind || '자료'} · {activityTime(a).text}
                </small>
              </span>
              <div className="mini-seg" role="radiogroup" aria-label={a.title}>
                {[
                  ['', '그대로'],
                  ['remove', '빼기'],
                  ['replace', '바꾸기'],
                ].map(([v, l]) => (
                  <label key={v}>
                    <input type="radio" name={`rg-${a.id}`} value={v} checked={(q.acts[a.id] || '') === v} onChange={() => setAt(`regenReq.acts.${a.id}`, v)} />
                    {l}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div> : null}
      <p className="small muted" style={{ margin: 0 }}>
        아무것도 고르지 않으면 같은 방식으로 구성이 다른 안을 새로 써요. 다시 만든 안은 새 버전으로 쌓이고 ‹ › 로 이전 버전과 넘겨 볼 수 있어요.{showActs ? '' : ' 이 코스의 학습 자료 추천도 새로 준비해요.'}
      </p>
    </div>
  );
}

/** 요청 창을 연 화면이 넘긴 실행기: 고른 자료를 먼저 저장한 뒤에만 다시 만들기를 시작하게 한다 */
type RegenRunner = (run: () => Promise<void>) => Promise<void>;
let regenRunner: RegenRunner | null = null;

async function regenGo(): Promise<void> {
  const q = ws().regenReq;
  const g = ws().draft.gen;
  if (!q || !g) return;
  const runner = regenRunner;
  regenRunner = null;
  closeSheet();
  const o = g.options[q.pid];
  /** 고른 활동(빼기·바꾸기)을 서버가 아는 {key, title} 로. 지금 안에 없는 활동은 뺀다 */
  const refs = (how: string): RegenRequest['removeActs'] =>
    Object.keys(q.acts || {})
      .filter((id) => q.acts[id] === how)
      .flatMap((id) => {
        const a = o.acts.find((x) => x.id === id);
        return a ? [{ key: a.id, title: a.title }] : [];
      });
  const req: RegenRequest = { wish: String(q.note || '').trim(), quick: q.chips.slice(), removeActs: refs('remove'), replaceActs: refs('replace') };
  const has = req.wish || req.quick.length || req.removeActs.length || req.replaceActs.length;
  updateWs((s) => void (s.regenReq = null));
  const run = async () => {
    updateWs((s) => {
      const gg = s.draft.gen;
      if (gg) gg.regenRun = { ...(gg.regenRun || {}), [q.pid]: { req } };
    });
    await draftCall(`${D.perspectives[q.pid].name}을 다시 만들지 못했어요`, (id) => draftsApi.regenerate(id, q.pid, has ? req : null), { soft: true });
  };
  if (runner) await runner(run);
  else await run();
}

export function openRegenSheet(pid: string, runner?: RegenRunner): void {
  const d = ws().draft;
  const g = d.gen;
  if (!g || !g.options[pid] || regenBusy(d, pid)) return;
  syncGenCur();
  const o = ws().draft.gen!.options[pid];
  const pl = buildPlan(o, paramsOf(d, o), d.goal);
  const showActs = !d.v2Assessment;
  regenRunner = runner || null;
  updateWs((s) => void (s.regenReq = { pid, note: '', chips: [], acts: {} }));
  openSheet({
    title: `${D.perspectives[pid].name} 다시 만들기`,
    wide: true,
    body: () => <RegenBody pl={pl} showActs={showActs} />,
    foot: () => (
      <>
        <button className="btn line" onClick={closeSheet}>
          취소
        </button>
        <button className="btn pri" onClick={() => void regenGo()}>
          다시 만들기
        </button>
      </>
    ),
  });
}

/** 다시 만들기가 끝나면 알린다(서버 작성 문서의 버전 수가 늘었을 때) */
function useRegenToast(): void {
  const counts = useWs((s) => JSON.stringify(Object.fromEntries(Object.entries(s.draft.gen?.hist || {}).map(([k, v]) => [k, v.length]))));
  const seen = useRef<Record<string, number> | null>(null);
  useEffect(() => {
    const n = JSON.parse(counts) as Record<string, number>;
    if (seen.current)
      Object.entries(n).forEach(([pid, c]) => {
        if (seen.current![pid] && c > seen.current![pid]) toast(`${D.perspectives[pid].name}을 다시 만들었어요 · 버전 ${c}`);
      });
    seen.current = n;
  }, [counts]);
}

export function OptionsStep() {
  usePrepareMaterials();
  const [selecting,setSelecting]=useState(false);
  /* 기본은 고른 코스의 자료만 보여 주고, 원할 때만 세 코스를 나란히 본다(#224) */
  const [compare,setCompare]=useState(false);
  const [preparation,reportPreparation]=useReducer(materialPreparation,initialMaterialPreparation);
  const materialPrepared=Object.fromEntries(Object.entries(preparation.courses).map(([course,value])=>[`${course}:${value.version}`,value.status]));
  const generationStatus=useWs(s=>JSON.stringify({unavailable:s.draft.gen?.missing||[],generating:[...Object.entries(s.draft.genRun?.rows||{}).filter(([,row])=>row?.st==='run').map(([course])=>course),...Object.keys(s.draft.gen?.regenRun||{})]}));
  const receivePrepared=useCallback((course:string,status:MaterialStatus,version:string)=>{
    const state=ws();
    const progress=JSON.parse(generationStatus) as {unavailable:string[];generating:string[]};
    reportPreparation({type:'report',scope:JSON.stringify([state.owner,state.draftId,state.draft.v2Assessment?.generationId]),course,version,status,
      versions:Object.fromEntries(Object.entries(state.draft.gen?.options||{}).map(([key,option])=>[key,materialVersionKey(option)])),
      unavailable:progress.unavailable,regenerating:progress.generating});
  },[generationStatus]);
  const materialScope = useWs(s => JSON.stringify([s.owner, s.draftId, s.draft.v2Assessment?.generationId]));
  const [materialTab, setMaterialTab] = useState<{ scope: string; skill: string } | null>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem('growpath:material-tab') ?? 'null');
      return saved?.scope === materialScope && typeof saved.skill === 'string' ? saved : null;
    } catch {
      return null;
    }
  });
  const materialSkill = materialTab?.scope === materialScope ? materialTab.skill : '';
  function setMaterialSkill(skill: string) {
    const next = { scope: materialScope, skill };
    setMaterialTab(next);
    try { sessionStorage.setItem('growpath:material-tab', JSON.stringify(next)); } catch { /* Current selection is still in memory. */ }
  }
  const [materialSections,setMaterialSections]=useState({books:true,courses:true});
  const toggleMaterialSection=useCallback((kind:'books'|'courses',open:boolean)=>setMaterialSections(old=>old[kind]===open?old:{...old,[kind]:open}),[]);
  const materialTabsId=useId();
  const materialPanel=useRef<HTMLElement|null>(null);
  const showMaterials=()=>requestAnimationFrame(()=>materialPanel.current?.scrollIntoView({behavior:'smooth',block:'start'}));
  const editors=useRef<Record<string,ResourceSelectionHandle|null>>({});
  const [totals,setTotals]=useState<Record<string,MaterialTotals>>({});
  const receiveTotals=useCallback((course:string,value:MaterialTotals)=>setTotals(old=>old[course]?.weeks===value.weeks&&old[course]?.amount===value.amount&&old[course]?.unknown===value.unknown&&old[course]?.version===value.version&&old[course]?.weeklyHours===value.weeklyHours?old:{...old,[course]:value}),[]);
  async function changeVersion(course:string,direction:number){
    if(selecting)return;
    setSelecting(true);
    try{await ver(course,direction,()=>editors.current[course]?.saveForVersion()||Promise.resolve(true));}
    finally{setSelecting(false);}
  }
  /** 고른 자료를 먼저 저장하고, 그사이 초안·버전이 바뀌지 않았을 때만 다시 만들기를 시작한다 */
  async function saveThenRegenerate(course:string,run:()=>Promise<void>){
    if(selecting)return;
    setSelecting(true);
    const owner=ws().owner,id=ws().draftId,version=materialVersionKey(ws().draft.gen?.options[course]);
    try{
      if(editors.current[course]&&!await editors.current[course]!.saveForVersion()){toast('자료 선택을 저장하지 못해 다시 만들기를 시작하지 않았어요.');return;}
      if(ws().owner===owner&&ws().draftId===id&&materialVersionKey(ws().draft.gen?.options[course])===version)await run();
    }finally{setSelecting(false);}
  }
  function askRegenerate(course:string){
    if(selecting)return;
    openRegenSheet(course,run=>saveThenRegenerate(course,run));
  }
  function selectCourse(course:string){
    if(selecting)return;
    updateWs(state=>{if(state.draft.chosen!==course){state.draft.chosen=course;invalidateDraft(state,'materials');}});
  }
  const go = useGo();
  const d = useWs((s) => s.draft);
  const comparisonScope = materialScope;
  const availableVersions=Object.fromEntries(Object.entries(d.gen?.options||{}).map(([course,option])=>[course,materialVersionKey(option)]));
  const status=JSON.parse(generationStatus) as {unavailable:string[];generating:string[]};
  const readyToReveal=canRevealMaterials(preparation.courses,availableVersions,status.unavailable,status.generating);
  const comparisonVisible=preparation.scope===comparisonScope&&(readyToReveal||preparation.revealed);
  const stateOf = (p: PlanContent) => materialPrepared[`${p.opt}:${materialVersionKey(p.def)}`];
  const currentTotals = (p: PlanContent) => currentMaterialTotals(totals[p.opt], materialVersionKey(p.def), p.hours, !regenBusy(d,p.opt) && stateOf(p) === 'ready');
  const amountText = (t: MaterialTotals) => t.amount === 0 ? (t.unknown ? '가격 미확인' : '무료') : `${t.amount.toLocaleString()}원${t.unknown ? ' + 가격 미확인' : ''}`;
  /** 자료가 준비되기 전이나 주차를 계산하는 동안에는 계산값 대신 지금 상태를 적는다(사용자가 할 일이 있는 것처럼 보이지 않게).
      값과 같은 굵기·크기로 적어 옆 칸의 값과 높이를 맞춘다(#227).
      계산에 실패하면 자료 영역이 이유와 다시 시도를 보여 준다 */
  const waitText = (p: PlanContent) => <b><Wait>{regenBusy(d, p.opt) ? '다시 만드는 중' : stateOf(p) === 'failed' ? '준비 실패' : '계산 중…'}</Wait></b>;
  const materialSummary = (p: PlanContent) => {
    const current = currentTotals(p);
    return current ? `자료 학습 ${current.weeks === null ? '주차 산정 필요' : `예상 ${current.weeks}주`} · 강좌 ${amountText(current)}` : '자료 준비 중…';
  };
  useCatalog((s) => s.res);
  useDraftWatch();
  useRegenToast();
  useEffect(() => {
    syncGenCur();
  }, []);
  const g = d.gen;
  if (!g || !d.handoff) return null;
  const ps = optsOf(d);
  const cur = d.chosen;
  const chosen = ps.find(p => p.opt === cur) || null;
  const chosenTotals = chosen ? currentTotals(chosen) : undefined;
  const materialNames=Array.from(new Set((d.selectedSkills || ps.flatMap(plan=>plan.def.learningSkills || [])).map(skill=>skill.name)));
  const activeMaterialSkill=materialNames.includes(materialSkill)?materialSkill:materialNames[0];
  const off = ps.some((p) => p.def.offDomain);
  const reviewLabel = STEPS.find(step => step[0] === 'review')?.[1] || '검토';
  /* 다음으로 갈 수 없는 이유는 버튼 옆에 미리 적는다 */
  const block = !chosen ? '코스를 고르면 다음 단계로 갈 수 있어요'
    : regenBusy(d, chosen.opt) ? '이 코스를 다시 만들고 있어요. 끝나면 진행할 수 있어요'
    : stateOf(chosen) === 'failed' ? '이 코스의 자료를 준비하지 못했어요. 아래에서 다시 시도해 주세요'
    : stateOf(chosen) !== 'ready' ? '이 코스의 자료를 준비하고 있어요'
    : null;
  function next() {
    if (!cur) { toast('코스를 먼저 선택해 주세요.'); return; }
    if (regenBusy(ws().draft, cur)) {
      toast('그 코스를 다시 만드는 중이에요. 잠시 뒤에 진행해 주세요');
      return;
    }
    const option=ws().draft.gen?.options[cur];
    const state=materialPrepared[`${cur}:${materialVersionKey(option)}`];
    if(state!=='ready'){showMaterials();toast(state==='failed'?'선택한 코스의 자료 추천에 실패했어요. 다시 시도한 뒤 진행해 주세요.':'선택한 코스의 자료를 준비하고 있어요. 완료 후 다시 눌러 주세요.');return;}
    if(!editors.current[cur]){showMaterials();toast('선택한 코스의 자료를 불러오는 중이에요. 잠시 뒤 다시 눌러 주세요.');return;}
    setSelecting(true);
    void choose(go,cur,()=>editors.current[cur]?.save()||Promise.resolve(false)).finally(()=>setSelecting(false));
  }
  const versions = (p: PlanContent) => {
    const list = (g.hist || {})[p.opt];
    const i = (g.cur || {})[p.opt] || 0;
    const o = p.def;
    const busy = selecting || regenBusy(d, p.opt);
    return (
      <>
        {list && list.length > 1 ? (
          <span className="opt-vnav">
            <button type="button" disabled={i === 0 || busy} aria-label="이전 버전" onClick={() => void changeVersion(p.opt, -1)}>
              <Icon name="left" />
            </button>
            <b className="num">
              버전 {i + 1}/{list.length}
            </b>
            <button type="button" disabled={i === list.length - 1 || busy} aria-label="다음 버전" onClick={() => void changeVersion(p.opt, 1)}>
              <Icon name="right" />
            </button>
          </span>
        ) : null}
        {i > 0 ? (
          <div className="opt-rev">
            {o.revSummary ? <p>바꾼 점: {planDescription(o.revSummary)}</p> : null}
            {o.revRequest ? <p className="muted">요청: {o.revRequest}</p> : null}
            {(o.revNotes || []).length ? <p className="muted">반영하지 못한 것: {(o.revNotes || []).map(planDescription).join(' ')}</p> : null}
          </div>
        ) : null}
      </>
    );
  };
  const courseCard = (p: PlanContent) => {
    const on = cur === p.opt;
    const remaking = regenBusy(d, p.opt);
    const busy = selecting || remaking;
    const err = regenErr(d, p.opt);
    const t = currentTotals(p);
    const name = trackName(p.opt, p.name);
    return (
      <article key={p.opt} className={`opt-course${on ? ' is-on' : ''}${remaking ? ' is-busy' : ''}`}
        onClick={event => { if (!(event.target as HTMLElement).closest('button,a,input,summary')) selectCourse(p.opt); }}>
        <div className="opt-course-top">
          <h3>{name}</h3>
          <span className={`tag${on ? ' acc' : ''}`}>{trackTrait(p.opt)}</span>
        </div>
        <p className="opt-tagline">{planDescription(p.tagline)}</p>
        <dl className="opt-facts">
          <div><dt>자료 학습 기간</dt><dd>{t && t.weeks != null ? <><b>{t.weeks}</b>주</> : waitText(p)}</dd></div>
          <div><dt>주당</dt><dd><b>{p.hours}</b>시간</dd></div>
          <div><dt>강좌 비용</dt><dd>{t ? <b>{amountText(t)}</b> : waitText(p)}</dd></div>
        </dl>
        <OptionSummary id={`course-summary-${p.opt}`} reason={p.def.reason} pros={p.def.pros} expanded />
        {versions(p)}
        {err && !busy ? (
          <>
            <p className="opt-fail">
              <Icon name="x" />
              <span>다시 만들지 못했어요 · {err.user}. 이전 안을 그대로 뒀어요. 다시 시도하려면 ‘다르게 다시 만들기’를 눌러 주세요.</span>
            </p>
            <OpsBox items={[['', err]]} cls="sm" />
          </>
        ) : null}
        <div className="opt-course-foot">
          <button type="button" role="radio" aria-checked={on} aria-label={`${name} 선택`} className={`btn sm ${on ? 'pri' : 'line'}`} disabled={selecting} onClick={() => selectCourse(p.opt)}>
            {on ? <><Icon name="check" /> 선택한 코스</> : '이 코스 선택'}
          </button>
          <button type="button" className="btn sm ghost" disabled={busy} onClick={() => askRegenerate(p.opt)}>
            {remaking ? <><span className="sp" aria-hidden="true" /> <Wait>다시 만드는 중…</Wait></> : <><Icon name="retry" /> 다르게 다시 만들기</>}
          </button>
        </div>
      </article>
    );
  };
  const missingCard = (id: string) => {
    const running = d.genRun?.rows[id]?.st === 'run';
    return (
      <article key={id} className="opt-course is-missing">
        <div className="opt-course-top">
          <h3>{trackName(id, D.perspectives[id].name)}</h3>
          <span className="tag warn">생성되지 않음</span>
        </div>
        <p className="opt-tagline">이 코스는 만들지 못했어요.</p>
        <div className="opt-course-foot">
          <button type="button" className="btn sm line" disabled={running} onClick={() => void draftCall('계획을 재생성하지 못했어요', draftId => draftsApi.optionRetry(draftId, id), { soft: true })}>
            {running ? <><span className="sp" aria-hidden="true" /> 생성 중</> : <><Icon name="retry" /> 이 코스 다시 받기</>}
          </button>
        </div>
      </article>
    );
  };
  return (
    <>
      <Stepper cur="options" busy={selecting} />
      <Page
        title={ps.length === 1 ? '작성된 로드맵과 학습 자료를 확인해 주세요' : '로드맵을 고르고 학습 자료를 정해 주세요'}
      >
        {d.selectionNotice&&<Note>{d.selectionNotice}</Note>}
        <section className="step-sec" aria-label="코스 고르기">
          <header className="step-sec-head">
            <span className="step-num">1</span>
            <div>
              <h2>코스 고르기</h2>
            </div>
          </header>
          <div className="opt-courses" role="radiogroup" aria-label="로드맵 코스">
            {D.optionOrder.map(id => {
              const p = ps.find(plan => plan.opt === id);
              return p ? courseCard(p) : missingCard(id);
            })}
          </div>
        </section>
        <section className="step-sec" aria-label="학습 자료 고르기">
          <header className="step-sec-head">
            <span className="step-num">2</span>
            <div>
              <h2>{compare ? '코스별 학습 자료 비교' : chosen ? `${trackName(chosen.opt, chosen.name)}의 학습 자료` : '학습 자료 고르기'}</h2>
              {compare ? <p>다음 단계에는 고른 코스의 자료만 반영돼요.</p> : null}
            </div>
            {chosen && ps.length > 1 ? (
              <button type="button" className="btn sm line step-sec-right" aria-expanded={compare} aria-controls="roadmap-material-comparison" disabled={selecting} onClick={() => setCompare(value => !value)}>
                {compare ? '고른 코스만 보기' : '다른 코스 자료와 비교'}
              </button>
            ) : null}
          </header>
          {!chosen && !compare ? <div className="opt-empty">위에서 코스를 먼저 골라 주세요</div> : null}
          {/* 세 코스의 자료 편집기는 늘 떠 있다(기간·금액 계산과 저장을 맡는다). 보기 방식만 바꾼다 */}
          <section id="roadmap-material-comparison" ref={materialPanel} className={compare ? 'roadmap-material-panel full-width-materials' : 'opt-materials'} aria-label={compare ? '스킬별 학습 자료 비교' : '고른 코스의 학습 자료'}>
            {compare && !comparisonVisible ? <><div className="loading" role="status"><span className="sp" aria-hidden="true" /><span>코스별 자료 제안을 준비하고 있어요. 1~2분쯤 걸릴 수 있어요.</span></div><Skeleton kind="columns" count={ps.length||3}/></> : null}
            <div hidden={compare && !comparisonVisible}>
              {compare ? <MaterialSkillTabs names={materialNames} active={activeMaterialSkill} onChange={setMaterialSkill} id={materialTabsId} panelId="material-comparison-panel"/> : null}
              <div className={compare ? 'material-course-comparison' : 'opt-material-list'} role={compare ? 'tabpanel' : undefined} id="material-comparison-panel" aria-labelledby={compare ? `${materialTabsId}-tab-${materialNames.indexOf(activeMaterialSkill)}` : undefined}>
                {ps.map(p=><section className={`material-course-column${cur===p.opt?' is-selected':''}`} key={p.opt} hidden={!compare&&cur!==p.opt} aria-label={`${trackName(p.opt,p.name)} 자료`}>
                  <header><h3>{trackName(p.opt,p.name)}</h3>{regenBusy(d,p.opt)?<span role="status"><span className="sp" aria-hidden="true"/> <Wait>이 코스의 로드맵을 다시 만드는 중…</Wait></span>:stateOf(p)!=='ready'?<span role="status"><Wait>{stateOf(p)==='failed'?'이 코스의 자료 준비 실패':'이 코스의 자료 준비 중…'}</Wait></span>:null}<span hidden={regenBusy(d,p.opt)||stateOf(p)!=='ready'} title={materialSummary(p)}>{materialSummary(p)}</span></header>
                  <ResourceSelection key={`${p.opt}:${p.def.optionId||p.tagline}`} ref={value=>{editors.current[p.opt]=value;}} courseId={p.opt} stacked={!compare} skillFilter={compare?activeMaterialSkill:undefined} sectionOpen={compare?materialSections:undefined} onSectionToggle={toggleMaterialSection} locked={regenBusy(d,p.opt)||selecting} onTotals={receiveTotals} onPrepared={receivePrepared} onChoicesChanged={()=>updateWs(state=>invalidateMaterialChoices(state,p.opt))}/>
                </section>)}
              </div>
            </div>
          </section>
        </section>
        {off ? <Note>저장된 예시 로드맵과 입력한 목표의 주제가 달라요. 목표에 맞는 안을 받으려면 AI 모델 설정을 확인한 뒤 다시 생성해 주세요.</Note> : null}
        <div className="step-bar">
          <div className="step-bar-sum" aria-live="polite">
            {chosen ? <b>{trackName(chosen.opt, chosen.name)}</b> : null}
            {block ? <span className="step-bar-wait">{block}</span>
              : chosenTotals && chosen ? <><span>자료 학습 {chosenTotals.weeks == null ? '기간 계산 중…' : `${chosenTotals.weeks}주`}</span><span>주 {chosen.hours}시간</span><span>강좌 {amountText(chosenTotals)}</span></>
              : null}
          </div>
          <div className="step-bar-btns">
            <button type="button" className="btn line" disabled={selecting} onClick={() => go(paths.newResult)}>
              <Icon name="left" />
              이전
            </button>
            <button type="button" className="btn pri" disabled={selecting || !!block} onClick={next}>
              다음: {reviewLabel}
            </button>
          </div>
        </div>
      </Page>
    </>
  );
}
