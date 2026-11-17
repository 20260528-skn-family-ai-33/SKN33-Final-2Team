/* 3안 작성 중에 다른 화면에 다녀와도 새 로드맵 탭이 그 앞의 테스트 결과(5단계)가 아니라 생성 화면(6단계)으로 돌아온다 */
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import type { Handoff } from '@/api/types/draft';
import { newIdToPath, pathToNewId, paths } from '@/app/paths';
import { D } from '@/shared/constants/data';
import { freshWs, type WsState } from '@/shared/state/workspace';
import { DraftScreen, genGate } from '../DraftScreen';
import { useRememberStep } from '../guard';
import { SUB, stepLabel } from '../model';
import { genRunning } from './GenerationStep';

vi.mock('../guard', async (importOriginal) => ({ ...(await importOriginal<typeof import('../guard')>()), useRememberStep: vi.fn() }));

afterEach(() => vi.mocked(useRememberStep).mockClear());

/** 3안 작성을 시작한 작성 문서. run: 화면을 떠날 때 본 상태, ok: 그사이 서버가 세 안을 모두 쓴 상태 */
function generation(st: 'run' | 'ok'): WsState {
  const s = freshWs('employee');
  s.draftId = 'draft';
  s.draft.v2Assessment = { generationId: 'g', completed: true };
  s.draft.handoff = { key: 'h' } as Handoff;
  s.draft.genRun = { key: 'h', rows: Object.fromEntries(D.optionOrder.map((id) => [id, { st }])) };
  if (st === 'ok') s.draft.gen = { key: 'h', missing: [], options: {} };
  return s;
}

it('생성 화면도 마지막 작성 단계로 기억해, 새 로드맵 탭과 홈의 이어서 작성이 6단계 생성 화면을 가리킨다', () => {
  renderToStaticMarkup(
    <MemoryRouter initialEntries={[paths.newGen]}>
      <DraftScreen extra={genGate} step="goal">
        <p>생성 화면</p>
      </DraftScreen>
    </MemoryRouter>,
  );
  expect(useRememberStep).toHaveBeenCalled();
  expect(newIdToPath(pathToNewId(paths.newGen))).toBe(paths.newGen);
  expect(stepLabel(SUB[paths.newGen])).toBe('로드맵·자료 선택');
});

it.each([
  ['아직 작성 중', 'run'],
  ['작성을 마친 뒤', 'ok'],
] as const)('%s 돌아와도 생성 화면에 머문다(테스트 결과로 돌려보내지 않는다)', (_, st) => {
  expect(genGate(generation(st))).toBeNull();
});

it('떠날 때 작성 중이던 기록만 돌아오자마자 다시 읽는다', () => {
  expect(genRunning(generation('run').draft)).toBe(true);
  expect(genRunning(generation('ok').draft)).toBe(false);
  const none = generation('run');
  none.draft.genRun = null;
  expect(genRunning(none.draft)).toBe(false);
  // 입력을 바꿔 전달 내용이 달라진 예전 작성 기록은 지금 작업으로 보지 않는다
  const old = generation('run');
  old.draft.handoff = { key: 'changed' } as Handoff;
  expect(genRunning(old.draft)).toBe(false);
});
