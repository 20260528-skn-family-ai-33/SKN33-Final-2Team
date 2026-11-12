import { MaterialBasis } from '@/shared/ui/MaterialBasis';
import { hrs } from '@/shared/lib/format';
import { courseDifficulty } from '@/shared/lib/courseDifficulty';
import { materialVersionKey } from './materialVersion';
import { loadRecommendations, recommendationUrl, requestMaterials as request, type Resource, type Result } from './materialRequests';
import { MaterialReason } from './MaterialReason';
import { ResourcePreviewButton } from './ResourcePreview';
import { OutdatedRecommendations, UnverifiedTargets } from './ResourceNotices';
import { MaterialSkillTabs } from './MaterialSkillTabs';
import { AssessmentResults } from './AssessmentResults';
import { prepareRoadmaps } from '../prepareRoadmaps';
import { useDraftWatch } from '../useDraftWatch';
import { CourseCostSummary } from '../materials/CourseCostSummary';
import { flush } from '../draftSync';
import { ResourceImage } from '@/shared/ui/ResourceImage';
import { planWeeklyHours } from '@/shared/lib/plan';
import { useEffect, useId, useImperativeHandle, useRef, useState, type Ref } from 'react';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { useWs } from '@/shared/state/workspace';
import { Page } from '@/shared/ui/parts';
import { Skeleton } from '@/shared/ui/Skeleton';
import { Stepper } from '../Stepper';
import { genStart, startEdit, ResultEdit } from './legacyResult';
import { displayOrder, currentWeeks, currentEstimates, durationLabel, totalWeeks, type Choices, type DurationEstimate } from './skillOrder';

