/* 5. 3안 생성 (로드맵 계획 에이전트 · 관점별 병렬 · 서버 작업 셋 · 5차 scr['new-gen'])
   하위 에이전트마다 따로 실행하고, API 오류를 가데이터로 대신하지 않는다. 실패한 줄은 빨간 X로 바뀌고
   그 안만 '다시 시도'(API-29)하거나, '로드맵 확인하기'(API-30)로 작성된 안만 가지고 다음 단계로 넘어갈 수 있다.
   진행 상태는 서버 작성 문서(genRun)에 있어 새로 고쳐도 이어서 보이고, 교육비 규정 안내는 생성 화면에서만 보여 준다 */
import { useEffect, useState } from 'react';
import { draftsApi } from '@/api/endpoints/drafts';
import type { DraftDoc, Handoff } from '@/api/types/draft';
import { paths } from '@/app/paths';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { won } from '@/shared/lib/format';
import { ai, cause, userText, userTodo } from '@/shared/state/ai';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { AgentRow, FailPage, OpsBox, Page, via } from '@/shared/ui/parts';
import { draftCall, syncGenCur } from '../draftSync';
import { startEdit, genStart } from '../result/ResultStep';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';
import { EducationGuide } from './EducationGuide';
import { genStartedAt } from './genStartedAt';

let hoOpen = false;
export function HandoffView({ h }: { h: Handoff }) {
  return (
    <details className="card flat handoff" id="hoView" open={hoOpen} onToggle={(e) => (hoOpen = (e.target as HTMLDetailsElement).open)}>
      <summary>
        <Icon name="right" />
        진단 에이전트가 넘긴 내용 보기
      </summary>
      <dl className="kv">
        <dt>목표</dt>
        <dd>
          {h.goal}
          {h.projectFile ? (
            <>
              <br />
              <span className="small muted">기획서: {String(h.projectFile)}</span>
            </>
          ) : null}
        </dd>
        <dt>익힐 역량</dt>
        <dd>{h.focus.join(', ')}</dd>
        <dt>이미 할 수 있는 것</dt>
        <dd>{h.known.join(', ') || '없음'}</dd>
        <dt>학습 선호</dt>
        <dd>
          주당 {h.prefs.weeklyHours ? `${h.prefs.weeklyHours}시간` : '알아서'} · 기간 제한 {h.prefs.deadlineWeeks ? h.prefs.deadlineWeeks + '주' : '없음'} ·
          예산 {h.prefs.budgetLimit != null ? won(h.prefs.budgetLimit) : h.prefs.budgetAuto ? '알아서' : '없음'}
        </dd>
        {h.projectSummary ? (
          <>
            <dt>기획서 요약</dt>
            <dd className="pre">{h.projectSummary}</dd>
          </>
        ) : null}
        {typeof h.profile?.workDescription === 'string' && h.profile.workDescription ? (
          <><dt>본인 업무 설명</dt><dd className="pre">{h.profile.workDescription}</dd></>
        ) : null}
        {Array.isArray(h.profile?.projectExperience) && h.profile.projectExperience.length ? (
          <><dt>본인 프로젝트 경험</dt><dd className="pre">{h.profile.projectExperience.map(String).join('\n')}</dd></>
        ) : null}
        <dt>메모</dt>
        <dd>{h.userNotes.concat(h.agentNotes).join(' / ') || '없음'}</dd>
        {h.userEdited && h.userEdited.length ? (
          <>
            <dt>직접 고친 항목</dt>
            <dd>{h.userEdited.join(', ')}</dd>
          </>
        ) : null}
      </dl>
    </details>
  );
}

export const curGen = (d: DraftDoc) => (d.genRun && d.handoff && d.genRun.key === d.handoff.key ? d.genRun : null);
export const curOut = (d: DraftDoc) => (d.gen && d.handoff && d.gen.key === d.handoff.key ? d.gen : null);
const genState = (rows: NonNullable<DraftDoc['genRun']>['rows']) => {
  const ps = D.optionOrder.map((id) => rows[id] || { st: 'run' });
  return { running: ps.some((x) => x.st === 'run'), ok: ps.filter((x) => x.st === 'ok').length, fail: ps.filter((x) => x.st === 'fail').length };
};

