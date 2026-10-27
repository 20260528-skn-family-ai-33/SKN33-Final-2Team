/* 로그인한 직원의 작업 공간 (5차 gp-core.js 의 S·OWN 과 gp-parts.js 의 상태 틀을 옮김)
   서버 기록: draft·draftId·draftPlan·lastNew(작성 중인 로드맵) · plans(확정 로드맵) · reports(결과 보고서)
   화면 상태(브라우저 저장소 · 직원별): demoOpen·mgr(쓰는 중인 코멘트)·mcEdit(고치는 중인 보낸 코멘트)·revs(쓰는 중인 수정 요청)·meEdit·regenReq·picks·lastRoute
   작성 중인 로드맵의 입력은 고칠 때마다 잠깐 기다렸다가 서버에 저장한다(features/draft/draftSync.ts) */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { DraftDoc, Prefs } from '@/api/types/draft';
import type { PlanContent, PlanRecord, Report, RevForm, Workspace } from '@/api/types/plan';
import { mergeReg, mergeRes } from './catalog';

export const emptyPrefs = (): Prefs => ({ format: '', cert: '', hours: '', weeks: '', budget: '', etc: '' });

export const freshDraft = (): DraftDoc => ({
  goal: '',
  project: null,
  prefs: emptyPrefs(),
  detailsOk: false,
  quiz: null,
  answers: {},
  deepOn: false,
  deepMcq: {},
  deepEssay: {},
  diag: null,
  startStage: null,
  fix: null,
  edit: null,
  handoff: null,
  gen: null,
  chosen: null,
  quizFail: null,
  diagFail: null,
  genRun: null,
  doc: null,
  genPrefs: null,
  quizRun: null,
  diagRun: null,
});

/** 부서장이 쓰는 중인 코멘트(열쇠: '직원~로드맵' · 고치는 중이면 '직원~로드맵~코멘트') */
export interface MgrDraft {
  fit?: string;
  fitText?: string;
  level?: string;
  levelText?: string;
  free?: string;
  orig?: Omit<MgrDraft, 'orig'>;
}

/** 실행 기록 창에서 쓰는 중인 값 */
export interface RecTmp {
  pid: string;
  id: string;
  status: string;
  memo: string;
}

/** 3안 중 하나 다시 만들기 창에서 쓰는 중인 요청 */
export interface RegenReq {
  pid: string;
  note: string;
  chips: string[];
  /** 활동 id → remove·replace */
  acts: Record<string, string>;
}

export interface WsState {
  owner: string | null;
  draft: DraftDoc;
  draftId: string | null;
  draftPlan: PlanContent | null;
  lastNew: string | null;
  plans: Record<string, PlanRecord>;
  reports: Report[];
  demoOpen: boolean;
  mgr: Record<string, MgrDraft>;
  mcEdit: string | null;
  tmp: RecTmp | null;
  meEdit: Record<string, unknown> | null;
  regenReq: RegenReq | null;
  picks: string[];
  lastRoute: string | null;
}

export const freshWs = (owner: string | null = null): WsState => ({
  owner,
  draft: freshDraft(),
  draftId: null,
  draftPlan: null,
  lastNew: null,
  plans: {},
  reports: [],
  demoOpen: false,
  mgr: {},
  mcEdit: null,
  tmp: null,
  meEdit: null,
  regenReq: null,
  picks: [],
  lastRoute: null,
});

export const useWs = create<WsState>()(immer(() => freshWs()));

/** immer 로 고친다: updateWs(s => { s.draft.goal = '…' }) */
export const updateWs = (fn: (s: WsState) => void): void => useWs.setState(fn);
export const ws = (): WsState => useWs.getState();

/* ── 브라우저 저장소 (화면 상태만 · 직원별) ── */
const UI_KEY = (id: string) => 'growpath.ui.' + id;
const UI_FIELDS = ['demoOpen', 'mgr', 'mcEdit', 'meEdit', 'regenReq', 'picks', 'lastRoute'] as const;

export const store = {
  get(k: string): string | null {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  set(k: string, v: string): void {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* 저장 불가 환경 */
    }
  },
};

