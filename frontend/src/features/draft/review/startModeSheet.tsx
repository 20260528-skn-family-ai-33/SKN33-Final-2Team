/* 새 로드맵을 확정할 때 진행 중인 로드맵이 있으면 시작 방식을 묻는다.
   취소하거나 창을 닫으면 아무것도 바뀌지 않고, 고른 방식은 서버가 확정과 함께 한 번에 처리한다 */
import type { StartMode } from '@/api/types/draft';
import type { PlanRecord } from '@/api/types/plan';
import { followingStart, monthDay, today0 } from '@/features/home/ganttCalc';
import { closeSheet, openSheet } from '@/shared/state/ui';
import { recs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note } from '@/shared/ui/parts';

interface StartOption {
  mode: StartMode;
  label: string;
  desc: string;
}

export function startOptions(active: PlanRecord[], now?: Date): StartOption[] {
  const all = active.length > 1 ? '모두 ' : '';
  const next = followingStart(active, now);
  return [
    { mode: 'together', label: '동시 진행', desc: '진행 중인 로드맵과 함께 이번 주부터 진행해요.' },
    {
      mode: 'after',
      label: '끝나고 시작',
      desc: next > today0(now) ? `진행 중인 로드맵이 ${all}끝난 다음 주, ${monthDay(next)}부터 시작해요.` : '진행 중인 로드맵의 기간이 이미 지나서 이번 주부터 시작해요.',
    },
    { mode: 'archive', label: '보관하고 시작', desc: `진행 중인 로드맵을 ${all}보관하고 이번 주부터 시작해요. 기록은 남고 언제든 다시 진행할 수 있어요.` },
  ];
}

/** 진행 중인 로드맵이 없으면 묻지 않고 바로 진행한다 */
export function chooseStartMode(proceed: (mode?: StartMode) => void): void {
  const active = recs(ws(), 'active');
  if (!active.length) {
    proceed();
    return;
  }
  const canArchive = !ws().draft.demoSeeded;
  const options = startOptions(active).filter(option => canArchive || option.mode !== 'archive');
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
                proceed(option.mode);
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
