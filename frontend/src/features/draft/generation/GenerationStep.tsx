/* 5. 3안 생성 (로드맵 계획 에이전트 · 관점별 병렬 · 서버 작업 셋 · 5차 scr['new-gen'])
   하위 에이전트마다 따로 실행하고, API 오류를 가데이터로 대신하지 않는다. 실패한 줄은 빨간 X로 바뀌고
   그 안만 '다시 시도'(API-29)하거나, '로드맵 확인하기'(API-30)로 작성된 안만 가지고 다음 단계로 넘어갈 수 있다.
   진행 상태는 서버 작성 문서(genRun)에 있어 새로 고쳐도 이어서 보이고, 지원 조건은 세 안이 정해지면 서버가 규정 에이전트로 확인한다 */
import { useEffect } from 'react';
import { draftsApi } from '@/api/endpoints/drafts';
import type { DraftDoc, Handoff } from '@/api/types/draft';
import { paths } from '@/app/paths';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { won } from '@/shared/lib/format';
import { regGroups } from '@/shared/lib/reg';
import { ai, cause, userText, userTodo } from '@/shared/state/ai';
import { useCatalog } from '@/shared/state/catalog';
import { me } from '@/shared/state/session';
import { onDataReset } from '@/shared/state/events';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { AgentRow, FailPage, OpsBox, Page, runSub, via } from '@/shared/ui/parts';
import { draftCall, takeDraft } from '../draftSync';
import { startEdit, genStart } from '../result/ResultStep';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';
import { SUP_LV, supRetry, syncGenCur } from '../options/support';

