import {expect,it} from 'vitest';
import {STEPS,stepOfPath,blockedTo} from './model';
import {freshWs} from '@/shared/state/workspace';
import {skillInputKey} from './details/skillInput';
it('입력 확인을 독립된 3단계로 둔 7단계 순서다',()=>{
 expect(STEPS.map(row=>row[0])).toEqual(['goal','details','check','quiz','result','options','review']);
 expect(stepOfPath('/new/details/check')).toBe('check');expect(STEPS[3][1]).toBe('역량 테스트');
});
it('스킬 선택 후 입력 확인을 거쳐야 역량 테스트로 진입한다',()=>{
 const s=freshWs('u');s.draft.goal='SQL 검증';s.draft.selectedSkills=[{name:'SQL',application:'집계'}];s.draft.skillInputKey=skillInputKey(s.draft);
 expect(blockedTo(s,'check')).toBeNull();expect(blockedTo(s,'quiz')).toBe('/new/details/check');
 s.draft.detailsOk=true;expect(blockedTo(s,'quiz')).toBeNull();
});
