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

  it.each([1, 2])('짧은 결과물이 %i개여도 숨겨진 완료 기준을 펼쳐 볼 수 있다', count => {
    const skills = Array.from({ length: count }, (_, i) => ({
      name: `스킬 ${i + 1}`, application: '', coreOutcome: '짧은 결과', coreCriteria: [' 기준 ', ' '],
    }));
    expect(crashCoreExpandable(crashCore(skills))).toBe(true);
  });

  it('결과물이나 완료 기준이 공백이면 펼칠 요약이 없다', () => {
    const core = crashCore([
      { name: 'SQL', application: '', coreOutcome: '짧은 결과', coreCriteria: ['', '  '] },
      { name: 'Python', application: '', coreOutcome: '  ', coreCriteria: ['기준'] },
    ]);
    expect(crashCoreExpandable(core)).toBe(false);
  });

  it('후속 학습은 접힌 요약의 32자 제한을 넘을 때 펼칠 수 있다', () => {
    const core = { rows: [{ name: 'SQL', outcome: '짧은 결과', criteria: [] }], followUp: [] };
    expect(crashCoreExpandable(core)).toBe(false);
    expect(crashCoreExpandable({ ...core, followUp: ['가'.repeat(32)] })).toBe(false);
    expect(crashCoreExpandable({ ...core, followUp: ['가'.repeat(33)] })).toBe(true);
  });
});
