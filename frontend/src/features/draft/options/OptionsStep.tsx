import { currentMaterialTotals } from './materialTotals';
import { optionSummary, planDescription } from '@/shared/lib/planDescription';
import { MaterialBasis } from '@/shared/ui/MaterialBasis';
import { activityTime } from '@/shared/lib/resourceTime';
import { invalidateDraft, invalidateMaterialChoices } from '../invalidation';
import { materialPreparation, canRevealMaterials, initialMaterialPreparation, type MaterialStatus } from './materialPreparation';
import './courseSkills.css';
import './materialPanel.css';
import { MaterialSkillTabs } from '../result/MaterialSkillTabs';
import { materialVersionKey } from '../result/materialVersion';
import { usePrepareMaterials, ResourceSelection, type ResourceSelectionHandle, type MaterialTotals } from '../result/ResultStep';
import { completeMaterialSelection } from '../materials/materialTransition';
import { OptionSummary } from './OptionSummary';
import { crashCore, crashCoreExpandable } from './crashCore';
import { comparisonEvidence } from './comparisonEvidence';
import { trackName } from '@/shared/constants/data';
/* 5. 3안 비교표 (10/14 · 5차 scr['new-options']): 열 순서는 A1·A2·A3 고정.
   마음에 들지 않는 안은 요청을 적어 그 안만 다시 만들고(API-32 · 버전으로 쌓임), ‹ › 로 버전을 넘겨 본다 */
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
import { DraftSaveError, draftCall, flush, takeDraft } from '../draftSync';
import { useKickSupport } from '../generation/GenerationStep';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';
import { SupCell, SupNote, syncGenCur } from './support';

/** 고른 안의 계획 계산 매개변수(진단 에이전트가 넘긴 학습 선호 기준) */
export function paramsOf(d: DraftDoc, opt?: OptionDef) {
  const h = d.handoff;
  return { start: h?.startStage || 1, hours: planWeeklyHours(h?.prefs.weeklyHours, opt?.weeklyHours), format: h?.prefs.formatKey || 'mixed', patch: {} };
}

export const optionIds = (d: DraftDoc): string[] => (d.gen ? D.optionOrder.filter((k) => d.gen?.options[k]) : []);
export const optsOf = (d: DraftDoc): PlanContent[] => optionIds(d).map((id) => buildPlan(d.gen!.options[id], paramsOf(d, d.gen!.options[id]), d.goal));

const regenBusy = (d: DraftDoc, pid: string) => !!(d.gen && d.gen.regenRun && d.gen.regenRun[pid]);
const regenErr = (d: DraftDoc, pid: string) => (d.gen && d.gen.regenErr && d.gen.regenErr[pid] ? cause(d.gen.regenErr[pid]) : null);

export async function choose(go: ReturnType<typeof useGo>, id: string, save?:()=>Promise<boolean>): Promise<void> {
  try {
    await flush();
    takeDraft(await draftsApi.select(ws().draftId as string, id, comparisonEvidence(ws().draft.gen)));
    if(save){if(!await completeMaterialSelection(save,go))toast('자료 선택을 저장하지 못했어요. 선택은 유지됩니다. 다시 시도해 주세요.');}
    else go(paths.newMaterials);
  } catch (err) {
    if (!(err instanceof DraftSaveError)) failToast(err, '안을 고르지 못했어요');
  }
}

function regeneratePlan(pid: string) {
  return draftCall('해당 계획을 다시 생성하지 못했어요', id => draftsApi.regenerate(id, pid, null), { soft: true });
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

/* 다시 만들기 요청 창: 바라는 점(문장) + 빠른 칩 + 활동별 그대로/빼기/바꾸기. 아무것도 고르지 않으면 활동 구성이 다른 안을 새로 쓴다 */
const QUICK = ['더 짧게', '실습 늘리기', '비용 줄이기', '영상 위주', '문서 위주', '업무 과제 늘리기'];
function RegenBody({ pl }: { pl: PlanContent }) {
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
      <div className="field">
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
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        아무것도 고르지 않으면 같은 관점으로 활동 구성이 다른 안을 새로 써요. 다시 만든 안은 새 버전으로 쌓이고 ‹ › 로 이전 버전과 넘겨 볼 수 있어요.
      </p>
    </div>
  );
}

