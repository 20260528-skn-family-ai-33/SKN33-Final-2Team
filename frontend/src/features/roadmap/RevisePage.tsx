/* 수정 요청 (10/14 · 5차 scr.revise · P.revForm·revCtl·revRow·goalRow·diffView)
   여러 항목을 함께 골라도 된다. 고른 항목과 요청 내용을 관점 에이전트가 함께 보고 수정안을 먼저 보여 준다. 확정하기 전까지 지금 로드맵은 그대로 */
import { useEffect } from 'react';
import { newIdToPath, paths } from '@/app/paths';
import type { PendingRevision, PlanContent, PlanRecord, RevForm } from '@/api/types/plan';
import { CertPicker } from '@/features/draft/details/CertPicker';
import { RevSupView } from '@/features/draft/options/support';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { clone, hrs } from '@/shared/lib/format';
import { actMeta, diff, st, stageName } from '@/shared/lib/plan';
import { certNameOf, prefText } from '@/shared/lib/prefs';
import { ai, cause, errText, PROV } from '@/shared/state/ai';
import { setAt } from '@/shared/state/bind';
import { useCatalog } from '@/shared/state/catalog';
import { toast } from '@/shared/state/ui';
import { draftActive, emptyPrefs, freshDraft, updateWs, useWs } from '@/shared/state/workspace';
import { BCheckArr, BInput, BNum, BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { ActThumb, AgentRow, FailPage, Note, OpsBox, Page, runSub } from '@/shared/ui/parts';
import { ResPicker } from '@/shared/ui/ResPicker';
import { CommentView, commentReq, CmTag } from './comments';
import { cmBy, PlanGate } from './parts';
import { acceptRevision, dropRevision, freshRev, pullPlan, REV_ITEMS, revise, revItemOk, revKey, revOk, usePlanWatch } from './planActions';


/** 수정안 비교 (5차 P.diffView) */
export function DiffView({ pd }: { pd: PendingRevision }) {
  useCatalog((s) => s.certById);
  const ch = diff(pd.from, pd.to, pd);
  const same = pd.from.opt === pd.to.opt;
  return (
    <>
      {pd.summary ? (
        <p className="rv-sum">
          <Icon name="spark" />
          <span>{pd.summary}</span>
        </p>
      ) : null}
      <div className="diff">
        {ch.length ? (
          ch.map((c, i) => (
            <div className="d" key={i}>
              <span className="k">{c.k}</span>
              <span className="ab">
                <s>{c.a}</s>
                <Icon name="arrow" />
                <span className="to">{c.b}</span>
              </span>
            </div>
          ))
        ) : (
          <div className="d">
            <span className="k">변경</span>
            <span>바뀌는 내용이 없어요</span>
          </div>
        )}
      </div>
      {pd.notes && pd.notes.length ? (
        <div className="callout soft rv-notes">
          <Icon name="info" />
          <div>
            <b>요청 중 반영하지 못한 것</b>
            <ul className="plain-list">
              {pd.notes.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      <p className="note">
        <Icon name="info" />
        <span>
          목표는 그대로예요.{same ? ` 관점(${pd.from.opt} ${pd.from.name})도 그대로예요.` : ''} 같은 활동의 진행 기록(완료·메모)은 이어져요.
          {pd.request ? ` 요청 내용: “${pd.request}”` : ''}
        </span>
      </p>
    </>
  );
}

const curText = (k: string, pl: PlanContent): string => {
  const p = pl.prefs || emptyPrefs();
  if (k === 'hours') return `주 ${pl.hours}시간${+p.hours > 0 ? '' : ' (에이전트가 정함)'}`;
  if (k === 'cert') return certNameOf(p) || '계획 없음';
  if (['weeks', 'budget', 'format', 'etc'].includes(k)) return prefText(k as 'weeks', p);
  if (k === 'start') return `${pl.start}단계 ${stageName(pl.start)}`;
  if (k === 'pid') return `${pl.opt} ${pl.name}`;
  return `활동 ${pl.acts.length}개`;
};

const REV_MISS: Record<string, string> = {
  hours: '0.5~40 사이로 적거나 비워 주세요',
  weeks: '1~52 사이로 적거나 비워 주세요',
  budget: '0 이상으로 적거나 비워 주세요',
  pid: '지금과 다른 관점을 골라 주세요',
  remove: '뺄 활동을 하나 이상 골라 주세요',
  replace: '바꿀 활동을 하나 이상 골라 주세요',
  add: '넣을 자료를 고르거나 과제를 적어 주세요',
};

function RevCtl({ k, R }: { k: string; R: PlanRecord }) {
  const pl = R.plan;
  const r = R.rev as RevForm;
  const base = `plans.${R.id}.rev.v`;
  const lab = REV_ITEMS.find((x) => x[0] === k)?.[1] || '';
  const num = (unit: string, min: number, max: number | undefined, step: number, ph: string, help: string) => (
    <>
      <div className="unit">
        <BNum path={`${base}.${k}`} min={min} max={max} step={step} placeholder={ph} ariaLabel={lab} />
        <span>{unit}</span>
      </div>
      <small className="muted">{help}</small>
    </>
  );
  const actList = (path: string) => (
    <div className="choices">
      {pl.acts.map((a) => (
        <label className="choice" key={a.id}>
          <BCheckArr path={path} value={a.id} />
          <ActThumb a={a} />
          <span className="tx">
            {a.title}
            <small>
              {a.stage}단계 · {actMeta(a)} · {hrs(a.hours)}
              {st(R.progress, a.id) === 'done' ? ' · 완료' : ''}
            </small>
          </span>
          <span className="ck">
            <Icon name="check" />
          </span>
        </label>
      ))}
    </div>
  );
  if (k === 'hours') return num('시간 / 주', 0.5, 40, 0.5, '알아서', '0.5~40시간. 비우면 관점과 기간에 맞게 에이전트가 정해요');
  if (k === 'weeks') return num('주 안에', 1, 52, 1, '없음', '1~52주. 비우면 기간을 정하지 않아요');
  if (k === 'budget') return num('원', 0, undefined, 10000, '알아서', '0을 넣으면 무료 자료만 써요. 비우면 알아서 골라요');
  if (k === 'format')
    return (
      <select className={`input df-sel ${r.v.format ? '' : 'empty'}`} aria-label={lab} value={r.v.format} onChange={(e) => setAt(`${base}.format`, e.target.value)}>
        <option value="">알아서</option>
        {D.formatOpts.map(([x, l]) => (
          <option value={x} key={x}>
            {l}
          </option>
        ))}
      </select>
    );
  if (k === 'cert')
    return (
      <>
        <CertPicker path={`${base}.cert`} />
        <small className="muted">분야를 고른 뒤 자격을 골라 주세요. ‘계획 없음’이면 자격 준비 활동을 빼요</small>
      </>
    );
  if (k === 'etc')
    return <BText path={`${base}.etc`} className="textarea sm" maxLength={500} ariaLabel={lab} placeholder="예: 다음 달 둘째 주는 출장이 많아요. 평일 저녁에만 공부할 수 있어요." />;
  if (k === 'start')
    return (
      <div className="chips">
        {D.stages.map((s) => (
          <label className="chip" key={s.n}>
            <input type="radio" name="rv-start" value={s.n} checked={+r.v.start === s.n} onChange={() => setAt(`${base}.start`, s.n)} />
            {s.n}단계 {s.name}
            {s.n === pl.start ? ' (지금)' : ''}
          </label>
        ))}
      </div>
    );
  if (k === 'pid')
    return (
      <>
        <div className="chips">
          {D.optionOrder.map((id) => (
            <label className="chip" key={id}>
              <input type="radio" name="rv-pid" value={id} checked={r.v.pid === id} onChange={() => setAt(`${base}.pid`, id)} />
              {id} {D.perspectives[id].name}
              {id === pl.opt ? ' (지금)' : ''}
            </label>
          ))}
        </div>
        <small className="muted">고른 관점의 하위 에이전트가 진단 내용과 바뀐 조건으로 로드맵을 새로 써요</small>
      </>
    );
  if (k === 'remove') return actList(`${base}.remove`);
  if (k === 'replace')
    return (
      <>
        {actList(`${base}.replace`)}
        <BInput path={`${base}.replaceHow`} maxLength={200} placeholder="어떻게 바꿀까요? (선택) 예: 영상 강의로, 더 짧은 자료로" ariaLabel="바꿀 방향" />
      </>
    );
  if (k === 'add') {
    const have = pl.acts.map((a) => a.res).filter(Boolean) as string[];
    return (
      <>
        <ResPicker path={`${base}.addRes`} exclude={have} />
        <BText
          path={`${base}.addTask`}
          className="textarea sm"
          maxLength={400}
          ariaLabel="직접 할 과제"
          placeholder={'직접 할 과제를 한 줄에 하나씩 적어 주세요 (선택)\n예: 부서 FAQ 20건으로 답변 품질 점검하기'}
        />
        <small className="muted">자격증은 위 ‘자격증 계획’에서 바꿔요</small>
      </>
    );
  }
  return null;
}

function RevRow({ k, R }: { k: string; R: PlanRecord }) {
  const r = R.rev as RevForm;
  const lab = REV_ITEMS.find((x) => x[0] === k)?.[1] || '';
  const on = !!r.on[k];
  const toggle = () => updateWs((s) => void ((s.plans[R.id].rev as RevForm).on[k] = !on));
  return (
    <div className={`ef rv${on ? ' on' : ''}`}>
      <label className="ef-l rv-l">
        <input type="checkbox" checked={on} onChange={toggle} />
        <span>
          {lab}
          <small>지금: {curText(k, R.plan)}</small>
        </span>
      </label>
      <div className="ef-c">
        {on ? (
          <>
            <RevCtl k={k} R={R} />
            {REV_MISS[k] ? (
              <span className="miss" hidden={revItemOk(r, k, R.plan.opt)}>
                <Icon name="info" />
                {REV_MISS[k]}
              </span>
            ) : null}
          </>
        ) : (
          <div>
            <button type="button" className="link quiet rv-pick" onClick={toggle}>
              <Icon name="edit" />
              바꾸기
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function GoalRow({ R }: { R: PlanRecord }) {
  const go = useGo();
  const drafting = useWs((s) => draftActive(s));
  const lastNew = useWs((s) => s.lastNew);
  const pl = R.plan;
  return (
    <div className="ef rv">
      <div className="ef-l rv-l nock">
        <span>
          목표<small>지금: {pl.goal}</small>
        </span>
      </div>
      <div className="ef-c">
        <p className="small muted" style={{ margin: 0 }}>
          목표가 바뀌면 사전 점검부터 다시 해야 해서 새 로드맵으로 만들어요. 지금 로드맵은 새 로드맵을 확정할 때까지 그대로예요.
        </p>
        <div>
          {drafting ? (
            <button type="button" className="btn line sm" onClick={() => go(newIdToPath(lastNew))}>
              <Icon name="pen" />
              작성 중인 새 로드맵 이어서 하기
            </button>
          ) : (
            <button
              type="button"
              className="btn line sm"
              onClick={() => {
                updateWs((s) => {
                  s.draft = freshDraft();
                  s.draft.prefs = { ...emptyPrefs(), ...clone(pl.prefs || emptyPrefs()) };
                  s.draftId = null;
                  s.draftPlan = null;
                  s.plans[R.id].rev = null;
                });
                go(paths.newGoal);
                toast('지금 로드맵의 학습 여건을 채워 뒀어요. 새 목표를 적어 주세요');
              }}
            >
              <Icon name="pen" />
              지금 조건으로 새 로드맵 작성
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function RevForm({ R }: { R: PlanRecord }) {
  const r = R.rev as RevForm;
  const grp = (g: 'cond' | 'plan' | 'acts', title: string) => (
    <div className="card rv-g">
      <h2 className="st">{title}</h2>
      <div className="efs">
        {REV_ITEMS.filter((x) => x[2] === g).map(([k]) => (
          <RevRow key={k} k={k} R={R} />
        ))}
        {g === 'plan' ? <GoalRow R={R} /> : null}
      </div>
    </div>
  );
  return (
    <>
      {grp('cond', '학습 여건')}
      {grp('plan', '로드맵 구성')}
      {grp('acts', '활동')}
      <div className="card rv-g">
        <h2 className="st">
          요청 내용 <span className="small muted">선택 · 항목 없이 문장만 적어도 돼요</span>
        </h2>
        {r.fromComment ? (
          <p className="small muted" style={{ margin: '0 0 8px' }}>
            부서장 코멘트로 채웠어요. 반영하지 않을 부분은 지우고, 덧붙일 내용을 적어 주세요.
          </p>
        ) : null}
        <BText path={`plans.${R.id}.rev.note`} maxLength={600} ariaLabel="요청 내용" placeholder="예: 평일 저녁에만 시간이 나요. 실습을 늘려 주세요." />
      </div>
    </>
  );
}

function Revise({ R }: { R: PlanRecord }) {
  const go = useGo();
  usePlanWatch(R.id);
  const base = R.plan;
  const noForm = !R.rev || !R.rev.v;
  useEffect(() => {
    if (noForm) updateWs((s) => void (s.plans[R.id].rev = freshRev(s.plans[R.id])));
  }, [noForm, R.id]);
  if (!R.rev || !R.rev.v) return null;
  const r = R.rev;
  const pd = R.pending;
  const busy = !!r.running;
  const pid = r.on.pid && r.v.pid !== base.opt ? r.v.pid : base.opt;
  const agent = `${pid} ${D.perspectives[pid].name}`;
  const cm = r.fromComment ? (R.comments || []).find((c) => c.id === r.fromComment) : undefined;
  /* 요청 내용을 채운 뒤 부서장이 코멘트를 고쳤으면(10/23 코멘트 수정) 알리고, 고친 내용으로 다시 채울 수 있게 한다 */
  const stale = !!(cm && r.cmStamp && cm.stamp !== r.cmStamp);
  const fail = r.fail && 'cause' in r.fail && r.fail.cause ? cause(r.fail.cause) : null;
  const ok = revOk(R);
  let out: React.ReactNode = null;
  if (busy)
    out = (
      <div className="agents">
        <AgentRow st="run" name={`${agent} · 수정안 작성`} sub={runSub('roadmap', '고른 항목과 요청 내용을 반영하고 있어요')} />
      </div>
    );
  else if (fail)
    out = (
      <FailPage
        title="수정안을 만들지 못했어요"
        desc={`${agent} 에이전트가 수정안을 쓰지 못했어요. 지금 로드맵은 그대로이고, 고른 항목과 요청 내용도 그대로 남아 있어요.`}
        cause={errText(fail)}
        body={
          <div className="agents">
            <AgentRow st="fail" name={`${agent} · 수정안 작성`} sub={ai.live() ? `${PROV[ai.mode()]} · ${ai.modelName('roadmap')}` : ''} tag="오류 발생" tagCls="fail" />
          </div>
        }
        ops={<OpsBox items={[['', fail]]} />}
        foot={
          <button className="btn pri" disabled={!ok} onClick={() => void revise(R.id)}>
            <Icon name="retry" />
            다시 시도하기
          </button>
        }
      />
    );
  else if (pd)
    out = (
      <>
        <div className="sec-h">
          <h2 className="st">수정안</h2>
          {pd.source && pd.source !== 'mock' ? <span className="tag acc">{PROV[pd.source] || 'API'} 작성</span> : <span className="tag">가데이터</span>}
        </div>
        {revKey(r) !== pd.key ? <Note>수정안을 만든 뒤 고른 항목이나 요청 내용을 바꿨어요. 바뀐 내용으로 보려면 ‘수정안 다시 만들기’를 눌러 주세요.</Note> : null}
        <DiffView pd={pd} />
        <RevSupView pd={pd} pid={R.id} onPulled={async () => void (await pullPlan(R.id))} />
      </>
    );
  const cmt = cm ? (
    <>
      <div className="callout soft rv-cmt">
        <Icon name="chat" />
        <div>
          <b>
            부서장 코멘트 · {cmBy(cm)} · {cm.at}
            {cm.editedAt ? ` · 수정됨 ${cm.editedAt}` : ''}
          </b>
          <br />
          <span className="small muted">
            {stale
              ? '이 수정 요청을 시작한 뒤 부서장이 코멘트를 고쳤어요. 아래가 고친 코멘트이고, ‘요청 내용’은 고치기 전 내용이에요.'
              : '아래 ‘요청 내용’에 채워 뒀어요. 반영할 부분만 남기고 수정안을 만들어 주세요.'}{' '}
            확정하면 이 코멘트가 ‘v{(base.version || 0) + 1}에 반영’으로 바뀌어요.
          </span>
          {stale && !busy ? (
            <div className="actions cm-act">
              <button
                className="btn line sm"
                onClick={() => {
                  updateWs((s) => {
                    const x = s.plans[R.id].rev as RevForm;
                    x.note = commentReq(cm);
                    x.cmStamp = cm.stamp;
                  });
                  toast('고친 코멘트로 요청 내용을 다시 채웠어요');
                }}
              >
                고친 코멘트로 요청 내용 다시 채우기
              </button>
            </div>
          ) : null}
        </div>
      </div>
      <CommentView c={cm} />
    </>
  ) : null;
  return (
    <Page
      back={r.fromComment ? paths.comments(base.rid || R.id) : paths.roadmap(base.rid || R.id)}
      eyebrow={`${base.name} · v${base.version} · ${base.goal}`}
      title="무엇을 바꿀까요?"
      lead={`여러 항목을 함께 골라도 돼요. 고른 항목과 요청 내용을 ${agent} 에이전트가 함께 보고 수정안을 먼저 보여 드려요. 확정하기 전까지 지금 로드맵은 그대로예요.`}
      foot={
        pd && !busy && !fail ? (
          <>
            <button className="btn pri" onClick={() => void acceptRevision(go, R.id)}>
              v{(base.version || 0) + 1}로 확정하기
            </button>
            <button className="btn line" onClick={() => void dropRevision(go, R.id)}>
              취소
            </button>
          </>
        ) : undefined
      }
    >
      {cmt}
      <RevForm R={R} />
      {fail && !busy ? null : (
        <div className="actions rv-act">
          <button className={`btn ${pd ? 'line' : 'pri'}`} disabled={!ok} onClick={() => void revise(R.id)}>
            {busy ? '수정안을 만드는 중…' : pd ? '수정안 다시 만들기' : '수정안 만들기'}
          </button>
        </div>
      )}
      <p className="small muted rv-hint" hidden={busy || ok}>
        바꿀 항목을 고르거나 요청 내용을 적어 주세요. 고른 항목의 값이 맞는지도 확인해 주세요.
      </p>
      {out ? (
        <div className="sec" id="diffSec">
          {out}
        </div>
      ) : null}
    </Page>
  );
}

export function RevisePage() {
  return (
    <PlanGate make={paths.revise} fallback={paths.roadmaps} needActive>
      {(R) => <Revise R={R} />}
    </PlanGate>
  );
}

export { CmTag };
