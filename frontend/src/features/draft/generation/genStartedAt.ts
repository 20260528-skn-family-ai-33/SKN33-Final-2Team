import type { GenRow, GenRun } from '@/api/types/draft';

/** 3안 작성이 시작된 시각(서버 기록 · 밀리초). 작성 중인 안이 있으면 그 가운데 가장 이른 시각, 없으면 모든 안 중 가장 이른 시각.
    화면 안의 상태가 아니라 서버 기록이라 다른 화면에 다녀오거나 새로 고쳐도 0초로 돌아가지 않는다.
    실패한 안만 다시 시도하면 그 안의 시각이 새로 찍혀 그때부터 센다. 기록이 없는 이전 작업은 null */
export function genStartedAt(run: GenRun | null): number | null {
  const rows = Object.values(run?.rows ?? {}).filter((row): row is GenRow => !!row);
  const running = rows.filter((row) => row.st === 'run');
  const times = (running.length ? running : rows)
    .map((row) => row.startedAt)
    .filter((at): at is number => typeof at === 'number' && Number.isFinite(at));
  return times.length ? Math.min(...times) : null;
}
