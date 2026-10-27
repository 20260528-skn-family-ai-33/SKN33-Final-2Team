/* 작성 중인 로드맵 서버 동기화 (5차 gp-parts.js 의 syncDraft·flush·ensureDraft·takeDraft·pullDraft 를 옮김)
   화면이 고치는 값(목표·기획서 이름·세부 사항·응답·고른 안·수정 화면 입력·마지막 단계)은 고친 뒤 0.4초 기다렸다가 서버에 저장한다.
   에이전트 결과(문항·진단·3안·지원 조건·기획서 요약 상태)는 서버만 쓰고, 화면은 서버 응답으로 받는다 */
import { ApiError } from '@/api/client';
import { accountApi } from '@/api/endpoints/account';
import { draftsApi } from '@/api/endpoints/drafts';
import type { DraftResponse } from '@/api/types/draft';
import { mergeReg, mergeRes } from '@/shared/state/catalog';
import { me, setWorkspaceLoader } from '@/shared/state/session';
import { failToast } from '@/shared/lib/fail';
import { freshDraft, fromWorkspace, updateWs, useWs, ws, type WsState } from '@/shared/state/workspace';

const CLIENT = ['goal', 'project', 'prefs', 'detailsOk', 'answers', 'deepOn', 'deepMcq', 'deepEssay', 'chosen', 'edit'] as const;

const snap = (st: WsState): string =>
  JSON.stringify([CLIENT.map((k) => st.draft[k]), st.lastNew, st.draft.doc ? st.draft.doc.summary : null, (st.draft.gen && st.draft.gen.cur) || null]);
const hasContent = (st: WsState): boolean => !!(String(st.draft.goal || '').trim() || st.draft.detailsOk || st.draft.project);

/* 보고 있는 버전(genCur)은 사용자가 버전을 바꿨을 때만 보낸다. 백엔드(drafts._apply_client)는 genCur 를 받으면
   버전이 그대로여도 고른 안(draftPlan)을 지우므로, 늘 보내면 검토·확정 화면에서 고른 안이 사라진다(10/26 발견 · 백엔드 요청 목록 B-4) */
let serverGenCur = 'null';
const curJ = (st: WsState) => JSON.stringify((st.draft.gen && st.draft.gen.cur) || null);

function bodyOf(st: WsState): Record<string, unknown> {
  const d = st.draft;
  const b: Record<string, unknown> = Object.fromEntries(CLIENT.map((k) => [k, d[k]]));
  b.lastNew = st.lastNew;
  if (d.doc && d.doc.status === 'ok') b.docSummary = d.doc.summary || '';
  if (d.gen && d.gen.cur && curJ(st) !== serverGenCur) b.genCur = d.gen.cur;
  return b;
}

/** 서버 응답을 상태에 넣는 동안에는 자동 저장을 걸지 않는다(사용자 입력만 저장 · 5차와 같음) */
let applying = false;
let lastSent: string | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
/** 저장 줄: 저장마다 성공 여부로 끝난다(실패해도 줄은 이어지고 다음 저장이 다시 시도한다) */
let queue: Promise<boolean> = Promise.resolve(true);
let pending: (() => Record<string, unknown>) | null = null;
let saveError: unknown = null;

/** 작성 내용 저장이 실패해 다음 작업(문항·진단·3안 생성, 안 고르기, 확정)을 멈췄다는 표시. 저장 실패 알림은 이미 띄웠다(PR #23 리뷰 2026-10-27) */
export class DraftSaveError extends Error {
  constructor(readonly original: unknown) {
    super('작성 내용을 저장하지 못했어요');
    this.name = 'DraftSaveError';
  }
}

/** 서버 응답 → 상태. soft: 입력 저장 응답이라 화면이 고치는 값은 화면 것을 둔다(타이핑 중에 덮지 않게) */
export function takeDraftInto(st: WsState, r: Partial<DraftResponse> | null | undefined, soft = false): void {
  if (!r) return;
  mergeRes(r.res);
  mergeReg(r.reg);
  st.draftId = r.draftId || null;
  const server = r.draft || freshDraft();
  if (soft && st.draft) {
    const keep = Object.fromEntries(CLIENT.map((k) => [k, st.draft[k]]));
    const summary = st.draft.doc && server.doc ? st.draft.doc.summary : undefined;
    st.draft = { ...freshDraft(), ...server, ...keep };
    if (summary !== undefined && st.draft.doc) st.draft.doc.summary = summary;
  } else st.draft = { ...freshDraft(), ...server };
  st.draftPlan = r.draftPlan || null;
  if (!soft && r.lastNew !== undefined && r.lastNew !== null) st.lastNew = r.lastNew;
}

