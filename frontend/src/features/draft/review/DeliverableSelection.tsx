import { reviewRequest as request } from './reviewRequest';
import { ReviewSkillBlocks, type ReviewMaterials } from './ReviewSkillBlocks';
import { useEffect, useImperativeHandle, useMemo, useState, type Ref } from 'react';
import type { DraftResponse } from '@/api/types/draft';
import { useWs, ws } from '@/shared/state/workspace';
import { reviewScope } from './reviewScope';
import { reviewTasks } from './reviewTasks';
import { flush, takeDraft } from '../draftSync';
import { reviewPlan, reviewTaskDisplay, type ReviewActivity as Activity, type ReviewProposal as Proposal, type ReviewPlanState } from './reviewPlan';

type ProposalResponse = { proposal: Proposal | null; versions: Proposal[] };
// Clear reusable results and detach pending flights on logout/account change.
useWs.subscribe((state, previous) => { if (state.owner !== previous.owner) reviewTasks.clear(); });
type ReviewBundle = { body: ProposalResponse; resources: ReviewMaterials; summaries?: Record<string, string[]> };
function reviewPath(id: string, route: string, course: string, extra = '') {
  return `/api/v2/drafts/${id}/${route}?course=${encodeURIComponent(course)}${extra}`;
}
async function initializeReview(id: string, course: string, scope: string): Promise<ReviewBundle> {
  // Rejoining a scope while its explicit regeneration runs must await that version.
  await reviewTasks.waitForChanges(scope);
  return reviewTasks.run(scope, 'initial', async () => {
    await flush();
    if (reviewScope(ws()) !== scope) throw new Error('검토 입력이 변경됐어요.');
    const [existing, resources] = await Promise.all([
      request<ProposalResponse>(reviewPath(id, 'activities', course)),
      request<ReviewMaterials>(reviewPath(id, 'recommendations', course)),
    ]);
    let body = existing;
    if (!body.proposal) {
      if (reviewScope(ws()) !== scope) throw new Error('검토 입력이 변경됐어요.');
      body = await request<ProposalResponse>(reviewPath(id, 'activities', course), {method: 'POST'});
    }
    if (!body.proposal) throw new Error('산출물 제안을 확인하지 못했어요. 다시 시도해 주세요.');
    let summaries: Record<string, string[]> | undefined;
    if (!body.proposal.skillSummaries) {
      // Do not start additional model work for a scope the user has left.
      if (reviewScope(ws()) !== scope) throw new Error('검토 입력이 변경됐어요.');
      summaries = (await request<{summaries: Record<string, string[]>}>(reviewPath(id, 'learning-outcomes', course), {method: 'POST'})).summaries;
    }
    return {body, resources, summaries};
  });
}

