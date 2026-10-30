/* 4. 점검 결과(API-25) · 4-1. 점검 결과 수정(API-26) (5차 scr['new-result'] · scr['new-result-edit'])
   진단 에이전트가 정리한 로드맵 미리보기 + 학습 선호(보기 전용 · 고치려면 '수정'). 수준 진단도 가데이터로 대신하지 않는다.
   실패는 서버(diagFail)에 남고 '다시 시도하기'를 눌러야만 다시 진단한다 */
import { resourceSource } from '@/shared/lib/resourceSource';
import { useEffect, useState } from 'react';
import { draftsApi } from '@/api/endpoints/drafts';
import type { EditDoc } from '@/api/types/draft';
import { paths } from '@/app/paths';
import { DeepReveal } from '@/features/assessment/quizParts';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { clone, sameJ } from '@/shared/lib/format';
import { ai, cause, errText } from '@/shared/state/ai';
import { setAt, useAt } from '@/shared/state/bind';
import { useCatalog } from '@/shared/state/catalog';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { AgentRow, FailPage, Note, OpsBox, Page, runSub, Thumb, via } from '@/shared/ui/parts';
import { ResPicker } from '@/shared/ui/ResPicker';
import { DetailsForm } from '../details/DetailsForm';
import { draftCall, pullDraft } from '../draftSync';
import { deepOnOf, diagKey, dv, edited, editMissing, editOk, FIX, startOf, staleOf } from '../model';
import { openStaleSheet } from '../stale';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';

const DIAG_AGENT = '진단 에이전트 · 수준 진단·로드맵 미리보기';
let diagAsk = '';

async function ensureDiag(retry = false): Promise<void> {
  const d = ws().draft;
  const key = diagKey(d);
  if ((d.diag && d.diag.key === key) || (d.diagRun && d.diagRun.key === key)) return;
  if (diagAsk === key || (!retry && d.diagFail && d.diagFail.key === key)) return;
  diagAsk = key;
  const r = await draftCall('점검 결과를 정리하지 못했어요', (id) => draftsApi.diagnosis(id));
  diagAsk = '';
  if (!r) return;
  await pullDraft();
}

const stageLabel = (n: number) => `${n}단계 ‘${D.stages.find((s) => s.n === +n)?.name || ''}’부터`;

/** 로드맵 생성(API-27): 서버가 전달 내용을 정리하고 세 안을 병렬로 쓰기 시작한다. 같은 내용으로 세 안을 모두 받은 적이 있으면 그 결과를 쓴다 */
export async function genStart(go: ReturnType<typeof useGo>): Promise<void> {
  /* 바꾼 앞 단계가 남아 있으면(홈에서 이어서 들어온 경우 등) 먼저 확인 */
  const st = staleOf(ws().draft);
  if (st) {
    openStaleSheet(go, st, paths.newResult);
    return;
  }
  const r = await draftCall('로드맵 생성을 시작하지 못했어요', (id) => draftsApi.optionsStart(id));
  if (!r) return;
  go(ws().draft.gen ? paths.newOptions : paths.newGen, { force: true });
}

function Preview() {
  const d = useWs((s) => s.draft);
  const res = useCatalog((s) => s.res);
  const a = d.diag;
  if (!a) return null;
  const start = startOf(d);
  /* 수정 화면에서 진단 에이전트 제안과 다르게 고친 항목은 '직접 고침'으로 표시 */
  const dt = (k: string, l: string) => (
    <dt>
      {l}
      {edited(d, k) ? <small className="ed">직접 고침</small> : null}
    </dt>
  );
  const shown = dv<string[]>(d, 'resourceIds').filter((id) => res[id] && res[id].kind !== '자격' && (res[id].stage || 1) >= start);
  const known = dv<string[]>(d, 'known');
  return (
    <div className="card acc preview">
      <p className="eyebrow">
        <Icon name="spark" />
        진단 에이전트가 정리한 로드맵 미리보기
      </p>
      <dl className="kv">
        {dt('start', '시작 지점')}
        <dd>
          <b>{stageLabel(start)}</b>
          <span className="small muted d-sub">
            {edited(d, 'start') ? `진단 에이전트 제안은 ${a.startStage}단계예요 · ${a.startReason}` : `진단 에이전트 제안 · ${a.startReason}`}
          </span>
        </dd>
        {dt('competencies', '익히게 될 역량')}
        <dd>
          <div className="chips">
            {dv<string[]>(d, 'competencies').map((c) => (
              <span className="chip" key={c}>
                {c}
              </span>
            ))}
          </div>
        </dd>
        {dt('resourceIds', '듣게 될 강좌·자료')}
        <dd>
          <ul className="plain-list res-list">
            {shown.length ? (
              shown.map((id) => {
                const r = res[id];
                return (
                  <li key={id}>
                    <Thumb r={r} size="xs" />
                    <span>
                      <b>{r.title}</b>{' '}
                      <span className="small muted">
                        {r.kind} · {resourceSource(r)}
                        {r.real ? '' : ' · 가상'}
                      </span>
                    </span>
                  </li>
                );
              })
            ) : (
              <li className="muted">로드맵 계획 에이전트가 등록 자료에서 고를 예정이에요</li>
            )}
          </ul>
        </dd>
        {dt('outcome', '만들 결과물')}
        <dd>{dv<string>(d, 'outcome')}</dd>
        {known.length || edited(d, 'known') ? (
          <>
            {dt('known', '이미 할 수 있는 것')}
            <dd className="small muted">
              {known.slice(0, 6).join(', ') || '없음'}
              {known.length ? ' — 다시 배우지 않도록 줄여요' : ''}
            </dd>
          </>
        ) : null}
      </dl>
    </div>
  );
}

