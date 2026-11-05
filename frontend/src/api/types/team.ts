/* 부서장 (API-55~59) — 서버가 소속 관계를 확인하고 공개 범위만 보낸다(메모·첨부·진단·작성 중인 로드맵 제외) */
import type { User } from './account';
import type { RegBundle, ResourceMap } from './catalog';
import type { PlanRecord, Report } from './plan';

/** 부서장 화면이 받는 직원 정보: 소속·직급·직위와 부서장 여부만(평정·본인 입력 등은 서버가 보내지 않음 · PR #23 리뷰) */
export type TeamUser = Pick<User, 'id' | 'code' | 'name' | 'role' | 'dept' | 'parentDept' | 'grade' | 'position' | 'supervisor'>;

export interface TeamMember {
  user: TeamUser;
  activePlans: number;
  pastPlans: number;
  reports: number;
  unreadComments: number;
  /** 부서장이 아직 확인하지 않은(알림을 읽지 않은) 이 직원의 로드맵·보고서 수(#96) */
  unseenPlans: number;
  unseenReports: number;
}

export interface TeamList {
  group: { name: string; id: string } | null;
  members: TeamMember[];
}

export interface MemberState {
  user: TeamUser;
  plans: Record<string, PlanRecord>;
  reports: Report[];
  res?: ResourceMap;
  reg?: RegBundle;
  /** 부서장이 아직 확인하지 않은 로드맵 id·보고서 id(#96) */
  unseen?: { plans: string[]; reports: string[] };
}

export interface CommentBody {
  fit: string;
  fitText: string;
  level: string;
  levelText: string;
  free: string;
}
