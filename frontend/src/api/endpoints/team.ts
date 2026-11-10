/* 부서장 (API-55~59 · 보낸 코멘트 수정·삭제) */
import { enc, http } from '../client';
import type { CommentBody, MemberState, TeamList } from '../types/team';

export const teamApi = {
  members: () => http.get<TeamList>('/team/members'),
  member: (uid: string) => http.get<MemberState>(`/team/members/${enc(uid)}/plans`),
  comment: (pid: string, body: CommentBody) => http.post<{ commentId: string; userId: string }>(`/team/plans/${enc(pid)}/comments`, body),
  commentsSend: (pid: string, comments: CommentBody[]) =>
    http.post<{ commentIds: string[]; userId: string }>(`/team/plans/${enc(pid)}/comments`, { comments }),
  commentEdit: (pid: string, cid: string, body: CommentBody) =>
    http.patch<{ commentId: string; userId: string; changed: boolean }>(`/team/plans/${enc(pid)}/comments/${enc(cid)}`, body),
  commentDelete: (pid: string, cid: string) =>
    http.del<{ commentId: string; userId: string }>(`/team/plans/${enc(pid)}/comments/${enc(cid)}`),
};
