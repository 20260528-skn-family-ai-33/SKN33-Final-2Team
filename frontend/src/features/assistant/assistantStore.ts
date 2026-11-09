/* 사내 생활 도우미 상태 (5차 gp-reg.js 를 옮김)
   · 이어 묻기: 답을 받은 최근 5턴을 에이전트에 넘긴다
   · 기록: 탭을 닫을 때까지 남는다(sessionStorage). 새로 고쳐도, 화면을 옮겨도 이어진다. '새 대화'로 지운다
   · 답을 쓰는 동안: 입력창은 그대로 쓸 수 있고 보내기 자리에 '멈추기'가 나온다. 써 둔 질문은 지우지 않는다 */
import { create } from 'zustand';
import { assistantApi, type AssistantAnswer, type AssistantResult, type HistoryTurn } from '@/api/endpoints/assistant';
import { cancelJob, waitJob } from '@/api/jobs';
import { cause, type Cause } from '@/shared/state/ai';
import { mergeReg } from '@/shared/state/catalog';
import { onDataReset } from '@/shared/state/events';
import { meOf, useSession } from '@/shared/state/session';

/** 말풍선: {me, t} 내 질문 · {q, group, a} 답 · {q, wait} 답 쓰는 중 · {q, fail} 실패 · {q, stop, cut} 멈춤(cut: 새로 고쳐 끊김) */
export type Msg = { me: true; t: string } | { q: string; group?: string; a?: AssistantAnswer; mlLabel?: string; demo?: boolean; wait?: boolean; fail?: Cause; stop?: boolean; cut?: boolean; me?: undefined };

const LOG_KEY = 'log';
const DRAFT_KEY = 'draft';
const OPEN_KEY = 'open';
const HISTORY_LIMIT = 5;
let employeeId = meOf(useSession.getState().account)?.id;
const storageKey = (k: string) => `growpath.assistant.${employeeId}.${k}`;
const ss = {
  get(k: string) {
    try {
      return employeeId === undefined ? null : sessionStorage.getItem(storageKey(k));
    } catch {
      return null;
    }
  },
  set(k: string, v: string) {
    try {
      if (employeeId !== undefined) sessionStorage.setItem(storageKey(k), v);
    } catch {
      /* 저장 불가 환경은 메모리만 */
    }
  },
};

/** 답을 쓰는 중에 새로 고쳤으면 그 답은 '끊김'으로 바꾼다. 다시 보내지 않는다(다시 시도는 사용자가 누를 때만) */
function load(): Msg[] {
  try {
    const v = JSON.parse(ss.get(LOG_KEY) || '[]');
    return Array.isArray(v) ? v.filter(Boolean).map((m: Msg) => (!m.me && m.wait ? { q: m.q, stop: true, cut: true } : m)) : [];
  } catch {
    return [];
  }
}

interface S {
  open: boolean;
  log: Msg[];
  input: string;
  hint: string;
  confirm: boolean;
  running: boolean;
  /** 패널이 닫힌 채 답이 오면 버튼에 표시 */
  fresh: boolean;
}

const initialState = (): S => ({
  open: ss.get(OPEN_KEY) === '1',
  log: load(),
  input: ss.get(DRAFT_KEY) || '',
  hint: '',
  confirm: false,
  running: false,
  fresh: false,
});

export const useAssistant = create<S>(initialState);

const get = () => useAssistant.getState();
const setLog = (log: Msg[]) => {
  useAssistant.setState({ log });
  ss.set(LOG_KEY, JSON.stringify(log));
};

/* 지금 답을 쓰는 중인 말풍선 */
let run: { i: number; ctrl: AbortController; job: string | null } | null = null;

useSession.subscribe(({ account }) => {
  const nextEmployeeId = meOf(account)?.id;
  if (employeeId === nextEmployeeId) return;
  run?.ctrl.abort();
  run = null;
  ss.set(LOG_KEY, '[]');
  ss.set(DRAFT_KEY, '');
  ss.set(OPEN_KEY, '0');
  employeeId = nextEmployeeId;
  useAssistant.setState(initialState());
});

