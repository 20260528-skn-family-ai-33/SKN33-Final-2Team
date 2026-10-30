/* 작성 흐름 규칙 (화면과 분리한 순수 함수 · 5차 gp-app.js 의 STEPS·quizKey·diagKey·stale·busyDraft 등을 옮김).
   열쇠 계산은 서버(drafts.quiz_key·diag_key)와 같아야 한다 — 서버가 바뀌면 여기도 함께 고친다 */
import type { DraftDoc, EditDoc, Prefs } from '@/api/types/draft';
import { paths } from '@/app/paths';
import { sameJ } from '@/shared/lib/format';
import { certOf } from '@/shared/lib/prefs';
import type { WsState } from '@/shared/state/workspace';

export type StepKey = 'goal' | 'details' | 'quiz' | 'result' | 'options' | 'materials' | 'review';

export const STEPS: [StepKey, string, string][] = [
  ['goal', '목표·기획서', paths.newGoal],
  ['details', '세부 사항', paths.newDetails],
  ['quiz', '사전 점검', paths.newQuiz],
  ['result', '점검 결과', paths.newResult],
  ['options', '로드맵 선택', paths.newOptions],
  ['materials', '자료·활동 선택', paths.newMaterials],
  ['review', '검토·확정', paths.newReview],
];

/** 단계 표시에 따로 없는 하위 화면은 속한 단계로 보여 준다 */
export const SUB: Record<string, StepKey> = { [paths.newDetailsCheck]: 'details', [paths.newResultEdit]: 'result', [paths.newGen]: 'options' };
export const stepOfPath = (p: string): StepKey | undefined => STEPS.find((x) => x[2] === p)?.[0] || SUB[p];

/* ── 검사 ── */
export const goalOk = (d: DraftDoc): boolean => (d.goal || '').trim().length >= 4;
/** 심화 질문(10/23): 고른 사람은 객관식에 모두 답해야 넘어간다('잘 모르겠어요' 포함 · 서술형은 비워도 됨) */
export const mcqDone = (mcq: Record<string, unknown>, ans: Record<string, string> | undefined): boolean => Object.keys(mcq).every((k) => (ans || {})[k]);
export const quizDone = (d: DraftDoc): boolean =>
  d.v2Assessment ? d.v2Assessment.completed : !!d.quiz && d.quiz.questions.every((q) => d.answers[q.id]) && (!(d.deepOn && d.quiz.deep) || mcqDone(d.quiz.deep.mcq, d.deepMcq));
export const docIdle = (d: DraftDoc): boolean => !d.doc || d.doc.status !== 'reading';

export function stepDone(s: Pick<WsState, 'draft' | 'draftPlan'>, k: StepKey): boolean {
  const d = s.draft;
  /* 세부 사항은 모두 선택 사항이라, 확인 화면에서 '다음'을 눌렀거나 사전 점검 문항이 있으면 지난 것으로 본다 */
  return { goal: goalOk(d), details: !!(d.detailsOk || d.quiz), quiz: quizDone(d), result: !!(d.handoff || d.gen || d.v2Assessment?.completed), options: !!s.draftPlan, materials: !!d.v2Assessment?.activitiesReady, review: false }[k];
}

/** 이 단계 앞에 마치지 않은 단계가 있으면 그 단계 주소 */
export function blockedTo(s: Pick<WsState, 'draft' | 'draftPlan'>, k: StepKey): string | null {
  const i = STEPS.findIndex((x) => x[0] === k);
  const b = STEPS.slice(0, i).find(([kk]) => !stepDone(s, kk));
  return b ? b[2] : null;
}

/* ── 열쇠: 사전 점검 문항은 목표·기획서(파일과 요약)·자격증 계획으로 만든다 ── */
export const docSummary = (d: DraftDoc): string => (d.doc && d.doc.status === 'ok' ? String(d.doc.summary || '').trim() : '');
export const certKey = (p: Prefs): string => (certOf(p) ? p.cert : '');
export const quizRest = (d: DraftDoc): string => String(d.goal || '').trim() + '|' + (d.project ? d.project.name : '') + '|' + docSummary(d);
export const quizKey = (d: DraftDoc): string => quizRest(d) + (certKey(d.prefs) ? '|cert:' + certKey(d.prefs) : '');
const keyCert = (key: string): string => String(key).split('|cert:')[1] || '';

/** 심화 질문을 골랐으면 객관식 답(자가 진단 문항 순서)과 서술형 답도 열쇠에 넣는다(서버 drafts.diag_key 와 같다) */
export const deepOnOf = (d: DraftDoc | null | undefined): boolean => !!(d && d.deepOn && d.quiz && d.quiz.deep);
export function diagKey(d: DraftDoc): string {
  let k = (d.quiz ? d.quiz.key : '') + '|' + (d.quiz ? d.quiz.questions.map((q) => d.answers[q.id] || '-').join(',') : '');
  if (deepOnOf(d) && d.quiz?.deep) {
    const dq = d.quiz.deep;
    k +=
      '|deep:' +
      d.quiz.questions
        .filter((q) => dq.mcq[q.id])
        .map((q) => (d.deepMcq || {})[q.id] || '-')
        .join(',') +
      '|' +
      dq.essays.map((e) => String((d.deepEssay || {})[e.id] || '').trim()).join('\x1f');
  }
  return k;
}

