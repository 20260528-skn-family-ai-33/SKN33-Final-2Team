/* 부서장 화면 서버 데이터 (TanStack Query) — 소속 직원 목록과 직원별 기록(서버가 공개 범위만 줌).
   화면에 들어올 때 한 번 새로 받는다(5차 m-list 의 '목록 끝없이 다시 부르기' 같은 문제가 생기지 않음 · 10/26 고친 버그) */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { teamApi } from '@/api/endpoints/team';
import type { MemberState } from '@/api/types/team';
import { mergeReg, mergeRes } from '@/shared/state/catalog';
import { isSup, me } from '@/shared/state/session';
import { prepRec } from '@/shared/state/workspace';

export const teamKey = ['team'] as const;
export const memberKey = (uid: string) => ['team-member', uid] as const;

export function useTeam() {
  return useQuery({ queryKey: teamKey, queryFn: teamApi.members, enabled: isSup(me()) });
}

export function useMemberOf(uid: string | undefined) {
  const t = useTeam();
  return { team: t, member: (t.data?.members || []).map((m) => m.user).find((u) => u.id === String(uid)) || null };
}

export function useMemberState(uid: string | undefined) {
  return useQuery({
    queryKey: memberKey(String(uid)),
    enabled: !!uid,
    queryFn: async (): Promise<MemberState> => {
      const w = await teamApi.member(String(uid));
      mergeRes(w.res);
      mergeReg(w.reg);
      return { ...w, plans: Object.fromEntries(Object.entries(w.plans || {}).map(([k, R]) => [k, prepRec(R, null)])) };
    },
  });
}

export function useRefreshTeam() {
  const qc = useQueryClient();
  return async (uid?: string) => {
    await qc.invalidateQueries({ queryKey: teamKey });
    if (uid) await qc.invalidateQueries({ queryKey: memberKey(uid) });
  };
}

export const mk = (uid: string, x: string) => `${uid}~${x}`;
