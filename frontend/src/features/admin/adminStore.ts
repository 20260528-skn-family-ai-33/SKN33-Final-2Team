/* 관리자 화면 상태 (5차 gp-admin.js 의 st) — 시트 탭·찾기·쪽·미리보기 필터, 한 건 고치기 패널.
   서버 데이터(행·개요·이력)는 adminData.ts 의 TanStack Query 가 맡고, 여기는 화면에만 있는 값만 둔다.
   한 건 고치기 칸 값은 표·엑셀과 같은 글자(Y/N, 2024-03-02, 세미콜론 목록)로 다루고 서버가 같은 규칙으로 읽는다 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { AdminColumn, AdminRow, AdminRows, DatasetId, EditRow, RowView, SheetInfo } from '@/api/types/admin';
import { onDataReset } from '@/shared/state/events';
import { DS } from './datasets';

type Vals = Record<string, string>;

export interface EditState {
  /** 열 때마다 새 번호(늦게 온 응답이 다른 패널을 고치지 않게 · 패널이 다시 미끄러져 들어오게) */
  id: number;
  ds: DatasetId;
  sheet: string;
  mode: 'edit' | 'add';
  cols: AdminColumn[];
  info: SheetInfo;
  key: Vals | null;
  orig: Vals;
  vals: Vals;
  /** 칸 머리글 → 오류 문구 */
  errs: Vals;
  /** 칸이 없는 오류(열쇠·시트 사이 검사) */
  msgs: string[];
  busy: boolean;
  /** 오류가 생기면 올려서 패널이 첫 오류 칸으로 옮겨 가게 한다 */
  focusErr: number;
}

export interface Pending {
  editId: number;
  ds: DatasetId;
  rows: EditRow[];
  token: string;
}

/** 창·화면의 고르기 값 (목표 후보 모드 · goalsAll 은 mock·employee·ollama·openai) */
export type Choice = 'goalsAll' | 'editGoal' | 'applyGoal';

/** 목표 후보 다시 만들기 창: 대상(재직 직원 모두 / 고른 직원만)·고른 직원·찾기 글자 */
export interface GoalPick {
  target: 'all' | 'pick';
  picked: number[];
  q: string;
}

interface AdminUi {
  tab: Partial<Record<DatasetId, string>>;
  q: Record<string, string>;
  page: Record<string, number>;
  filter: string;
  /** 여러 건 고치기(엑셀·CSV) 펼침 */
  bulk: boolean;
  /** 미리보기 만드는 중 */
  busy: boolean;
  edit: EditState | null;
  pending: Pending | null;
  saving: boolean;
  choice: Record<Choice, string>;
  goal: GoalPick;
}

const fresh = (): AdminUi => ({
  tab: {},
  q: {},
  page: {},
  filter: 'all',
  bulk: false,
  busy: false,
  edit: null,
  pending: null,
  saving: false,
  choice: { goalsAll: 'mock', editGoal: 'employee', applyGoal: 'mock' },
  goal: { target: 'all', picked: [], q: '' },
});

export const useAdmin = create<AdminUi>()(immer(fresh));
export const adm = () => useAdmin.getState();
export const setAdm = useAdmin.setState;

/* 로그아웃·초기화: 다른 관리자에게 이전 화면 상태가 남지 않게 */
onDataReset(() => useAdmin.setState(fresh(), true));

export const curSheet = (s: AdminUi, ds: DatasetId): string => s.tab[ds] || DS[ds].sheets[0];
export const qKey = (ds: string, sheet: string) => ds + sheet;
export const setChoice = (k: Choice, v: string) => setAdm((s) => void (s.choice[k] = v));
export const setGoal = (v: Partial<GoalPick>) => setAdm((s) => void Object.assign(s.goal, v));
/** 직원 고르기: ids 를 모두 넣거나(on) 모두 뺀다 */
export const pickGoal = (ids: number[], on: boolean) =>
  setAdm((s) => {
    const cur = new Set(s.goal.picked);
    ids.forEach((i) => (on ? cur.add(i) : cur.delete(i)));
    s.goal.picked = [...cur];
  });

