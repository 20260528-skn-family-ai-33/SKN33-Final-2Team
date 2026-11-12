import { describe, expect, it } from 'vitest';
import type { PlanContent } from '@/api/types/plan';
import { count } from './plan';

// 두 스킬이 같은 강좌(c)를 쓰고, 스킬마다 과제가 하나씩 있는 계획. 자료 정보가 없으면 도서로 보지 않는다
const act = (id: string, skill: string, res: string | null) => ({ id, skill, res, stage: 1, title: id, hours: 1, wFrom: 1, wTo: 1 }) as unknown as PlanContent['acts'][number];
const pl = { acts: [act('c-a', 'A', 'c'), act('c-b', 'B', 'c'), act('t-a', 'A', null), act('t-b', 'B', null)] } as unknown as PlanContent;
const done = (...ids: string[]) => Object.fromEntries(ids.map(id => [id, { status: 'done' }])) as never;

describe('공통 강좌의 완료 수', () => {
  it('공통 강좌는 하나로 센다', () => {
    expect(count(pl)).toEqual({ t: 3, done: 0 });
    expect(count(pl, done('c-a', 'c-b'))).toEqual({ t: 3, done: 1 });
    expect(count(pl, done('c-a', 'c-b', 't-a', 't-b'))).toEqual({ t: 3, done: 3 });
  });

  it('한쪽만 완료된 예전 기록은 아직 완료로 세지 않는다', () => {
    expect(count(pl, done('c-a'))).toEqual({ t: 3, done: 0 });
  });
});
