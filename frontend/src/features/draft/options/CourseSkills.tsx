import { useEffect, useState } from 'react';
import type { DraftResponse, LearningSkillSelection, OptionDef } from '@/api/types/draft';
import { useWs } from '@/shared/state/workspace';
import { flush, takeDraft } from '../draftSync';
import './courseSkills.css';

const initialFlights = new Map<string, Promise<DraftResponse>>();

export function CourseSkills({ option, disabled, onSavingChange }: { option: OptionDef; disabled: boolean; onSavingChange?: (course: string, saving: boolean) => void }) {
  const id = useWs(s => s.draftId);
  const generation = useWs(s => s.draft.v2Assessment?.generationId);
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState<string | null>(null);
  const rows = option.learningSkills || [];
  const selection = option.learningSkillSelection || rows.map(row => ({ name: row.name, enabled: true }));
  const locked = disabled || saving;
  const initialKey = JSON.stringify([id, generation, option.id, option.reason, option.scope, option.acts, attempt]);
  useEffect(() => {
    if (!id || rows.length || disabled) return;
    let active = true;
    onSavingChange?.(option.id, true);
    let work = initialFlights.get(initialKey);
    if (!work) {
      work = fetch(`/api/v2/drafts/${id}/options/${option.id}/skills`, { method: 'POST', credentials: 'same-origin' }).then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(body?.error?.message || '최초 역량 추천을 만들지 못했어요.');
        return body as DraftResponse;
      });
      initialFlights.set(initialKey, work);
      void work.finally(() => { if (initialFlights.get(initialKey) === work) initialFlights.delete(initialKey); }).catch(() => {});
    }
    void work.then(body => { if (active) { takeDraft(body, true); setError(''); } })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : '역량 추천을 만들지 못했어요.'); })
      .finally(() => { if (active) onSavingChange?.(option.id, false); });
    return () => { active = false; onSavingChange?.(option.id, false); };
  }, [id, option.id, rows.length, disabled, initialKey, onSavingChange]);
  async function save(next: LearningSkillSelection[]) {
    if (!id || locked) return;
    setSaving(true); onSavingChange?.(option.id, true); setError('');
    try {
      await flush();
      const response = await fetch(`/api/v2/drafts/${id}/options/${option.id}/skills`, { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: option.learningSkillsKey, selection: next }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || '역량 선택을 저장하지 못했어요.');
      takeDraft(body as DraftResponse, true);
    } catch (e) { setError(e instanceof Error ? e.message : '역량 선택을 저장하지 못했어요.'); }
    finally { setSaving(false); onSavingChange?.(option.id, false); }
  }
  function move(source: string, target: string) {
    if (source === target || locked) return;
    const next = [...selection];
    const from = next.findIndex(row => row.name === source), to = next.findIndex(row => row.name === target);
    if (from < 0 || to < 0) return;
    next.splice(to, 0, next.splice(from, 1)[0]);
    void save(next);
  }
  if (!rows.length) return error ? <div><p role="alert" className="err small">{error}</p><button type="button" className="btn line small" disabled={disabled} onClick={() => { setError(''); setAttempt(n => n + 1); }}>역량 추천 다시 시도</button></div> : <p role="status" className="small muted"><span className="sp" aria-hidden="true" /> 지식·역량을 추천하고 있어요.</p>;
  return <div className="course-skills" onClick={event => event.stopPropagation()}>
    <p className="small muted">드래그로 학습 순서 변경</p>
    {[...selection.filter(item => item.enabled), ...selection.filter(item => !item.enabled)].map((item, index, displayed) => <div key={item.name} className={`course-skill${item.enabled ? '' : ' excluded'}`} draggable={!locked}
      onDragStart={event => { setDragging(item.name); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', item.name); }}
      onDragEnd={() => setDragging(null)} onDragOver={event => { if (dragging && !locked) event.preventDefault(); }}
      onDrop={event => { event.preventDefault(); if (dragging) move(dragging, item.name); setDragging(null); }}>
      <div className="course-skill-copy"><b>⠿ {item.name}</b><p>{rows.find(row => row.name === item.name)?.application}</p></div>
      <div className="course-skill-actions">
        <button type="button" aria-label={`${item.name} 위로`} disabled={locked || index === 0} onClick={() => move(item.name, displayed[index - 1].name)}>↑</button>
        <button type="button" aria-label={`${item.name} 아래로`} disabled={locked || index === displayed.length - 1} onClick={() => move(item.name, displayed[index + 1].name)}>↓</button>
        <button type="button" aria-pressed={item.enabled} disabled={locked || (item.enabled && selection.filter(row => row.enabled).length === 1)} onClick={() => { const next = selection.map(row => row.name === item.name ? { ...row, enabled: !row.enabled } : row); void save([...next.filter(row => row.enabled), ...next.filter(row => !row.enabled)]); }}>{item.enabled ? '제외' : '포함'}</button>
      </div>
    </div>)}
    {saving && <p role="status" className="small muted">역량 선택 저장 중…</p>}
    {error && <p role="alert" className="err small">{error}</p>}
  </div>;
}
