/* 화면 주소 (5차 해시 주소 → 경로 주소). 5차 화면 ID 와의 대응은 docs/구조_설명.md 표에 있다.
   화면 코드는 문자열을 직접 쓰지 않고 이 함수만 쓴다(주소를 바꿀 때 한 곳만 고치게) */
export const paths = {
  login: '/login',
  home: '/',
  me: '/me',
  // 새 로드맵 작성
  newGoal: '/new/goal',
  newDetails: '/new/details',
  newDetailsCheck: '/new/details/check',
  newQuiz: '/new/quiz',
  newResult: '/new/result',
  newResultEdit: '/new/result/edit',
  newGen: '/new/generating',
  newOptions: '/new/options',
  newMaterials: '/new/materials',
  newReview: '/new/review',
  // 내 로드맵
  roadmaps: '/roadmaps',
  roadmap: (pid: string) => `/roadmaps/${pid}`,
  confirmed: (pid: string) => `/roadmaps/${pid}/confirmed`,
  revise: (pid: string) => `/roadmaps/${pid}/revise`,
  comments: (pid: string) => `/roadmaps/${pid}/comments`,
  post: (pid: string) => `/roadmaps/${pid}/post`,
  // 점검·보고서
  checks: '/checks',
  report: (rid: string) => `/reports/${rid}`,
  // 학습 자료
  resources: '/resources',
  resource: (id: string) => `/resources/${encodeURIComponent(id)}`,
  // 부서장
  team: '/team',
  member: (uid: string) => `/team/${uid}`,
  memberPlan: (uid: string, pid: string) => `/team/${uid}/plans/${pid}`,
  memberReport: (uid: string, rid: string) => `/team/${uid}/reports/${rid}`,
  commentSent: (uid: string, pid: string) => `/team/${uid}/plans/${pid}/sent`,
  // 관리자
  admin: '/admin',
  adminData: (ds: string) => `/admin/data/${ds}`,
  adminRegulations: '/admin/regulations',
  adminPreview: (uploadId: string) => `/admin/uploads/${uploadId}`,
  adminHistory: '/admin/history',
} as const;

/** 작성 단계 화면 순서(앞 단계를 바꾸고 앞으로 넘어갈 때만 확인 창을 띄운다) */
export const NEW_ORDER = [
  paths.newGoal,
  paths.newDetails,
  paths.newDetailsCheck,
  paths.newQuiz,
  paths.newResult,
  paths.newResultEdit,
  paths.newGen,
  paths.newOptions,
  paths.newMaterials,
  paths.newReview,
] as string[];

/** 5차 화면 ID(lastNew 에 저장된 값) → 경로. 서버 작성 문서의 lastNew 는 5차 ID 로 저장돼 있어 서로 바꿔 쓴다 */
const NEW_ID_TO_PATH: Record<string, string> = {
  'new-goal': paths.newGoal,
  'new-details': paths.newDetails,
  'new-details-check': paths.newDetailsCheck,
  'new-quiz': paths.newQuiz,
  'new-result': paths.newResult,
  'new-result-edit': paths.newResultEdit,
  'new-gen': paths.newGen,
  'new-options': paths.newOptions,
  'new-materials': paths.newMaterials,
  'new-review': paths.newReview,
};
export const newIdToPath = (id: string | null | undefined): string => (id && NEW_ID_TO_PATH[id]) || paths.newGoal;

/** 서버가 돌려주는 5차 화면 ID(시연 단계 이동의 entry 등) → 경로. 예: 'post:abc' → /roadmaps/abc/post */
export function legacyToPath(id: string | null | undefined): string {
  if (!id) return paths.home;
  const [k, p] = String(id).split(':');
  if (NEW_ID_TO_PATH[k]) return NEW_ID_TO_PATH[k];
  if (!p) return ({ home: paths.home, roadmap: paths.roadmaps, checks: paths.checks, resources: paths.resources, me: paths.me } as Record<string, string>)[k] || paths.home;
  const by: Record<string, (x: string) => string> = { confirmed: paths.confirmed, roadmap: paths.roadmap, revise: paths.revise, comment: paths.comments, post: paths.post, report: paths.report, res: paths.resource };
  return by[k] ? by[k](p) : paths.home;
}
export const pathToNewId = (p: string): string | null => Object.entries(NEW_ID_TO_PATH).find(([, v]) => v === p)?.[0] || null;
