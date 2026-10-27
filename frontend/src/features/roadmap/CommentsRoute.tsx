/* 받은 코멘트 화면 진입 (5차 scr.comment guard): 그 로드맵이 있으면 그대로, 없으면 새 코멘트가 있는 진행 중 로드맵 → 코멘트가 있는 로드맵 → 홈 */
import { Navigate, useParams } from 'react-router';
import { paths } from '@/app/paths';
import { newComments, recs, useWs } from '@/shared/state/workspace';
import { CommentsPage } from './comments';

export function CommentsRoute() {
  const { pid } = useParams();
  const R = useWs((s) => (pid ? s.plans[pid] : undefined));
  const alt = useWs((s) => (recs(s, 'active').find((x) => newComments(x).length) || recs(s).find((x) => (x.comments || []).length))?.id);
  if (R) return <CommentsPage R={R} />;
  return <Navigate to={alt ? paths.comments(alt) : paths.home} replace />;
}