const brief = (a: AssistantAnswer): HistoryTurn['a'] => ({
  kind: a.kind,
  level: a.level,
  source: a.source || '',
  summary: a.summary,
  basis: a.basis || [],
  intranet: a.intranet || [],
  question: a.question || '',
  options: a.options || [],
});
/** 이 말풍선(i) 앞까지 답을 받은 최근 질문·답을 넘긴다. */
const historyBefore = (i: number): HistoryTurn[] =>
  get()
    .log.slice(0, i)
    .filter((m): m is Extract<Msg, { q: string }> => !m.me && !!m.a && m.a.kind !== 'out')
    .slice(-HISTORY_LIMIT)
    .map((m) => ({ q: m.q, a: brief(m.a as AssistantAnswer) }));

export const setHint = (hint: string) => useAssistant.setState({ hint });
export function setInput(v: string): void {
  useAssistant.setState({ input: v });
  ss.set(DRAFT_KEY, v);
}

const ALL_EMPLOYEE_GROUPS = ['일반직', '실무직', '운영직', '전문직', '특정직', '청원경찰', '특수직', '기간제근로자'];

const isGroupOption = (val: string) =>
  ALL_EMPLOYEE_GROUPS.includes(val) || val.endsWith('직') || val === '청원경찰' || val === '기간제근로자';

function findPreviousQuestion(): string {
  const logs = get().log;
  for (let idx = logs.length - 1; idx >= 0; idx--) {
    const m = logs[idx];
    if (m.me && m.t && !isGroupOption(m.t.trim())) {
      return m.t.trim();
    }
    if (!m.me && m.q && !isGroupOption(m.q.trim())) {
      return m.q.trim();
    }
  }
  return '';
}

/** i 번째 말풍선 자리에 답을 채운다 (다시 시도하면 그 자리에 그대로). 멈추면 기다리기를 그만두고 서버 작업도 멈춘다 */
async function answer(q: string, i: number, group?: string): Promise<void> {
  const ctrl = new AbortController();
  run = { i, ctrl, job: null };
  const log = get().log.slice();
  log[i] = { q, group, wait: true };
  setLog(log);
  useAssistant.setState({ running: true });
  let a: AssistantAnswer | null = null;
  let mlLabel: string | undefined;
  let demo = false;
  let err: unknown = null;
  try {
    const j = await assistantApi.ask(q, historyBefore(i), group, ctrl.signal);
    if (run?.ctrl !== ctrl) return;
    run.job = j.jobId;
    const out = await waitJob<AssistantResult>(j.jobId, { signal: ctrl.signal });
    if (run?.ctrl !== ctrl) return;
    mergeReg(out.reg);
    a = out.answer;
    mlLabel = out.meta?.classification?.label ?? ((out.answer as unknown as { ml_label?: string })?.ml_label);
    demo = out.meta?.mode === 'mock';
  } catch (e) {
    err = e;
  }
  /* 멈췄거나 새 대화를 시작했으면 늦게 온 답은 버린다 */
  if (ctrl.signal.aborted || !run || run.ctrl !== ctrl) return;
  run = null;
  const next = get().log.slice();
  next[i] = err ? { q, group, fail: cause(err) } : { q, group, a: a as AssistantAnswer, mlLabel, demo };
  setLog(next);
  useAssistant.setState({ running: false, hint: '', fresh: !get().open });
}

