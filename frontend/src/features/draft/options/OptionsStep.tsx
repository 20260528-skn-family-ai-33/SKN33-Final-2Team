import { trackName } from '@/shared/constants/data';
/* 5. 3안 비교표 (10/14 · 5차 scr['new-options']): 열 순서는 A1·A2·A3 고정.
   마음에 들지 않는 안은 요청을 적어 그 안만 다시 만들고(API-32 · 버전으로 쌓임), ‹ › 로 버전을 넘겨 본다 */
import { useEffect, useRef } from 'react';
import { draftsApi } from '@/api/endpoints/drafts';
import type { DraftDoc, OptionDef, RegenRequest } from '@/api/types/draft';
import type { PlanContent } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { hrs, won } from '@/shared/lib/format';
import { buildPlan, stageActs } from '@/shared/lib/plan';
import { cause, PROV } from '@/shared/state/ai';
import { setAt } from '@/shared/state/bind';
import { resOf, useCatalog } from '@/shared/state/catalog';
import { failToast } from '@/shared/lib/fail';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { ActThumb, Note, OpsBox, Page } from '@/shared/ui/parts';
import { DraftSaveError, draftCall, flush, takeDraft } from '../draftSync';
import { useKickSupport } from '../generation/GenerationStep';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';
import { SupCell, SupNote, syncGenCur } from './support';

/** 고른 안의 계획 계산 매개변수(진단 에이전트가 넘긴 학습 선호 기준) */
export function paramsOf(d: DraftDoc, opt?: OptionDef) {
  const h = d.handoff;
  return { start: h?.startStage || 1, hours: h?.prefs.weeklyHours || opt?.weeklyHours || D.autoHours, format: h?.prefs.formatKey || 'mixed', patch: {} };
}

export const optionIds = (d: DraftDoc): string[] => (d.gen ? D.optionOrder.filter((k) => d.gen?.options[k]) : []);
export const optsOf = (d: DraftDoc): PlanContent[] => optionIds(d).map((id) => buildPlan(d.gen!.options[id], paramsOf(d, d.gen!.options[id]), d.goal));

const regenBusy = (d: DraftDoc, pid: string) => !!(d.gen && d.gen.regenRun && d.gen.regenRun[pid]);
const regenErr = (d: DraftDoc, pid: string) => (d.gen && d.gen.regenErr && d.gen.regenErr[pid] ? cause(d.gen.regenErr[pid]) : null);

export async function choose(go: ReturnType<typeof useGo>, id: string): Promise<void> {
  try {
    await flush();
    takeDraft(await draftsApi.select(ws().draftId as string, id));
    go(paths.newReview);
  } catch (err) {
    if (!(err instanceof DraftSaveError)) failToast(err, '안을 고르지 못했어요');
  }
}

async function ver(pid: string, dir: number): Promise<void> {
  const d = ws().draft;
  const g = d.gen;
  if (!g || regenBusy(d, pid) || !(g.hist || {})[pid]) return;
  const list = g.hist![pid];
  const i = Math.min(list.length - 1, Math.max(0, ((g.cur || {})[pid] || 0) + dir));
  updateWs((s) => {
    const gg = s.draft.gen;
    if (!gg) return;
    gg.cur = gg.cur || {};
    gg.cur[pid] = i;
    gg.options[pid] = list[i];
    if (s.draftPlan && s.draftPlan.opt === pid) s.draftPlan = null;
  });
  try {
    await flush();
  } catch {
    /* 저장 실패는 이미 알렸고, 다음 입력이나 안 고르기 때 다시 저장한다 */
  }
}

