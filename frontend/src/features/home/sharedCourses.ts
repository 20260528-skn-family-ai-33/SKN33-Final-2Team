import type { Activity } from '@/api/types/plan';
import type { ResourceMap } from '@/api/types/catalog';
export type SharedCourse={id:string;title:string;skills:string[];activities:Activity[];from:number;to:number};
/** Visual grouping only: never rewrites activity IDs, hours, costs, or saved progress. */
export function sharedCourses(activities:Activity[],resources:ResourceMap):SharedCourse[]{
 const groups=new Map<string,SharedCourse>();
 for(const activity of activities){
  const resource=activity.res?resources[activity.res]:undefined;
  if(!activity.res||activity.task||!activity.skill||!(resource?.type==='course'||resource?.kind==='강좌'))continue;
  const previous=groups.get(activity.res);
  if(previous){
   previous.activities.push(activity);if(!previous.skills.includes(activity.skill))previous.skills.push(activity.skill);
   const canonical=previous.activities.find(row=>row.resourceWindow)?.resourceWindow;
   if(canonical){previous.from=canonical.from;previous.to=canonical.to;}
   else{previous.from=Math.min(previous.from,activity.wFrom);previous.to=Math.max(previous.to,activity.wTo);}
  }else groups.set(activity.res,{id:activity.res,title:resource.title,skills:[activity.skill],activities:[activity],from:activity.resourceWindow?.from??activity.wFrom,to:activity.resourceWindow?.to??activity.wTo});
 }
 return [...groups.values()].filter(group=>group.skills.length>1);
}
