/* 부서장이 직원의 로드맵·보고서 화면을 열면 그 대상의 알림을 읽음으로 바꾼다(#96).
   알림 창에서 누르지 않고 소속 직원 계획에서 직접 들어와도 '확인함'이 되게 한다 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import type { NotificationTargetKind } from '@/api/types/notification';
import { currentSignIn, markTargetRead, stillSignedIn } from '@/features/notifications/notificationActions';
import { failToast } from '@/shared/lib/fail';

/** ready: 그 기록이 화면에 실제로 보일 때만(teamList.detailShown · 로딩 중이거나 없어서 목록으로 돌려보내는 중에는 읽음으로 바꾸지 않는다) */
export function useMarkSeen(kind: NotificationTargetKind, id: string, ready: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!ready || !id) return;
    const t = currentSignIn();
    if (!t) return;
    markTargetRead(qc, t, kind, id).catch((err) => {
      // 확인 표시만 못 남긴 것이라 화면은 그대로 둔다(다음에 열 때 다시 시도)
      if (stillSignedIn(t)) failToast(err, '확인 표시를 저장하지 못했어요');
    });
  }, [qc, kind, id, ready]);
}
