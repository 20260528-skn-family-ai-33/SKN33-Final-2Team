/* 가운데 창·알림 (5차 GP.sheet·GP.toast) — 창 내용은 열린 동안 상태가 바뀌면 다시 그린다 */
import { useEffect } from 'react';
import { useAi } from '@/shared/state/ai';
import { useCatalog } from '@/shared/state/catalog';
import { closeSheet, useUi } from '@/shared/state/ui';
import { useWs } from '@/shared/state/workspace';
import { Icon } from './Icon';

export function SheetHost() {
  const sheet = useUi((s) => s.sheet);
  // 창 안의 입력·상태가 바뀌면 다시 그리기 위해 구독만 한다
  useWs();
  useCatalog();
  useAi();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeSheet();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);
  if (!sheet) return null;
  return (
    <div
      className="ov"
      id="sheet"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) closeSheet();
      }}
    >
      <div className={`sheet ${sheet.wide ? 'wide' : ''}`} role="dialog" aria-modal="true">
        <div className="sheet-h">
          <div>
            <b>{sheet.title}</b>
            {sheet.sub ? <small>{sheet.sub}</small> : null}
          </div>
          <button className="x" aria-label="닫기" onClick={closeSheet}>
            <Icon name="x" />
          </button>
        </div>
        <div className="sheet-b">{sheet.body()}</div>
        {sheet.foot ? <div className="sheet-f">{sheet.foot()}</div> : null}
      </div>
    </div>
  );
}

export function ToastHost() {
  const t = useUi((s) => s.toast);
  return (
    <div id="toast" className="toast" role="status" hidden={!t}>
      {t?.msg}
    </div>
  );
}