/** 보내기. 답을 쓰는 중이면 보내지 않고 입력창에 남겨 둔다(지우지 않음) */
export function ask(q: string, group?: string, displayText?: string): boolean {
  q = String(q || '').trim();
  if (!q || employeeId === undefined) return false;
  if (run) {
    setHint('지금 앞 질문의 답을 쓰고 있어요. 다 쓰면 보낼 수 있어요. 멈추려면 ■를 누르세요.');
    return false;
  }

  // 직군 선택 카드가 떠 있는 상태에서는 채팅 직접 입력으로 진행하지 않고 직군 선택 버튼을 누르도록 유도
  const logs = get().log;
  const lastBotMsg = [...logs].reverse().find((m) => !m.me && m.a);
  if (!group && lastBotMsg && !lastBotMsg.me && lastBotMsg.a?.kind === 'clarify') {
    setHint('위에서 직군을 먼저 선택해 주세요.');
    return false;
  }

  // 직군 파라미터(group)는 버튼 '선택' 시에만 전달되며, 채팅 입력 시에는 질문 텍스트 그대로 전송
  const effectiveQ = q;
  const effectiveGroup = group;
  const showText = displayText || q;

  const log = get().log.concat([{ me: true, t: showText }, { q: effectiveQ, group: effectiveGroup, wait: true }]);
  setLog(log);
  void answer(effectiveQ, log.length - 1, effectiveGroup);
  return true;
}

export function stop(): void {
  if (!run) return;
  const { i, ctrl, job } = run;
  run = null;
  ctrl.abort();
  if (job) cancelJob(job).catch(() => { });
  const log = get().log.slice();
  const m = log[i];
  if (m && !m.me) log[i] = { q: m.q, group: m.group, stop: true };
  setLog(log);
  useAssistant.setState({ running: false, hint: '' });
}

export function retry(i: number): void {
  const m = get().log[i];
  if (!m || m.me || !(m.fail || m.stop)) return;
  if (run) {
    setHint('지금 다른 질문의 답을 쓰고 있어요. 다 쓴 뒤에 다시 시도해 주세요.');
    return;
  }
  void answer(m.q, i, m.group);
}

/** 되묻기에서 직군 선택 버튼이나 추천 질문을 선택했을 때 실행 (선택 시에만 group 파라미터 적용) */
export function pick(q: string): void {
  const trimmed = String(q || '').trim();
  if (run) {
    if (!get().input.trim()) setInput(trimmed);
    setHint('앞 질문의 답을 쓰는 중이에요. 다 쓰면 보내 주세요.');
    return;
  }

  if (isGroupOption(trimmed)) {
    const prevQ = findPreviousQuestion();
    if (prevQ) {
      // 직군 버튼을 선택했을 때만 검색 대상 group에 직군을 전달하고, 검색어는 원래 질문(prevQ) 유지
      ask(prevQ, trimmed, trimmed);
      return;
    }
  }

  ask(trimmed);
}

/** 대화 지우기: 쓰는 중인 답은 멈추고, 입력창에 써 둔 글은 남긴다 */
export function clearLog(): void {
  if (run) {
    run.ctrl.abort();
    if (run.job) cancelJob(run.job).catch(() => { });
    run = null;
  }
  setLog([]);
  useAssistant.setState({ running: false, hint: '' });
}

export function openAssistant(question?: string): void {
  useAssistant.setState({ open: true, fresh: false });
  ss.set(OPEN_KEY, '1');
  if (!question) return;
  /* 다른 화면의 '도우미에게 묻기': 답을 쓰는 중이면 보내지 않고 입력창에 넣어 둔다(써 둔 글이 있으면 그대로 둠) */
  if (!run) {
    ask(question);
    return;
  }
  if (!get().input.trim()) {
    setInput(question);
    setHint('앞 질문의 답을 쓰는 중이라 질문을 입력창에 넣어 뒀어요. 다 쓰면 보내 주세요.');
  } else setHint('앞 질문의 답을 쓰는 중이에요. 입력 중인 글은 그대로 뒀어요.');
}

export function closeAssistant(): void {
  useAssistant.setState({ open: false });
  ss.set(OPEN_KEY, '0');
}

/* 시연 데이터 초기화·단계 이동·로그아웃: 다른 사람·다른 상황의 대화가 남지 않게 지운다 */
onDataReset(() => {
  clearLog();
  setInput('');
  closeAssistant();
});
