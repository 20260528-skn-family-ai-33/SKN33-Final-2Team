import { afterEach, expect, it, vi } from 'vitest';
import type { Handoff } from '@/api/types/draft';
import { paths } from '@/app/paths';
import { freshWs, useWs, type WsState } from '@/shared/state/workspace';
import { genGate, optionsGate } from './DraftScreen';
import { genStart } from './result/legacyResult';

function generated() {
  const s = freshWs('employee');
  s.draftId = 'draft';
  s.draft.handoff = { key: 'h' } as Handoff;
  s.draft.gen = { key: 'h', missing: [], options: {} };
  s.draft.genRun = { key: 'h', rows: { A1: { st: 'ok' }, A2: { st: 'ok' }, A3: { st: 'ok' } } };
  return s;
}

// 진단 결과의 다음 버튼과 단계 표시줄·이어 쓰기·직접 주소의 진입 가드를 함께 검증한다.
async function expectEntry(s: WsState, path: string) {
  useWs.setState(s, true);
  const go = vi.fn();
  await genStart(go);
  expect(go).toHaveBeenCalledExactlyOnceWith(path, { force: true });
  expect(optionsGate(s)).toBe(path === paths.newOptions ? null : paths.newGen);
}

afterEach(() => useWs.setState(freshWs(), true));

it('미리 생성된 초안도 첫 비교 전에는 규정 안내를 거치고, 다른 초안의 표시 기록은 재사용하지 않는다', async () => {
  const s = generated();
  s.educationGuideShownFor = 'earlier-draft';
  await expectEntry(s, paths.newGen);
  expect(genGate(s)).toBeNull();
});

it.each(['화면에 표시됨', '조회 완료·근거 없음'] as const)('%s: 다시 비교할 때 안내 화면을 반복하지 않는다', async (state) => {
  const s = generated();
  if (state === '화면에 표시됨') s.educationGuideShownFor = s.draftId;
  else s.draft.educationGuide = { basis: null };
  await expectEntry(s, paths.newOptions);
  // 생성 화면에 머물러 안내를 읽는 동안에는 자동으로 넘어가지 않는다.
  expect(genGate(s)).toBeNull();
});

it.each(['fail', 'run'])('일부 수락 후 누락 코스가 %s 상태여도 생성 화면으로 되돌리지 않는다', async (st) => {
  const s = generated();
  s.draft.gen!.missing = ['A3'];
  s.draft.genRun!.rows.A3 = { st };
  await expectEntry(s, paths.newOptions);
  expect(genGate(s)).toBe(paths.newOptions);
});

it('기존 선택이 있거나 생성 기록이 없는 옛 초안은 비교표로 바로 돌아간다', async () => {
  const chosen = generated();
  chosen.draft.chosen = 'A2';
  await expectEntry(chosen, paths.newOptions);
  const legacy = generated();
  legacy.draft.genRun = null;
  await expectEntry(legacy, paths.newOptions);
});
