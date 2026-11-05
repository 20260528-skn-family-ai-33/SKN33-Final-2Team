/* 완료 알림(#82) — 상단 띠의 알림 버튼과 목록 창. 직원 계정(부서장 포함)에서만 보인다.
   30초마다(창이 보일 때만)·화면을 옮길 때·창을 열 때 새로 받는다. 누르면 읽음으로 바꾸고 그 로드맵·보고서 화면으로 간다.
   부서장(#96): 내 알림을 위, 소속 직원 알림을 아래에 나눠 두고, 소속 직원 알림은 직원별 한 줄로 묶는다.
   묶음을 누르면 창 안에서 그 직원의 알림을 건별로 보여 주고(2단계), 건을 누르면 바로 그 화면으로 간다.
   서버 동기화(직원별 캐시·다른 로그인의 늦은 응답 버리기·없는 대상 기록만 받기)는 notificationActions.ts */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { notificationsApi } from '@/api/endpoints/notifications';
import type { AppNotification } from '@/api/types/notification';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { useMe } from '@/shared/state/session';
import { Icon } from '@/shared/ui/Icon';
import { currentSignIn, markRead, notificationKey, refreshTarget, stillSignedIn } from './notificationActions';
import { notificationSub, notificationTarget, notificationTime, notificationTitle, splitNotifications, staffGroupSub, type StaffGroup } from './notificationView';

