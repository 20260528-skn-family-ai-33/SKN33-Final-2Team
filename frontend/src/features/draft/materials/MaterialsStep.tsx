import { useEffect, useRef, useState } from 'react';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { useWs } from '@/shared/state/workspace';
import { Page } from '@/shared/ui/parts';
import { Stepper } from '../Stepper';
import { ResourceSelection, type ResourceSelectionHandle } from '../result/ResultStep';
import { takeDraft } from '../draftSync';
import type { DraftResponse } from '@/api/types/draft';

type Act = { id: string; title: string; skill: string; how: string; hours: number };
type Proposal = { key: string; option: { acts: Act[] }; selectedIds: string[] };
async function call(path: string, init?: RequestInit) {
 const response=await fetch(path,{...init,credentials:'same-origin',headers:{'Content-Type':'application/json'}});
 const body=await response.json();if(!response.ok)throw new Error(body?.error?.message || '활동을 처리하지 못했어요.');return body;
}
export function MaterialsStep(){
 const id=useWs(s=>s.draftId), go=useGo();
 const editor=useRef<ResourceSelectionHandle>(null);
 const [proposal,setProposal]=useState<Proposal|null>(null),[selected,setSelected]=useState<string[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{if(!id)return;let active=true;void call(`/api/v2/drafts/${id}/activities`).then(body=>{if(active){setProposal(body.proposal);setSelected(body.proposal?.selectedIds || []);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[id]);
 async function propose(){
  if(!id||busy)return;setBusy(true);setError('');
  try{if(!await editor.current?.save())return;const body=await call(`/api/v2/drafts/${id}/activities`,{method:'POST'});setProposal(body.proposal);setSelected(body.proposal.selectedIds);}
  catch(e){setError(e instanceof Error?e.message:'활동을 제안하지 못했어요.');}finally{setBusy(false);}
 }
 async function next(){
  if(!id||!proposal||busy)return;setBusy(true);setError('');
  try{const body=await call(`/api/v2/drafts/${id}/activities/selection`,{method:'PUT',body:JSON.stringify({key:proposal.key,selectedIds:selected})});takeDraft(body as DraftResponse);go(paths.newReview);}
  catch(e){setError(e instanceof Error?e.message:'선택을 저장하지 못했어요.');}finally{setBusy(false);}
 }
 return <><Stepper cur="materials"/><Page title="자료와 활동을 골라 주세요" lead="도서·강좌를 고른 뒤 활동을 제안받으세요. 활동은 모두 선택되며 필요 없는 활동만 제외할 수 있어요."
 foot={<><button className="btn line" disabled={busy} onClick={()=>go(paths.newOptions)}>이전: 로드맵 선택</button><button className="btn pri" disabled={busy||!proposal||!selected.length} onClick={()=>void next()}>다음: 검토·확정</button></>}>
 <ResourceSelection ref={editor} locked={busy} onChoicesChanged={()=>{setProposal(null);setSelected([]);}}/>
 <div className="sec"><button className="btn pri" disabled={busy} onClick={()=>void propose()}>{busy?<><span className="sp" aria-hidden="true" /> 활동을 제안 중</>:'선택 자료로 활동 제안받기'}</button></div>
 {error&&<p className="err" role="alert">{error}</p>}
 {proposal&&<div className="sec"><h2>제안된 활동</h2><div className="stack">{proposal.option.acts.map(act=><label className="card" key={act.id} style={{display:'flex',gap:12,alignItems:'flex-start',cursor:'pointer'}}><input type="checkbox" checked={selected.includes(act.id)} disabled={busy} onChange={()=>setSelected(old=>old.includes(act.id)?old.filter(x=>x!==act.id):[...old,act.id])}/><span><span className="small muted">{act.skill} · 예상 {act.hours}시간</span><br/><b>{act.title}</b><p className="small muted">{act.how}</p></span></label>)}</div></div>}
 </Page></>;
}
