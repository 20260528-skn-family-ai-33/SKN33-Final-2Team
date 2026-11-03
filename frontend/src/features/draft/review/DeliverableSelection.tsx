import { reviewRequest as request } from './reviewRequest';
import { ReviewSkillBlocks, type ReviewMaterials } from './ReviewSkillBlocks';
import { useEffect, useImperativeHandle, useState, type Ref } from 'react';
import type { DraftResponse } from '@/api/types/draft';
import { useWs } from '@/shared/state/workspace';
import { flush, takeDraft } from '../draftSync';

type Activity = { res?: string | null; id: string; title: string; skill: string; how: string; hours: number };
type Proposal = { id: string; key: string; skillProposalIds?: Record<string, string>; skillSummaries?: Record<string, string[]>; option: { acts: Activity[] }; selectedIds: string[] };
type ProposalResponse = { proposal: Proposal | null; versions: Proposal[] };
const initialFlights = new Map<string, Promise<ProposalResponse>>();

function initializeProposal(id: string, course: string, dependency: string) {
  const key = `${id}:${course}:${dependency}`;
  const pending = initialFlights.get(key);
  if (pending) return pending;
  const work = flush().then(() => request<ProposalResponse>(`/api/v2/drafts/${id}/activities`)).then(body => body.proposal ? body : request<ProposalResponse>(`/api/v2/drafts/${id}/activities`, { method: 'POST' }));
  initialFlights.set(key, work);
  void work.finally(() => { if (initialFlights.get(key) === work) initialFlights.delete(key); }).catch(() => {});
  return work;
}