/* ── 앞 단계를 고쳤을 때 (10/14) ──
   입력하는 동안에는 뒤 단계 결과를 지우지 않는다. 바꾼 채로 앞으로 넘어가려 할 때 무엇을 다시 만드는지 확인하고,
   '바꾼 내용으로 계속'이면 서버가 그때 지우고(API-17), '원래대로 되돌리기'면 결과를 만들 때의 입력으로 돌려 놓는다(API-18) */
export interface Stale {
  kind: 'quiz' | 'diag' | 'gen';
  note?: 'cert';
  input: string;
  what: string;
  back: boolean;
}

export const DOWN: Record<Stale['kind'], string[]> = {
  quiz: [paths.newQuiz, paths.newResult, paths.newResultEdit, paths.newGen, paths.newOptions, paths.newReview],
  diag: [paths.newResult, paths.newResultEdit, paths.newGen, paths.newOptions, paths.newReview],
  gen: [paths.newGen, paths.newOptions, paths.newReview],
};

/** 지금 입력이 뒤 단계 결과를 만들 때와 다르면 그 단계: quiz(목표·기획서·자격증 계획) > diag(사전 점검 응답) > gen(그 밖의 세부 사항) */
export function staleOf(d: DraftDoc): Stale | null {
  // V_2의 문항·응답 유효성은 입력 스냅샷을 확인하는 API가 판정한다.
  if (d.v2Assessment) return null;
  if (d.quiz && d.quiz.key !== quizKey(d)) {
    const rest = String(d.quiz.key).split('|cert:')[0] !== quizRest(d);
    const cert = keyCert(d.quiz.key) !== certKey(d.prefs);
    if (cert && !rest) return { kind: 'quiz', note: 'cert', input: paths.newDetails, what: '자격증 계획을', back: !!d.quiz.base };
    return { kind: 'quiz', input: paths.newGoal, what: cert ? '목표·기획서와 자격증 계획을' : '목표·기획서를', back: !!d.quiz.base };
  }
  if (d.diag && d.diag.key !== diagKey(d)) return { kind: 'diag', input: paths.newQuiz, what: '사전 점검 응답을', back: !!d.diag.answers };
  if ((d.handoff || d.gen) && d.genPrefs && !sameJ(d.genPrefs, d.prefs)) return { kind: 'gen', input: paths.newDetails, what: '세부 사항을', back: true };
  return null;
}

export function lossList(s: Pick<WsState, 'draft' | 'draftPlan'>, st: Stale): string[] {
  const d = s.draft;
  const n = Object.values(d.answers || {}).filter(Boolean).length;
  const out: string[] = [];
  if (st.kind === 'quiz') out.push(`사전 점검 문항${n ? `과 응답 ${n}개` : ''}`);
  if (st.kind !== 'gen' && d.diag) out.push(`점검 결과${d.fix || d.startStage ? ' (직접 고친 내용 포함)' : ''}`);
  if (d.gen || d.handoff) out.push(`로드맵 3안${s.draftPlan ? '과 고른 안' : ''}`);
  return out;
}

/* ── 진행 중인 작업이 있으면 서버 상태를 다시 읽어야 한다 ── */
export const busyDraft = (d: DraftDoc): boolean =>
  !!(
    d.quizRun ||
    d.diagRun ||
    (d.doc && d.doc.status === 'reading') ||
    (d.genRun && Object.values(d.genRun.rows || {}).some((x) => x.st === 'run')) ||
    (d.gen && ((d.gen.regenRun && Object.keys(d.gen.regenRun).length) || Object.values(d.gen.options || {}).some((o) => !o.support && !o.supportFail)))
  );

/* ── 점검 결과 ── */
export const startOf = (d: DraftDoc): number => (+(d.startStage || 0) >= 1 && +(d.startStage || 0) <= 4 ? +(d.startStage as number) : d.diag?.startStage || 1);
export const FIX: [string, string][] = [
  ['competencies', '익히게 될 역량'],
  ['resourceIds', '듣게 될 강좌·자료'],
  ['outcome', '만들 결과물'],
  ['known', '이미 할 수 있는 것'],
];
/** 진단 값(직접 고친 값이 있으면 그 값) */
export function dv<T = unknown>(d: DraftDoc, k: string): T {
  return (d.fix && d.fix[k] != null ? d.fix[k] : d.diag?.[k]) as T;
}
export const edited = (d: DraftDoc, k: string): boolean => (k === 'start' ? startOf(d) !== d.diag?.startStage : !!(d.fix && d.fix[k] != null));

/** 학습 선호(세부 사항)는 모두 선택 사항이라 빈 칸 검사는 로드맵 내용에만 */
export const editMissing = (e: EditDoc): { competencies: boolean; outcome: boolean } => ({
  competencies: !e.competencies.length,
  outcome: !String(e.outcome || '').trim(),
});
export const editOk = (d: DraftDoc): boolean => {
  const e = d.edit;
  return !!e && !Object.values(editMissing(e)).some(Boolean);
};
