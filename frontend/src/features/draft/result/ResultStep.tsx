import { Fragment } from 'react';
import type { Prefs } from '@/api/types/draft';
import { D } from '@/shared/constants/data';
import { prefText } from '@/shared/lib/prefs';
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { useWs } from '@/shared/state/workspace';
import { Page } from '@/shared/ui/parts';
import { Stepper } from '../Stepper';
import { displayOrder, moveSkill, currentWeeks, totalWeeks, type Choices, type DurationEstimate } from './skillOrder';

type Resource = { id: string; title: string; provider?: string; image?: string; url?: string; cost: number | null; why: string; knowledge: string; aiRecommended: boolean };
type Skill = { name: string; courses: Resource[]; books: Resource[]; selectedCourse: string | null; selectedBooks: string[] };
type Result = { courseId?: string | null; skillDetails?: { name: string; application: string }[]; generationId: string; recommendations: { id: string; skills: Skill[] } | null; choices: Choices; skillOrder?: string[]; durationEstimates?: Record<string, DurationEstimate> };
async function request(path: string, init?: RequestInit): Promise<Result> {
  const response = await fetch(path, { ...init, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...init?.headers } });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.error?.message ?? '추천 자료를 읽지 못했어요.');
  return body;
}
const durationFlights = new Map<string, Promise<Result>>();
const recommendationFlights = new Map<string, Promise<Result>>();
function loadRecommendations(key: string, path: string): Promise<Result> {
  const pending = recommendationFlights.get(key);
  if (pending) return pending;
  const work = request(path).then(body => body.recommendations ? body : request(path, { method: 'POST' }));
  recommendationFlights.set(key, work);
  void work.finally(() => { if (recommendationFlights.get(key) === work) recommendationFlights.delete(key); }).catch(() => {});
  return work;
}
function recommendationUrl(id: string, course?: string | null, suffix = '') { return `/api/v2/drafts/${id}/recommendations${suffix}${course ? `?course=${encodeURIComponent(course)}` : ''}`; }
function ResourceCard({ resource, kind, checked, disabled, onChange }: { resource: Resource; kind: 'course' | 'book'; checked: boolean; disabled?: boolean; onChange: () => void }) {
  return <article className={`v2-resource ${checked ? 'v2-resource-selected' : ''}`} role={kind === 'course' ? 'radio' : 'checkbox'} aria-checked={checked} aria-disabled={disabled} aria-label={resource.title} tabIndex={disabled ? -1 : 0}
    onClick={event => { if (!disabled && !(event.target as HTMLElement).closest('a,input,label')) onChange(); }}
    onKeyDown={event => { if (event.target === event.currentTarget && !disabled && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onChange(); } }}>
    {resource.image && <img className="v2-resource-image" src={resource.image} alt="" loading="lazy" draggable={false} onError={event => { event.currentTarget.hidden = true; }} />}
    <div className="v2-resource-info"><label className="v2-resource-choice">
      <input type={kind === 'course' ? 'radio' : 'checkbox'} checked={checked} disabled={disabled} onChange={onChange} />
      <span><b>{resource.title}</b>{resource.aiRecommended && <span className="tag acc">AI 추천</span>}</span>
    </label>
    <div className="v2-resource-meta"><span>{resource.provider || '출처 미확인'} · {resource.cost == null ? '가격 미확인' : resource.cost === 0 ? '무료' : `${Number(resource.cost).toLocaleString()}원`}</span>
    </div></div>
    {resource.url && <a className="v2-resource-link" href={resource.url} draggable={false} target="_blank" rel="noreferrer" aria-label={`${resource.title} 바로가기`}>바로가기 ↗</a>}
  </article>;

}
export type ResourceSelectionHandle = { save: () => Promise<boolean> };
export function ResultStep() { return <ResultSelection />; }
export function ResourceSelection({ ref, onChoicesChanged, locked }: { ref?: Ref<ResourceSelectionHandle>; onChoicesChanged?: () => void; locked?: boolean }) { return <ResultSelection resourcesOnly editorRef={ref} onChoicesChanged={onChoicesChanged} locked={locked} />; }
function ResultSelection({ resourcesOnly = false, editorRef, onChoicesChanged, locked = false }: { resourcesOnly?: boolean; editorRef?: Ref<ResourceSelectionHandle>; onChoicesChanged?: () => void; locked?: boolean }) {
  const id = useWs(s => s.draftId);
  const draft = useWs(s => s.draft);
  const course = resourcesOnly ? draft.chosen : undefined;
  const generation = useWs(s => s.draft.v2Assessment?.generationId);
  const go = useGo();
  const [storedResult, setResult] = useState<Result | null>(null);
  const result = storedResult && (storedResult.courseId ?? null) === (course ?? null) ? storedResult : null;
  const [choices, setChoices] = useState<Choices>({});
  const [order, setOrder] = useState<string[]>([]);
  const [estimates, setEstimates] = useState<Record<string,DurationEstimate>>({});
  const [dragging, setDragging] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [estimating, setEstimating] = useState(false);
  const attemptedDurations = useRef(new Set<string>());
  useImperativeHandle(editorRef, () => ({ save }));
  useEffect(() => {
    if (!id) return;
    let active = true;
    void loadRecommendations(`${id}:${generation}:${course || 'base'}`, recommendationUrl(id, course)).then(body => {
      if (active) { setResult(body); setChoices(body.choices); setOrder(body.skillOrder ?? body.recommendations?.skills.map(s => s.name) ?? []); setEstimates(body.durationEstimates ?? {}); }
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : '추천을 읽지 못했어요.'); });
    return () => { active = false; };
  }, [id, generation, course]);
  async function generate() {
    if (!id || busy) return;
    setBusy(true); setError('');
    try {
      const body = await request(recommendationUrl(id, course), { method: 'POST' });
      setResult(body); setChoices(body.choices); setOrder(body.skillOrder ?? body.recommendations?.skills.map(s => s.name) ?? []); setEstimates(body.durationEstimates ?? {});
    } catch (e) { setError(e instanceof Error ? e.message : '추천하지 못했어요.'); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!id || !result?.recommendations || busy || saving) return false;
    setSaving(true); setError('');
    try {
      await request(recommendationUrl(id, course, '/choices'), { method: 'PUT', body: JSON.stringify({ generationId: result.generationId, recommendationId: result.recommendations.id, choices, skillOrder: order }) });
      return true;
    } catch (e) { setError(e instanceof Error ? e.message : '선택을 저장하지 못했어요.'); return false; }
    finally { setSaving(false); }
  }
  useEffect(() => {
    if (!id || !result?.recommendations) return;
    const needsEstimate = order.some(name => {
      const choice = choices[name], estimate = estimates[name];
      return choice && choice.enabled !== false && (!estimate || estimate.method !== 'course-hours-books/v1' || estimate.weeks === null || estimate.course !== choice.course || JSON.stringify([...estimate.books].sort()) !== JSON.stringify([...choice.books].sort()));
    });
    if (!needsEstimate) return;
    const signature = JSON.stringify([id, course, result.generationId, result.recommendations.id, choices, order]);
    if (attemptedDurations.current.has(signature)) return;
    let active = true;
    const timer = window.setTimeout(() => {
      attemptedDurations.current.add(signature);
      setEstimating(true);
      const body = { generationId: result.generationId, recommendationId: result.recommendations!.id, choices, skillOrder: order };
      const key = JSON.stringify([id, course, body]);
      let work = durationFlights.get(key);
      if (!work) {
        work = request(recommendationUrl(id, course, '/durations'), { method: 'POST', body: JSON.stringify(body) });
        durationFlights.set(key, work);
        void work.finally(() => durationFlights.delete(key)).catch(() => {});
      }
      void work.then(body => { if (active) setEstimates(body.durationEstimates ?? {}); })
        .catch(e => { if (active) setError(e instanceof Error ? e.message : '기간을 계산하지 못했어요.'); })
        .finally(() => { if (active) setEstimating(false); });
    }, 600);
    return () => { active = false; window.clearTimeout(timer); };
  }, [id, course, result, choices, order, estimates]);
  const total = totalWeeks(order, choices, estimates);
  const activeNames = order.filter(name => choices[name]?.enabled !== false);
  const missingCount = activeNames.filter(name => !choices[name] || currentWeeks(choices[name], estimates[name]) === null).length;
  const knownWeeks = activeNames.reduce((sum, name) => sum + (choices[name] ? currentWeeks(choices[name], estimates[name]) ?? 0 : 0), 0);
  function selectBook(skill: string, resource: string) {
    onChoicesChanged?.();
    setChoices(previous => {
      const current = previous[skill]; if (!current) return previous;
      const exists = current.books.includes(resource);
      if (!exists && current.books.length >= 3) return previous;
      return { ...previous, [skill]: { ...current, books: exists ? current.books.filter(id => id !== resource) : [...current.books, resource] } };
    });
  }
  const content = <>
    {!resourcesOnly && <div className="card preview"><h2>로드맵 세부 사항</h2><dl className="kv"><dt>학습 목표</dt><dd>{draft.goal}</dd>
      {draft.diag?.outcome && <><dt>만들 결과물</dt><dd>{draft.diag.outcome}</dd></>}
    </dl>
      <h3>프로젝트 요약</h3><p className="small" style={{ whiteSpace: 'pre-wrap' }}>{draft.doc?.summary?.trim() || '첨부한 프로젝트 기획서가 없어요.'}</p>
      <h3>입력한 세부 사항</h3><dl className="kv">{D.detailFields.map(([key, label]) => <Fragment key={key}><dt>{label}</dt><dd>{prefText(key as keyof Prefs, draft.prefs)}</dd></Fragment>)}</dl>
    </div>}
    <div className="v2-skill-summary"><h2>{resourcesOnly ? '도서·강좌 선택' : '익히게 될 지식 역량'}</h2>
      <div><b aria-live="polite">총 예상 {total === null ? (knownWeeks ? `${knownWeeks}주 + 미정 ${missingCount}개` : '주차 산정 필요') : `${total}주`}</b>
        {estimating && <span className="small muted" role="status"><span className="sp" aria-hidden="true" /> 주차 계산 중…</span>}</div>
    </div>
    {!resourcesOnly && result?.recommendations && <div className="v2-skill-sort" aria-label="스킬 순서 변경">{displayOrder(order, choices).map(name => {
      const selected = choices[name];
      const excluded = selected?.enabled === false;
      const weeks = selected ? currentWeeks(selected, estimates[name]) : null;
      return <div key={name} className={`v2-sort-item${excluded ? ' v2-skill-excluded' : ''}`}
        draggable={!busy && !saving && !excluded}
        onDragStart={event => { setDragging(name); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', name); }}
        onDragEnd={() => setDragging(null)}
        onDragOver={event => { if (dragging && !excluded && !busy) event.preventDefault(); }}
        onDrop={event => { event.preventDefault(); if (dragging && !busy) setOrder(old => moveSkill(old, dragging, name, choices)); setDragging(null); }}>
        <div className="v2-sort-description"><b>{name}</b>{result.skillDetails?.find(skill => skill.name === name)?.application && <p className="small muted">{result.skillDetails.find(skill => skill.name === name)!.application}</p>}</div><span className="small muted">{excluded ? '미선택' : weeks === null ? '주차 계산 중' : `${weeks}주`}</span>
        <button className="btn line small" disabled={busy || saving} onClick={() => setChoices(old => ({ ...old, [name]: { ...selected, enabled: excluded } }))}>{excluded ? '다시 포함' : '제외'}</button>
      </div>;
    })}</div>}
    {error && <div><p className="err" role="alert">{error}</p>{!result?.recommendations && <button className="btn line" disabled={busy} onClick={() => void generate()}>다시 시도하기</button>}</div>}
    {busy ? resourcesOnly && <div className="loading" role="status"><span className="sp" aria-hidden="true" />자료를 확인하고 추천을 정리하고 있어요.</div>
      : result?.recommendations ? resourcesOnly ? <div className="v2-skills-board">{displayOrder(order, choices).map(name => {
        const skill = result.recommendations!.skills.find(s => s.name === name)!;
        const selected = choices[skill.name] ?? { course: skill.selectedCourse, books: skill.selectedBooks };
        const excluded = selected.enabled === false;
        const weeks = currentWeeks(selected, estimates[skill.name]);
        return <section className={`card v2-skill${excluded ? ' v2-skill-excluded' : ''}`} key={skill.name} data-skill={skill.name}>
          <div className="v2-skill-heading"><h2>{skill.name}</h2><span className="small muted">{excluded ? '미선택' : weeks === null ? '주차 계산 중' : `예상 ${weeks}주`}</span></div>
          <h3>도서 <span className="small muted">최대 3권</span></h3>
          {skill.books.some(resource => course !== 'A1' || resource.cost === 0) ? <div className="v2-resource-grid">{skill.books.filter(resource => course !== 'A1' || resource.cost === 0).map(resource => <ResourceCard key={resource.id} resource={resource} kind="book" checked={selected.books.includes(resource.id)} disabled={locked || busy || excluded || (!selected.books.includes(resource.id) && selected.books.length >= 3)} onChange={() => selectBook(skill.name, resource.id)} />)}</div> : <p className="small muted">프로젝트에 맞는 도서를 찾지 못했어요.</p>}
          <h3>강좌 <span className="small muted">1개 선택</span></h3>
          {skill.courses.some(resource => course !== 'A1' || resource.cost === 0) ? <div className="v2-resource-grid">{skill.courses.filter(resource => course !== 'A1' || resource.cost === 0).map(resource => <ResourceCard key={resource.id} resource={resource} kind="course" checked={selected.course === resource.id} disabled={locked || busy || excluded} onChange={() => { onChoicesChanged?.(); setChoices(old => ({ ...old, [skill.name]: { ...selected, course: resource.id } })); }} />)}</div> : <p className="small muted">프로젝트에 맞는 강좌를 찾지 못했어요.</p>}
        </section>;
      })}</div> : null : resourcesOnly && !error && <div className="loading" role="status"><span className="sp" aria-hidden="true" />추천 자료를 준비하고 있어요.</div>}
    <style>{`
      .v2-skill-summary{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
      .v2-skill-summary>div,.v2-skill-tools{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
      .v2-skills-board{display:grid;gap:16px;margin-top:20px}
      .v2-skills-board>.v2-skill{min-width:0;margin:0;padding:20px}.v2-skill-heading{display:flex;justify-content:space-between;gap:12px}.v2-skill-sort{display:grid;gap:8px;padding:8px 0 14px}.v2-sort-item{min-width:0;border:1px solid var(--line,#ddd);border-radius:12px;padding:12px 16px;display:flex;align-items:center;gap:12px;background:var(--card,#fff)}.v2-sort-description{flex:1;min-width:0;overflow-wrap:anywhere}.v2-sort-description p{margin:4px 0 0}.v2-sort-item[draggable=true]{cursor:grab}.v2-sort-item b{font-size:13px}.v2-sort-item .btn{flex-shrink:0;padding:3px 8px;min-height:0;font-size:11px}
      .v2-skill-heading h2{font-size:17px;margin:0 0 8px;overflow-wrap:anywhere}
      .v2-skill-tools{font-size:12px}.v2-skill-tools .btn{padding:4px 7px;min-height:0;font-size:12px}
      .v2-skill-tools b{width:100%;margin-bottom:4px}.v2-skill h3{font-size:14px;margin:18px 0 8px}
      .v2-skill-excluded{filter:grayscale(1);background:#f0f0f0;opacity:.7}
      .v2-skill-tools button[draggable=true]{cursor:grab}
      .v2-resource-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:8px}
      .v2-resource{cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:16px;border:1px solid var(--line,#ddd);border-radius:10px;padding:9px;background:var(--card,#fff)}
      .v2-resource-image{width:52px;height:64px;object-fit:contain;flex-shrink:0;border-radius:4px}.v2-resource[aria-disabled=true]{cursor:default}.v2-resource:focus-visible{outline:2px solid var(--acc,#138575);outline-offset:2px}.v2-resource-selected{border-color:var(--acc,#138575)}
      .v2-resource-choice{flex:1;min-width:0;display:flex;gap:7px;align-items:flex-start;cursor:pointer;font-size:13px;line-height:1.45}
      .v2-resource-choice input{flex-shrink:0;margin-top:3px}.v2-resource-choice b{overflow-wrap:anywhere}
      .v2-resource .tag{font-size:10px;padding:2px 5px;margin-left:5px;white-space:nowrap}
      .v2-resource-info{flex:1;min-width:0}.v2-resource-meta{display:flex;align-items:center;justify-content:flex-start;flex-wrap:wrap;gap:12px;margin-top:6px;font-size:11px;color:var(--muted,#777)}
      .v2-resource-meta span{min-width:0;overflow-wrap:anywhere}.v2-resource-link{align-self:center;flex-shrink:0;font-size:12px;white-space:nowrap}
      @media(max-width:650px){.v2-resource{gap:10px}.v2-resource-meta{width:100%;justify-content:flex-start}.v2-skills-board>.v2-skill{padding:14px}}
    `}</style>
  </>;
  if (resourcesOnly) return content;
  return <><Stepper cur="result" /><Page title="이런 로드맵이 만들어질 예정이에요" lead="학습할 스킬의 순서와 포함 여부를 정해 주세요. 도서·강좌는 검토·확정에서 선택합니다."
    foot={<><button className="btn line" disabled={busy} onClick={() => go(paths.newQuiz)}>이전: 사전 점검</button>
      <button className="btn pri" disabled={busy || saving || !result?.recommendations} onClick={() => void (async () => { if (await save()) go(paths.newGen); })()}>로드맵 계획하기</button></>}>{content}</Page></>;
}
// 로드맵 3안 생성 연결은 다음 단계에서 기존 호출 계약과 함께 교체한다.
export { genStart, startEdit, ResultEdit } from './legacyResult';
