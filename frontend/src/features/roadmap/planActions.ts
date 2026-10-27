/* 확정한 로드맵 서버 동기화·동작 (5차 gp-parts.js takePlan·pullPlan·saveProgress·revise·acceptRevision·dropRevision, gp-app.js 보관·다시 진행) */
import { useEffect } from 'react';
import { plansApi } from '@/api/endpoints/plans';
import type { PlanRecord, PlanResponse, RevForm } from '@/api/types/plan';
import { paths } from '@/app/paths';
import type { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { clone } from '@/shared/lib/format';
import { cause } from '@/shared/state/ai';
import { mergeReg, mergeRes } from '@/shared/state/catalog';
import { me } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { putRec, updateWs, useWs, ws } from '@/shared/state/workspace';

type Go = ReturnType<typeof useGo>;

export function takePlan(r: PlanResponse | null | undefined): PlanRecord | null {
  if (!r) return null;
  mergeRes(r.res);
  mergeReg(r.reg);
  updateWs((s) => void putRec(s, r.plan));
  return ws().plans[r.plan.id] || null;
}

export async function pullPlan(pid: string): Promise<PlanRecord | null> {
  try {
    return takePlan(await plansApi.get(pid));
  } catch (err) {
    failToast(err, '로드맵을 불러오지 못했어요');
    return null;
  }
}

/** 수정안을 만드는 중이거나 수정안의 지원 조건을 확인하는 중이면 그 로드맵을 다시 읽는다 */
export const busyPlan = (R: PlanRecord | null | undefined): boolean =>
  !!(R && ((R.revision && R.revision.status === 'running') || (R.pending && !R.pending.to.def.support && !R.pending.supFail)));

/** 진행 중인 수정안 작업이 있으면 1.2초마다 그 로드맵을 다시 읽는다(화면을 떠나면 멈춤 · 5차 P.watchPlan) */
export function usePlanWatch(pid: string | undefined): void {
  const busy = useWs((s) => !!pid && busyPlan(s.plans[pid]));
  useEffect(() => {
    if (!busy || !pid) return;
    let stop = false;
    let t: ReturnType<typeof setTimeout>;
    const until = Date.now() + 600000;
    const tick = async () => {
      if (stop || Date.now() > until || !me()) return;
      await pullPlan(pid);
      if (!stop) t = setTimeout(tick, 1200);
    };
    t = setTimeout(tick, 900);
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [busy, pid]);
}

/** 진행 기록 저장(API-38). 실행 기록 창의 저장하기에서만 부른다(상태·메모, 첨부는 있을 때만) */
export async function saveProgress(pid: string, actId: string, body: Record<string, unknown>): Promise<boolean> {
  try {
    takePlan(await plansApi.progress(pid, actId, body));
    return true;
  } catch (err) {
    failToast(err, '진행 기록을 저장하지 못했어요');
    await pullPlan(pid);
    return false;
  }
}

/* ── 수정 요청 → 수정안 (API-43~45) ──
   항목(여러 개)과 요청 문장을 받아, 로드맵을 쓴 관점의 하위 에이전트(관점을 바꾸면 새 관점)가 서버에서 수정안을 쓴다.
   확정하기 전까지 기존 로드맵은 그대로. 실패하면 가데이터로 대신하지 않고 안내하며, 다시 시도는 사용자가 눌러야만 한다 */
export const REV_ITEMS: [string, string, 'cond' | 'plan' | 'acts'][] = [
  ['hours', '주당 학습 시간', 'cond'],
  ['weeks', '정해진 기간', 'cond'],
  ['budget', '교육 예산', 'cond'],
  ['format', '학습 방식', 'cond'],
  ['cert', '자격증 계획', 'cond'],
  ['etc', '일정·환경 제약', 'cond'],
  ['start', '시작 단계', 'plan'],
  ['pid', '관점', 'plan'],
  ['remove', '활동 빼기', 'acts'],
  ['replace', '활동 바꾸기', 'acts'],
  ['add', '활동 추가', 'acts'],
];

export function freshRev(R: PlanRecord, note = '', fromComment: string | false = false): RevForm {
  const pl = R.plan;
  const p = pl.prefs || ({} as NonNullable<typeof pl.prefs>);
  return {
    on: {},
    note,
    fromComment,
    fail: null,
    v: {
      hours: pl.hours,
      weeks: p.weeks || '',
      budget: p.budget == null ? '' : p.budget,
      format: p.format || '',
      cert: p.cert || '',
      etc: p.etc || '',
      start: pl.start,
      pid: pl.opt,
      remove: [],
      replace: [],
      replaceHow: '',
      addRes: [],
      addTask: '',
    },
  };
}

const blankNum = (v: unknown) => v === '' || v == null;
const addTasks = (r: RevForm) =>
  String(r.v.addTask || '')
    .split('\n')
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 5);

export function revItemOk(r: RevForm, k: string, opt: string): boolean {
  const v = r.v;
  if (k === 'hours') return blankNum(v.hours) || (+v.hours >= 0.5 && +v.hours <= 40);
  if (k === 'weeks') return blankNum(v.weeks) || (+v.weeks >= 1 && +v.weeks <= 52);
  if (k === 'budget') return blankNum(v.budget) || +v.budget >= 0;
  if (k === 'pid') return v.pid !== opt;
  if (k === 'remove') return v.remove.length > 0;
  if (k === 'replace') return v.replace.length > 0;
  if (k === 'add') return v.addRes.length > 0 || addTasks(r).length > 0;
  return true;
}
export const revPicked = (r: RevForm): string[] => REV_ITEMS.map(([k]) => k).filter((k) => r.on[k]);
export const revKey = (r: RevForm): string =>
  JSON.stringify([
    revPicked(r).map((k) => [
      k,
      ['remove', 'replace'].includes(k) ? r.v[k as 'remove'] : k === 'add' ? [r.v.addRes, r.v.addTask] : r.v[k as keyof RevForm['v']],
    ]),
    r.v.replaceHow,
    String(r.note || '').trim(),
  ]);
export function revOk(R: PlanRecord | null | undefined): boolean {
  const r = R?.rev;
  if (!R || !r || r.running) return false;
  const ks = revPicked(r);
  return ks.every((k) => revItemOk(r, k, R.plan.opt)) && (ks.length > 0 || !!String(r.note || '').trim());
}

export async function revise(pid: string): Promise<void> {
  const R = ws().plans[pid];
  const r = R && R.rev;
  if (!r || r.running) return;
  const key = revKey(r);
  updateWs((s) => {
    const x = s.plans[pid];
    if (!x.rev) return;
    x.rev.running = true;
    x.rev.fail = null;
    x.pending = null;
  });
  try {
    await plansApi.revise(pid, { rev: { on: r.on, v: r.v, note: r.note, fromComment: r.fromComment }, key });
  } catch (err) {
    updateWs((s) => {
      const x = s.plans[pid];
      if (x.rev) {
        x.rev.running = false;
        x.rev.fail = { cause: cause(err) };
      }
    });
    return;
  }
  await pullPlan(pid);
}

export async function acceptRevision(go: Go, pid: string): Promise<void> {
  const R = ws().plans[pid];
  const rv = R && R.revision;
  if (!R || !R.pending || !rv) return;
  try {
    const Rn = takePlan(await plansApi.acceptRevision(rv.id));
    if (!Rn) return;
    updateWs((s) => {
      s.plans[Rn.id].rev = null;
      if (Rn.plan.opt && !s.picks.includes(Rn.plan.opt)) s.picks.push(Rn.plan.opt);
    });
    go(paths.confirmed(Rn.id));
  } catch (err) {
    failToast(err, '수정안을 확정하지 못했어요');
  }
}

export async function dropRevision(go: Go, pid: string): Promise<void> {
  const R = ws().plans[pid];
  const rv = R && R.revision;
  const back = R ? (R.rev && R.rev.fromComment ? paths.comments(R.id) : paths.roadmap(R.id)) : paths.roadmaps;
  try {
    if (rv) await plansApi.dropRevision(rv.id);
  } catch (err) {
    failToast(err, '수정안을 버리지 못했어요');
    return;
  }
  updateWs((s) => {
    const x = s.plans[pid];
    if (x) {
      x.pending = null;
      x.rev = null;
      x.revision = null;
    }
  });
  go(back);
  toast('수정안을 버렸어요. 계획은 그대로예요');
}

/** 수정 요청 시작: 쓰던 양식이 없으면 새로 만든다 */
export function startRevise(go: Go, pid: string): void {
  const R = ws().plans[pid];
  if (!R || R.status !== 'active') return;
  if (!(R.revision && R.revision.status === 'running'))
    updateWs((s) => {
      s.plans[pid].rev = freshRev(s.plans[pid]);
      s.plans[pid].pending = null;
    });
  go(paths.revise(pid));
}

/* 보관(API-41): 진행을 멈추고 지난 로드맵으로 옮긴다. 기록은 그대로이고 언제든 다시 진행할 수 있다(API-42) */
export async function archivePlan(go: Go, pid: string): Promise<void> {
  try {
    const R = takePlan(await plansApi.archive(pid));
    if (R) updateWs((s) => void (s.plans[R.id].rev = null));
    go(paths.roadmaps);
    toast('로드맵을 보관했어요 · 지난 로드맵에서 볼 수 있어요');
  } catch (err) {
    failToast(err, '로드맵을 보관하지 못했어요');
  }
}

export async function resumePlan(go: Go, pid: string): Promise<void> {
  try {
    const R = takePlan(await plansApi.resume(pid));
    if (R) go(paths.roadmap(R.id));
    toast('로드맵을 다시 진행해요. 기록은 그대로 이어져요');
  } catch (err) {
    failToast(err, '로드맵을 다시 진행하지 못했어요');
  }
}

export const cloneRev = (r: RevForm) => clone(r);
