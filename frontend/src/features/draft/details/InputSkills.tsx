import { useEffect, useState } from 'react';
import type { SelectedSkill } from '@/api/types/draft';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { invalidateDraft } from '../invalidation';
import { useDraftWatch } from '../useDraftWatch';
import { skillInputKey, skillsReady, hasExistingSkillProgress, shouldRecommendSkills } from './skillInput';
import { loadSkills, summaryStage } from './skillRequest';
import { MAX_SKILLS, canIncludeSkill, overSkillLimit, reorderSkills } from './skillOrder';
import { Icon } from '@/shared/ui/Icon';
import { Skeleton } from '@/shared/ui/Skeleton';
import './inputSkills.css';
export function InputSkills(){
  const draft=useWs(s=>s.draft),owner=useWs(s=>s.owner);
  const current=skillInputKey(draft);
  const fallbackScope=useWs(s=>JSON.stringify([s.owner,s.draftId,skillInputKey(s.draft)]));
  const [goalOnlyScope,setGoalOnlyScope]=useState('');
  const goalOnly=goalOnlyScope===fallbackScope;
  const stage=summaryStage(draft,goalOnly);
  const available=draft.skillCandidates||draft.selectedSkills||[];
  const ready=skillsReady(draft);
  const existing=hasExistingSkillProgress(draft);
  const selected=ready?draft.selectedSkills||[]:[];
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
  const [dragging,setDragging]=useState<string|null>(null);
  const [dropTarget,setDropTarget]=useState<string|null>(null);
  useDraftWatch();
  useEffect(()=>{
    if(stage!=='ready'||!owner||!shouldRecommendSkills(ws().draft,attempt>0))return;
    let active=true;
    const timer=setTimeout(()=>{
      setBusy(true);setError('');
      void loadSkills(owner,current).then(rows=>{
        if(!active||ws().owner!==owner||skillInputKey(ws().draft)!==current||!shouldRecommendSkills(ws().draft,attempt>0))return;
        setBusy(false);
        updateWs(s=>{s.draft.skillCandidates=rows;s.draft.selectedSkills=rows;s.draft.skillInputKey=current;invalidateDraft(s);});
      }).catch(e=>{if(active)setError(e instanceof Error?e.message:'스킬을 제안하지 못했어요.');}).finally(()=>{if(active)setBusy(false);});
    },450);
    return()=>{active=false;clearTimeout(timer);};
  },[owner,current,stage,attempt]);
  function save(rows:SelectedSkill[]){updateWs(s=>{s.draft.selectedSkills=rows;s.draft.skillInputKey=current;invalidateDraft(s);});}
  function move(source:string,target:string){if(busy)return;const next=reorderSkills(selected,source,target);if(next!==selected)save(next);}
  const excluded=available.filter(row=>!selected.some(item=>item.name===row.name));
  const canInclude=canIncludeSkill(selected),over=overSkillLimit(selected);
  return <section className="card input-skills" aria-labelledby="inputSkillsTitle">
    <header className="input-skills-header">
      <div><h2 id="inputSkillsTitle">학습할 스킬과 순서</h2><p className="small muted">목표·프로젝트 요약·내 정보를 바탕으로 자동 제안해요.</p></div>
      <button type="button" className="btn line small input-skills-retry" disabled={busy||stage!=='ready'} onClick={()=>setAttempt(value=>value+1)}><Icon name="retry"/>{busy?'제안 중…':'다시 제안받기'}</button>
    </header>
    {((busy&&stage==='ready')||stage==='reading')&&<div className="loading" role="status"><span className="sp" aria-hidden="true"/><span>{stage==='reading'?'프로젝트 요약 생성 중… 완료되면 스킬을 자동으로 제안해요.':'학습할 스킬을 제안하고 있어요…'}</span></div>}
    {((busy&&stage==='ready')||stage==='reading')&&!(ready&&available.length>0)&&<Skeleton kind="rows" count={4}/>}
    {existing&&!ready&&<p className="small muted">기존 초안의 점검·로드맵을 유지하고 있어요. 스킬을 다시 제안받으면 이후 결과가 갱신됩니다.</p>}
    {stage==='missing'&&<div><p role="alert">프로젝트 요약을 확인하지 못했어요. 목표·기획서에서 다시 읽거나, 요약 없이 목표만으로 진행할 수 있어요.</p><button type="button" className="btn line small" disabled={busy} onClick={()=>{setGoalOnlyScope(fallbackScope);setAttempt(value=>value+1);}}>목표만으로 스킬 제안받기</button></div>}
    {goalOnly&&summaryStage(draft)==='missing'&&<p className="small muted">첨부 파일은 유지하며, 기획서 요약 없이 목표와 내 정보를 바탕으로 제안합니다.</p>}
    {ready&&available.length>0&&<>
      <div className="input-skills-meta"><span>선택 <b>{selected.length}</b>개 · 제안 {available.length}개</span><span>카드를 드래그하거나 화살표로 순서를 바꿔 주세요.</span></div>
      <ol className="input-skills-list" aria-label="선택한 스킬과 학습 순서">
        {selected.map((row,index)=><li key={row.name} className={`input-skill-card${dragging===row.name?' is-dragging':''}${dropTarget===row.name&&dragging!==row.name?' is-drop-target':''}`} draggable={!busy}
          onDragStart={event=>{if(busy){event.preventDefault();return;}setDragging(row.name);event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',row.name);}}
          onDragOver={event=>{if(dragging&&!busy){event.preventDefault();event.dataTransfer.dropEffect='move';setDropTarget(row.name);}}}
          onDragEnd={()=>{setDragging(null);setDropTarget(null);}}
          onDrop={event=>{event.preventDefault();if(dragging&&!busy)move(dragging,row.name);setDragging(null);setDropTarget(null);}}>
          <span className="input-skill-grip" aria-hidden="true">⠿</span><span className="input-skill-number" aria-hidden="true">{index+1}</span>
          <div className="input-skill-copy"><div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><h3>{row.name}</h3>{row.learned && <span className="tag acc" style={{ fontSize: '0.75rem', padding: '2px 6px' }}>보유 기술</span>}</div><p>{row.application}</p>{row.reason&&<details className="input-skill-reason"><summary>선정 이유</summary><p>{row.reason}</p></details>}</div>
          <div className="input-skill-actions" role="group" aria-label={`${row.name} 순서와 포함 여부`}>
            <div className="input-skill-arrows"><button type="button" disabled={busy||index===0} aria-label={`${row.name} 위로`} onClick={()=>move(row.name,selected[index-1].name)}>↑</button><button type="button" disabled={busy||index===selected.length-1} aria-label={`${row.name} 아래로`} onClick={()=>move(row.name,selected[index+1].name)}>↓</button></div>
            <button type="button" className="input-skill-exclude" aria-label={`${row.name} 제외`} disabled={busy||selected.length===1} onClick={()=>save(selected.filter(item=>item.name!==row.name))}>제외</button>
          </div>
        </li>)}
      </ol>
      {excluded.length>0&&<div className="input-skills-excluded"><span>제외한 스킬</span><div>{excluded.map(row=><button type="button" className="btn line small" key={row.name} disabled={busy||!canInclude} title={canInclude?undefined:`스킬은 최대 ${MAX_SKILLS}개까지 고를 수 있어요`} onClick={()=>save([...selected,row])}><Icon name="plus"/>{row.name} 포함</button>)}</div></div>}
      {over>0&&<p className="err small" role="alert">스킬은 최대 {MAX_SKILLS}개까지 고를 수 있어요. {over}개를 제외해 주세요.</p>}
      <p className="input-skills-count-note">목표에 필요한 핵심 스킬을 최대 {MAX_SKILLS}개 제안하며, 개수를 채우기 위해 무관한 스킬을 추가하지 않아요.</p>
    </>}
    {error&&stage==='ready'&&<p className="err small" role="alert">{error}</p>}
  </section>;
}
