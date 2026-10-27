/* 서버가 돌려주는 5차 화면 ID(lastNew·시연 단계 이동 entry)를 새 주소로 바꾸는 표 */
import { describe, expect, it } from 'vitest';
import { legacyToPath, newIdToPath, pathToNewId, paths } from './paths';

describe('legacyToPath', () => {
  it('작성 단계 ID 는 작성 화면 주소로', () => {
    expect(legacyToPath('new-quiz')).toBe(paths.newQuiz);
    expect(legacyToPath('new-options')).toBe(paths.newOptions);
  });
  it('기록 ID 가 붙은 화면은 그 기록 주소로', () => {
    expect(legacyToPath('post:abc')).toBe('/roadmaps/abc/post');
    expect(legacyToPath('report:r1')).toBe('/reports/r1');
    expect(legacyToPath('comment:p1')).toBe('/roadmaps/p1/comments');
    expect(legacyToPath('res:KMOOC_1')).toBe('/resources/KMOOC_1');
  });
  it('목록 화면과 모르는 ID', () => {
    expect(legacyToPath('roadmap')).toBe(paths.roadmaps);
    expect(legacyToPath('checks')).toBe(paths.checks);
    expect(legacyToPath('nope')).toBe(paths.home);
    expect(legacyToPath(null)).toBe(paths.home);
  });
});

describe('작성 단계 ID ↔ 주소', () => {
  it('서로 바꿔도 같은 값', () => {
    for (const id of ['new-goal', 'new-details', 'new-result-edit', 'new-review']) expect(pathToNewId(newIdToPath(id))).toBe(id);
  });
  it('저장된 단계가 없으면 첫 단계', () => {
    expect(newIdToPath(null)).toBe(paths.newGoal);
    expect(pathToNewId('/roadmaps')).toBeNull();
  });
});