export function ResultStep() {
  const go = useGo();
  const d = useWs((s) => s.draft);
  const key = diagKey(d);
  const ready = !!(d.diag && d.diag.key === key);
  const running = !!d.diagRun;
  const failKey = d.diagFail?.key;
  useDraftWatch();
  useEffect(() => {
    void ensureDiag();
  }, [key, ready, running, failKey]);

  const err = !ready && !d.diagRun && d.diagFail && d.diagFail.key === key ? cause(d.diagFail.cause) : null;
  if (err)
    return (
      <>
        <Stepper cur="result" />
        <FailPage
          title="점검 결과를 정리하는 중 문제가 발생했어요"
          desc="진단 에이전트가 사전 점검 응답을 정리하지 못했어요. 입력한 목표·세부 사항과 사전 점검 응답은 그대로 남아 있어요."
          cause={errText(err)}
          body={
            <div className="agents">
              <AgentRow st="fail" name={DIAG_AGENT} sub={ai.live() ? via('default') : ''} tag="오류 발생" tagCls="fail" />
            </div>
          }
          ops={<OpsBox items={[['', err]]} />}
          foot={
            <>
              <button className="btn line" onClick={() => go(paths.newQuiz)}>
                <Icon name="left" />
                사전 점검 응답 고치기
              </button>
              <button
                className="btn pri"
                onClick={() => {
                  updateWs((s) => void (s.draft.diagFail = null));
                  void ensureDiag(true);
                }}
              >
                <Icon name="retry" />
                다시 시도하기
              </button>
            </>
          }
        />
      </>
    );
  return (
    <>
      <Stepper cur="result" />
      <Page
        title="이런 로드맵이 만들어질 예정이에요"
        lead="사전 점검 응답과 세부 사항을 진단 에이전트가 정리했어요. 바꿀 내용이 있으면 아래 ‘수정’을 눌러 주세요. 수준 점수는 보여주지 않고 사후 점검 비교용으로만 저장해요."
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newQuiz)}>
              <Icon name="left" />
              이전
            </button>
            <button className="btn line" disabled={!ready} onClick={() => startEdit(go)}>
              <Icon name="edit" />
              수정
            </button>
            <button className="btn pri" disabled={!ready} onClick={() => void genStart(go)}>
              로드맵 생성
            </button>
          </>
        }
      >
        {ready ? (
          <>
            <Preview />
            {deepOnOf(d) && d.diag?.deep && d.quiz ? (
              <DeepReveal
                questions={d.quiz.questions}
                dq={d.quiz.deep}
                mcqAns={d.deepMcq}
                essayAns={d.deepEssay}
                grade={d.diag.deep.grade}
                judge={d.diag.deep.judge}
                title="심화 질문 정답·모범 답안 보기"
              />
            ) : null}
            <Note>목표·기획서나 사전 점검 응답을 고치려면 위 단계를 눌러 이동하세요. ‘로드맵 생성’을 누를 때 지금 내용이 로드맵 계획 에이전트에게 전달돼요.</Note>
          </>
        ) : (
          <div className="agents">
            <AgentRow st="run" name={DIAG_AGENT} sub={runSub('default', '사전 점검 응답과 세부 사항을 정리하고 있어요')} />
          </div>
        )}
      </Page>
    </>
  );
}

/* ── 4-1. 점검 결과 수정: 점검 결과 화면에 보이는 내용을 한곳에서 고친다. 저장해야 반영되고(API-26), 취소하면 그대로 ── */
const sameSet = (x: string[] | undefined, y: string[] | undefined) => JSON.stringify((x || []).slice().sort()) === JSON.stringify((y || []).slice().sort());

