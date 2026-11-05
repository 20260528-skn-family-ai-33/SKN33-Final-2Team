export type MaterialStatus='ready'|'pending'|'failed';
export type MaterialPreparation={scope:string;revealed:boolean;courses:Record<string,{version:string;status:MaterialStatus}>};
export type PreparationAction={type:'reset';scope:string}|{type:'report';scope:string;course:string;version:string;status:MaterialStatus;versions:Record<string,string>;regenerating:string[];unavailable?:string[]};
export const initialMaterialPreparation:MaterialPreparation={scope:'',revealed:false,courses:{}};
/** Missing/failed roadmap columns must not block usable materials in other columns. */
export function canRevealMaterials(courses:MaterialPreparation['courses'],versions:Record<string,string>,unavailable:string[],generating:string[]):boolean {
 const ready=(course:string)=>!!versions[course]&&courses[course]?.version===versions[course]&&courses[course]?.status==='ready';
 const settled=['A1','A2','A3'].every(course=>{
  if(generating.includes(course))return !!versions[course];
  if(!versions[course])return unavailable.includes(course);
  return courses[course]?.version===versions[course]&&['ready','failed'].includes(courses[course]?.status);
 });
 return settled&&Object.keys(versions).some(ready);
}
/** Once revealed, a comparison stays visible while a single course is replaced. */
export function materialPreparation(state:MaterialPreparation,action:PreparationAction):MaterialPreparation {
 const current=state.scope===action.scope?state:{...initialMaterialPreparation,scope:action.scope};
 if(action.type==='reset')return {...initialMaterialPreparation,scope:action.scope};
 if(action.versions[action.course]!==action.version)return current;
 const courses={...current.courses,[action.course]:{version:action.version,status:action.status}};
 const allReady=canRevealMaterials(courses,action.versions,action.unavailable||[],action.regenerating);
 return {scope:action.scope,revealed:current.revealed||allReady,courses};
}
