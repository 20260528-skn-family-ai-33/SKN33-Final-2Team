/* 새 로드맵 작성 탭에 들어가려 할 때 진행 중인 로드맵이 있으면 시작 방식을 묻는다.
   취소하거나 창을 닫으면 들어가지 않는다. 고른 방식은 작성 문서에 저장했다가 확정할 때 서버가 적용하므로, 작성을 그만두면 기존 로드맵은 그대로다 */
import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router';
import type { StartMode } from '@/api/types/draft';
import type { PlanRecord } from '@/api/types/plan';
import { isNewPath, paths } from '@/app/paths';
import { followingStart, monthDay, today0 } from '@/features/home/ganttCalc';
import { addNavGuard, useGo } from '@/shared/hooks/useGo';
import { closeSheet, openSheet } from '@/shared/state/ui';
import { recs, updateWs, ws, type WsState } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note } from '@/shared/ui/parts';

type Go = ReturnType<typeof useGo>;

interface StartOption {
  mode: StartMode;
  label: string;
  desc: string;
}

export function startOptions(active: PlanRecord[], now?: Date): StartOption[] {
  const all = active.length > 1 ? '모두 ' : '';
  const next = followingStart(active, now);
  return [
    { mode: 'together', label: '동시 진행', desc: '새 로드맵을 확정하면 진행 중인 로드맵과 함께 바로 시작해요.' },
    {
      mode: 'after',
      label: '끝나고 시작',
      desc: next > today0(now) ? `진행 중인 로드맵이 ${all}끝난 다음 주, ${monthDay(next)}부터 시작해요.` : '진행 중인 로드맵의 기간이 이미 지나서 확정하면 바로 시작해요.',
    },
    { mode: 'archive', label: '보관하고 시작', desc: `새 로드맵을 확정할 때 진행 중인 로드맵을 ${all}보관하고 바로 시작해요. 기록은 남고 언제든 다시 진행할 수 있어요.` },
  ];
}

/** 진행 중인 로드맵이 있는데 이번 작성 문서의 시작 방식을 아직 고르지 않았는지. 한 번 고른 문서는 다시 묻지 않는다 */
export const needsStartMode = (s: Pick<WsState, 'draft' | 'plans'>): boolean => !s.draft.startMode && recs(s, 'active').length > 0;

/** 작성 탭 밖에서 안으로 들어가는 이동만 막는다(작성 단계끼리의 이동은 그대로) */
export const blocksEntry = (to: string, from: string, s: Pick<WsState, 'draft' | 'plans'>): boolean => isNewPath(to) && !isNewPath(from) && needsStartMode(s);

function openStartModeSheet(enter: (mode: StartMode) => void): void {
  const active = recs(ws(), 'active');
  const canArchive = !ws().draft.demoSeeded;
  const options = startOptions(active).filter((option) => canArchive || option.mode !== 'archive');
  const only = active.length === 1 ? active[0].plan : null;
  openSheet({
    title: '새 로드맵을 언제 시작할까요?',
    sub: only ? `진행 중 · ${only.displayTitle || only.goal}` : `진행 중인 로드맵 ${active.length}개`,
    body: () => (
      <>
        <div className="list">
          {options.map((option) => (
            <button
              type="button"
              className="li"
              key={option.mode}
              onClick={() => {
                closeSheet();
                enter(option.mode);
              }}
            >
              <div className="tx">
                <b>{option.label}</b>
                <small>{option.desc}</small>
              </div>
              <span className="end">
                <Icon name="right" />
              </span>
            </button>
          ))}
        </div>
        {canArchive && active.some((R) => R.pending) ? <Note>보관하면 만들어 둔 수정안은 버려요.</Note> : null}
      </>
    ),
    foot: () => (
      <button type="button" className="btn line" onClick={closeSheet}>
        취소
      </button>
    ),
  });
}

/** 작성 탭으로 들어간다. 물어야 하면 고른 뒤에만 들어가고, before(들어가기 직전 준비)도 그때 실행한다 */
export function enterNewRoadmap(go: Go, to: string, before?: () => void): void {
  const enter = (mode?: StartMode) => {
    before?.();
    if (mode) updateWs((s) => void (s.draft.startMode = mode));
    go(to, { force: true });
  };
  if (needsStartMode(ws())) openStartModeSheet(enter);
  else enter();
}

/** 메뉴·버튼·알림 등 useGo 를 거치는 모든 진입을 한 곳에서 막는다 */
export function StartModeNavGuard() {
  const go = useGo();
  useEffect(
    () =>
      addNavGuard((to, from) => {
        if (!blocksEntry(to, from, ws())) return true;
        enterNewRoadmap(go, to);
        return false;
      }),
    [go],
  );
  return null;
}

/** 주소를 직접 열거나 뒤로 가기로 들어온 경우: 홈으로 돌려보낸 뒤 묻고, 고르면 원래 가려던 단계로 간다 */
export function StartModeRedirect() {
  const go = useGo();
  const { pathname } = useLocation();
  useEffect(() => enterNewRoadmap(go, pathname), [go, pathname]);
  return <Navigate to={paths.home} replace />;
}
