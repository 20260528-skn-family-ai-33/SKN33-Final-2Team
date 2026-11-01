import { expect, it } from 'vitest';
import { preserveOtherSkillSelections } from './proposalSelection';
it('재제안하지 않은 스킬의 제외 상태와 자료 선택을 보존한다', () => {
  const acts=[{id:'material-S',skill:'S'},{id:'new-task-S',skill:'S'},{id:'material-T',skill:'T'},{id:'task-T',skill:'T'}];
  expect(preserveOtherSkillSelections(['material-S','material-T'],acts,acts.map(a=>a.id),'S')).toEqual(['material-S','new-task-S','material-T']);
});
