/* 과제 제출·전송 응답을 캐시에 넣을 때 늦게 끝난 조회가 덮어쓰지 않는지 (PR #140 리뷰) */
import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import type { ReportTask } from '@/api/types/task';
import { putTasks, taskKey } from './taskData';

const task = (id: string, submittedAt: string | null = null): ReportTask => ({
  id,
  planId: 'p1',
  body: '과제',
  createdAt: '2026-11-09',
  head: { id: '8', name: '부서장' },
  submittedAt,
  answer: submittedAt ? '완료' : '',
  file: null,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe('putTasks', () => {
  const before = [task('t1')];
  const submitted = [task('t1', '2026-11-09')];

  it('먼저 시작한 조회가 늦게 끝나도 제출 결과를 덮지 않는다', async () => {
    const qc = new QueryClient();
    qc.setQueryData(taskKey('p1'), before);
    const late = deferred<ReportTask[]>();
    const fetching = qc.fetchQuery({ queryKey: taskKey('p1'), queryFn: () => late.promise }).catch(() => null);

    await putTasks(qc, 'p1', submitted);
    late.resolve(before);
    await fetching;
    await new Promise((r) => setTimeout(r, 0));

    expect(qc.getQueryData(taskKey('p1'))).toEqual(submitted);
    expect(qc.isFetching({ queryKey: taskKey('p1') })).toBe(0);
  });

  it('진행 중인 조회가 없으면 받은 목록을 그대로 넣는다', async () => {
    const qc = new QueryClient();
    await putTasks(qc, 'p1', submitted);
    expect(qc.getQueryData(taskKey('p1'))).toEqual(submitted);
  });

  describe('같은 보고서의 과제를 동시에 제출할 때', () => {
    const notYet = [task('a'), task('b')];
    const onlyA = [task('a', '2026-11-09'), task('b')];
    const both = [task('a', '2026-11-09'), task('b', '2026-11-09')];

    it('응답이 역순으로 와도 제출한 과제를 제출 전으로 되돌리지 않는다', async () => {
      const qc = new QueryClient();
      qc.setQueryData(taskKey('p1'), notYet);

      await putTasks(qc, 'p1', both);
      await putTasks(qc, 'p1', onlyA);

      expect(qc.getQueryData(taskKey('p1'))).toEqual(both);
    });

    it('응답이 순서대로 오면 차례로 반영한다', async () => {
      const qc = new QueryClient();
      qc.setQueryData(taskKey('p1'), notYet);

      await putTasks(qc, 'p1', onlyA);
      expect(qc.getQueryData(taskKey('p1'))).toEqual(onlyA);

      await putTasks(qc, 'p1', both);
      expect(qc.getQueryData(taskKey('p1'))).toEqual(both);
    });
  });

  it('아직 제출하지 않은 과제는 제출 전으로 두고, 새로 온 과제도 넣는다', async () => {
    const qc = new QueryClient();
    qc.setQueryData(taskKey('p1'), [task('a')]);

    await putTasks(qc, 'p1', [task('a'), task('new')]);

    expect(qc.getQueryData(taskKey('p1'))).toEqual([task('a'), task('new')]);
  });

  it('다른 보고서의 조회는 취소하지 않는다', async () => {
    const qc = new QueryClient();
    const other = deferred<ReportTask[]>();
    const fetching = qc.fetchQuery({ queryKey: taskKey('p2'), queryFn: () => other.promise });

    await putTasks(qc, 'p1', submitted);
    other.resolve(before);

    await expect(fetching).resolves.toEqual(before);
    expect(qc.getQueryData(taskKey('p2'))).toEqual(before);
  });
});
