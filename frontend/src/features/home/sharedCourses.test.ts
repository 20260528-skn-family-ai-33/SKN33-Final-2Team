import { expect,it } from 'vitest';
import type { Activity } from '@/api/types/plan';
import type { ResourceMap } from '@/api/types/catalog';
import { sharedCourses } from './sharedCourses';
const activity=(id:string,skill:string,res:string,from:number,to:number)=>({id,skill,res,wFrom:from,wTo:to,hours:8,task:false}) as Activity;
const resources={c:{type:'course',title:'Shared course'},b:{type:'book',title:'Book'}} as unknown as ResourceMap;
it('same course spans all related skills without mutating learning records',()=>{
 const acts=[activity('one','SQL','c',1,2),activity('two','Python','c',4,5)];const before=JSON.stringify(acts);
 const group=sharedCourses(acts,resources)[0];expect(group.skills).toEqual(['SQL','Python']);expect([group.from,group.to]).toEqual([1,5]);
 expect(group.activities.map(act=>act.id)).toEqual(['one','two']);expect(JSON.stringify(acts)).toBe(before);
});
it('one skill, different courses, books, and tasks are not merged',()=>{
 expect(sharedCourses([activity('a','SQL','c',1,1),activity('b','SQL','c',2,2)],resources)).toEqual([]);
 expect(sharedCourses([activity('a','SQL','b',1,1),activity('b','Python','b',2,2)],resources)).toEqual([]);
 expect(sharedCourses([activity('a','SQL','c',1,1),{...activity('b','Python','c',2,2),task:true}],resources)).toEqual([]);
});
it('each roadmap is grouped independently',()=>{
 expect(sharedCourses([activity('a','SQL','c',1,2)],resources)).toEqual([]);expect(sharedCourses([activity('b','Python','c',3,4)],resources)).toEqual([]);
});
