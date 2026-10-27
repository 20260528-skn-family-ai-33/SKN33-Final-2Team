/* 서버 요청 실패를 쉬운 말로 알린다(원문은 콘솔에만 · 5차 GP.fail) */
import { isAbort } from '@/api/jobs';
import { cause } from '@/shared/state/ai';
import { toast } from '@/shared/state/ui';

export function failToast(err: unknown, what?: string): void {
  if (isAbort(err)) return;
  const c = cause(err);
  console.warn('GrowPath', what || '', c.raw || err);
  toast(`${what ? what + ' · ' : ''}${c.user}`);
}