const POLL_MS = 30_000;

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  // 2단계로 들어간 소속 직원 id. 창을 닫으면 처음 단계로 돌아간다
  const [staffId, setStaffId] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  // 2단계에서 돌아올 때 초점을 되돌릴 묶음(직원 id)
  const returnTo = useRef<string | null>(null);
  const qc = useQueryClient();
  const go = useGo();
  const { pathname } = useLocation();
  const owner = useMe()?.id || '';
  const q = useQuery({ queryKey: notificationKey(owner), queryFn: notificationsApi.inbox, refetchInterval: POLL_MS, enabled: !!owner });
  const items = q.data?.items || [];
  const unread = q.data?.unread || 0;
  const { mine, staff } = splitNotifications(items);
  // 새로 받은 목록에 그 직원의 알림이 없어졌으면 처음 단계를 보여 준다
  const group = staffId ? staff.find((g) => g.employee.id === staffId) : undefined;

  // 화면을 옮길 때마다 새로 받는다(로드맵 확정·보고서 작성 뒤 다음 화면으로 가면 바로 보이게). 처음 그릴 때는 useQuery 가 이미 받는다
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    void qc.invalidateQueries({ queryKey: notificationKey(owner) });
  }, [pathname, qc, owner]);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !boxRef.current?.contains(event.target)) {
        setOpen(false);
        setStaffId(null);
      }
    };
    document.addEventListener('pointerdown', closeOutside, true);
    return () => document.removeEventListener('pointerdown', closeOutside, true);
  }, [open]);

  // 단계를 옮기면 초점도 옮긴다: 들어가면 '뒤로' 버튼, 돌아오면 눌렀던 묶음
  useEffect(() => {
    if (staffId) {
      backRef.current?.focus();
      return;
    }
    const id = returnTo.current;
    returnTo.current = null;
    if (id) boxRef.current?.querySelector<HTMLButtonElement>(`[data-staff="${CSS.escape(id)}"]`)?.focus();
  }, [staffId]);

  const close = () => {
    setOpen(false);
    setStaffId(null);
  };

  const back = () => {
    returnTo.current = staffId;
    setStaffId(null);
  };

  const openItem = async (n: AppNotification) => {
    // 누른 로그인(t)이 기다리는 사이 로그아웃·다른 로그인(같은 직원의 재로그인 포함)이 되면 응답을 넣지도, 이동하지도 않는다(PR #84 리뷰 P1·P3)
    const t = currentSignIn();
    close();
    if (!t) return;
    if (!n.read) {
      try {
        await markRead(qc, t, n.id);
      } catch (err) {
        // 읽음 저장에 실패해도 보려던 화면으로는 간다(알림은 읽지 않은 채로 남는다)
        if (stillSignedIn(t)) failToast(err, '알림을 읽음으로 바꾸지 못했어요');
      }
    }
    if (!stillSignedIn(t)) return;
    if (n.audience === 'head') {
      // 직원 기록을 새로 받기 시작한 뒤 기다리지 않고 바로 옮긴다. 기다리면 지금 보고 있는 옛 보고서 화면이 새 기록(옛 보고서가
      // 지워진)으로 먼저 다시 그려져 직원 목록으로 튕긴다. 옮긴 화면은 받는 동안 '불러오는 중'을 보여 준다(TeamPages)
      void refreshTarget(qc, t, n);
      go(notificationTarget(n));
      return;
    }
    try {
      await refreshTarget(qc, t, n);
    } catch (err) {
      if (stillSignedIn(t)) failToast(err, '최신 기록을 불러오지 못했어요');
    }
    if (stillSignedIn(t)) go(notificationTarget(n));
  };

  const readAll = async () => {
    const t = currentSignIn();
    if (!t) return;
    try {
      await markRead(qc, t);
    } catch (err) {
      if (stillSignedIn(t)) failToast(err, '알림을 모두 읽음으로 바꾸지 못했어요');
    }
  };

  const toggle = () => {
    if (open) {
      close();
      return;
    }
    void q.refetch();
    setOpen(true);
  };

  /** bare: 직원 묶음 안(2단계)이라 직원 이름을 빼고 보여 준다 */
  const itemRow = (n: AppNotification, bare = false) => (
    <li key={n.id}>
      <button type="button" className={`notif-it${n.read ? '' : ' new'}`} onClick={() => void openItem(n)}>
        <span className="notif-dot" aria-hidden="true" />
        <span className="notif-tx">
          <b>{notificationTitle(n, bare)}</b>
          <small>{notificationSub(n)}</small>
        </span>
        <time dateTime={n.createdAt}>{notificationTime(n.createdAt)}</time>
        {n.read ? null : <span className="notif-sr">읽지 않음</span>}
      </button>
    </li>
  );

  const staffRow = (g: StaffGroup) => (
    <li key={g.employee.id}>
      <button type="button" className={`notif-it notif-grp${g.unread ? ' new' : ''}`} data-staff={g.employee.id} onClick={() => setStaffId(g.employee.id)}>
        <span className="notif-dot" aria-hidden="true" />
        <span className="notif-tx">
          <b>{g.employee.name} 님</b>
          <small>{staffGroupSub(g)}</small>
        </span>
        <span className="notif-end">
          <time dateTime={g.latestAt}>{notificationTime(g.latestAt)}</time>
          {g.unread ? (
            <span className="notif-badge" aria-hidden="true">
              {g.unread}
            </span>
          ) : null}
          <Icon name="right" />
        </span>
        <span className="notif-sr">{g.unread ? `읽지 않음 ${g.unread}건, ` : ''}눌러서 건별로 보기</span>
      </button>
    </li>
  );

  let body: React.ReactNode;
  if (group) {
    body = (
      <section className="notif-depth" aria-labelledby="notif-who">
        <div className="notif-back-h">
          <button type="button" ref={backRef} className="notif-back" aria-label="소속 직원 알림으로 돌아가기" onClick={back}>
            <Icon name="left" />
          </button>
          <span className="notif-who">
            <b id="notif-who">{group.employee.name} 님의 알림</b>
            <small>
              {group.items.length}건{group.unread ? ` · 읽지 않음 ${group.unread}건` : ''}
            </small>
          </span>
        </div>
        <ul className="notif-list">{group.items.map((n) => itemRow(n, true))}</ul>
      </section>
    );
  } else if (staff.length) {
    body = (
      <>
        {mine.length ? (
          <section className="notif-sec" aria-labelledby="notif-sec-mine">
            <h3 id="notif-sec-mine" className="notif-sec-h">
              <Icon name="user" />내 알림
            </h3>
            <ul className="notif-list">{mine.map((n) => itemRow(n))}</ul>
          </section>
        ) : null}
        <section className="notif-sec staff" aria-labelledby="notif-sec-staff">
          <h3 id="notif-sec-staff" className="notif-sec-h">
            <Icon name="users" />
            소속 직원 알림 <small>{staff.length}명</small>
          </h3>
          <ul className="notif-list">{staff.map(staffRow)}</ul>
        </section>
      </>
    );
  } else if (items.length) {
    // 부서장이 아니거나 소속 직원 알림이 없으면 예전처럼 한 목록
    body = <ul className="notif-list">{items.map((n) => itemRow(n))}</ul>;
  } else {
    body = q.isError ? null : <p className="notif-empty">{q.isPending ? '불러오는 중…' : '알림이 없어요'}</p>;
  }

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
          if (event.key === 'Escape') close();
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
            if (event.key !== 'Escape') return;
            // 2단계에서는 Esc 가 한 단계 뒤로, 처음 단계에서는 창을 닫는다
            if (group) back();
            else close();
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
          {body}
        </div>
      ) : null}
    </div>
  );
}
