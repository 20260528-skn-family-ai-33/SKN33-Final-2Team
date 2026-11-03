import { useRef } from 'react';
export function MaterialSkillTabs({names,active,onChange,id,panelId}:{names:string[];active:string;onChange:(name:string)=>void;id:string;panelId?:string}) {
  const buttons=useRef<Array<HTMLButtonElement|null>>([]);
  return <div className="material-skill-tabs" role="tablist" aria-label="학습 자료 스킬 선택">{names.map((name,index)=><button key={name} ref={element=>{buttons.current[index]=element;}} type="button" role="tab" id={`${id}-tab-${index}`} aria-controls={panelId || `${id}-panel-${index}`} aria-selected={name===active} tabIndex={name===active?0:-1} onClick={()=>onChange(name)} onKeyDown={event=>{
    let target:number;
    if(event.key==='ArrowRight')target=(index+1)%names.length;
    else if(event.key==='ArrowLeft')target=(index-1+names.length)%names.length;
    else if(event.key==='Home')target=0;
    else if(event.key==='End')target=names.length-1;
    else return;
    event.preventDefault();onChange(names[target]);buttons.current[target]?.focus();
  }}><span>{String(index+1).padStart(2,'0')}</span>{name}</button>)}</div>;
}