/* ── 칸 값 다루기 ── */
export const norm = (v: unknown): string =>
  String(v == null ? '' : v)
    .split(/[;\n]/)
    .map((x) => x.trim())
    .filter(Boolean)
    .join('; ');
export const splitList = (v: unknown): string[] =>
  String(v || '')
    .split(/[;\n]/)
    .map((x) => x.trim())
    .filter(Boolean);
export const keyOf = (cols: AdminColumn[], r: AdminRow): Vals => Object.fromEntries(cols.filter((c) => c.key).map((c) => [c.field, r[c.field] || '']));
export const sameKey = (a: Vals | null, b: Vals | null): boolean => !!(a && b) && Object.keys(a).every((f) => String(a[f]) === String(b[f]));

let nextId = 1;
export function newEdit(ds: DatasetId, sheet: string, d: AdminRows, r: AdminRow | null): EditState {
  const orig = Object.fromEntries(d.columns.map((c) => [c.field, r ? r[c.field] || '' : c.default || '']));
  return {
    id: nextId++,
    ds,
    sheet,
    mode: r ? 'edit' : 'add',
    cols: d.columns,
    info: d.sheetInfo,
    key: r ? keyOf(d.columns, r) : null,
    orig,
    vals: { ...orig },
    errs: {},
    msgs: [],
    busy: false,
    focusErr: 0,
  };
}

/** 패널에서 고칠 칸: 추가할 때는 번호를 서버가 정하는 열쇠를 빼고, 고칠 때는 열쇠를 뺀다 */
export const editable = (ed: EditState): AdminColumn[] => ed.cols.filter((c) => !c.readonly && (ed.mode === 'add' ? !(c.key && ed.info.autoKey) : !c.key));

/** 저장하지 않은 칸이 있는지 */
export const dirty = (ed: EditState | null): boolean => !!ed && ed.cols.some((c) => !c.readonly && norm(ed.vals[c.field]) !== norm(ed.orig[c.field]));

/** 서버에 보낼 행: 고칠 때는 바뀐 칸만, 추가할 때는 적은 칸만 */
export function editRows(ed: EditState, del: boolean): EditRow[] {
  if (del) return [{ sheet: ed.sheet, key: ed.key, delete: true }];
  const pick = (cols: AdminColumn[], box: Vals, base?: Vals) => {
    const out: Vals = {};
    cols.forEach((c) => {
      if (base ? norm(box[c.field]) !== norm(base[c.field]) : norm(box[c.field]) !== '') out[c.field] = box[c.field] || '';
    });
    return out;
  };
  if (ed.mode === 'edit') return [{ sheet: ed.sheet, key: ed.key, values: pick(ed.cols.filter((c) => !c.readonly && !c.key), ed.vals, ed.orig) }];
  return [{ sheet: ed.sheet, key: null, values: pick(ed.cols.filter((c) => !c.readonly && !(c.key && ed.info.autoKey)), ed.vals) }];
}

/** 서버 오류를 칸 옆에 붙인다. 칸이 없는 오류(열쇠·시트 사이 검사)는 패널 위에 */
export function placeErrors(ed: EditState, rows: RowView[]): void {
  ed.errs = {};
  ed.msgs = [];
  const shown = new Set(editable(ed).map((c) => c.header));
  rows.forEach((r) => {
    (r.errors || []).forEach((e) => {
      if (shown.has(e.col) && !ed.errs[e.col]) ed.errs[e.col] = e.msg;
      else ed.msgs.push(`${e.col} · ${e.msg}`);
    });
  });
}

/** 칸 하나 고치기. 고치면 그 칸의 오류 표시를 지운다 */
export function setVal(field: string, header: string, v: string): void {
  setAdm((s) => {
    const ed = s.edit;
    if (!ed) return;
    ed.vals[field] = v;
    delete ed.errs[header];
  });
}
