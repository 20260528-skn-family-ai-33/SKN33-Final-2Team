/* 알림이 가리키는 화면을 이미 보고 있으면 그 알림을 읽음으로 바꾼다(#96).
   3안 생성처럼 화면에서 기다리다 결과를 본 일이 알림 창에 쌓이지 않게 하고, 보고 있는 화면의 내용도 새로 받는다 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import type { AppNotification } from '@/api/types/notification';
import { failToast } from '@/shared/lib/fail';
import { currentSignIn, markRead, refreshTarget, stillSignedIn } from './notificationActions';
import { viewedNow } from './notificationView';

export function useReadOnView(items: AppNotification[], pathname: string): void {
  const qc = useQueryClient();
  // 읽음 응답이 오기 전에 목록을 또 받아도 같은 알림을 두 번 처리하지 않게
  const busy = useRef(new Set<string>());
  useEffect(() => {
    const t = currentSignIn();
    if (!t) return;
    for (const n of viewedNow(items, pathname)) {
      if (busy.current.has(n.id)) continue;
      busy.current.add(n.id);
      Promise.all([markRead(qc, t, n.id), refreshTarget(qc, t, n)])
        .catch((err) => {
          if (stillSignedIn(t)) failToast(err, '알림을 읽음으로 바꾸지 못했어요');
        })
        .finally(() => busy.current.delete(n.id));
    }
  }, [qc, items, pathname]);
}
