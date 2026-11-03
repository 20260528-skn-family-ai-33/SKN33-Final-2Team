import { expect,it } from 'vitest';
import type { OptionDef } from '@/api/types/draft';
import { materialVersionKey } from './materialVersion';
const option={id:'A1',optionId:'first',learningSkillsVersion:'skills',acts:[]} as unknown as OptionDef;
it('support responses preserve the same material editor version',()=>{
 expect(materialVersionKey({...option,support:{message:'ready'}} as unknown as OptionDef)).toBe(materialVersionKey(option));
 expect(materialVersionKey({...option,supportFail:{message:'error'}} as unknown as OptionDef)).toBe(materialVersionKey(option));
});
it('new and restored proposals have distinct and repeatable versions',()=>{
 const newer={...option,optionId:'second'};
 expect(materialVersionKey(newer)).not.toBe(materialVersionKey(option));
 expect(materialVersionKey(structuredClone(option))).toBe(materialVersionKey(option));
});
it('legacy proposals exclude support from the fallback version',()=>{
 const legacy={...option,optionId:undefined};
 expect(materialVersionKey({...legacy,supportFail:{}} as unknown as OptionDef)).toBe(materialVersionKey(legacy));
 expect(materialVersionKey({...legacy,tagline:'changed'})).not.toBe(materialVersionKey(legacy));
});
