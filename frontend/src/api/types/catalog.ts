/* 학습 자료·자격증·규정·스킬 지도 (API-22, 53, 54 + 설계서 밖 /skills/map) */

/** 학습 자료 하나(catalog._public). 팀 DB 에 없는 값은 규칙으로 채우고 estimated 에 그 칸 이름을 적는다 */
export interface ResourceCurriculum {
  coverage?: 'public_outline' | 'partial_outline' | 'sample' | 'description_only';
  item_count?: number;
  items?: { title: string; section?: string; description?: string; suspended?: boolean }[];
  source_url?: string;
}

export interface Resource {
  id: string;
  title: string;
  provider: string;
  kind: string; // 강좌 · 도서 · 자격 · 공식 문서
  format?: string;
  hours?: number | null;
  timeStatus?: 'confirmed' | 'estimated' | 'manual' | null;
  durationKind?: 'video' | 'learning' | 'manual' | null;
  durationSeconds?: number | null;
  timeNote?: string | null;
  cost?: number | null;
  stage?: number | null;
  real?: boolean;
  skills?: string[];
  audience?: string;
  prereq?: string;
  content?: string;
  detailsLoaded?: boolean;
  curriculum?: ResourceCurriculum | null;
  note?: string;
  url?: string;
  image?: string;
  type?: string; // course · book · cert · doc
  source?: string;
  checked?: string;
  estimated?: string[];
  certCode?: string | null;
  platform?: string;
  difficulty?: string;
  weeks?: number | null;
  author?: string | null;
}

export type ResourceMap = Record<string, Resource>;

export interface ResourceSearch {
  total: number;
  items: Resource[];
}

export interface Cert {
  id: string;
  res: string;
  short: string;
  sub: string;
  name: string;
  issuer: string;
  vendor: string | null;
  hours: number;
  url: string;
  image: string;
  group?: string;
}

export interface CertGroup {
  key: string;
  label: string;
  issuer: string;
  url: string;
  certs: Cert[];
}

export interface RegInfo {
  key: string;
  id?: string;
  name: string;
  category?: string;
  rev: string;
  effective: string;
  file?: string;
  overseas: boolean;
  group?: string;
}

export interface RegSet {
  group: string;
  label: string;
  org: string;
  regs: RegInfo[];
}

export type RegSets = Record<string, RegSet>;

export interface Article {
  id: string;
  reg: string;
  no: string;
  title: string;
  chapter: string;
  page: number;
  text: string;
  type: string;
  node: string;
  path: string;
  group: string;
  overseas: boolean;
  prev?: boolean;
  [k: string]: unknown;
}

/** 응답에 함께 오는 규정 조항 묶음 */
export interface RegBundle {
  articles?: Record<string, Article>;
  regs?: Record<string, RegInfo>;
}

export interface SkillMapData {
  skills: { id: number; name: string; category: string; resources: number }[];
  prerequisites: [number, number][];
  /** 선수 관계 초안(CSV)에서 스킬 이름을 찾지 못한 줄 */
  unmatched: { skill: string; prerequisite: string }[];
  prerequisiteSource: string;
}
