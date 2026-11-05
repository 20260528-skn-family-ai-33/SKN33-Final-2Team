import { expect, it } from 'vitest';
import type { Handoff, OptionDef } from '@/api/types/draft';
import { freshWs } from '@/shared/state/workspace';
import { genGate, optionsGate } from './DraftScreen';
import { blockedTo, docBusy } from './model';

it('기획서를 다시 요약하는 동안에는 이미 만든 3안이 있어도 어느 단계로도 넘어가지 않는다', () => {
  const s = freshWs('u');
  s.draft.goal = '점검 절차 검색';
  s.draft.project = { name: 'plan.txt', size: 10 };
  const option: OptionDef = { id: 'A1', name: 'Free', short: '기초', tagline: '목표', pros: [], cons: [], acts: [] };
  s.draft.gen = { key: 'h', options: { A1: option }, missing: [] };
  s.draft.handoff = { key: 'h' } as Handoff;
  s.draft.chosen = 'A1';
  // 요약 실패 뒤 '다시 시도'는 앞 결과를 지우지 않고 읽는 중으로만 바꾼다
  s.draft.doc = { name: 'plan.txt', status: 'reading', step: 'summary' };
  expect(docBusy(s)).toBe(true);
  expect(blockedTo(s, 'details')).toBe('/new/goal');
  expect(blockedTo(s, 'review')).toBe('/new/goal');
  expect(genGate(s)).toBe('/new/goal');
  expect(optionsGate(s)).toBe('/new/goal');

  s.draft.doc = { name: 'plan.txt', status: 'ok', summary: '요약' };
  expect(docBusy(s)).toBe(false);
  expect(genGate(s)).toBeNull();
  expect(optionsGate(s)).toBeNull();
});

it('파일을 올리는 중이면 서버 응답이 읽는 중 표시를 지워도 1단계에 머문다', () => {
  const s = freshWs('u');
  s.draft.goal = '점검 절차 검색';
  s.draft.doc = null;
  s.docUpload = 1;
  expect(docBusy(s)).toBe(true);
  expect(blockedTo(s, 'details')).toBe('/new/goal');
  s.docUpload = null;
  expect(docBusy(s)).toBe(false);
  expect(blockedTo(s, 'details')).toBeNull();
});
