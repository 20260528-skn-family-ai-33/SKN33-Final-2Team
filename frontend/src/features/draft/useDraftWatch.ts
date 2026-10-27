/* 진행 중인 작업(문항·진단·3안·지원 조건·기획서 요약)이 있으면 1.2초마다 서버 상태를 다시 읽는다.
   화면을 떠나거나 작업이 끝나면 멈추고, 10분이 지나도 멈춘다 (5차 P.watchDraft 를 화면 생명주기에 묶음) */
import { useEffect } from 'react';
import { useWs } from '@/shared/state/workspace';
import { busyDraft } from './model';
import { pullDraft } from './draftSync';

export function useDraftWatch(): void {
  const busy = useWs((s) => !!s.owner && busyDraft(s.draft));
  useEffect(() => {
    if (!busy) return;
    let stop = false;
    let t: ReturnType<typeof setTimeout>;
    const until = Date.now() + 600000;
    const tick = async () => {
      if (stop || Date.now() > until) return;
      await pullDraft();
      if (!stop) t = setTimeout(tick, 1200);
    };
    t = setTimeout(tick, 900);
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [busy]);
}