/* 다시 만들기 요청 창: 바라는 점(문장) + 빠른 칩 + 활동별 그대로/빼기/바꾸기. 아무것도 고르지 않으면 활동 구성이 다른 안을 새로 쓴다 */
const QUICK = ['더 짧게', '실습 늘리기', '비용 줄이기', '영상 위주', '문서 위주', '업무 과제 늘리기'];
function RegenBody({ pl }: { pl: PlanContent }) {
  const q = useWs((s) => s.regenReq);
  if (!q) return null;
  return (
    <div className="rg">
      <div className="field">
        <label>
          바라는 점 <span className="muted small">선택</span>
        </label>
        <BText path="regenReq.note" className="textarea sm" maxLength={300} ariaLabel="바라는 점" placeholder="예: 평일 저녁에 맞게 짧은 자료로 바꿔 주세요" />
        <div className="chips rg-chips">
          {QUICK.map((c) => {
            const on = q.chips.includes(c);
            return (
              <button
                type="button"
                key={c}
                className={`chip${on ? ' on' : ''}`}
                aria-pressed={on}
                onClick={() => setAt('regenReq.chips', on ? q.chips.filter((x) => x !== c) : [...q.chips, c])}
              >
                {c}
              </button>
            );
          })}
        </div>
      </div>
      <div className="field">
        <label>
          빼거나 바꿀 활동 <span className="muted small">선택</span>
        </label>
        <div className="rg-acts">
          {pl.acts.map((a) => (
            <div className="rg-act" key={a.id}>
              <ActThumb a={a} size="xs" />
              <span className="tx">
                {a.title}
                <small>
                  {a.stage}단계 · {a.task ? '직접 수행 과제' : resOf(a.res)?.kind || '자료'} · {hrs(a.hours)}
                </small>
              </span>
              <div className="mini-seg" role="radiogroup" aria-label={a.title}>
                {[
                  ['', '그대로'],
                  ['remove', '빼기'],
                  ['replace', '바꾸기'],
                ].map(([v, l]) => (
                  <label key={v}>
                    <input type="radio" name={`rg-${a.id}`} value={v} checked={(q.acts[a.id] || '') === v} onChange={() => setAt(`regenReq.acts.${a.id}`, v)} />
                    {l}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        아무것도 고르지 않으면 같은 관점으로 활동 구성이 다른 안을 새로 써요. 다시 만든 안은 새 버전으로 쌓이고 ‹ › 로 이전 버전과 넘겨 볼 수 있어요.
      </p>
    </div>
  );
}

async function regenGo(): Promise<void> {
  const q = ws().regenReq;
  const g = ws().draft.gen;
  if (!q || !g) return;
  closeSheet();
  const o = g.options[q.pid];
  /** 고른 활동(빼기·바꾸기)을 서버가 아는 {key, title} 로. 지금 안에 없는 활동은 뺀다 */
  const refs = (how: string): RegenRequest['removeActs'] =>
    Object.keys(q.acts || {})
      .filter((id) => q.acts[id] === how)
      .flatMap((id) => {
        const a = o.acts.find((x) => x.id === id);
        return a ? [{ key: a.id, title: a.title }] : [];
      });
  const req: RegenRequest = { wish: String(q.note || '').trim(), quick: q.chips.slice(), removeActs: refs('remove'), replaceActs: refs('replace') };
  const has = req.wish || req.quick.length || req.removeActs.length || req.replaceActs.length;
  updateWs((s) => {
    s.regenReq = null;
    const gg = s.draft.gen;
    if (gg) gg.regenRun = { ...(gg.regenRun || {}), [q.pid]: { req } };
  });
  await draftCall(`${D.perspectives[q.pid].name}을 다시 만들지 못했어요`, (id) => draftsApi.regenerate(id, q.pid, has ? req : null), { soft: true });
}

export function openRegenSheet(pid: string): void {
  const d = ws().draft;
  const g = d.gen;
  if (!g || !g.options[pid] || regenBusy(d, pid)) return;
  syncGenCur();
  const o = ws().draft.gen!.options[pid];
  const pl = buildPlan(o, paramsOf(d, o), d.goal);
  updateWs((s) => void (s.regenReq = { pid, note: '', chips: [], acts: {} }));
  openSheet({
    title: `${D.perspectives[pid].name} 다시 만들기`,
    wide: true,
    body: () => <RegenBody pl={pl} />,
    foot: () => (
      <>
        <button className="btn line" onClick={closeSheet}>
          취소
        </button>
        <button className="btn pri" onClick={() => void regenGo()}>
          다시 만들기
        </button>
      </>
    ),
  });
}

/** 다시 만들기가 끝나면 알린다(서버 작성 문서의 버전 수가 늘었을 때) */
function useRegenToast(): void {
  const counts = useWs((s) => JSON.stringify(Object.fromEntries(Object.entries(s.draft.gen?.hist || {}).map(([k, v]) => [k, v.length]))));
  const seen = useRef<Record<string, number> | null>(null);
  useEffect(() => {
    const n = JSON.parse(counts) as Record<string, number>;
    if (seen.current)
      Object.entries(n).forEach(([pid, c]) => {
        if (seen.current![pid] && c > seen.current![pid]) toast(`${D.perspectives[pid].name}을 다시 만들었어요 · 버전 ${c}`);
      });
    seen.current = n;
  }, [counts]);
}

export function OptionsStep() {
  const go = useGo();
  const d = useWs((s) => s.draft);
  useCatalog((s) => s.res);
  useDraftWatch();
  useKickSupport();
  useRegenToast();
  useEffect(() => {
    syncGenCur();
  }, []);
  const g = d.gen;
  if (!g || !d.handoff) return null;
  const ps = optsOf(d);
  const cur = d.chosen;
  const colCls = (p: PlanContent) => (regenBusy(d, p.opt) ? 'busy' : undefined);
  const src = (o: OptionDef) => (o.source && o.source !== 'mock' ? <span className="tag acc">{PROV[o.source] || 'API'} 작성</span> : <span className="tag">가데이터</span>);
  const off = ps.some((p) => p.def.offDomain);
  const missing = g.missing || [];
  const row = (k: string, f: (p: PlanContent, x: OptionDef) => React.ReactNode) => (
    <tr>
      <td className="k">{k}</td>
      {ps.map((p) => (
        <td key={p.opt} data-col={p.opt} className={colCls(p)}>
          {f(p, p.def)}
        </td>
      ))}
    </tr>
  );
  const Ver = ({ p }: { p: PlanContent }) => {
    const list = (g.hist || {})[p.opt];
    const i = (g.cur || {})[p.opt] || 0;
    const o = p.def;
    const busy = regenBusy(d, p.opt);
    return (
      <>
        {list && list.length > 1 ? (
          <span className="vnav">
            <button type="button" disabled={i === 0 || busy} aria-label="이전 버전" onClick={() => void ver(p.opt, -1)}>
              <Icon name="left" />
            </button>
            <b className="num">
              버전 {i + 1}/{list.length}
            </b>
            <button type="button" disabled={i === list.length - 1 || busy} aria-label="다음 버전" onClick={() => void ver(p.opt, 1)}>
              <Icon name="right" />
            </button>
          </span>
        ) : null}
        {i > 0 ? (
          <>
            {o.revSummary ? <span className="small rev">바꾼 점: {o.revSummary}</span> : null}
            {o.revRequest ? <span className="small muted rev">요청: {o.revRequest}</span> : null}
            {(o.revNotes || []).length ? <span className="small muted rev">반영하지 못한 것: {(o.revNotes || []).join(' ')}</span> : null}
          </>
        ) : null}
      </>
    );
  };
  const head = (p: PlanContent) => {
    const busy = regenBusy(d, p.opt);
    const err = regenErr(d, p.opt);
    return (
      <th key={p.opt} data-col={p.opt} className={colCls(p)}>
        <label>
          <input type="radio" name="pick" value={p.opt} checked={cur === p.opt} onChange={() => setAt('draft.chosen', p.opt)} />
          <span>
            <b>
              {trackName(p.opt, p.name)}
            </b>
            <small>{p.tagline}</small>
          </span>
        </label>
        <Ver p={p} />
        <button className="regen" disabled={busy} onClick={() => openRegenSheet(p.opt)}>
          {busy ? (
            <>
              <span className="sp" />
              다시 쓰는 중…
            </>
          ) : (
            <>
              <Icon name="history" />이 안만 다시 만들기
            </>
          )}
        </button>
        {err && !busy ? (
          <>
            <span className="small rev fail-t">
              <Icon name="x" />
              <span>다시 만들지 못했어요 · {err.user}. 이전 안을 그대로 뒀어요. 다시 해 보려면 ‘이 안만 다시 만들기’를 눌러 주세요.</span>
            </span>
            <OpsBox items={[['', err]]} cls="sm" />
          </>
        ) : null}
      </th>
    );
  };
  return (
    <>
      <Stepper cur="options" />
      <Page
        title={ps.length === 3 ? '로드맵 3안을 비교하고 골라 주세요' : ps.length === 1 ? '작성된 로드맵을 확인해 주세요' : `작성된 로드맵 ${ps.length}안을 비교하고 골라 주세요`}
        lead="같은 목표와 학습 여건으로 방법만 달라요. 마음에 들지 않는 안은 바라는 점을 적어 그 안만 다시 만들 수 있고, 다시 만든 안은 버전으로 넘겨 볼 수 있어요."
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newResult)}>
              <Icon name="left" />
              이전
            </button>
            <button
              className="btn pri"
              disabled={!cur}
              onClick={() => {
                if (!cur) return;
                if (regenBusy(ws().draft, cur)) {
                  toast('그 안을 다시 쓰는 중이에요. 잠시 뒤에 골라 주세요');
                  return;
                }
                void choose(go, cur);
              }}
            >
              해당 계획 검토하기
            </button>
          </>
        }
      >
        <div className="tblwrap">
          <table className="cmp">
            <thead>
              <tr>
                <th />
                {ps.map(head)}
              </tr>
            </thead>
            <tbody>
              {row('기간 · 주당', (p) => (
                <>
                  <span className="numv">{p.weeks}주</span> · 주 {p.hours}시간
                  {d.handoff?.prefs.hoursAuto ? <small className="muted"> (에이전트가 정함)</small> : null}
                </>
              ))}
              {row('예상 비용', (p) => (
                <span className="numv">
                  {won(p.cost)}
                  {p.costUnknown ? ' + 확인 필요' : ''}
                </span>
              ))}
              {row('활동', (p) => (
                <details className="more" open>
                  <summary>
                    <Icon name="right" />
                    {p.acts.length}개 보기
                  </summary>
                  <ul className="cmp-acts">
                    {p.acts.map((a) => (
                      <li key={a.id}>
                        <ActThumb a={a} size="xs" />
                        <span>
                          {a.title}{' '}
                          <span className="muted small">
                            {a.task ? '직접 수행' : ''} {hrs(a.hours)}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
              {row('지원 조건', (_p, x) => (
                <SupCell o={x} />
              ))}
              {row('단계', (p) =>
                D.stages
                  .filter((s) => s.n >= p.start && stageActs(p, s.n).length)
                  .map((s) => s.name)
                  .join(' › '),
              )}
              {row('추천 이유', (_p, x) => x.reason)}
              {row('좋은 점', (_p, x) => (
                <ul>
                  {x.pros.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              ))}
              {row('아쉬운 점', (_p, x) => (
                <ul>
                  {x.cons.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              ))}
              {row('작성', (_p, x) => src(x))}
            </tbody>
          </table>
        </div>
        <SupNote />
        {ps.some((p) => p.costUnknown) ? <Note>‘확인 필요’는 팀 DB에 가격이 없는 자료(도서 가격·응시료·K-MOOC 수강료 등)가 들어 있다는 뜻이에요. 예상 비용에는 넣지 않았어요.</Note> : null}
        {missing.length ? (
          <Note>
            {missing.map((id) => `${D.perspectives[id].name}`).join(', ')}은 작성에 실패해 빠졌어요. 세 안을 다시 받으려면 ‘점검 결과’에서 ‘로드맵 생성’을 다시 눌러 주세요.
          </Note>
        ) : null}
        <Note>
          {ps.length > 1
            ? '고른 안(보고 있는 버전)을 쓴 에이전트(관점)만 저장해요. 고르지 않은 안과 다른 버전은 저장하지 않아요.'
            : '고른 안(보고 있는 버전)을 쓴 에이전트(관점)만 저장해요.'}
        </Note>
        {off ? <Note>가데이터 모드에는 RAG 시나리오 후보만 있어요. 다른 목표의 후보는 좌측 ‘AI 모델’에서 RunPod-Ollama나 OpenAI API를 쓰면 확인할 수 있어요.</Note> : null}
      </Page>
    </>
  );
}
