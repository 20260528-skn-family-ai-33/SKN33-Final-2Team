import { expect,it } from 'vitest';
import { freshWs } from '@/shared/state/workspace';
import { skillInputKey,skillsReady,shouldRecommendSkills,canContinueSkills } from './skillInput';
import { inputSignature,invalidateDraft } from '../invalidation';
it('learning conditions preserve selected skills, inclusion and order',()=>{
 const s=freshWs('u');s.draft.selectedSkills=[{name:'Python',application:'CSV'},{name:'SQL',application:'Join'}];s.draft.skillCandidates=[...s.draft.selectedSkills,{name:'Git',application:'History'}];s.draft.skillInputKey=skillInputKey(s.draft);
 const selected=structuredClone(s.draft.selectedSkills),candidates=structuredClone(s.draft.skillCandidates),key=s.draft.skillInputKey;
 for(const change of [{hours:8},{weeks:12},{budget:10000},{etc:'주말만 가능'}]){
  Object.assign(s.draft.prefs,change);expect(skillInputKey(s.draft)).toBe(key);expect(skillsReady(s.draft)).toBe(true);
  expect(s.draft.selectedSkills).toEqual(selected);expect(s.draft.skillCandidates).toEqual(candidates);
 }
});
it('older saved skill signatures survive changes to learning conditions',()=>{
 const s=freshWs('u');s.draft.goal='SQL';s.draft.selectedSkills=[{name:'SQL',application:'Join'}];
 s.draft.skillInputKey=JSON.stringify([s.draft.goal,s.draft.project,structuredClone(s.draft.prefs),null]);
 s.draft.prefs.hours=8;expect(skillsReady(s.draft)).toBe(true);
 s.draft.goal='Python';expect(skillsReady(s.draft)).toBe(false);
});
it('goal or project changes still invalidate skill input signatures',()=>{
 const s=freshWs('u');s.draft.selectedSkills=[{name:'SQL',application:'Join'}];s.draft.skillInputKey=skillInputKey(s.draft);
 s.draft.goal='new goal';expect(skillsReady(s.draft)).toBe(false);
 s.draft.skillInputKey=skillInputKey(s.draft);s.draft.project={name:'changed.pdf',size:12};expect(skillsReady(s.draft)).toBe(false);
});
it('editing skill selection does not alter learning conditions',()=>{
 const s=freshWs('u');s.draft.prefs.hours=8;s.draft.prefs.weeks=12;s.draft.prefs.budget=10000;s.draft.prefs.etc='주말';const before=structuredClone(s.draft.prefs);
 s.draft.selectedSkills=[{name:'SQL',application:'Join'}];invalidateDraft(s);expect(s.draft.prefs).toEqual(before);
});
it('skill order changes invalidate assessment inputs but retain the new selection',()=>{
 const s=freshWs('u');s.draft.selectedSkills=[{name:'SQL',application:'Join'},{name:'Python',application:'CSV'}];
 const before=inputSignature(s.draft);s.draft.selectedSkills.reverse();expect(inputSignature(s.draft)).not.toBe(before);
 s.draft.v2Assessment={generationId:'g',completed:true};invalidateDraft(s);expect(s.draft.v2Assessment).toBeUndefined();expect(s.draft.selectedSkills[0].name).toBe('Python');
});

it('visiting an existing legacy draft does not recommend skills or mutate completed results',()=>{
 const s=freshWs('u');s.draft.goal='SQL 프로젝트';s.draft.detailsOk=true;s.draft.v2Assessment={generationId:'existing',completed:true};
 s.draft.gen={key:'existing-plan',options:{},missing:[]};const before=structuredClone(s.draft);
 expect(shouldRecommendSkills(s.draft)).toBe(false);expect(canContinueSkills(s.draft)).toBe(true);expect(s.draft).toEqual(before);
 expect(shouldRecommendSkills(s.draft,true)).toBe(true);
});
it('new drafts still request initial skills, and a completed pending flow is protected',()=>{
 const s=freshWs('u');expect(shouldRecommendSkills(s.draft)).toBe(true);
 s.draft.v2Assessment={generationId:'existing',completed:false};expect(shouldRecommendSkills(s.draft)).toBe(false);
});
it('explicit skill re-selection invalidates the old flow only after applying the new selection',()=>{
 const s=freshWs('u');s.draft.v2Assessment={generationId:'existing',completed:true};s.draft.gen={key:'old',options:{},missing:[]};
 expect(shouldRecommendSkills(s.draft,true)).toBe(true);expect(s.draft.gen?.key).toBe('old');
 s.draft.selectedSkills=[{name:'SQL',application:'집계'}];s.draft.skillInputKey=skillInputKey(s.draft);invalidateDraft(s);
 expect(s.draft.gen).toBeNull();expect(s.draft.v2Assessment).toBeUndefined();expect(skillsReady(s.draft)).toBe(true);
});
