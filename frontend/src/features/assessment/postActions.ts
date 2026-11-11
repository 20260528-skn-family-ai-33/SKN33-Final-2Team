/* 사후 점검 저장·결과 보고서 만들기 (5차 scr.post 의 savePost·waitReport·make-report · PostCheckPage 에서 옮김)
   응답은 고칠 때마다 서버에 저장한다(API-49). 저장이 실패하면 보고서를 만들지 않는다 — 서버에 남은 예전 응답으로 보고서가 나오지 않게(PR #23 리뷰 2026-10-27) */
import { plansApi } from '@/api/endpoints/plans';
import { waitJob } from '@/api/jobs';
import type { PostDeep } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { reloadWorkspace } from '@/features/draft/draftSync';
import { pullPlan, takePlan } from '@/features/roadmap/planActions';
import type { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { onBound } from '@/shared/state/bind';
import { me } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { planReports, updateWs, ws } from '@/shared/state/workspace';

/** 사후 심화 답은 문항이 준비되고 보고서를 만들기 전까지만 보낸다(보고서를 만든 뒤에는 서버가 고정) */
export const deepOpen = (dp: PostDeep | null | undefined) => !!(dp && dp.status === 'ready' && !dp.judge);
const quizFlights = new Map<string, Promise<void>>();
export function ensurePostQuiz(pid: string): Promise<void> {
  if (ws().plans[pid]?.post.quizSurvey) return Promise.resolve();
  const pending = quizFlights.get(pid); if (pending) return pending;
  const apply = (result: Awaited<ReturnType<typeof plansApi.postQuiz>>) => {
    const mine = ws().plans[pid]?.post;
    const keep = mine ? { answers: { ...mine.answers }, quizAnswers: { ...mine.quizAnswers }, goalSelf: mine.goalSelf } : null;
    takePlan(result);
    if (keep && ws().plans[pid]) updateWs(s => { Object.assign(s.plans[pid].post, keep); });
  };
  const work = (typeof plansApi.get === 'function'
    ? plansApi.get(pid).then(got => got?.plan?.post?.quizSurvey ? got : plansApi.postQuiz(pid), () => plansApi.postQuiz(pid))
    : plansApi.postQuiz(pid)
  ).then(apply);
  quizFlights.set(pid, work);
  void work.finally(() => quizFlights.delete(pid)).catch(() => {});
  return work;
}
let postQ: Promise<boolean> = Promise.resolve(true);

/** 사후 점검 응답 저장. 성공하면 true, 실패하면 알림을 띄우고 false(화면 입력은 그대로 두어 다시 시도할 수 있다) */
export function savePost(pid: string, extra?: Record<string, unknown> | null): Promise<boolean> {
  postQ = postQ.then(async () => {
    const cur = ws().plans[pid];
    if (!cur) return false;
    const dp = cur.post.deep;
    const body = { ...(cur.post.quizSurvey ? { quizAnswers: cur.post.quizAnswers || {} } : {}), answers: cur.post.answers, goalSelf: cur.post.goalSelf, ...(deepOpen(dp) ? { deepMcq: dp!.mcq || {}, deepEssay: dp!.essay || {} } : {}), ...(extra || {}) };
    try {
      const res = await plansApi.savePost(pid, body);
      /* 보내는 사이 서술형을 더 썼으면 서버 응답이 덮지 않게 화면의 심화 답을 그대로 둔다
         immer 는 draft 를 고치면서 값도 돌려주면 예외를 던지므로 Object.assign 의 결과를 돌려주지 않는다(#48) */
      const mine = ws().plans[pid]?.post;
      const keep = mine && deepOpen(mine.deep) ? { mcq: mine.deep!.mcq, essay: mine.deep!.essay } : null;
      const keepAnswers = mine ? { answers: { ...mine.answers }, quizAnswers: { ...mine.quizAnswers }, goalSelf: mine.goalSelf, ...(mine.running ? { running: true } : {}), ...(mine.reportId ? { reportId: mine.reportId } : {}), ...(mine.jobId ? { jobId: mine.jobId } : {}) } : null;
      takePlan(res);
      if (keepAnswers && ws().plans[pid]) updateWs(s => { Object.assign(s.plans[pid].post, keepAnswers); });
      if (keep && deepOpen(ws().plans[pid]?.post.deep)) updateWs((s) => void Object.assign(s.plans[pid].post.deep as PostDeep, keep));
      return true;
    } catch (err) {
      failToast(err, '사후 점검 응답을 저장하지 못했어요');
      return false;
    }
  });
  return postQ;
}

/* 입력 연결 뒤처리: 사후 점검 응답은 바로 서버에 저장한다(글자 입력은 0.6초 기다림) */
let postT: ReturnType<typeof setTimeout> | undefined;
onBound((_s, path, evt) => {
  const m = /^plans\.([^.]+)\.post\.(.+)$/.exec(path);
  if (!m || m[2] === 'file') return;
  clearTimeout(postT);
  postT = setTimeout(() => void savePost(m[1]), evt === 'input' ? 600 : 50);
});

/* 보고서 작성(API-50): 서버 작업. 끝나면 보고서 목록을 다시 읽고 사후 점검 화면이면 완료 상태를 남긴다 */
const repWait = new Set<string>();
export async function waitReport(_go: ReturnType<typeof useGo>, pid: string, jobId: string): Promise<void> {
  if (repWait.has(jobId)) return;
  repWait.add(jobId);
  let out: { reportId?: string } | null = null;
  try {
    out = await waitJob<{ reportId?: string }>(jobId);
  } catch {
    /* 실패 원인은 서버(post.fail)에 남아 있다 */
  }
  repWait.delete(jobId);
  if (!me()) return;
  const here = () => window.location.pathname === paths.post(pid);
  if (out && out.reportId) {
    const reportId = out.reportId;
    if (here()) updateWs((s) => { if (s.plans[pid]) { s.plans[pid].post.running = false; s.plans[pid].post.reportId = reportId; } });
    try {
      if (!await reloadWorkspace()) return;
    } catch (error) {
      failToast(error, '보고서는 저장됐어요. 보고서 화면에서 다시 불러와 주세요.');
      if (here()) updateWs((s) => { if (s.plans[pid]) { s.plans[pid].post.running = false; s.plans[pid].post.reportId = reportId; } });
      return;
    }
    if (here()) updateWs((s) => { if (s.plans[pid]) s.plans[pid].post.reportId = reportId; });
    else {
      updateWs((s) => { if (s.plans[pid]?.post.reportId) s.plans[pid].post.reportId = null; });
      toast('결과 보고서가 나왔어요 · 점검·보고서에서 볼 수 있어요');
    }
  } else {
    const updated = await pullPlan(pid);
    if (updated?.status === 'done' && !updated.post.running) {
      try {
        if (!await reloadWorkspace()) return;
      } catch {
        return;
      }
      const repId = planReports(ws(), updated)[0]?.id;
      if (repId && here()) updateWs((s) => { if (s.plans[pid]) s.plans[pid].post.reportId = repId; });
      else if (repId) toast('결과 보고서가 나왔어요 · 점검·보고서에서 볼 수 있어요');
    }
  }
}

export async function makeReport(go: ReturnType<typeof useGo>, pid: string): Promise<void> {
  const R = ws().plans[pid];
  if (!R || R.post.running) return;
  clearTimeout(postT);
  const alreadySubmitted = (R.post.quizSurvey?.groups || []).some((g) => g.quizzes.some((q) => typeof q.answer === 'number'));
  updateWs((s) => {
    s.plans[pid].post.running = true;
    s.plans[pid].post.reportId = null;
    s.plans[pid].post.fail = null;
  });
  if ((!alreadySubmitted || R.post.fail) && !(await savePost(pid, R.post.fail ? { clearFail: true } : null))) {
    updateWs((s) => {
      if (s.plans[pid]) s.plans[pid].post.running = false;
    });
    return;
  }
  try {
    const j = await plansApi.makeReport(pid);
    updateWs((s) => {
      if (s.plans[pid]) {
        s.plans[pid].post.running = true;
        s.plans[pid].post.jobId = j.jobId;
        if (j.quizSurvey) s.plans[pid].post.quizSurvey = j.quizSurvey;
      }
    });
    void waitReport(go, pid, j.jobId);
  } catch (err) {
    updateWs((s) => void (s.plans[pid].post.running = false));
    failToast(err, '결과 보고서를 만들지 못했어요');
    await pullPlan(pid);
  }
}
