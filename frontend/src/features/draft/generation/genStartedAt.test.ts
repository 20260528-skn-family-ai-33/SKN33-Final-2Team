import { describe, expect, it } from 'vitest';
import type { GenRun } from '@/api/types/draft';
import { genStartedAt } from './genStartedAt';

const run = (rows: GenRun['rows']): GenRun => ({ key: 'h', rows });

describe('genStartedAt', () => {
  it('작성 기록이 없으면 null', () => {
    expect(genStartedAt(null)).toBeNull();
    expect(genStartedAt(run({}))).toBeNull();
  });

  it('세 안을 함께 요청했으면 가장 먼저 요청한 시각부터 센다', () => {
    expect(genStartedAt(run({ A1: { st: 'run', startedAt: 1_002 }, A2: { st: 'run', startedAt: 1_000 }, A3: { st: 'run', startedAt: 1_001 } }))).toBe(1_000);
  });

  it('먼저 끝난 안이 있어도 남은 안의 시작 시각을 유지한다', () => {
    expect(genStartedAt(run({ A1: { st: 'ok', startedAt: 1_000 }, A2: { st: 'run', startedAt: 1_001 }, A3: { st: 'run', startedAt: 1_002 } }))).toBe(1_001);
  });

  it('실패한 안만 다시 시도하면 다시 요청한 시각부터 센다', () => {
    expect(genStartedAt(run({ A1: { st: 'ok', startedAt: 1_000 }, A2: { st: 'run', startedAt: 9_000 }, A3: { st: 'ok', startedAt: 1_000 } }))).toBe(9_000);
  });

  it('작성 중인 안이 없으면 모든 안 중 가장 이른 시각', () => {
    expect(genStartedAt(run({ A1: { st: 'ok', startedAt: 1_000 }, A2: { st: 'ok', startedAt: 1_001 }, A3: { st: 'ok', startedAt: 1_002 } }))).toBe(1_000);
  });

  it('시작 시각이 없는 이전 기록은 null(화면을 연 시각으로 대신 센다)', () => {
    expect(genStartedAt(run({ A1: { st: 'run', tries: 1 }, A2: { st: 'run', startedAt: Number.NaN }, A3: { st: 'run' } }))).toBeNull();
  });
});
