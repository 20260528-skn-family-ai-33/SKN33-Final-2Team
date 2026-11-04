/* 완료 알림(#82) — 상단 띠의 알림 버튼과 목록 창. 직원 계정(부서장 포함)에서만 보인다.
   30초마다(창이 보일 때만)·화면을 옮길 때·창을 열 때 새로 받는다. 누르면 읽음으로 바꾸고 그 로드맵·보고서 화면으로 간다 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { notificationsApi } from '@/api/endpoints/notifications';
import type { AppNotification, NotificationInbox } from '@/api/types/notification';
import { reloadWorkspace } from '@/features/draft/draftSync';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { needsWorkspace, notificationSub, notificationTarget, notificationTime, notificationTitle } from './notificationView';

const notificationKey = ['notifications'] as const;
const POLL_MS = 30_000;

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const go = useGo();
  const { pathname } = useLocation();
  const q = useQuery({ queryKey: notificationKey, queryFn: notificationsApi.inbox, refetchInterval: POLL_MS });
  const items = q.data?.items || [];
  const unread = q.data?.unread || 0;

  // 화면을 옮길 때마다 새로 받는다(로드맵 확정·보고서 작성 뒤 다음 화면으로 가면 바로 보이게). 처음 그릴 때는 useQuery 가 이미 받는다
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    void qc.invalidateQueries({ queryKey: notificationKey });
  }, [pathname, qc]);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !boxRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside, true);
    return () => document.removeEventListener('pointerdown', closeOutside, true);
  }, [open]);

  const save = (box: NotificationInbox) => qc.setQueryData(notificationKey, box);

  const openItem = async (n: AppNotification) => {
    setOpen(false);
    if (!n.read) {
      try {
        save(await notificationsApi.read(n.id));
      } catch (err) {
        // 읽음 저장에 실패해도 보려던 화면으로는 간다(알림은 읽지 않은 채로 남는다)
        failToast(err, '알림을 읽음으로 바꾸지 못했어요');
      }
    }
    if (needsWorkspace(n, useWs.getState())) {
      try {
        await reloadWorkspace();
      } catch (err) {
        failToast(err, '최신 기록을 불러오지 못했어요');
      }
    }
    go(notificationTarget(n));
  };

  const readAll = async () => {
    try {
      save(await notificationsApi.readAll());
    } catch (err) {
      failToast(err, '알림을 모두 읽음으로 바꾸지 못했어요');
    }
  };

  const toggle = () => {
    if (!open) void q.refetch();
    setOpen((v) => !v);
  };

  return (
    <div className="api-picker notif" ref={boxRef}>
      <button
        type="button"
        className="api-picker-button gray notif-button"
        aria-label={unread ? `알림 · 읽지 않은 알림 ${unread}개` : '알림'}
        aria-expanded={open}
        aria-controls="notif-panel"
        onClick={toggle}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setOpen(false);
        }}
      >
        <Icon name="bell" />
        <span className="notif-l">알림</span>
        {unread ? <span className="notif-count">{unread > 99 ? '99+' : unread}</span> : null}
      </button>

      {open ? (
        <div
          id="notif-panel"
          className="api-picker-panel notif-panel"
          role="dialog"
          aria-label="알림"
          onKeyDown={(event) => {
            if (event.key === 'Escape') setOpen(false);
          }}
        >
          <div className="notif-h">
            <b>알림</b>
            {unread ? (
              <button type="button" className="link" onClick={() => void readAll()}>
                모두 읽음
              </button>
            ) : null}
          </div>
          {q.isError ? (
            <p className="notif-empty" role="alert">
              알림을 불러오지 못했어요.{' '}
              <button type="button" className="link" onClick={() => void q.refetch()}>
                다시 시도
              </button>
            </p>
          ) : null}
          {items.length ? (
            <ul className="notif-list">
              {items.map((n) => (
                <li key={n.id}>
                  <button type="button" className={`notif-it${n.read ? '' : ' new'}`} onClick={() => void openItem(n)}>
                    <span className="notif-dot" aria-hidden="true" />
                    <span className="notif-tx">
                      <b>{notificationTitle(n)}</b>
                      <small>{notificationSub(n)}</small>
                    </span>
                    <time dateTime={n.createdAt}>{notificationTime(n.createdAt)}</time>
                    {n.read ? null : <span className="notif-sr">읽지 않음</span>}
                  </button>
                </li>
              ))}
            </ul>
          ) : q.isError ? null : (
            <p className="notif-empty">{q.isPending ? '불러오는 중…' : '알림이 없어요'}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
