import { describe, expect, it } from 'vitest';
import { crashCore, crashCoreExpandable } from './crashCore';

describe('crashCore', () => {
  it('핵심 결과물·완료 기준이 있는 스킬만 보여 주고 후속 학습은 중복 없이 모은다', () => {
    const core = crashCore([
      { name: 'SQL', application: '집계 검증', coreOutcome: ' 월별 집계 쿼리 ', coreCriteria: ['집계 결과 정합성 확인', ' '],
        followUpScope: ['실행 계획 튜닝', '실행 계획 튜닝'] },
      { name: 'Python', application: '수집기', coreOutcome: '수집 스크립트', coreCriteria: [], followUpScope: ['비동기 처리'] },
    ]);
    expect(core).toEqual({
      rows: [{ name: 'SQL', outcome: '월별 집계 쿼리', criteria: ['집계 결과 정합성 확인'] }],
      followUp: ['실행 계획 튜닝', '비동기 처리'],
    });
  });

  it('기준이 없는 이전 Crash 안과 다른 코스는 표시하지 않는다', () => {
    expect(crashCore([{ name: 'SQL', application: '집계 검증' }])).toBeNull();
    expect(crashCore(undefined)).toBeNull();
    expect(crashCoreExpandable(null)).toBe(false);
  });

  it('긴 결과물이나 세 개 이상의 항목이 있으면 펼쳐 볼 수 있다', () => {
    const rows = [{ name: 'A', application: '', coreOutcome: '짧은 결과', coreCriteria: ['기준'] }];
    expect(crashCoreExpandable(crashCore(rows))).toBe(false);
    expect(crashCoreExpandable(crashCore([{ ...rows[0], followUpScope: ['1', '2', '3'] }]))).toBe(true);
    expect(crashCoreExpandable(crashCore([{ ...rows[0], coreOutcome: '가'.repeat(33) }]))).toBe(true);
  });
});
