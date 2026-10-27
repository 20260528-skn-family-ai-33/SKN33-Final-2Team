/* 부서장 (API-55~59) — 서버가 소속 관계를 확인하고 공개 범위만 보낸다(메모·첨부·진단·작성 중인 로드맵 제외) */
import type { User } from './account';
import type { RegBundle, ResourceMap } from './catalog';
import type { PlanRecord, Report } from './plan';

export interface TeamMember {
  user: User;
  activePlans: number;
  pastPlans: number;
  reports: number;
  unreadComments: number;
}

export interface TeamList {
  group: { name: string; id: string } | null;
  members: TeamMember[];
}

export interface MemberState {
  user: User;
  plans: Record<string, PlanRecord>;
  reports: Report[];
  res?: ResourceMap;
  reg?: RegBundle;
}

export interface CommentBody {
  fit: string;
  fitText: string;
  level: string;
  levelText: string;
  free: string;
}
