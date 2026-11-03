import { expect, it } from 'vitest';
import { freshWs } from '@/shared/state/workspace';
import { reviewScope } from './reviewScope';

const fixture = () => {
  const s = freshWs('employee'); s.draftId = 'draft'; s.draft.goal = '검색 구현';
  s.draft.chosen = 'A1'; s.draft.selectedSkills = [{name:'SQL',application:'집계'}];
  s.draft.v2Assessment = {generationId:'questions',completed:true,materialsKey:'materials'};
  return s;
};
it('직원·초안·코스·문항·자료·입력이 바뀌면 이전 산출물 범위를 재사용하지 않는다', () => {
  const base = fixture(), key = reviewScope(base);
  for (const change of [
    (s: typeof base) => { s.owner = 'other'; },
    (s: typeof base) => { s.draftId = 'other'; },
    (s: typeof base) => { s.draft.chosen = 'A3'; },
    (s: typeof base) => { s.draft.v2Assessment!.generationId = 'new'; },
    (s: typeof base) => { s.draft.v2Assessment!.materialsKey = 'new'; },
    (s: typeof base) => { s.draft.prefs.hours = 8; },
    (s: typeof base) => { s.draft.selectedSkills![0].application = '조인'; },
  ]) { const changed = fixture(); change(changed); expect(reviewScope(changed)).not.toBe(key); }
});
it('산출물 저장 완료나 JSON 항목 순서만 달라져도 같은 입력 범위를 유지한다', () => {
  const s=fixture(), key=reviewScope(s);
  s.draft.v2Assessment!.activitiesReady=true;
  s.draft.prefs={...s.draft.prefs};
  expect(reviewScope(s)).toBe(key);
});