const editFrom = (): EditDoc => {
  const d = ws().draft;
  return {
    start: startOf(d),
    competencies: dv<string[]>(d, 'competencies').slice(),
    resourceIds: dv<string[]>(d, 'resourceIds').slice(),
    outcome: dv<string>(d, 'outcome'),
    known: dv<string[]>(d, 'known').slice(),
    prefs: clone(d.prefs),
  };
};

export function startEdit(go: ReturnType<typeof useGo>): void {
  if (!ws().draft.diag) return;
  updateWs((s) => void (s.draft.edit = editFrom()));
  go(paths.newResultEdit);
}

/** 바뀌었는지는 서버와 같은 규칙(진단 제안과 다른 항목만 fix)으로 미리 본다 — 3안을 버리기 전에 묻기 위해 */
function editNext() {
  const d = ws().draft;
  const e = d.edit!;
  const a = d.diag!;
  const start = +e.start;
  const val: Record<string, unknown> = { competencies: e.competencies, resourceIds: e.resourceIds, outcome: String(e.outcome).trim(), known: e.known };
  const fix: Record<string, unknown> = {};
  FIX.forEach(([k]) => {
    if (!(k === 'resourceIds' ? sameSet(val[k] as string[], a[k] as string[]) : JSON.stringify(val[k]) === JSON.stringify(a[k]))) fix[k] = val[k];
  });
  return { startStage: start === a.startStage ? null : start, fix: Object.keys(fix).length ? fix : null, prefs: clone(e.prefs) };
}

async function editSave(go: ReturnType<typeof useGo>): Promise<void> {
  const e = ws().draft.edit!;
  const r = await draftCall('수정한 내용을 저장하지 못했어요', (id) =>
    draftsApi.overrides(id, { start: +e.start, competencies: e.competencies, resourceIds: e.resourceIds, outcome: e.outcome, known: e.known, prefs: e.prefs }),
  );
  if (!r) return;
  go(paths.newResult);
  toast((r as { changed?: boolean }).changed ? '수정한 내용을 저장했어요' : '바뀐 내용이 없어요');
}

function ListEdit({ k, ph }: { k: 'competencies' | 'known'; ph: string }) {
  const arr = useAt<string[]>(`draft.edit.${k}`) || [];
  const [v, setV] = useState('');
  const add = () => {
    const t = v.trim().replace(/\s+/g, ' ');
    if (!t) return;
    if (!arr.includes(t)) setAt(`draft.edit.${k}`, [...arr, t]);
    setV('');
  };
  return (
    <>
      <div className="chips">
        {arr.length ? (
          arr.map((t, i) => (
            <span className="chip on" key={t}>
              {t}
              <button type="button" className="link quiet" aria-label={`${t} 빼기`} onClick={() => setAt(`draft.edit.${k}`, arr.filter((_, j) => j !== i))}>
                <Icon name="x" />
              </button>
            </span>
          ))
        ) : (
          <span className="muted small">없음</span>
        )}
      </div>
      <div className="addrow">
        <input
          className="input"
          id={`add-${k}`}
          placeholder={ph}
          maxLength={60}
          autoComplete="off"
          value={v}
          onChange={(e) => setV(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
              e.preventDefault();
              add();
            }
          }}
        />
        <button type="button" className="btn line sm" onClick={add}>
          <Icon name="plus" />
          추가
        </button>
      </div>
    </>
  );
}

/** 진단 에이전트 제안과 다르게 고친 항목에만 '제안대로 되돌리기'를 보여 준다 */
function SugBack({ k }: { k: string }) {
  const d = useWs((s) => s.draft);
  const e = d.edit!;
  const a = d.diag!;
  const same =
    k === 'start'
      ? +e.start === a.startStage
      : k === 'resourceIds'
        ? sameSet(e.resourceIds, a.resourceIds as string[])
        : JSON.stringify(e[k as keyof EditDoc]) === JSON.stringify(a[k]);
  if (same) return null;
  return (
    <button type="button" className="link quiet back-sug" onClick={() => setAt(`draft.edit.${k}`, k === 'start' ? a.startStage : clone(a[k]))}>
      <Icon name="history" />
      제안대로 되돌리기
    </button>
  );
}

const Ef = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="ef">
    <div className="ef-l">{label}</div>
    <div className="ef-c">{children}</div>
  </div>
);

function MissTip({ k, t }: { k: 'competencies' | 'outcome'; t: string }) {
  const e = useWs((s) => s.draft.edit);
  const miss = e ? editMissing(e)[k] : false;
  return (
    <span className="miss" hidden={!miss}>
      <Icon name="info" />
      {t}
    </span>
  );
}