export type DeliverableSelectionHandle = { save: () => Promise<boolean> };
export function DeliverableSelection({ ref, onReadyChange, onBusyChange, onDurationChange }: {
  ref?: Ref<DeliverableSelectionHandle>; onReadyChange: (ready: boolean) => void; onBusyChange: (busy: boolean) => void; onDurationChange: (weeks: number | null) => void;
}) {
  const id = useWs(s => s.draftId);
  const course = useWs(s => s.draft.chosen);
  const dependency = useWs(s => JSON.stringify([s.draft.v2Assessment?.generationId, s.draft.v2Assessment?.materialsKey]));
  const [attempt, setAttempt] = useState(0);
  const [materials, setMaterials] = useState<ReviewMaterials | null>(null);
  const [summaries, setSummaries] = useState<Record<string, string[]> | null>(null);
  const [versions, setVersions] = useState<Proposal[]>([]);
  const [chosen, setChosen] = useState('');
  const [skillPicks, setSkillPicks] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [generatingSkill, setGeneratingSkill] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const proposal = versions.find(row => row.id === chosen) || null;
  const alternatives: Record<string, { proposalId: string; task: Activity }[]> = {};
  for (const row of versions) for (const task of row.option.acts.filter(act => !act.res)) {
    const items = alternatives[task.skill] ||= [];
    if (!items.some(item => item.task.id === task.id)) items.push({ proposalId: row.id, task });
  }
  useEffect(() => {
    if (!id) return;
    let active = true;
    void Promise.all([initializeProposal(id, course || '', dependency), request<ReviewMaterials>(`/api/v2/drafts/${id}/recommendations?course=${encodeURIComponent(course || '')}`).then(resources => { if (active) setMaterials(resources); return resources; })]).then(async ([body, resources]) => {
      if (!active) return;
      setVersions(body.versions); setChosen(body.proposal?.id || ''); setSkillPicks(body.proposal?.skillProposalIds || {}); setMaterials(resources);
      if (!body.proposal?.skillSummaries) {
        const result = await request<{ summaries: Record<string, string[]> }>(`/api/v2/drafts/${id}/learning-outcomes`, { method: 'POST' });
        if (active) setSummaries(result.summaries);
      }
    }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, course, dependency, attempt]);
  useEffect(() => {
    if (!materials) { onDurationChange(null); return; }
    const names = (materials.skillOrder || materials.recommendations?.skills.map(skill => skill.name) || []).filter(name => materials.choices[name]?.enabled !== false);
    const values = names.map(name => materials.durationEstimates?.[name]?.weeks);
    onDurationChange(values.length && values.every(value => typeof value === 'number') ? values.reduce<number>((sum, value) => sum + (value || 0), 0) : null);
  }, [materials, onDurationChange]);
  useEffect(() => onReadyChange(!!proposal?.selectedIds.length && !loading), [proposal, loading, onReadyChange]);
  useEffect(() => onBusyChange(busy || loading), [busy, loading, onBusyChange]);
  useImperativeHandle(ref, () => ({ save: async () => {
    if (!id || !proposal?.selectedIds.length || busy || loading) return false;
    setBusy(true); setError('');
    try {
      await flush();
      const body = await request<DraftResponse>(`/api/v2/drafts/${id}/activities/selection`, {
        method: 'PUT', body: JSON.stringify({ key: proposal.key, proposalId: proposal.id, selectedIds: proposal.selectedIds, skillProposalIds: skillPicks }),
      });
      takeDraft(body);
      return true;
    } catch (e) { setError(e instanceof Error ? e.message : '산출물 선택을 저장하지 못했어요.'); return false; }
    finally { setBusy(false); }
  } }));
  async function propose(skill?: string) {
    if (!id || busy || loading) return;
    setGeneratingSkill(skill || null);
    setBusy(true); setError('');
    try {
      await flush();
      const body = await request<ProposalResponse>(`/api/v2/drafts/${id}/activities${proposal ? skill ? `?skill=${encodeURIComponent(skill)}` : '?regenerate=true' : ''}`, { method: 'POST' });
      if (!body.proposal) throw new Error('제안 결과가 없어요. 기존 제안은 유지됩니다.');
      const original = proposal?.option.acts.find(act => !act.res && act.skill === skill);
      const replacement = body.proposal.option.acts.find(act => !act.res && act.skill === skill);
      const replaceSelected = !!(skill && original && replacement && skillPicks[skill] && skillPicks[skill] !== chosen && versions.some(row => row.option.acts.some(act => !act.res && act.skill === skill && proposal?.selectedIds.includes(act.id))));
      const oldTaskIds = new Set(versions.flatMap(row => row.option.acts.filter(act => !act.res && act.skill === skill).map(act => act.id)));
      setVersions(old => body.versions.map(row => {
        const saved = old.find(item => item.id === row.id);
        return saved && row.id === chosen && replaceSelected && replacement ? { ...saved, selectedIds: [...saved.selectedIds.filter(id => !oldTaskIds.has(id)), replacement.id] } : saved || row;
      }));
      if (replaceSelected && skill) setSkillPicks(old => ({ ...old, [skill]: body.proposal!.id }));
      if (!proposal) setChosen(body.proposal.id);
    } catch (e) { setError(e instanceof Error ? e.message : '산출물을 제안하지 못했어요. 기존 제안은 유지됩니다.'); }
    finally { setBusy(false); setGeneratingSkill(null); }
  }
  function pick(skill: string, proposalId: string) {
    const task = versions.find(row => row.id === proposalId)?.option.acts.find(act => !act.res && act.skill === skill);
    if (!task) return;
    const taskIds = new Set(versions.flatMap(row => row.option.acts.filter(act => !act.res && act.skill === skill).map(act => act.id)));
    setSkillPicks(old => ({ ...old, [skill]: proposalId }));
    setVersions(old => old.map(row => row.id === chosen ? { ...row, selectedIds: [...row.selectedIds.filter(id => !taskIds.has(id)), task.id] } : row));
  }
  function toggle(actId: string) {
    const task = proposal?.option.acts.find(act => act.id === actId && !act.res);
    if (task && !proposal?.selectedIds.includes(actId)) { pick(task.skill, chosen); return; }
    setVersions(old => old.map(row => row.id === chosen ? { ...row, selectedIds: row.selectedIds.includes(actId) ? row.selectedIds.filter(value => value !== actId) : [...row.selectedIds, actId] } : row));
  }
  return <section className="sec" aria-label="산출물 제안">
    <h2>산출물 제안</h2>
    <p className="small muted">선택한 강좌·도서를 바탕으로 스킬별 산출물을 제안받아요. 기본으로 모두 선택되며 필요 없는 항목만 제외할 수 있어요.</p>
    {(loading || busy) && <p className="review-generation-status" role="status"><span className="review-proposal-spinner" aria-hidden="true" />{loading ? '최종 검토 결과 생성 중… 선택한 자료를 바탕으로 역량과 산출물을 준비하고 있어요.' : '해당 스킬의 과제를 다시 제안하고 있어요.'}</p>}
    {error && <div><p className="err" role="alert">{error}</p><button type="button" className="btn line small" disabled={busy || loading} onClick={() => { setLoading(true); setError(''); setAttempt(n => n + 1); }}>다시 불러오기</button></div>}
    {materials && <ReviewSkillBlocks materials={{ ...materials, skillDetails: (materials.skillOrder || materials.recommendations?.skills.map(s => s.name) || []).map(name => ({ name, application: '', competencySummary: proposal?.skillSummaries?.[name] || summaries?.[name] || materials.skillDetails?.find(s => s.name === name)?.competencySummary })) }} acts={proposal?.option.acts || []} alternatives={alternatives} onPick={pick} selectedIds={proposal?.selectedIds || []} busy={busy || loading} generatingSkill={generatingSkill} onToggle={toggle} onPropose={name => void propose(proposal ? name : undefined)} />}

  </section>;
}