export type DeliverableSelectionHandle = { save: () => Promise<boolean> };
type SelectionProps = {
  ref?: Ref<DeliverableSelectionHandle>; onReadyChange: (ready: boolean) => void; onBusyChange: (busy: boolean) => void; onPlanChange: (state: ReviewPlanState) => void;
};
export function DeliverableSelection(props: SelectionProps) {
  const scope = useWs(reviewScope);
  return <ScopedDeliverableSelection key={scope} {...props} scope={scope} />;
}
function ScopedDeliverableSelection({ ref, onReadyChange, onBusyChange, onPlanChange, scope }: SelectionProps & { scope: string }) {
  const current = () => reviewScope(ws()) === scope;
  const id = useWs(s => s.draftId);
  const course = useWs(s => s.draft.chosen);
  const handoff = useWs(s => s.draft.handoff);
  const goal = useWs(s => s.draft.goal);
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
  const preview = useMemo(() => {
    if (loading || !proposal || !materials || !handoff) return { value: null, error: '' };
    try { return { value: reviewPlan(proposal, versions, skillPicks, materials, handoff, goal), error: '' }; }
    catch (error) { return { value: null, error: error instanceof Error ? error.message : '검토 계획을 계산하지 못했어요.' }; }
  }, [loading, proposal, versions, skillPicks, materials, handoff, goal]);
  const alternatives: Record<string, { proposalId: string; task: Activity }[]> = {};
  for (const row of versions) for (const task of row.option.acts.filter(act => !act.res)) {
    const items = alternatives[task.skill] ||= [];
    if (!items.some(item => item.task.id === task.id)) items.push({ proposalId: row.id, task });
  }
  useEffect(() => {
    if (!id) return;
    let active = true;
    // Existing materials and proposals are readable before any missing AI work finishes.
    void Promise.all([
      request<ReviewMaterials>(reviewPath(id,'recommendations',course || '')),
      request<ProposalResponse>(reviewPath(id,'activities',course || '')),
    ]).then(([resources,existing])=>{
      if(!active||reviewScope(ws())!==scope)return;
      setMaterials(resources);
      if(existing.proposal){setVersions(existing.versions);setChosen(existing.proposal.id);setSkillPicks(existing.proposal.skillProposalIds||{});}
    }).catch(()=>{});
    void initializeReview(id, course || '', scope).then(({body, resources, summaries}) => {
      if (!active || reviewScope(ws()) !== scope) return;
      const picks = reviewTasks.recall<{versions: Proposal[]; chosen: string; skillPicks: Record<string, string>}>(scope, 'picks');
      const reusable = picks && body.versions.some(row => row.id === picks.chosen);
      setVersions(reusable ? picks.versions : body.versions); setChosen(reusable ? picks.chosen : body.proposal?.id || ''); setSkillPicks(reusable ? picks.skillPicks : body.proposal?.skillProposalIds || {}); setMaterials(resources);
      setSummaries(summaries || null);
    }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, course, dependency, scope, attempt]);
  useEffect(() => {
    if (!loading && !busy && !preview.error && chosen && versions.length && reviewScope(ws()) === scope) {
      reviewTasks.remember(scope, 'picks', {versions, chosen, skillPicks});
    }
  }, [scope, loading, busy, versions, chosen, skillPicks, preview.error]);
  useEffect(() => {
    onPlanChange({ scope, plan: preview.value?.plan || null, error: preview.error || error });
  }, [scope, preview, error, onPlanChange]);
  useEffect(() => onReadyChange(!!proposal?.selectedIds.length && !!preview.value && !loading), [proposal, preview, loading, onReadyChange]);
  useEffect(() => onBusyChange(busy || loading), [busy, loading, onBusyChange]);
  useImperativeHandle(ref, () => ({ save: async () => {
    if (!id || !proposal?.selectedIds.length || !preview.value || busy || loading) return false;
    setBusy(true); setError('');
    try {
      await flush();
      if (!current()) return false;
      const latest = await request<ProposalResponse>(reviewPath(id, 'activities', course || ''));
      if (!current()) return false;
      if (!latest.versions.some(row => row.id === proposal.id && row.key === proposal.key)) {
        reviewTasks.forget(scope); setLoading(true); setAttempt(value => value + 1);
        throw new Error('저장된 제안이 변경되어 최신 결과를 다시 준비합니다.');
      }
      const body = await request<DraftResponse>(`/api/v2/drafts/${id}/activities/selection`, {
        method: 'PUT', body: JSON.stringify({ key: proposal.key, proposalId: proposal.id, selectedIds: proposal.selectedIds, skillProposalIds: skillPicks }),
      });
      if (!current()) return false;
      reviewTasks.forget(scope);
      takeDraft(body);
      return true;
    } catch (e) { setError(e instanceof Error ? e.message : '산출물 선택을 저장하지 못했어요.'); return false; }
    finally { setBusy(false); }
  } }));
  async function propose(skill?: string) {
    if (!id || busy || loading || preview.error || error) return;
    setGeneratingSkill(skill || null);
    setBusy(true); setError('');
    try {
      await flush();
      if (!current()) return;
      reviewTasks.forget(scope);
      const body = await reviewTasks.run(scope, `regenerate:${skill || 'all'}`, async () => {
        const result = await request<ProposalResponse>(reviewPath(id, 'activities', course || '', proposal ? skill ? `&skill=${encodeURIComponent(skill)}` : '&regenerate=true' : ''), {method: 'POST'});
        reviewTasks.forget(scope);
        return result;
      }, true);
      if (!current()) return;
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
    {(error || preview.error) && <div><p className="err" role="alert">{error || preview.error}</p><button type="button" className="btn line small" disabled={busy || loading} onClick={() => { reviewTasks.forget(scope); setLoading(true); setError(''); setAttempt(n => n + 1); }}>다시 불러오기</button></div>}
    {materials && <ReviewSkillBlocks materials={{ ...materials, durationEstimates: preview.value?.plan.def.learningReport?.durationEstimates || materials.durationEstimates, skillDetails: (materials.skillOrder || materials.recommendations?.skills.map(s => s.name) || []).map(name => ({ name, application: '', competencySummary: proposal?.skillSummaries?.[name] || summaries?.[name] || materials.skillDetails?.find(s => s.name === name)?.competencySummary })) }} acts={preview.value?.acts || reviewTaskDisplay(proposal, versions, skillPicks, handoff?.startStage)} alternatives={alternatives} onPick={pick} selectedIds={proposal?.selectedIds || []} busy={busy || loading} proposeDisabled={!!preview.error || !!error} generatingSkill={generatingSkill} onToggle={toggle} onPropose={name => void propose(proposal ? name : undefined)} />}

  </section>;
}