async function regenGo(): Promise<void> {
  const q = ws().regenReq;
  const g = ws().draft.gen;
  if (!q || !g) return;
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
  updateWs((s) => {
    s.regenReq = null;
    const gg = s.draft.gen;
    if (gg) gg.regenRun = { ...(gg.regenRun || {}), [q.pid]: { req } };
  });
  await draftCall(`${D.perspectives[q.pid].name}을 다시 만들지 못했어요`, (id) => draftsApi.regenerate(id, q.pid, has ? req : null), { soft: true });
}

export function openRegenSheet(pid: string): void {
  const d = ws().draft;
  const g = d.gen;
  if (!g || !g.options[pid] || regenBusy(d, pid)) return;
  syncGenCur();
  const o = ws().draft.gen!.options[pid];
  const pl = buildPlan(o, paramsOf(d, o), d.goal);
  updateWs((s) => void (s.regenReq = { pid, note: '', chips: [], acts: {} }));
  openSheet({
    title: `${D.perspectives[pid].name} 다시 만들기`,
    wide: true,
    body: () => <RegenBody pl={pl} />,
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
  const [supportOpen, setSupportOpen] = useState(false);
  const [summariesOpen, setSummariesOpen] = useState(false);
  const [selecting,setSelecting]=useState(false);
  const [materialsOpen,setMaterialsOpen]=useState(true);
  const [materialAttempt,setMaterialAttempt]=useState(0);
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
  const [materialSkill,setMaterialSkill]=useState('');
  const [materialSections,setMaterialSections]=useState({books:true,courses:true});
  const toggleMaterialSection=useCallback((kind:'books'|'courses',open:boolean)=>setMaterialSections(old=>old[kind]===open?old:{...old,[kind]:open}),[]);
  const materialTabsId=useId();
  const materialPanel=useRef<HTMLElement|null>(null);
  function openMaterials(){
    setMaterialsOpen(true);
    requestAnimationFrame(()=>materialPanel.current?.scrollIntoView({behavior:'smooth',block:'start'}));
  }
  const editors=useRef<Record<string,ResourceSelectionHandle|null>>({});
  const [totals,setTotals]=useState<Record<string,MaterialTotals>>({});
  const receiveTotals=useCallback((course:string,value:MaterialTotals)=>setTotals(old=>old[course]?.weeks===value.weeks&&old[course]?.amount===value.amount&&old[course]?.unknown===value.unknown&&old[course]?.version===value.version&&old[course]?.weeklyHours===value.weeklyHours?old:{...old,[course]:value}),[]);
  async function changeVersion(course:string,direction:number){
    if(selecting)return;
    setSelecting(true);
    try{await ver(course,direction,()=>editors.current[course]?.saveForVersion()||Promise.resolve(true));}
    finally{setSelecting(false);}
  }
  async function regenerateWithMaterials(course:string){
    if(selecting)return;
    setSelecting(true);
    const owner=ws().owner,id=ws().draftId,version=materialVersionKey(ws().draft.gen?.options[course]);
    try{
      if(editors.current[course]&&!await editors.current[course]!.saveForVersion()){toast('자료 선택을 저장하지 못해 재생성을 시작하지 않았어요.');return;}
      if(ws().owner===owner&&ws().draftId===id&&materialVersionKey(ws().draft.gen?.options[course])===version)await regeneratePlan(course);
    }finally{setSelecting(false);}
  }
  function selectCourse(course:string){
    if(selecting)return;
    updateWs(state=>{if(state.draft.chosen!==course){state.draft.chosen=course;invalidateDraft(state,'materials');}});
  }
  const go = useGo();
  const d = useWs((s) => s.draft);
  const comparisonScope=useWs(s=>JSON.stringify([s.owner,s.draftId,s.draft.v2Assessment?.generationId]));
  const availableVersions=Object.fromEntries(Object.entries(d.gen?.options||{}).map(([course,option])=>[course,materialVersionKey(option)]));
  const status=JSON.parse(generationStatus) as {unavailable:string[];generating:string[]};
  const readyToReveal=canRevealMaterials(preparation.courses,availableVersions,status.unavailable,status.generating);
  const comparisonVisible=preparation.scope===comparisonScope&&(readyToReveal||preparation.revealed);
  const currentTotals = (p: PlanContent) => currentMaterialTotals(totals[p.opt], materialVersionKey(p.def), p.hours, !regenBusy(d,p.opt) && materialPrepared[`${p.opt}:${materialVersionKey(p.def)}`] === 'ready');
  const materialSummary = (p: PlanContent) => {
    const current = currentTotals(p);
    return current ? `자료 학습 ${current.weeks === null ? '주차 산정 필요' : `예상 ${current.weeks}주`} · 강좌 총계 ${current.amount.toLocaleString()}원${current.unknown ? ' + 가격 미확인' : ''}` : '자료 준비 중…';
  };
  useCatalog((s) => s.res);
  useDraftWatch();
  useKickSupport();
  useRegenToast();
  useEffect(() => {
    syncGenCur();
  }, []);
  const g = d.gen;
  if (!g || !d.handoff) return null;
  const ps = optsOf(d);
  const cur = d.chosen;
  const materialsFailed=ps.some(p=>materialPrepared[`${p.opt}:${materialVersionKey(p.def)}`]==='failed');
  const materialNames=Array.from(new Set((d.selectedSkills || ps.flatMap(plan=>plan.def.learningSkills || [])).map(skill=>skill.name)));
  const activeMaterialSkill=materialNames.includes(materialSkill)?materialSkill:materialNames[0];
  const colCls = (p: PlanContent) => (regenBusy(d, p.opt) ? 'busy' : undefined);
  const off = ps.some((p) => p.def.offDomain);
  const missing = g.missing || [];
  const row = (k: string, f: (p: PlanContent, x: OptionDef) => React.ReactNode) => (
    <tr>
      <td className="k">{k}</td>
      {D.optionOrder.map(id => {
        const p = ps.find(plan => plan.opt === id);
        return p ? (
        <td key={p.opt} data-col={p.opt} className={colCls(p)} onClick={event => { if (!(event.target as HTMLElement).closest('button,a,input,summary')) selectCourse(p.opt); }} style={{ cursor: 'pointer' }}>
          {f(p, p.def)}
        </td>
      ) : <td key={id} data-col={id} className="muted">—</td>; })}
    </tr>
  );
  const Ver = ({ p }: { p: PlanContent }) => {
    const list = (g.hist || {})[p.opt];
    const i = (g.cur || {})[p.opt] || 0;
    const o = p.def;
    const busy = selecting || regenBusy(d, p.opt);
    return (
      <>
        {list && list.length > 1 ? (
          <span className="vnav">
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
          <>
            {o.revSummary ? <span className="small rev">바꾼 점: {planDescription(o.revSummary)}</span> : null}
            {o.revRequest ? <span className="small muted rev">요청: {o.revRequest}</span> : null}
            {(o.revNotes || []).length ? <span className="small muted rev">반영하지 못한 것: {(o.revNotes || []).map(planDescription).join(' ')}</span> : null}
          </>
        ) : null}
      </>
    );
  };
  const head = (p: PlanContent) => {
    const busy = selecting || regenBusy(d, p.opt);
    const err = regenErr(d, p.opt);
    return (
      <th key={p.opt} data-col={p.opt} className={colCls(p)} onClick={event => { if (!(event.target as HTMLElement).closest('button,a,input,label')) selectCourse(p.opt); }} style={{ cursor: 'pointer' }}>
        <div className="course-title-row">
          <label><input type="radio" name="pick" value={p.opt} checked={cur === p.opt} disabled={selecting} onChange={() => selectCourse(p.opt)} /><b>{trackName(p.opt, p.name)}</b></label>
          <button type="button" className="course-regenerate" disabled={busy} onClick={() => void regenerateWithMaterials(p.opt)}>{busy ? '계획 생성 중…' : '해당 계획 다시 생성'}</button>
        </div>
        <small className="course-tagline">{planDescription(p.tagline)}</small>
        <OptionSummary id={`course-summary-${p.opt}`} reason={p.def.reason} pros={p.def.pros} expanded={summariesOpen}
          core={p.opt === 'A2' ? crashCore(p.def.learningSkills) : null} />
        <Ver p={p} />
        {err && !busy ? (
          <>
            <span className="small rev fail-t">
              <Icon name="x" />
              <span>다시 만들지 못했어요 · {err.user}. 이전 안을 그대로 뒀어요. 다시 시도하려면 제목 옆 ‘해당 계획 다시 생성’을 눌러 주세요.</span>
            </span>
            <OpsBox items={[['', err]]} cls="sm" />
          </>
        ) : null}
      </th>
    );
  };
  return (
    <>
      <Stepper cur="options" busy={selecting} />
      <Page
        title={ps.length === 3 ? '로드맵 제안' : ps.length === 1 ? '작성된 로드맵을 확인해 주세요' : `작성된 로드맵 ${ps.length}안을 비교하고 골라 주세요`}
        lead="앞에서 선택한 스킬·순서는 유지합니다. 로드맵을 비교하며 강좌·도서를 고르고, 예상 기간·금액을 확인한 뒤 검토로 진행해 주세요."
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newResult)}>
              <Icon name="left" />
              이전
            </button>
            <button
              className="btn pri"
              disabled={selecting}
              onClick={() => {
                if (!cur) { toast('로드맵을 먼저 선택해 주세요.'); return; }
                if (regenBusy(ws().draft, cur)) {
                  toast('그 안을 다시 쓰는 중이에요. 잠시 뒤에 골라 주세요');
                  return;
                }
                const option=ws().draft.gen?.options[cur];
                const state=materialPrepared[`${cur}:${materialVersionKey(option)}`];
                if(state!=='ready'){openMaterials();toast(state==='failed'?'선택한 코스의 자료 추천에 실패했어요. 다시 시도한 뒤 저장해 주세요.':'선택한 코스의 자료를 준비하고 있어요. 완료 후 다시 눌러 주세요.');return;}
                if(!editors.current[cur]){openMaterials();toast('선택한 코스의 자료를 불러오는 중이에요. 잠시 뒤 다시 눌러 주세요.');return;}
                setSelecting(true);
                void choose(go,cur,()=>editors.current[cur]?.save()||Promise.resolve(false)).finally(()=>setSelecting(false));
              }}
            >
              자료 저장 후 검토·산출물 선택
            </button>
          </>
        }
      >
        <style>{`.v2-course-boundaries [data-col]{border-left:3px solid #f2f2f2}.v2-course-boundaries [data-col]:last-child{border-right:3px solid #f2f2f2}`}</style>
        {d.selectionNotice&&<Note>{d.selectionNotice}</Note>}
        <div className="tblwrap">
          <table className="cmp v2-course-boundaries">
            <thead>
              <tr>
                <th />
                {D.optionOrder.map(id => {
                  const p = ps.find(plan => plan.opt === id);
                  if (p) return head(p);
                  const running = d.genRun?.rows[id]?.st === 'run';
                  return <th key={id} data-col={id}><div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                    <b>{trackName(id, D.perspectives[id].name)}</b><span style={{ color: 'var(--danger, #dc3545)', fontSize: 12 }}>생성되지 않음</span>
                    <button className="link" disabled={running} onClick={() => void draftCall('계획을 재생성하지 못했어요', draftId => draftsApi.optionRetry(draftId, id), { soft: true })}>
                      {running ? <><span className="sp" aria-hidden="true" /> 생성 중</> : '재생성'}
                    </button></div></th>;
                })}
              </tr>
              {ps.some(plan => optionSummary(plan.def.reason, plan.def.pros).expandable
                || (plan.opt === 'A2' && crashCoreExpandable(crashCore(plan.def.learningSkills)))) &&<tr><th /><th colSpan={3} style={{ textAlign: 'center', padding: '2px 8px 7px', fontWeight: 400 }}><button type="button" className="course-more" aria-expanded={summariesOpen} aria-controls={ps.map(plan => `course-summary-${plan.opt}`).join(' ')} onClick={() => setSummariesOpen(open => !open)}>{summariesOpen ? '접기' : '더보기'}</button></th></tr>}
            </thead>
            <tbody>
              {row('자료 학습 예상 기간', (p) => (
                <><span className="numv">{currentTotals(p)?.weeks == null ? '산정 필요' : `${currentTotals(p)!.weeks}주`}</span> · 주 {p.hours}시간</>
              ))}
              {row('예상 금액',p=><span>{currentTotals(p)?`${currentTotals(p)!.amount.toLocaleString()}원${currentTotals(p)!.unknown?' + 가격 미확인':''}`:'자료 선택 후 계산'}<small className="muted"> · 선택 강좌 기준</small></span>)}
              <tr><td className="k">학습 자료</td><td colSpan={3} className="material-expand-cell"><button type="button" className={`btn line small material-expand${materialsOpen?' is-open':''}`} aria-expanded={materialsOpen} aria-controls="roadmap-material-comparison" disabled={selecting} onClick={()=>materialsOpen?setMaterialsOpen(false):openMaterials()}><Icon name="book"/>{materialsOpen?'자료 비교 접기':'자료 비교하기'}</button></td></tr>
              <tr><td className="k"><button className="link" aria-expanded={supportOpen} onClick={() => setSupportOpen(open => !open)}>지원 조건 {supportOpen ? '접기' : '보기'}</button></td>
                {D.optionOrder.map(id => { const p = ps.find(plan => plan.opt === id); return <td key={id} data-col={id} className={p ? colCls(p) : undefined}>{p && supportOpen && <SupCell o={p.def} />}</td>; })}
              </tr>
            </tbody>
          </table>
          <MaterialBasis />
        </div>
        <section id="roadmap-material-comparison" ref={materialPanel} className="roadmap-material-panel full-width-materials" hidden={!materialsOpen} aria-label="스킬별 학습 자료 비교">
          <header className="roadmap-material-header"><div><span>학습 자료</span><h2>스킬별 자료 비교</h2></div><button type="button" className="btn line small" disabled={selecting} onClick={()=>setMaterialsOpen(false)}>접기 <Icon name="x"/></button></header>
          {!comparisonVisible&&<div className="loading" role="status"><span className="sp" aria-hidden="true"/><span>{materialsFailed?'자료 제안 일부를 준비하지 못했어요. 다시 시도해 주세요.':'세 코스의 자료 제안을 준비하고 있어요. 완료되면 함께 표시합니다.'}</span>{materialsFailed&&<button type="button" className="btn line small" onClick={()=>{reportPreparation({type:'reset',scope:comparisonScope});setMaterialAttempt(n=>n+1);}}>다시 시도</button>}</div>}
          <div hidden={!comparisonVisible}>
          <MaterialSkillTabs names={materialNames} active={activeMaterialSkill} onChange={setMaterialSkill} id={materialTabsId} panelId="material-comparison-panel"/>
          <div className="material-course-comparison" role="tabpanel" id="material-comparison-panel" aria-labelledby={`${materialTabsId}-tab-${materialNames.indexOf(activeMaterialSkill)}`}>{ps.map(p=><section className={`material-course-column${cur===p.opt?' is-selected':''}`} key={p.opt} aria-label={`${trackName(p.opt,p.name)} 자료`}>
            <header><h3>{trackName(p.opt,p.name)}</h3>{regenBusy(d,p.opt)?<span role="status"><span className="sp" aria-hidden="true"/> 이 코스의 로드맵을 다시 만드는 중…</span>:materialPrepared[`${p.opt}:${materialVersionKey(p.def)}`]!=='ready'?<span role="status">{materialPrepared[`${p.opt}:${materialVersionKey(p.def)}`]==='failed'?'이 코스의 자료 준비 실패':'이 코스의 자료 준비 중…'}</span>:null}<span hidden={regenBusy(d,p.opt)||materialPrepared[`${p.opt}:${materialVersionKey(p.def)}`]!=='ready'} title={materialSummary(p)}>{materialSummary(p)}</span></header>
            <ResourceSelection key={`${materialAttempt}:${p.opt}:${p.def.optionId||p.tagline}`} ref={value=>{editors.current[p.opt]=value;}} courseId={p.opt} skillFilter={activeMaterialSkill} sectionOpen={materialSections} onSectionToggle={toggleMaterialSection} locked={regenBusy(d,p.opt)||selecting} onTotals={receiveTotals} onPrepared={receivePrepared} onChoicesChanged={()=>updateWs(state=>invalidateMaterialChoices(state,p.opt))}/>
          </section>)}</div>
          </div>
        </section>
        <SupNote />
        {missing.length ? (
          <Note>
            {missing.map((id) => `${D.perspectives[id].name}`).join(', ')}은 생성되지 않았어요. 코스 이름 옆 ‘재생성’으로 해당 코스만 다시 받을 수 있어요. 성공한 코스는 유지됩니다.
          </Note>
        ) : null}
        <Note>
          {ps.length > 1
            ? '고른 안(보고 있는 버전)을 쓴 에이전트(관점)만 저장해요. 고르지 않은 안과 다른 버전은 저장하지 않아요.'
            : '고른 안(보고 있는 버전)을 쓴 에이전트(관점)만 저장해요.'}
        </Note>
        {off ? <Note>가데이터 모드에는 RAG 시나리오 후보만 있어요. 다른 목표의 후보는 좌측 ‘AI 모델’에서 RunPod-Ollama나 OpenAI API를 쓰면 확인할 수 있어요.</Note> : null}
      </Page>
    </>
  );
}