const rowName = (id: string) => `${D.perspectives[id].name}`;

async function genRetry(id: string): Promise<void> {
  const r = curGen(ws().draft);
  if (!r || !r.rows[id] || r.rows[id].st !== 'fail') return;
  updateWs((s) => {
    const rr = curGen(s.draft);
    // 서버 응답이 새 시작 시각을 줄 때까지 이전 시도의 시각으로 세지 않게 지금 시각을 둔다
    if (rr) Object.assign(rr.rows[id], { st: 'run', startedAt: Date.now() });
  });
  await draftCall(`${D.perspectives[id].name}을 다시 쓰지 못했어요`, (did) => draftsApi.optionRetry(did, id));
}

function GenRowView({ d, id }: { d: DraftDoc; id: string }) {
  const r = curGen(d);
  const row = r ? r.rows[id] : { st: 'run', tries: 1 };
  const name = rowName(id);
  if (!row || row.st === 'run') return <AgentRow st="run" name={name} sub="진단 결과를 토대로 계획 생성 중" />;
  if (row.st === 'ok') return <AgentRow st="ok" name={name} sub="준비가 완료되었습니다." tag="작성 완료" tagCls="acc" />;
  const c = cause(row.err || {});
  return (
    <AgentRow
      st="fail"
      name={name}
      sub={ai.live() ? via('roadmap') : ''}
      failLabel="생성 실패"
      tag="오류 발생"
      tagCls="fail"
      onRetry={() => void genRetry(id)}
      detail={c.user || userText(c.kind)}
    />
  );
}

/** 3안 진행 막대: 결과는 다음 화면(비교표)에서 보이므로 결과 모양을 흉내 내지 않고, 몇 안이 끝났는지와 작성을 요청한 뒤 기다린 시간을 보여 준다.
    시작 시각은 서버 기록(genStartedAt)을 쓰고, 기록이 없는 이전 작업만 이 화면을 연 시각부터 센다 */