export function takeDraft(r: Partial<DraftResponse> | null | undefined, soft = false): void {
  const owner = ws().owner;
  applying = true;
  try {
    updateWs((s) => {
      if (s.owner === owner) takeDraftInto(s, r, soft);
    });
  } finally {
    applying = false;
  }
  if (r && r.draft) serverGenCur = JSON.stringify((r.draft.gen && r.draft.gen.cur) || null);
  if (!soft) lastSent = snap(ws());
}

function send(): Promise<boolean> {
  const make = pending;
  pending = null;
  if (!make) return queue;
  const owner = ws().owner;
  queue = queue.then(async () => {
    const body = make();
    const st = ws();
    if (st.owner !== owner) return true;
    try {
      const r = st.draftId ? await draftsApi.patch(st.draftId, body) : await draftsApi.create({ draft: body, lastNew: st.lastNew });
      if (ws().owner === owner) takeDraft(r, true);
      saveError = null;
      return true;
    } catch (err) {
      lastSent = null;
      // 작성 문서가 서버에서 없어졌으면 ensureDraft 가 지금 입력으로 새로 만든다
      if (err instanceof ApiError && err.status === 404) {
        updateWs((s) => void (s.draftId = null));
        return true;
      }
      saveError = err;
      failToast(err, '작성 내용을 저장하지 못했어요');
      return false;
    }
  });
  return queue;
}

/** 입력이 바뀌면(작성 문서의 화면 칸) 0.4초 뒤 서버에 저장한다 — 스토어 구독으로 자동 */
useWs.subscribe((st) => {
  if (applying || !st.owner || !me()) return;
  const s = snap(st);
  if (s === lastSent) return;
  if (!st.draftId && !hasContent(st)) return;
  clearTimeout(timer);
  pending = () => bodyOf(ws());
  timer = setTimeout(() => {
    lastSent = snap(ws());
    void send();
  }, 400);
});

/** 에이전트 호출 전에 쓰던 입력을 먼저 서버에 저장한다. 저장이 실패하면 DraftSaveError 로 멈춘다(서버의 예전 값으로 다음 작업을 하지 않게) */
export async function flush(): Promise<void> {
  const st = ws();
  if (!st.owner) return;
  clearTimeout(timer);
  if (snap(st) !== lastSent && (st.draftId || hasContent(st))) {
    lastSent = snap(st);
    pending = () => bodyOf(ws());
    void send();
  }
  if (!(await queue)) throw new DraftSaveError(saveError);
}

export async function ensureDraft(): Promise<string> {
  await flush();
  const st = ws();
  if (!st.draftId) {
    const r = await draftsApi.create({ draft: bodyOf(st), lastNew: st.lastNew });
    takeDraft(r);
  }
  return ws().draftId as string;
}

/** 서버 상태를 다시 읽는다(진행 중인 작업 확인용). 바뀌었으면 true */
export async function pullDraft(): Promise<boolean> {
  const st = ws();
  if (!st.draftId) return false;
  const before = JSON.stringify([st.draft, st.draftPlan]);
  try {
    takeDraft(await draftsApi.get(st.draftId), true);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404)
      updateWs((s) => {
        s.draftId = null;
        s.draft = freshDraft();
      });
    return true;
  }
  const after = ws();
  return JSON.stringify([after.draft, after.draftPlan]) !== before;
}

/** 작성 중인 로드맵 서버 호출: 입력을 먼저 저장하고(작성 시작 포함) 부른 뒤, 응답(작성 문서)을 상태에 넣는다 */
export async function draftCall<T extends Partial<DraftResponse>>(what: string, fn: (id: string) => Promise<T>, opts?: { soft?: boolean }): Promise<T | null> {
  const owner = ws().owner;
  try {
    const id = await ensureDraft();
    const r = await fn(id);
    if (ws().owner !== owner) return null;
    if (r && r.draft !== undefined) takeDraft(r, opts?.soft);
    return r || ({} as T);
  } catch (err) {
    if (!(err instanceof DraftSaveError)) failToast(err, what);
    return null;
  }
}

/** 로그인 직원의 작업 공간 읽기(세션이 부른다) */
setWorkspaceLoader(async () => {
  const u = me();
  if (!u) return;
  const w = await accountApi.workspace();
  const st = fromWorkspace(w, u.id, (s, d) => takeDraftInto(s, d));
  applying = true;
  useWs.setState(st, true);
  applying = false;
  serverGenCur = curJ(ws());
  lastSent = snap(ws());
});

export const reloadWorkspace = async (): Promise<void> => {
  const u = me();
  if (!u) return;
  const w = await accountApi.workspace();
  const keep = { lastRoute: ws().lastRoute };
  const st = fromWorkspace(w, u.id, (s, d) => takeDraftInto(s, d));
  applying = true;
  useWs.setState({ ...st, ...keep }, true);
  applying = false;
  serverGenCur = curJ(ws());
  lastSent = snap(ws());
};
