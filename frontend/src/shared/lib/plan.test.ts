/* 로드맵 계산: 주당 시간으로 주차를 나누는 규칙(서버도 같은 규칙으로 저장한다)과 비용 합계 */
import { beforeAll, describe, expect, it } from 'vitest';
import type { OptionDef } from '@/api/types/draft';
import { mergeRes } from '@/shared/state/catalog';
import { buildPlan, count, nextAct, range } from './plan';

const def: OptionDef = {
  id: 'A1',
  name: '기초부터',
  short: '기초',
  tagline: '',
  pros: [],
  cons: [],
  acts: [
    { id: 'a1', stage: 1, title: '입문 강좌', res: 'r-course' },
    { id: 'a2', stage: 2, title: '실습 과제', res: null, hours: 3, skills: ['RAG'] },
    { id: 'a3', stage: 3, title: '도서 읽기', res: 'r-book' },
  ],
};

beforeAll(() => {
  mergeRes({
    'r-course': { id: 'r-course', title: '입문', provider: 'K-MOOC', kind: '강좌', hours: 6, cost: 0 },
    // 시간·비용을 모르는 자료: 시간은 2시간으로 보고 비용은 '확인 필요'
    'r-book': { id: 'r-book', title: '책', provider: '출판사', kind: '도서', hours: null, cost: null },
  });
});

describe('buildPlan', () => {
  it('누적 시간을 주당 시간으로 나눠 활동마다 시작·끝 주차를 정한다', () => {
    const pl = buildPlan(def, { hours: 4 }, '목표');
    expect(pl.acts.map((a) => [a.id, a.hours, a.wFrom, a.wTo])).toEqual([
      ['a1', 6, 1, 2],
      ['a2', 3, 2, 3],
      ['a3', 2, 3, 3],
    ]);
    expect(pl.totalH).toBe(11);
    expect(pl.weeks).toBe(3);
  });

  it('시작 단계보다 앞 단계 활동은 빼고 계산한다', () => {
    const pl = buildPlan(def, { hours: 4, start: 2 }, '목표');
    expect(pl.acts.map((a) => a.id)).toEqual(['a2', 'a3']);
    expect(pl.acts[0].wFrom).toBe(1);
  });

  it('비용은 아는 값만 더하고, 모르는 자료가 있으면 확인 필요로 표시한다', () => {
    const pl = buildPlan(def, { hours: 4 }, '목표');
    expect(pl.cost).toBe(0);
    expect(pl.costUnknown).toBe(true);
  });

  it('과제는 자료가 없으므로 과제 표시와 에이전트가 고른 스킬을 남긴다', () => {
    const a2 = buildPlan(def, {}, '').acts.find((a) => a.id === 'a2')!;
    expect(a2.task).toBe(true);
    expect(a2.skills).toEqual(['RAG']);
  });

  it('활동별 고친 값(patch)은 주차 계산 전에 반영된다', () => {
    const pl = buildPlan(def, { hours: 4, patch: { a1: { hours: 1 } } }, '');
    expect(pl.acts[0].wTo).toBe(1);
    expect(pl.totalH).toBe(6);
  });
});

describe('진행 계산', () => {
  it('완료한 활동 수와 다음 활동을 센다', () => {
    const pl = buildPlan(def, { hours: 4 }, '');
    const progress = { a1: { status: 'done' } } as never;
    expect(count(pl, progress)).toMatchObject({ t: 3, done: 1 });
    expect(nextAct(pl, progress)?.id).toBe('a2');
  });

  it('주차 범위를 처음~끝으로 쓴다(한 주면 그 주만)', () => {
    const pl = buildPlan(def, { hours: 4 }, '');
    expect(range(pl.acts)).toBe('1~3주차');
    expect(range(pl.acts.slice(2))).toBe('3주차');
  });
});