function GenProgress({ d, done }: { d: DraftDoc; done: boolean }) {
  const r = curGen(d);
  const sts = D.optionOrder.map((id) => r?.rows[id]?.st || 'run');
  const ok = sts.filter((st) => st === 'ok').length;
  const [opened] = useState(() => Date.now());
  const [now, setNow] = useState(opened);
  const start = genStartedAt(r) ?? opened;
  useEffect(() => {
    if (done) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [done]);
  const sec = Math.max(0, Math.floor((now - start) / 1000));
  return (
    <div className={`gen-progress${done ? ' done' : ''}`}>
      <div className="gen-progress-head">
        <b role="status" aria-live="polite">{done ? `${sts.length}안 모두 작성 완료` : `${sts.length}안 중 ${ok}안 작성 완료`}</b>
        {!done && <span className="small muted" aria-hidden="true">기다린 시간 {Math.floor(sec / 60)}:{String(sec % 60).padStart(2, '0')}</span>}
      </div>
      <div className="gen-progress-bar" style={{ gridTemplateColumns: `repeat(${sts.length}, minmax(0, 1fr))` }} role="progressbar" aria-label="로드맵 3안 작성 진행" aria-valuemin={0} aria-valuemax={sts.length} aria-valuenow={ok}>
        {D.optionOrder.map((id, i) => <span key={id} className={`gen-seg ${sts[i] === 'ok' ? 'ok' : 'run'}`} title={`${rowName(id)} · ${sts[i] === 'ok' ? '작성 완료' : '작성 중'}`} />)}
      </div>
      {!done && <p className="small muted">세 안을 모두 쓰면 ‘로드맵 계획 미리보기’에서 나란히 비교할 수 있어요.</p>}
    </div>
  );
}

/** 여러 안이 실패했을 때 할 일은 겹치지 않게 한 번씩만 */
const todoOf = (errs: { kind: string }[]) => [...new Set(errs.flatMap((e) => userTodo(e.kind)))].join(' ');

export function GenerationStep() {
  const go = useGo();
  const d = useWs((s) => s.draft);
  const h = d.handoff;
  const r = curGen(d);
  useDraftWatch();
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const cur = ws().draft;
      if (cur.v2Assessment && !curGen(cur) && !curOut(cur)) {
        void genStart(go);
        return;
      }
      if (!curGen(cur) && curOut(cur)) {
        go(paths.newOptions, { force: true, replace: true });
        return;
      }
      if (!curGen(cur) && !curOut(cur)) void genStart(go);
      syncGenCur();
    }, 0);
    return () => window.clearTimeout(timer);
    // 생성 화면 진입 뒤 시작하며, StrictMode 재실행은 중복 요청하지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const g = r ? genState(r.rows) : { running: true, ok: 0, fail: 0 };
  const rows = (
    <div className="agents">
      {D.optionOrder.map((id) => (
        <GenRowView key={id} d={d} id={id} />
      ))}
      {r && <EducationGuide saved={d.educationGuide} />}
    </div>
  );
  if (g.fail && r) {
    const failed = D.optionOrder.filter((id) => r.rows[id]?.st === 'fail');
    const names = failed.map((id) => `${D.perspectives[id].name}`).join(', ');
    const errs = failed.map((id) => cause(r.rows[id].err || {}));
    return (
      <>
        <Stepper cur="options" />
        <FailPage
          title="로드맵 3안 작성 중 문제가 발생했어요"
          desc={
            g.ok
              ? `${names}을 쓰지 못했어요. 작성된 안만 가지고 다음 단계로 넘어가거나, 실패한 안만 다시 시도할 수 있어요.`
              : '관점별 하위 에이전트가 로드맵 안을 쓰지 못했어요. 실패한 안을 다시 시도하거나, 조건을 고쳐 다시 만들어 주세요.'
          }
          cause={`${failed.map((id, i) => `${D.perspectives[id].name} — ${errs[i].user || userText(errs[i].kind)}`).join(' · ')}. ${todoOf(errs)}`}
          body={
            <>
              {h && <HandoffView h={h} />}
              {rows}
            </>
          }
          ops={<OpsBox items={failed.map((id, i) => [rowName(id), errs[i]])} />}
          foot={
            <>
              <button className="btn line" onClick={() => startEdit(go)}>
                <Icon name="left" />
                조건 수정하고 다시 만들기
              </button>
              <button
                className="btn pri"
                disabled={g.running || !g.ok}
                onClick={async () => {
                  if (await draftCall('작성된 안으로 넘어가지 못했어요', (id) => draftsApi.acceptPartial(id))) go(paths.newOptions);
                }}
              >
                <Icon name="map" />
                로드맵 확인하기
              </button>
            </>
          }
          hint={
            g.running
              ? '작성 중인 안이 끝나면 ‘로드맵 확인하기’를 누를 수 있어요.'
              : !g.ok
                ? '작성된 안이 없어요. 실패한 안을 다시 시도하거나 조건을 고쳐 주세요.'
                : `‘로드맵 확인하기’를 누르면 작성된 ${g.ok}개 안만 비교해요. 실패한 안은 저장하지 않아요.`
          }
        />
      </>
    );
  }
  const done = !!r && !g.running && g.ok === D.optionOrder.length && !!curOut(d);
  return (
    <>
      <Stepper cur="options" />
      <Page
        title={done ? '로드맵 3안을 다 썼어요' : '로드맵 계획 에이전트가 3안을 쓰고 있어요'}
        lead={
          done
            ? '‘로드맵 계획 미리보기’를 눌러 비교해 보세요.'
            : ai.mode() === 'ollama'
              ? '관점별 하위 에이전트 셋이 진단 에이전트가 넘긴 같은 내용으로 동시에 요청해요. AI 서버 사정에 따라 차례대로 처리돼 시간이 더 걸릴 수 있어요. 화면을 떠나도 서버가 이어서 써요.'
              : '관점별 하위 에이전트 셋이 진단 에이전트가 넘긴 같은 내용으로 동시에 작성해요. 화면을 떠나도 서버가 이어서 써요.'
        }
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newResult)}>
              <Icon name="left" />
              이전
            </button>
            <button className="btn pri" disabled={!done} onClick={() => go(paths.newOptions)}>
              로드맵 계획 미리보기
            </button>
          </>
        }
      >
        <GenProgress d={d} done={done} />
        {h && <HandoffView h={h} />}
        {rows}
      </Page>
    </>
  );
}
