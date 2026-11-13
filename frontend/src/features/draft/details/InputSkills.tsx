import { useQuery } from '@tanstack/react-query';
import { catalogApi } from '@/api/endpoints/catalog';
import { useMe } from '@/shared/state/session';
import { useCatalog } from '@/shared/state/catalog';
import { earnedSkills } from '@/features/skillmap/earned';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
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
  const plans = useWs(s => s.plans), reports = useWs(s => s.reports);
  const profile = useMe();
  const owned = new Set((profile?.tech || []).map(name => name.trim().toLowerCase()));
  const resources = useCatalog(s => s.res);
  const { data: skillMap } = useQuery({ queryKey: ['skills-map'], queryFn: catalogApi.skillMap, staleTime: Infinity });
  const completed = useMemo(() => {
    if (!skillMap) return new Map<string, number>();
    const { marks } = earnedSkills(skillMap, Object.values(plans), reports, resources);
    return new Map(skillMap.skills.map(skill => [
      skill.name, new Set(marks.get(skill.id)?.plans.filter(plan => plan.finished).map(plan => plan.id)).size,
    ]));
  }, [skillMap, plans, reports, resources]);
  const poolKey = JSON.stringify([current, profile?.tech, profile?.certs, profile?.profile, profile?.projects, profile?.learning]);
  const fixed = selected.filter(row => draft.fixedSkillNames?.includes(row.name));
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
  const [dragging,setDragging]=useState<string|null>(null);
  const [dropTarget,setDropTarget]=useState<string|null>(null);
  const list = useRef<HTMLOListElement>(null);
  const [loadingHeights, setLoadingHeights] = useState(new Map<string, number>());
  const positions = useRef(new Map<string, number>());
  useLayoutEffect(()=>{
    const previous=positions.current;
    positions.current=new Map();
    for(const card of list.current?.querySelectorAll<HTMLElement>('[data-skill]')||[]){
      const top=previous.get(card.dataset.skill||'');
      if(top===undefined)continue;
      const delta=top-card.getBoundingClientRect().top;
      if(delta)card.animate([{transform:'translateY('+delta+'px)'},{transform:'translateY(0)'}],{duration:180,easing:'ease-out'});
    }
  },[selected]);
  useDraftWatch();
  useEffect(()=>{
    if(stage!=='ready'||!owner||!shouldRecommendSkills(ws().draft,attempt>0))return;
    let active=true;
    const timer=setTimeout(()=>{
      setLoadingHeights(new Map(Array.from(list.current?.querySelectorAll<HTMLElement>('[data-skill]') ?? [], card => [card.dataset.skill!, card.getBoundingClientRect().height])));
      setBusy(true);setError('');
      const before = ws().draft;
      const old = skillsReady(before) ? before.selectedSkills || [] : [];
      const locked = old.filter(row => before.fixedSkillNames?.includes(row.name)).map(row => row.name);
      if (locked.length >= MAX_SKILLS) { setBusy(false); return; }
      const blocked = skillsReady(before) ? (before.skillCandidates || []).filter(row => !old.some(item => item.name === row.name)) : [];
      const cached = before.skillPool?.key === poolKey ? before.skillPool : undefined;
      const blockedNames = blocked.map(row => row.name);
      const unseen = (cached?.rows || []).filter(row => !locked.includes(row.name) &&
        !blockedNames.includes(row.name) && !cached?.shown.includes(row.name));
      const slots = MAX_SKILLS - locked.length;
      const previous = attempt > 0 ? old.filter(row => !locked.includes(row.name)).map(row => row.name) : [];
      const request = unseen.length >= slots ? Promise.resolve([]) : loadSkills(owner,current,locked,blockedNames,previous);
      void request.then(rows=>{
        if(!active||ws().owner!==owner||skillInputKey(ws().draft)!==current||!shouldRecommendSkills(ws().draft,attempt>0))return;
        setBusy(false);
        const eligible = [...new Map([...rows, ...(cached?.rows || []), ...old].filter(row => !locked.includes(row.name) &&
          !blockedNames.includes(row.name)).map(row => [row.name, row])).values()];
        const fresh = attempt > 0
          ? eligible.map((row, rank) => ({ row, draw: -Math.log(1 - Math.random()) * (rank + 1) }))
              .sort((a, b) => a.draw - b.draw).slice(0, slots).map(({ row }) => row)
          : eligible.slice(0, slots);
        const merged = old.flatMap(row => locked.includes(row.name) ? [row] : fresh.splice(0, 1)).concat(fresh);
        updateWs(s=>{
          s.draft.skillCandidates=[...merged,...blocked];s.draft.selectedSkills=merged;s.draft.skillInputKey=current;
          s.draft.fixedSkillNames=locked;
          const candidates = [...new Map([...unseen, ...rows, ...(cached?.rows || [])].map(row => [row.name, row])).values()];
          const shown = new Set([...(cached?.shown || []), ...old.map(row => row.name), ...merged.map(row => row.name)]);
          candidates.sort((a,b) => Number(shown.has(a.name)) - Number(shown.has(b.name)));
          s.draft.skillPool = { key: poolKey, rows: candidates.slice(0, 8), shown: [...shown] };
          if (JSON.stringify(old) !== JSON.stringify(merged)) invalidateDraft(s);
        });
      }).catch(e=>{if(active)setError(e instanceof Error?e.message:'스킬을 제안하지 못했어요.');}).finally(()=>{if(active)setBusy(false);});
    },450);
    return()=>{active=false;clearTimeout(timer);};
  },[owner,current,stage,attempt,poolKey]);
  function save(rows:SelectedSkill[]){updateWs(s=>{s.draft.selectedSkills=rows;s.draft.fixedSkillNames=s.draft.fixedSkillNames?.filter(name=>rows.some(row=>row.name===name));s.draft.skillInputKey=current;invalidateDraft(s);});}
  function move(source:string,target:string){if(busy)return;const next=reorderSkills(selected,source,target);if(next!==selected){if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches){for(const card of list.current?.querySelectorAll<HTMLElement>('[data-skill]')||[])positions.current.set(card.dataset.skill||'',card.getBoundingClientRect().top);}save(next);}}
  const excluded=available.filter(row=>!selected.some(item=>item.name===row.name));
  const canInclude=canIncludeSkill(selected),over=overSkillLimit(selected);
  return <section className="card input-skills" aria-labelledby="inputSkillsTitle">
    <header className="input-skills-header">
      <div><h2 id="inputSkillsTitle">학습할 스킬과 순서</h2><p className="small muted">목표·프로젝트 요약·내 정보를 바탕으로 자동 제안해요.</p></div>
      <button type="button" className="btn line small input-skills-retry" disabled={busy||stage!=='ready'||fixed.length>=MAX_SKILLS} onClick={()=>setAttempt(value=>value+1)}>{busy?<span className="sp input-skills-spinner" aria-hidden="true"/>:<Icon name="retry"/>}<span role="status">{busy?'제안 중…':'다시 제안받기'}</span></button>
    </header>
    {stage==='reading'&&<div className="loading" role="status"><span className="sp" aria-hidden="true"/><span>프로젝트 요약 생성 중… 완료되면 스킬을 자동으로 제안해요.</span></div>}
    {((busy&&stage==='ready')||stage==='reading')&&!(ready&&available.length>0)&&<ol className="input-skills-list input-skills-initial" aria-hidden="true">{Array.from({ length: MAX_SKILLS }, (_, index) => <li className="input-skill-placeholder" key={index}><Skeleton kind="rows" count={1}/></li>)}</ol>}
    {existing&&!ready&&<p className="small muted">기존 초안의 점검·로드맵을 유지하고 있어요. 스킬을 다시 제안받으면 이후 결과가 갱신됩니다.</p>}
    {stage==='missing'&&<div><p role="alert">프로젝트 요약을 확인하지 못했어요. 목표·기획서에서 다시 읽거나, 요약 없이 목표만으로 진행할 수 있어요.</p><button type="button" className="btn line small" disabled={busy} onClick={()=>{setGoalOnlyScope(fallbackScope);setAttempt(value=>value+1);}}>목표만으로 스킬 제안받기</button></div>}
    {goalOnly&&summaryStage(draft)==='missing'&&<p className="small muted">첨부 파일은 유지하며, 기획서 요약 없이 목표와 내 정보를 바탕으로 제안합니다.</p>}
    {ready&&available.length>0&&<>
      <div className="input-skills-meta"><span>선택 <b>{selected.length}</b>개 · 제안 {available.length-excluded.length}개</span><span>카드를 드래그하거나 화살표로 순서를 바꿔 주세요.</span></div>
      <ol ref={list} className="input-skills-list" aria-label="선택한 스킬과 학습 순서">
        {selected.map((row,index)=>busy && !draft.fixedSkillNames?.includes(row.name) ? <li key={row.name} className="input-skill-placeholder" style={{ minHeight: loadingHeights.get(row.name) }}><Skeleton kind="rows" count={1}/></li> : <li key={row.name} data-skill={row.name} className={`input-skill-card${dragging===row.name?' is-dragging':''}${dropTarget===row.name&&dragging!==row.name?' is-drop-target':''}`} draggable={!busy}
          onDragStart={event=>{if(busy){event.preventDefault();return;}setDragging(row.name);event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',row.name);}}
          onDragOver={event=>{if(dragging&&!busy){event.preventDefault();event.dataTransfer.dropEffect='move';setDropTarget(row.name);}}}
          onDragEnd={()=>{setDragging(null);setDropTarget(null);}}
          onDrop={event=>{event.preventDefault();if(dragging&&!busy)move(dragging,row.name);setDragging(null);setDropTarget(null);}}>
          <span className="input-skill-grip" aria-hidden="true">⠿</span><span className="input-skill-number" aria-hidden="true">{index+1}</span>
          <div className="input-skill-copy"><div className="input-skill-actions input-skill-arrows"><button type="button" disabled={busy||index===0} aria-label={`${row.name} 위로`} onClick={()=>move(row.name,selected[index-1].name)}>↑</button><button type="button" disabled={busy||index===selected.length-1} aria-label={`${row.name} 아래로`} onClick={()=>move(row.name,selected[index+1].name)}>↓</button></div><div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><h3>{row.name}</h3>{(completed.get(row.name)||0)>0&&<span className="tag line">학습 완료 {completed.get(row.name)}회</span>}{(row.learned || owned.has(row.name.trim().toLowerCase())) && <span className="tag acc" style={{ fontSize: '0.75rem', padding: '2px 6px' }}>보유 스킬</span>}</div><p>{row.application}</p><div className="input-skill-footer">{row.reason&&<details className="input-skill-reason"><summary>선정 이유</summary><p>{row.reason}</p></details>}<div className="input-skill-actions input-skill-buttons">
            <button type="button" className="input-skill-exclude" aria-pressed={fixed.some(item=>item.name===row.name)}
              disabled={busy} onClick={()=>updateWs(s=>{
                const names=s.draft.fixedSkillNames||[];
                s.draft.fixedSkillNames=names.includes(row.name)?names.filter(name=>name!==row.name):[...names,row.name];
              })}>고정</button>
            <button type="button" className="input-skill-exclude" aria-label={`${row.name} 제외`} disabled={busy||selected.length===1} onClick={()=>save(selected.filter(item=>item.name!==row.name))}>제외</button>
          </div></div></div>
        </li>)}
      </ol>
      {excluded.length>0&&<div className="input-skills-excluded"><span>제외한 스킬</span><div>{excluded.map(row=><button type="button" className="btn line small" key={row.name} disabled={busy||!canInclude} title={canInclude?undefined:`스킬은 최대 ${MAX_SKILLS}개까지 고를 수 있어요`} onClick={()=>save([...selected,row])}><Icon name="plus"/>{row.name} 포함</button>)}</div></div>}
      {over>0&&<p className="err small" role="alert">스킬은 최대 {MAX_SKILLS}개까지 고를 수 있어요. {over}개를 제외해 주세요.</p>}
      <p className="input-skills-count-note">목표에 맞는 스킬을 최대 {MAX_SKILLS}개 제안해요. 적합한 스킬이 적으면 1~2개만 제안할 수 있어요.</p>
    </>}
    {error&&stage==='ready'&&<p className="err small" role="alert">{error}</p>}
  </section>;
}
