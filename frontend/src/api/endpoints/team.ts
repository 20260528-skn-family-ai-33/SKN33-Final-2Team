/* 부서장 (API-55~59 · 보낸 코멘트 고치기는 설계서 밖 추가 10/23, 삭제 API 없음) */
import { enc, http } from '../client';
import type { CommentBody, MemberState, TeamList } from '../types/team';

export const teamApi = {
  members: () => http.get<TeamList>('/team/members'),
  member: (uid: string) => http.get<MemberState>(`/team/members/${enc(uid)}/plans`),
  comment: (pid: string, body: CommentBody) => http.post<{ commentId: string; userId: string }>(`/team/plans/${enc(pid)}/comments`, body),
  commentEdit: (pid: string, cid: string, body: CommentBody) =>
    http.patch<{ commentId: string; userId: string; changed: boolean }>(`/team/plans/${enc(pid)}/comments/${enc(cid)}`, body),
};