export function ResultEdit() {
  const go = useGo();
  const d = useWs((s) => s.draft);
  useEffect(() => {
    if (!ws().draft.edit && ws().draft.diag) updateWs((s) => void (s.draft.edit = editFrom()));
  }, []);
  const e = d.edit;
  const a = d.diag;
  if (!e || !a) return null;
  const start = +e.start;
  const save = () => {
    if (!ws().draft.edit || !editOk(ws().draft)) return;
    /* 이미 만든 3안이 있으면, 저장하면 버리고 다시 만든다는 것을 먼저 확인 (10/14) */
    const cur = ws();
    const n = editNext();
    if ((cur.draft.handoff || cur.draft.gen) && !sameJ([cur.draft.startStage || null, cur.draft.fix || null, cur.draft.prefs], [n.startStage, n.fix, n.prefs])) {
      openSheet({
        title: '바꾼 내용으로 저장할까요?',
        body: () => (
          <>
            <p style={{ margin: '0 0 8px' }}>저장하면 바꾼 내용으로 아래를 새로 만들어요.</p>
            <ul className="plain-list">
              <li>로드맵 3안{ws().draftPlan ? '과 고른 안' : ''}</li>
            </ul>
            <p className="small muted" style={{ marginTop: 10 }}>
              점검 결과와 사전 점검 응답은 그대로예요.
            </p>
          </>
        ),
        foot: () => (
          <>
            <button className="btn line" onClick={closeSheet}>
              계속 고치기
            </button>
            <button
              className="btn pri"
              onClick={() => {
                closeSheet();
                if (ws().draft.edit) void editSave(go);
              }}
            >
              저장
            </button>
          </>
        ),
      });
      return;
    }
    void editSave(go);
  };
  return (
    <>
      <Stepper cur="result" />
      <Page
        eyebrow="점검 결과 수정"
        title="바꿀 내용을 고친 뒤 저장해 주세요"
        lead="점검 결과 화면에 보이는 내용을 여기서 한꺼번에 고쳐요. 저장해야 반영되고, 취소하면 그대로예요. 목표·기획서나 사전 점검 응답은 위 단계를 눌러 고치세요."
        foot={
          <>
            <button
              className="btn line"
              onClick={() => {
                updateWs((s) => void (s.draft.edit = null));
                go(paths.newResult);
              }}
            >
              취소
            </button>
            <button className="btn pri" disabled={!editOk(d)} onClick={save}>
              저장
            </button>
          </>
        }
      >
        <div className="card">
          <h2 className="st">
            로드맵 내용 <span className="small muted">진단 에이전트가 정리</span>
          </h2>
          <div className="efs">
            <Ef label="시작 지점">
              <div className="chips">
                {D.stages.map((s) => (
                  <label className="chip" key={s.n}>
                    <input type="radio" name="draft.edit.start" value={s.n} checked={String(start) === String(s.n)} onChange={() => setAt('draft.edit.start', s.n)} />
                    {s.n}단계 {s.name}
                  </label>
                ))}
              </div>
              <p className="small muted ef-n">
                진단 에이전트 제안: {stageLabel(a.startStage)} · {a.startReason} <SugBack k="start" />
              </p>
            </Ef>
            <Ef label="익히게 될 역량">
              <ListEdit k="competencies" ph="예: 답변 근거 표시하기" />
              <MissTip k="competencies" t="역량을 하나 이상 넣어 주세요" />
              <SugBack k="competencies" />
            </Ef>
            <Ef label="듣게 될 강좌·자료">
              <ResPicker path="draft.edit.resourceIds" stage={start} />
              <p className="small muted ef-n">
                팀 DB 등록 자료에서 검색해 골라요. 시작 지점 이후 단계만 보여요. 자격증은 아래 학습 선호에서 정해요. <SugBack k="resourceIds" />
              </p>
            </Ef>
            <Ef label="만들 결과물">
              <BText path="draft.edit.outcome" className="textarea sm" maxLength={200} ariaLabel="만들 결과물" />
              <MissTip k="outcome" t="만들 결과물을 적어 주세요" />
              <SugBack k="outcome" />
            </Ef>
            <Ef label="이미 할 수 있는 것">
              <ListEdit k="known" ph="예: Python 기초" />
              <p className="small muted ef-n">
                여기 있는 내용은 로드맵에서 다시 배우지 않도록 줄여요. <SugBack k="known" />
              </p>
            </Ef>
          </div>
        </div>
        <div className="card" style={{ marginTop: 12 }}>
          <h2 className="st">
            학습 선호 <span className="small muted">세부 사항에서 입력 · 비워 두면 알아서</span>
          </h2>
          <DetailsForm path="draft.edit.prefs" />
        </div>
      </Page>
    </>
  );
}