function readUi(id: string): Partial<WsState> & { revs?: Record<string, RevForm> } {
  try {
    return JSON.parse(store.get(UI_KEY(id)) || '{}') || {};
  } catch {
    return {};
  }
}

let uiTimer: ReturnType<typeof setTimeout> | undefined;
useWs.subscribe((s) => {
  if (!s.owner) return;
  clearTimeout(uiTimer);
  uiTimer = setTimeout(() => {
    const cur = ws();
    if (!cur.owner) return;
    const ui: Record<string, unknown> = Object.fromEntries(UI_FIELDS.map((k) => [k, cur[k]]));
    ui.revs = Object.fromEntries(
      Object.entries(cur.plans)
        .filter(([, R]) => R.rev)
        .map(([id, R]) => [id, { ...R.rev, running: false, fail: null }]),
    );
    store.set(UI_KEY(cur.owner), JSON.stringify(ui));
  }, 150);
});

/** 로드맵 기록 하나를 화면 형식으로: 쓰는 중인 수정 요청(rev)은 브라우저에 두고, 서버 수정안 상태를 이어 붙인다 */
export function prepRec(R: PlanRecord, rev: RevForm | null | undefined): PlanRecord {
  R.rev = rev || null;
  const rv = R.revision;
  if (rv && R.rev) {
    R.rev.running = rv.status === 'running';
    R.rev.fail = rv.status === 'failed' ? rv.error || {} : null;
    R.rev.jobId = rv.status === 'running' ? rv.jobId : null;
  } else if (rv && rv.status !== 'ready' && rv.request) {
    R.rev = {
      ...({ on: {}, v: {}, note: '' } as unknown as RevForm),
      ...(rv.request as unknown as RevForm),
      running: rv.status === 'running',
      fail: rv.status === 'failed' ? rv.error || {} : null,
      jobId: rv.jobId,
    };
  }
  if (R.pending && R.rev == null && rv && rv.request) R.rev = { ...({ on: {}, v: {}, note: '' } as unknown as RevForm), ...(rv.request as unknown as RevForm) };
  R.post = R.post || { answers: {}, goalSelf: '', file: null };
  return R;
}

/** 서버가 보낸 로드맵 하나를 상태에 넣는다(쓰는 중인 수정 요청은 이어 둔다) */
export function putRec(s: WsState, R: PlanRecord): PlanRecord {
  const old = s.plans[R.id];
  const prev = old && old.rev ? JSON.parse(JSON.stringify(old.rev)) : null;
  s.plans[R.id] = prepRec(R, prev);
  if (old && old.rev && !R.revision) s.plans[R.id].rev = old.rev.running ? null : prev;
  return s.plans[R.id];
}

/** 서버 작업 공간(작성 중인 로드맵·확정 로드맵·보고서) → 상태 */
export function fromWorkspace(w: Workspace, id: string, takeDraftInto: (s: WsState, r: Workspace['draft']) => void): WsState {
  const st = freshWs(id);
  const ui = readUi(id);
  UI_FIELDS.forEach((k) => {
    if (ui[k] !== undefined) (st as unknown as Record<string, unknown>)[k] = ui[k];
  });
  const revs = ui.revs || {};
  Object.entries(w.plans || {}).forEach(([pid, R]) => {
    st.plans[pid] = prepRec(R, revs[pid]);
  });
  st.reports = w.reports || [];
  mergeRes(w.res);
  mergeReg(w.reg);
  takeDraftInto(st, w.draft || ({} as Workspace['draft']));
  return st;
}

/* ── 자주 쓰는 읽기 ── */
export const recs = (s: Pick<WsState, 'plans'>, status?: string): PlanRecord[] => Object.values(s.plans || {}).filter((R) => !status || R.status === status);
export const newComments = (R: PlanRecord) => (R.comments || []).filter((c) => c.status === 'new');
export const planReports = (s: Pick<WsState, 'reports'>, R: PlanRecord) => s.reports.filter((r) => r.planId === R.id);
export const draftActive = (s: Pick<WsState, 'draft'>): boolean => !!(s.draft && (String(s.draft.goal || '').trim() || s.draft.detailsOk));
