/* 로그아웃·초기화처럼 여러 상태를 함께 바꾸는 동작 */
import { paths } from '@/app/paths';
import { flush } from '@/features/draft/draftSync';
import { dataReset } from '@/shared/state/events';
import { logout } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';

export async function logoutAndReset(go: (to: string, o?: { force?: boolean }) => void): Promise<void> {
  await logout(flush);
  dataReset();
  go(paths.login, { force: true });
  toast('로그아웃했어요');
}
