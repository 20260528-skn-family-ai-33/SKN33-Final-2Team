import { expect,it } from 'vitest';
import { freshWs } from '@/shared/state/workspace';
import { skillInputKey,skillsReady } from './skillInput';
import { inputSignature,invalidateDraft } from '../invalidation';
it('skill recommendation cannot be reused after changing upstream conditions',()=>{
 const s=freshWs('u');s.draft.selectedSkills=[{name:'SQL',application:'Join'}];s.draft.skillInputKey=skillInputKey(s.draft);
 expect(skillsReady(s.draft)).toBe(true);s.draft.prefs.hours=8;expect(skillsReady(s.draft)).toBe(false);
});
it('skill order changes invalidate assessment inputs but retain the new selection',()=>{
 const s=freshWs('u');s.draft.selectedSkills=[{name:'SQL',application:'Join'},{name:'Python',application:'CSV'}];
 const before=inputSignature(s.draft);s.draft.selectedSkills.reverse();expect(inputSignature(s.draft)).not.toBe(before);
 s.draft.v2Assessment={generationId:'g',completed:true};invalidateDraft(s);expect(s.draft.v2Assessment).toBeUndefined();expect(s.draft.selectedSkills[0].name).toBe('Python');
});