let hoOpen = false;
export function HandoffView({ h }: { h: Handoff }) {
  const res = useCatalog((s) => s.res);
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
        <dt>시작 단계</dt>
        <dd>
          {h.startStage}단계 · {h.startReason}
        </dd>
        <dt>익힐 역량</dt>
        <dd>{h.focus.join(', ')}</dd>
        <dt>이미 할 수 있는 것</dt>
        <dd>{h.known.join(', ') || '없음'}</dd>
        <dt>학습 선호</dt>
        <dd>
          방식 {h.prefs.format} · 주당 {h.prefs.weeklyHours ? `${h.prefs.weeklyHours}시간` : '알아서'} · 기간 {h.prefs.deadlineWeeks ? h.prefs.deadlineWeeks + '주' : '없음'} ·
          예산 {h.prefs.budgetLimit != null ? won(h.prefs.budgetLimit) : h.prefs.budgetAuto ? '알아서' : '없음'} · 자격증 {h.prefs.certPlan}
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
        <dt>자료 후보</dt>
        <dd>{h.resourceHints.map((id) => (res[id] ? res[id].title : id)).join(', ') || '없음'}</dd>
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

/* 서버를 다시 켜서 끊긴 지원 조건 확인을 이어서 시작한다(실패한 확인은 건드리지 않음 · 화면에 들어올 때 한 번).
   4초 뒤에 부를 때 그때의 작성 문서·계정이 처음 본 것과 같은지 다시 확인한다(계정·초안을 바꾸는 사이 다른 초안에 요청하지 않게) */
const supKicked = new Set<string>();
onDataReset(() => supKicked.clear());
export function useKickSupport(): void {
  const info = useWs((s) => {
    const g = curOut(s.draft);
    if (!g || !s.draftId || !s.owner) return '';
    const pid = D.optionOrder.find((x) => g.options[x] && !g.options[x].support && !g.options[x].supportFail);
    return pid ? JSON.stringify([s.owner, s.draftId, g.key, pid, g.cur || {}]) : '';
  });
  useEffect(() => {
    if (!info || supKicked.has(info)) return;
    supKicked.add(info);
    const [owner, draftId, , pid] = JSON.parse(info) as [string, string, string, string];
    let fired = false;
    const t = setTimeout(() => {
      fired = true;
      if (ws().owner !== owner || ws().draftId !== draftId) return;
      draftsApi
        .supportRetry(draftId, pid)
        .then((r) => {
          if (ws().owner === owner && ws().draftId === draftId) takeDraft(r, true);
        })
        .catch(() => {});
    }, 4000);
    return () => {
      clearTimeout(t);
      if (!fired) supKicked.delete(info);
    };
  }, [info]);
}

const rowName = (id: string) => `${id} ${D.perspectives[id].name}`;

async function genRetry(id: string): Promise<void> {
  const r = curGen(ws().draft);
  if (!r || !r.rows[id] || r.rows[id].st !== 'fail') return;
  updateWs((s) => {
    const rr = curGen(s.draft);
    if (rr) rr.rows[id].st = 'run';
  });
  await draftCall(`${id} 안을 다시 쓰지 못했어요`, (did) => draftsApi.optionRetry(did, id));
}

function GenRowView({ d, id }: { d: DraftDoc; id: string }) {
  const r = curGen(d);
  const row = r ? r.rows[id] : { st: 'run', tries: 1 };
  const name = rowName(id);
  if (!row || row.st === 'run') return <AgentRow st="run" name={name} sub={runSub('roadmap', (row?.tries || 1) > 1 ? '다시 시도하는 중이에요' : '진단 에이전트가 넘긴 내용으로 작성 중이에요')} />;
  if (row.st === 'ok') return <AgentRow st="ok" name={name} sub={row.out?.tagline} tag="작성 완료" tagCls="acc" />;
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

/** 규정 에이전트 줄: 3안이 정해지기 전에는 기다림, 확인 중, 안별 결과, 실패(다시 시도는 눌러야만) */
function SupRow({ d }: { d: DraftDoc }) {
  const name = '규정 에이전트 · 안별 지원 조건 확인';
  const g = curOut(d);
  if (!g) return <AgentRow st="wait" name={name} sub="세 안이 정해지면 안마다 교육비 지원·근무시간 학습 인정을 확인해요" />;
  const os = D.optionOrder.map((pid) => g.options[pid]).filter(Boolean);
  const fails = os.filter((o) => o.supportFail);
  if (fails.length) {
    const c = cause(fails[0].supportFail?.cause);
    return (
      <AgentRow
        st="fail"
        name={name}
        sub={ai.live() ? via('regulation') : ''}
        failLabel="확인 실패"
        tag="오류 발생"
        tagCls="fail"
        onRetry={() => void supRetry('all')}
        detail={`${c.user || userText(c.kind)} · 지원 조건은 ‘확인 필요’로 두고 넘어갈 수 있어요`}
      />
    );
  }
  if (os.some((o) => !o.support)) return <AgentRow st="run" name={name} sub={runSub('regulation', '안마다 유료 자료·학습 형태로 등록된 규정을 확인하고 있어요')} />;
  if (os.every((o) => o.support?.level === 'scope'))
    return (
      <AgentRow
        st="ok"
        warn
        name={name}
        sub={`등록된 규정은 ${regGroups().join('·')} 대상이라 ${me()?.empGroup || ''} 직원은 확인하지 않았어요`}
        tag="적용 대상 아님"
        tagCls="warn"
      />
    );
  const allOk = os.every((o) => o.support?.level === 'ok');
  return (
    <AgentRow
      st="ok"
      warn={!allOk}
      name={name}
      sub={os.map((o) => `${o.id} ${(SUP_LV[o.support?.level || ''] || SUP_LV.missing)[0]}`).join(' · ')}
      tag={allOk ? '근거 확인' : '확인 필요'}
      tagCls={allOk ? 'acc' : 'warn'}
    />
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
  useKickSupport();
  useEffect(() => {
    const cur = ws().draft;
    if (!curGen(cur) && curOut(cur)) {
      go(paths.newOptions, { force: true, replace: true });
      return;
    }
    if (!curGen(cur) && !curOut(cur)) void genStart(go);
    syncGenCur();
    // 화면에 들어올 때 한 번
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!h) return null;
  const g = r ? genState(r.rows) : { running: true, ok: 0, fail: 0 };
  const rows = (
    <div className="agents">
      {D.optionOrder.map((id) => (
        <GenRowView key={id} d={d} id={id} />
      ))}
      <SupRow d={d} />
    </div>
  );
  if (g.fail && r) {
    const failed = D.optionOrder.filter((id) => r.rows[id]?.st === 'fail');
    const names = failed.map((id) => `${id} ${D.perspectives[id].name}`).join(', ');
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
          cause={`${failed.map((id, i) => `${id} ${D.perspectives[id].name} — ${errs[i].user || userText(errs[i].kind)}`).join(' · ')}. ${todoOf(errs)}`}
          body={
            <>
              <HandoffView h={h} />
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
            ? '‘3안 보러 가기’를 눌러 비교해 보세요. 지원 조건 확인이 끝나지 않았어도 넘어갈 수 있어요(비교표에서 이어서 보여 줘요).'
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
              3안 보러 가기
            </button>
          </>
        }
      >
        <HandoffView h={h} />
        {rows}
      </Page>
    </>
  );
}
