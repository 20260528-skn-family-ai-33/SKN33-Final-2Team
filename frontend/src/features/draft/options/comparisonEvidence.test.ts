import { expect, it } from 'vitest';
import type { Gen } from '@/api/types/draft';
import { comparisonEvidence } from './comparisonEvidence';

const generation = () => ({ key:'g', missing:[], options:Object.fromEntries(['A1','A2','A3'].map(course => [course,{optionId:`${course}-o`,promptProvenance:{promptVersionId:`${course}-v`}}])) }) as unknown as Gen;

it('sends only displayed option and prompt identifiers without user text', () => {
  const value = generation();
  value.options.A1.reason = '기획서 원문을 보내지 않음';
  expect(comparisonEvidence(value)).toEqual(['A1','A2','A3'].map(course => ({course,optionId:`${course}-o`,promptVersionId:`${course}-v`})));
});

it('does not fabricate a complete comparison for missing, old, or regenerating options', () => {
  expect(comparisonEvidence(undefined)).toBeUndefined();
  const missing = generation(); delete missing.options.A2;
  expect(comparisonEvidence(missing)).toBeUndefined();
  const old = generation(); delete old.options.A1.promptProvenance;
  expect(comparisonEvidence(old)).toBeUndefined();
  const running = generation(); running.regenRun = {A3:{jobId:'job'}};
  expect(comparisonEvidence(running)).toBeUndefined();
});