const durationFlights = new Map<string, Promise<Result>>();
export function usePrepareMaterials() {
  const id=useWs(s=>s.draftId), generation=useWs(s=>s.draft.v2Assessment?.generationId);
  const optionsKey=useWs(s=>JSON.stringify(Object.entries(s.draft.gen?.options||{}).filter(([course])=>!s.draft.gen?.regenRun?.[course]).map(([course,option])=>[course,materialVersionKey(option)])));
  useEffect(()=>{
    if(!id||!generation)return;
    for(const [course,version] of JSON.parse(optionsKey) as [string,string][]) {
      void loadRecommendations(id, generation, course, version).catch(()=>{});
    }
  },[id,generation,optionsKey]);
}
function ResourceCard({ resource, kind, checked, disabled, preload = false, onChange }: { resource: Resource; kind: 'course' | 'book'; checked: boolean; disabled?: boolean; preload?: boolean; onChange: () => void }) {
  const price = resource.cost == null ? (kind === 'book' ? null : '가격 미확인') : resource.cost === 0 ? '무료' : `${resource.cost.toLocaleString('ko-KR')}원`;
  return <article className={`v2-resource ${checked ? 'v2-resource-selected' : ''}`} role={kind === 'course' ? 'radio' : 'checkbox'} aria-checked={checked} aria-disabled={disabled} aria-label={resource.title} tabIndex={disabled ? -1 : 0}
    onClick={event => { if (!disabled && !(event.target as HTMLElement).closest('a,button,input,label')) onChange(); }}
    onKeyDown={event => { if (event.target === event.currentTarget && !disabled && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onChange(); } }}>
    <ResourceImage className="v2-resource-image" image={resource.image} type={kind} />
    <div className="v2-resource-info"><label className="v2-resource-choice">
      <input type={kind === 'course' ? 'radio' : 'checkbox'} checked={checked} disabled={disabled} onChange={onChange} />
      <span><b title={resource.title}>{resource.title}</b>{resource.aiRecommended && <span className="tag acc">AI 추천</span>}</span>
    </label>
    <div className="v2-resource-meta"><span>{resource.provider || '출처 미확인'}{price && ` · ${price}`}</span>
    {kind === 'course' && resource.difficulty && <span>{courseDifficulty(resource)}</span>}
    <span>{kind === 'book' ? '일정 산정 제외' : resource.hours && resource.hours > 0 && resource.timeStatus !== 'unknown' ? `${hrs(resource.hours)}${resource.timeStatus === 'estimated' || resource.estimated?.includes('hours') ? ' (추정)' : ''}` : '시간 미확인 · 일정 1주 가정'}</span></div>
    {kind === 'course' && <UnverifiedTargets topics={resource.unverifiedTargetTopics} />}</div>
    <ResourcePreviewButton resource={resource} kind={kind} preload={preload} />
  </article>;

}
export type ResourceSelectionHandle = { save: () => Promise<boolean>; saveForVersion: () => Promise<boolean> };
export type MaterialTotals = { weeks: number | null; amount: number; unknown: boolean; version: string; weeklyHours: number };
export function ResultStep() {
  usePrepareMaterials();
  const d = useWs(s => s.draft);
  const go = useGo();
  const [busy, setBusy] = useState(false);
  const [error,setError] = useState('');
  const id=useWs(s=>s.draftId),generation=d.v2Assessment?.generationId;
  useDraftWatch();
  useEffect(()=>{if(d.v2Assessment?.completed)void prepareRoadmaps().catch(e=>setError(e instanceof Error?e.message:'로드맵 준비에 실패했어요.'));},[id,generation,d.v2Assessment?.completed]);
  return <><Stepper cur="result" busy={busy} /><Page title="역량 테스트 결과를 확인해 주세요"
    lead="설문에서 선택한 응답과 퀴즈 정오답을 확인해 주세요."
    foot={<><button className="btn line" disabled={busy} onClick={() => go(paths.newQuiz)}>이전: 역량 테스트</button>
      <button className="btn pri" disabled={busy} onClick={() => { setBusy(true); void genStart(go).finally(() => setBusy(false)); }}>{busy ? '이동 중…' : '다음: 로드맵·자료 선택'}</button></>}>
      <AssessmentResults />
      {error&&<p role="alert">{error} 다음 버튼으로 다시 시도할 수 있어요.</p>}
    </Page></>;
}
export function ResourceSelection({ ref, onChoicesChanged, locked, courseId, onTotals, onPrepared, skillFilter, sectionOpen, onSectionToggle, stacked }: { stacked?: boolean; ref?: Ref<ResourceSelectionHandle>; onChoicesChanged?: () => void; locked?: boolean; courseId?: string; onTotals?: (course:string,totals:MaterialTotals)=>void; onPrepared?:(course:string,state:'ready'|'pending'|'failed',version:string)=>void; skillFilter?:string; sectionOpen?:{books:boolean;courses:boolean}; onSectionToggle?:(kind:'books'|'courses',open:boolean)=>void }) { const scope=useWs(s=>JSON.stringify([s.owner,s.draftId,s.draft.v2Assessment?.generationId,courseId||s.draft.chosen,materialVersionKey(s.draft.gen?.options[courseId||s.draft.chosen||''])])); return <ResultSelection key={scope} editorRef={ref} onChoicesChanged={onChoicesChanged} locked={locked} courseId={courseId} onTotals={onTotals} onPrepared={onPrepared} skillFilter={skillFilter} sectionOpen={sectionOpen} onSectionToggle={onSectionToggle} stacked={stacked} />; }
/* stacked: 탭 없이 모든 스킬을 순서대로 펼쳐 보여 준다(6단계에서 고른 코스의 자료) */
function ResultSelection({ editorRef, onChoicesChanged, locked = false, courseId, onTotals, onPrepared, skillFilter, sectionOpen, onSectionToggle, stacked = false }: { stacked?: boolean; editorRef?: Ref<ResourceSelectionHandle>; onChoicesChanged?: () => void; locked?: boolean; courseId?:string; onTotals?:(course:string,totals:MaterialTotals)=>void; onPrepared?:(course:string,state:'ready'|'pending'|'failed',version:string)=>void; skillFilter?:string; sectionOpen?:{books:boolean;courses:boolean}; onSectionToggle?:(kind:'books'|'courses',open:boolean)=>void }) {
  const id = useWs(s => s.draftId);
  const draft = useWs(s => s.draft);
  const course = courseId || draft.chosen;
  const version = materialVersionKey(draft.gen?.options[course || '']);
  const generation = useWs(s => s.draft.v2Assessment?.generationId);
  const [storedResult, setResult] = useState<Result | null>(null);
  const result = storedResult && (storedResult.courseId ?? null) === (course ?? null) ? storedResult : null;
  const [choices, setChoices] = useState<Choices>({});
  const [order, setOrder] = useState<string[]>([]);
  const [storedEstimates, setEstimates] = useState<Record<string,DurationEstimate>>({});
  const weeklyHours = planWeeklyHours(draft.handoff?.prefs.weeklyHours, draft.gen?.options[course || '']?.weeklyHours);
  const estimates = currentEstimates(order, choices, storedEstimates, weeklyHours);
  const [activeSkill,setActiveSkill]=useState('');
  const tabsId=useId();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const savedSelection = useRef('');
  const attemptedDurations = useRef(new Set<string>());
  useEffect(() => {
    if (!id) return;
    let active = true;
    void loadRecommendations(id, generation, course, version).then(body => {
      if (active) { setResult(body); setChoices(body.choices); setOrder(body.skillOrder ?? body.recommendations?.skills.map(s => s.name) ?? []); setEstimates(body.durationEstimates ?? {}); savedSelection.current=JSON.stringify([body.choices,body.skillOrder ?? body.recommendations?.skills.map(s=>s.name) ?? [],weeklyHours]); }
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : '추천을 읽지 못했어요.'); });
    return () => { active = false; };
  }, [id, generation, course, version, weeklyHours]);
  async function generate() {
    if (!id || busy) return;
    setBusy(true); setError('');
    try {
      const body = await request(recommendationUrl(id, course), { method: 'POST', headers: { Prefer: 'respond-async' } });
      setResult(body); setChoices(body.choices); setOrder(body.skillOrder ?? body.recommendations?.skills.map(s => s.name) ?? []); setEstimates(body.durationEstimates ?? {}); savedSelection.current=JSON.stringify([body.choices,body.skillOrder ?? body.recommendations?.skills.map(s=>s.name) ?? [],weeklyHours]);
    } catch (e) { setError(e instanceof Error ? e.message : '추천하지 못했어요.'); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!id || !result?.recommendations || busy || saving) { setError(busy||saving?'자료를 처리하고 있어요. 잠시 뒤 다시 시도해 주세요.':'자료 추천을 준비한 뒤 저장해 주세요.'); return false; }
    setSaving(true); setError('');
    try {
      await flush();
      const saved = await request(recommendationUrl(id, course, '/choices'), { method: 'PUT', body: JSON.stringify({ generationId: result.generationId, recommendationId: result.recommendations.id, choices, skillOrder: order }) });
      setEstimates(saved.durationEstimates || {});
      savedSelection.current=JSON.stringify([choices,order,weeklyHours]);
      return true;
    } catch (e) { setError(e instanceof Error ? e.message : '선택을 저장하지 못했어요.'); return false; }
    finally { setSaving(false); }
  }
  useImperativeHandle(editorRef, () => ({ save, saveForVersion: async () => {
    if(!result?.recommendations)return true;
    if(savedSelection.current===JSON.stringify([choices,order,weeklyHours]))return true;
    return save();
  } }));
  useEffect(() => {
    if (!id || !result?.recommendations) return;
    const needsEstimate = order.some(name => choices[name] && choices[name].enabled !== false && !currentEstimates(order, choices, storedEstimates, weeklyHours)[name]);
    if (!needsEstimate) return;
    const signature = JSON.stringify([id, course, result.generationId, result.recommendations.id, choices, order, weeklyHours]);
    if (attemptedDurations.current.has(signature)) return;
    let active = true;
    const timer = window.setTimeout(() => {
      attemptedDurations.current.add(signature);
      setEstimating(true);
      const body = { generationId: result.generationId, recommendationId: result.recommendations!.id, choices, skillOrder: order };
      const key = JSON.stringify([id, course, body, weeklyHours]);
      let work = durationFlights.get(key);
      if (!work) {
        work = flush().then(() => request(recommendationUrl(id, course, '/durations'), { method: 'POST', body: JSON.stringify(body) }));
        durationFlights.set(key, work);
        void work.finally(() => durationFlights.delete(key)).catch(() => {});
      }
      void work.then(body => { if (active) setEstimates(body.durationEstimates ?? {}); })
        .catch(e => { if (active) setError(e instanceof Error ? e.message : '기간을 계산하지 못했어요.'); })
        .finally(() => { if (active) setEstimating(false); });
    }, 600);
    return () => { active = false; window.clearTimeout(timer); };
  }, [id, course, result, choices, order, storedEstimates, weeklyHours]);
  const total = totalWeeks(order, choices, estimates, weeklyHours);
  const selectedCourses=new Map((result?.recommendations?.skills||[]).flatMap(skill=>skill.courses.filter(resource=>choices[skill.name]?.enabled!==false && choices[skill.name]?.course===resource.id)).map(resource=>[resource.id,resource]));
  const amount=[...selectedCourses.values()].reduce((sum,resource)=>sum+(resource.cost||0),0);
  const unknown=[...selectedCourses.values()].some(resource=>resource.cost==null);
  useEffect(()=>{if(course && result?.recommendations)onTotals?.(course,{weeks:total,amount,unknown,version,weeklyHours});},[course,total,amount,unknown,version,weeklyHours,onTotals,result?.recommendations]);
  useEffect(()=>{if(course)onPrepared?.(course,result?.recommendations?'ready':error?'failed':'pending',version);},[course,version,result?.recommendations,error,onPrepared]);
  const activeNames = order.filter(name => choices[name]?.enabled !== false);
  const missingCount = activeNames.filter(name => !choices[name] || currentWeeks(choices[name], estimates[name]) === null).length;
  function selectBook(skill: string, resource: string) {
    onChoicesChanged?.();
    setChoices(previous => {
      const current = previous[skill]; if (!current) return previous;
      const exists = current.books.includes(resource);
      if (!exists && current.books.length >= 3) return previous;
      return { ...previous, [skill]: { ...current, books: exists ? current.books.filter(id => id !== resource) : [...current.books, resource] } };
    });
  }
  const materialNames=displayOrder(order,choices).filter(name=>result?.recommendations?.skills.some(skill=>skill.name===name));
  const shownSkill=skillFilter || (materialNames.includes(activeSkill)?activeSkill:materialNames[0]);
  const content = <>
    <div className="v2-skill-summary"><h2>도서·강좌 선택</h2>
      <div><b aria-live="polite">자료 학습 예상 기간 {total === null ? `주차 산정 필요${missingCount ? ` (${missingCount}개)` : ''}` : `${total}주`}</b>
        {Object.values(estimates).some(row => row.unknownCourses?.length) ? <span className="small muted">시간 미확인 강좌는 각 1주로 가정</span> : Object.values(estimates).some(row => row.estimatedCourses?.length) && <span className="small muted">추정 시간 포함</span>}
        {estimating && <span className="small muted" role="status"><span className="sp" aria-hidden="true" /> 주차 계산 중…</span>}</div>
    </div>
    {!courseId && <MaterialBasis />}
    {result?.recommendations && <OutdatedRecommendations outdated={result.recommendations.outdated} courseId={courseId} />}
    {error && <div><p className="err" role="alert">{error}</p>{!result?.recommendations && <button className="btn line" disabled={busy} onClick={() => void generate()}>다시 시도하기</button>}</div>}
    {busy ? <><div className="loading" role="status"><span className="sp" aria-hidden="true" />자료를 확인하고 추천을 정리하고 있어요.</div><Skeleton kind="grid" count={courseId ? 2 : 4} /></>
      : result?.recommendations ? <>{!skillFilter&&!stacked&&<MaterialSkillTabs names={materialNames} active={shownSkill} onChange={setActiveSkill} id={tabsId}/>}<div className="v2-skills-board">{materialNames.map((name,skillIndex) => {
        const skill = result.recommendations!.skills.find(s => s.name === name)!;
        const selected = choices[skill.name] ?? { course: skill.selectedCourse, books: skill.selectedBooks };
        const excluded = selected.enabled === false;
        const weeks = currentWeeks(selected, estimates[skill.name]);
        const courses = skill.courses.filter(resource => course !== 'A1' || resource.cost === 0);
        const hasLegacyBookCandidates = result.recommendations?.retrieval?.matches?.some(match => match.skill === skill.name && match.resourceId.startsWith('book_'));
        return <section className={`card v2-skill${excluded ? ' v2-skill-excluded' : ''}`} key={skill.name} data-skill={skill.name} role={skillFilter||stacked?'region':'tabpanel'} id={`${tabsId}-panel-${skillIndex}`} aria-labelledby={skillFilter||stacked?undefined:`${tabsId}-tab-${skillIndex}`} aria-label={skillFilter||stacked?skill.name:undefined} hidden={!stacked&&skill.name!==shownSkill}>
          {!skillFilter&&<div className="v2-skill-heading">{stacked&&<span className="v2-skill-order">{String(skillIndex+1).padStart(2,'0')}</span>}<h2>{skill.name}</h2><span className="small muted">{excluded ? '미선택' : weeks === null ? '주차 계산 중' : durationLabel(estimates[skill.name])}</span></div>}
          <details className="material-kind material-kind-books" open={sectionOpen?.books??true} onToggle={event=>{if(sectionOpen&&event.currentTarget.open!==sectionOpen.books)onSectionToggle?.('books',event.currentTarget.open);}}><summary><span>도서</span><small>선택 {selected.books.length} / 최대 3권</small><span className="material-kind-chevron" aria-hidden="true">⌄</span></summary>
          {skill.books.length > 0 && <div className="v2-resource-grid">{skill.books.map(resource => <ResourceCard key={resource.id} resource={resource} kind="book" checked={selected.books.includes(resource.id)} disabled={locked || busy || excluded || (!selected.books.includes(resource.id) && selected.books.length >= 3)} onChange={() => selectBook(skill.name, resource.id)} />)}</div>}
          <MaterialReason kind="도서" diagnostic={skill.bookDiagnostic} hasOptions={skill.books.length > 0}
            fallback={hasLegacyBookCandidates ? '도서 후보는 있지만 이번 추천에서는 선정되지 않았어요.' : '이 스킬에 추천할 도서가 없어요.'} />
          </details><details className="material-kind material-kind-courses" open={sectionOpen?.courses??true} onToggle={event=>{if(sectionOpen&&event.currentTarget.open!==sectionOpen.courses)onSectionToggle?.('courses',event.currentTarget.open);}}><summary><span>강좌</span><small>{selected.course?'1개 선택됨':'1개 선택'}</small><span className="material-kind-chevron" aria-hidden="true">⌄</span></summary>
          {courses.length > 0 && <div className="v2-resource-grid">{courses.map(resource => <ResourceCard key={resource.id} resource={resource} kind="course" preload={skill.name === shownSkill && sectionOpen?.courses !== false} checked={selected.course === resource.id} disabled={locked || busy || excluded} onChange={() => { onChoicesChanged?.(); setChoices(old => ({ ...old, [skill.name]: { ...selected, course: resource.id } })); }} />)}</div>}
          <MaterialReason kind="강좌" diagnostic={skill.courseDiagnostic} hasOptions={courses.length > 0} fallback="프로젝트에 맞는 강좌를 찾지 못했어요." />
          </details>
        </section>;
      })}{!stacked&&skillFilter&&!materialNames.includes(skillFilter)&&<p className="small muted">이 코스에는 해당 스킬의 추천 자료가 없어요.</p>}</div></> : !error && <><div className="loading" role="status"><span className="sp" aria-hidden="true" />추천 자료를 준비하고 있어요. 1~2분쯤 걸릴 수 있어요.</div><Skeleton kind="grid" count={courseId ? 2 : 4} /></>}
    <style>{`
      .v2-skill-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
      .v2-skill-summary>div,.v2-skill-tools{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
      .v2-skills-board{display:grid;gap:16px;margin-top:20px}
      .v2-skills-board>.v2-skill{min-width:0;margin:0;padding:20px}.v2-skill-heading{display:flex;justify-content:space-between;gap:12px}
      .material-reason{margin:8px 0 0;overflow-wrap:anywhere}
      .v2-skill-heading h2{font-size:17px;margin:0 0 8px;overflow-wrap:anywhere}
      .v2-skill-tools{font-size:12px}.v2-skill-tools .btn{padding:4px 7px;min-height:0;font-size:12px}
      .v2-skill-tools b{width:100%;margin-bottom:4px}.v2-skill h3{font-size:14px;margin:18px 0 8px}
      .v2-skill-excluded{filter:grayscale(1);background:#f0f0f0;opacity:.7}
      .v2-resource-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:8px}
      .v2-resource{cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:16px;border:1px solid var(--line,#ddd);border-radius:10px;padding:9px;background:var(--card,#fff)}
      .v2-resource-image{width:52px;height:64px;object-fit:contain;flex-shrink:0;border-radius:4px}.v2-resource[aria-disabled=true]{cursor:default}.v2-resource:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.v2-resource-selected{border-color:var(--accent)}
      .v2-resource-choice{flex:1;min-width:0;display:flex;gap:7px;align-items:flex-start;cursor:pointer;font-size:13px;line-height:1.45}
      .v2-resource-choice input{flex-shrink:0;margin-top:3px}.v2-resource-choice b{overflow-wrap:anywhere}
      .v2-resource .tag{font-size:12px;padding:2px 5px;margin-left:5px;white-space:nowrap}
      .v2-resource-info{flex:1;min-width:0}.v2-resource-meta{display:flex;align-items:center;justify-content:flex-start;flex-wrap:wrap;gap:12px;margin-top:6px;font-size:11px;color:var(--muted,#777)}
      .v2-resource-meta span{min-width:0;overflow-wrap:anywhere}.v2-resource-link{align-self:center;flex-shrink:0;font:inherit;font-size:12px;white-space:nowrap;color:inherit;border:0;padding:0;background:transparent;cursor:pointer}.v2-resource-link:hover,.v2-resource-link:focus-visible{text-decoration:underline}
      @media(max-width:650px){.v2-resource{gap:10px}.v2-resource-meta{width:100%;justify-content:flex-start}.v2-skills-board>.v2-skill{padding:14px}}
      .course-material-editor .v2-skill h3{font-size:12px;line-height:1.5}
      .course-material-editor .v2-skill h3 .small{font-size:12px}
      .course-material-editor .v2-resource-choice{font-size:12.5px;line-height:1.5}
      .course-material-editor .v2-resource-choice b{font-size:12.5px;font-weight:600}
      .course-material-editor .v2-resource-meta{font-size:12px}
      .course-material-editor .v2-resource-link{font-size:12px}
    `}</style>
  </>;
  if (courseId) return <div className="course-material-editor" onClick={event=>event.stopPropagation()}>{content}</div>;
  return <div className="materials-with-cost"><div>{content}</div><CourseCostSummary skills={result?.recommendations?.skills || []} choices={choices} order={order} /></div>;
}
export { genStart, startEdit, ResultEdit };
