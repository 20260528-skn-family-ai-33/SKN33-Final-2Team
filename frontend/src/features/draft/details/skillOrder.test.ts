import {expect,it} from 'vitest';
import {MAX_SKILLS,canIncludeSkill,overSkillLimit,reorderSkills} from './skillOrder';
const rows=[{name:'A',application:'A 적용'},{name:'B',application:'B 적용'},{name:'C',application:'C 적용'}];
it('드래그로 뒤로 이동해도 스킬 내용과 원본 순서를 보존한다',()=>{expect(reorderSkills(rows,'A','C').map(row=>row.name)).toEqual(['B','C','A']);expect(rows.map(row=>row.name)).toEqual(['A','B','C']);expect(reorderSkills(rows,'A','C')[2].application).toBe('A 적용');});
it('앞으로 이동하고, 같은 위치나 알 수 없는 항목은 순서를 바꾸지 않는다',()=>{expect(reorderSkills(rows,'C','A').map(row=>row.name)).toEqual(['C','A','B']);expect(reorderSkills(rows,'A','A')).toBe(rows);expect(reorderSkills(rows,'missing','A')).toBe(rows);});
it('스킬은 3개까지 포함할 수 있고 4개째부터는 막으며 이전에 저장된 초과분 수를 알려 준다',()=>{const row=(name:string)=>({name,application:`${name} 적용`});expect(MAX_SKILLS).toBe(3);expect(canIncludeSkill(rows.slice(0,2))).toBe(true);expect(canIncludeSkill(rows)).toBe(false);expect(overSkillLimit(rows)).toBe(0);expect(overSkillLimit([...rows,row('D')])).toBe(1);expect(overSkillLimit([...rows,row('D'),row('E')])).toBe(2);});
