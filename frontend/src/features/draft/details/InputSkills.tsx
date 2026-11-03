import { useEffect, useState } from 'react';
import type { SelectedSkill } from '@/api/types/draft';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { invalidateDraft } from '../invalidation';
import { useDraftWatch } from '../useDraftWatch';
import { skillInputKey, skillsReady } from './skillInput';
import { loadSkills, summaryStage } from './skillRequest';
import { reorderSkills } from './skillOrder';
import { Icon } from '@/shared/ui/Icon';
import './inputSkills.css';
export function InputSkills(){
  const draft=useWs(s=>s.draft),owner=useWs(s=>s.owner);
  const current=skillInputKey(draft),stage=summaryStage(draft);
  const available=draft.skillCandidates||draft.selectedSkills||[],key=draft.skillInputKey||'';
  const selected=key===current?draft.selectedSkills||[]:[];
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
  const [dragging,setDragging]=useState<string|null>(null);
  const [dropTarget,setDropTarget]=useState<string|null>(null);
  useDraftWatch();
  useEffect(()=>{
    if(stage!=='ready'||!owner || (attempt===0 && skillsReady(ws().draft)))return;
    let active=true;
    const timer=setTimeout(()=>{
      setBusy(true);setError('');
      void loadSkills(owner,current).then(rows=>{
        if(!active||ws().owner!==owner||skillInputKey(ws().draft)!==current)return;
        setBusy(false);
        updateWs(s=>{s.draft.skillCandidates=rows;s.draft.selectedSkills=rows;s.draft.skillInputKey=current;invalidateDraft(s);});
      }).catch(e=>{if(active)setError(e instanceof Error?e.message:'스킬을 제안하지 못했어요.');}).finally(()=>{if(active)setBusy(false);});
    },450);
    return()=>{active=false;clearTimeout(timer);};
  },[owner,current,stage,attempt]);
  function save(rows:SelectedSkill[]){updateWs(s=>{s.draft.selectedSkills=rows;s.draft.skillInputKey=current;invalidateDraft(s);});}
  function move(source:string,target:string){if(busy)return;const next=reorderSkills(selected,source,target);if(next!==selected)save(next);}
  const excluded=available.filter(row=>!selected.some(item=>item.name===row.name));
  return <section className="card input-skills" aria-labelledby="inputSkillsTitle">
    <header className="input-skills-header">
      <div><h2 id="inputSkillsTitle">학습할 스킬과 순서</h2><p className="small muted">목표·프로젝트 요약·내 정보를 바탕으로 자동 제안해요.</p></div>
      <button type="button" className="btn line small input-skills-retry" disabled={busy||stage!=='ready'} onClick={()=>setAttempt(value=>value+1)}><Icon name="retry"/>{busy?'제안 중…':'다시 제안받기'}</button>
    </header>
    {((busy&&stage==='ready')||stage==='reading')&&<div className="loading" role="status"><span className="sp" aria-hidden="true"/><span>{stage==='reading'?'프로젝트 요약 생성 중… 완료되면 스킬을 자동으로 제안해요.':'학습할 스킬을 제안하고 있어요…'}</span></div>}
    {stage==='missing'&&<p role="alert">프로젝트 요약이 준비되지 않았어요. 목표·기획서 화면에서 요약 상태를 확인해 주세요.</p>}
    {key===current&&available.length>0&&<>
      <div className="input-skills-meta"><span>선택 <b>{selected.length}</b>개 · 제안 {available.length}개</span><span>카드를 드래그하거나 화살표로 순서를 바꿔 주세요.</span></div>
      <ol className="input-skills-list" aria-label="선택한 스킬과 학습 순서">
        {selected.map((row,index)=><li key={row.name} className={`input-skill-card${dragging===row.name?' is-dragging':''}${dropTarget===row.name&&dragging!==row.name?' is-drop-target':''}`} draggable={!busy}
          onDragStart={event=>{if(busy){event.preventDefault();return;}setDragging(row.name);event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',row.name);}}
          onDragOver={event=>{if(dragging&&!busy){event.preventDefault();event.dataTransfer.dropEffect='move';setDropTarget(row.name);}}}
          onDragEnd={()=>{setDragging(null);setDropTarget(null);}}
          onDrop={event=>{event.preventDefault();if(dragging&&!busy)move(dragging,row.name);setDragging(null);setDropTarget(null);}}>
          <span className="input-skill-grip" aria-hidden="true">⠿</span><span className="input-skill-number" aria-hidden="true">{index+1}</span>
          <div className="input-skill-copy"><h3>{row.name}</h3><p>{row.application}</p>{row.reason&&<details className="input-skill-reason"><summary>선정 이유</summary><p>{row.reason}</p></details>}</div>
          <div className="input-skill-actions" role="group" aria-label={`${row.name} 순서와 포함 여부`}>
            <div className="input-skill-arrows"><button type="button" disabled={busy||index===0} aria-label={`${row.name} 위로`} onClick={()=>move(row.name,selected[index-1].name)}>↑</button><button type="button" disabled={busy||index===selected.length-1} aria-label={`${row.name} 아래로`} onClick={()=>move(row.name,selected[index+1].name)}>↓</button></div>
            <button type="button" className="input-skill-exclude" aria-label={`${row.name} 제외`} disabled={busy||selected.length===1} onClick={()=>save(selected.filter(item=>item.name!==row.name))}>제외</button>
          </div>
        </li>)}
      </ol>
      {excluded.length>0&&<div className="input-skills-excluded"><span>제외한 스킬</span><div>{excluded.map(row=><button type="button" className="btn line small" key={row.name} disabled={busy} onClick={()=>save([...selected,row])}><Icon name="plus"/>{row.name} 포함</button>)}</div></div>}
      <p className="input-skills-count-note">목표에 필요한 핵심 스킬을 최대 5개 제안하며, 개수를 채우기 위해 무관한 스킬을 추가하지 않아요.</p>
    </>}
    {error&&stage==='ready'&&<p className="err small" role="alert">{error}</p>}
  </section>;
}
