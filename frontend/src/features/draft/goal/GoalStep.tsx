/* 1. 목표·기획서 (5차 scr['new-goal'] · P.goalField·goalSug·projectField·docBox)
   기획서 읽기: 파일을 서버에 올리면 서버가 글자를 꺼내고(API-20) 이미지 보기·요약을 작업으로 이어 한다(API-21).
   요약은 화면에서 고칠 수 있고, 요약만 문항·진단·로드맵 에이전트에게 넘긴다. 실패하면 '다시 시도'를 눌러야만 다시 읽는다 */
import { useEffect, useRef } from 'react';
import { draftsApi } from '@/api/endpoints/drafts';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { kb } from '@/shared/lib/format';
import { cause, errText, PROV, type Cause } from '@/shared/state/ai';
import { setAt } from '@/shared/state/bind';
import { toast } from '@/shared/state/ui';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { BText } from '@/shared/ui/bound';
import { me } from '@/shared/state/session';
import { resolveGoalInput } from './goalInput';
import { Icon } from '@/shared/ui/Icon';
import { AgentRow, Note, OpsBox, Page, runSub } from '@/shared/ui/parts';
import { Skeleton } from '@/shared/ui/Skeleton';
import { draftCall, pullDraft } from '../draftSync';
import { clearProject, docDoneText, uploadProject } from './projectDoc';
import { docBusy, goalOk } from '../model';
import { StaleNote } from '../stale';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';
import { loadGoals, loadGoalsIfOld, regenGoals, useGoalStore } from './goalStore';

function GoalSuggestions() {
  const g = useGoalStore((s) => s.gs);
  const go = useGo();
  const run = !!g && g.status === 'running';
  const list = (g && g.candidates) || [];
  const tag =
    !g || run ? null : g.source === 'mock' ? (
      <span className="tag">가데이터</span>
    ) : g.source === 'default' || g.status === 'default' ? null : g.source ? (
      <span className="tag acc">{PROV[g.source] || 'API'} 작성</span>
    ) : null;
  const pick = (i: number) => {
    const c = list[i];
    if (!c) return;
    setAt('draft.goal', c.goal);
    const t = document.querySelector<HTMLTextAreaElement>('#goalText');
    t?.focus();
    toast('목표 칸에 넣었어요. 내 말로 고쳐 써도 돼요');
  };
  const items = (
    <div className={`gs-list${run ? ' busy' : ''}`}>
      {list.map((c, i) => (
        <button type="button" className="gs-it" key={i} disabled={run} onClick={() => pick(i)}>
          <b>{c.goal}</b>
          <small>{c.why}</small>
        </button>
      ))}
    </div>
  );
  let body;
  if (!g)
    body = (
      <div className="agents">
        <AgentRow st="run" name="목표 후보 불러오기" sub="서버에 저장해 둔 목표 후보를 불러오고 있어요…" />
      </div>
    );
  else if (g.status === 'loadfail')
    body = (
      <div className="gs-fail">
        <Icon name="alert" />
        <div className="grow">
          <b>목표 후보를 불러오지 못했어요</b>
          <p className="small">{errText(g.loadError)}</p>
        </div>
        <button type="button" className="btn line sm" onClick={() => void loadGoals()}>
          <Icon name="retry" />
          다시 불러오기
        </button>
      </div>
    );
  else if (run)
    body = (
      <>
        <div className="agents">
          <AgentRow st="run" name="새 목표 후보 생성 중" sub={runSub('default', '인사 정보와 업무 설명·프로젝트를 참고하고 있어요. 완성되면 새 후보 3개로 교체해요.')} />
        </div>
        {list.length ? items : <Skeleton kind="cards" />}
      </>
    );
  else if (g.status === 'failed') {
    const c = cause(g.error || {});
    body = (
      <>
        <div className="gs-fail">
          <Icon name="alert" />
          <div className="grow">
            <b>목표 후보를 {list.length ? '다시 ' : ''}만들지 못했어요</b>
            <p className="small">
              {errText(c)}
              {list.length ? ' 이전 후보를 그대로 보여 드려요.' : ''}
            </p>
            <OpsBox items={[['', c]]} cls="sm" />
          </div>
          <button type="button" className="btn line sm" onClick={() => void regenGoals()}>
            <Icon name="retry" />
            다시 시도
          </button>
        </div>
        {list.length ? items : null}
      </>
    );
  } else if (!list.length)
    body = (
      <p className="small muted" style={{ margin: '6px 0' }}>
        아직 만든 목표 후보가 없어요. 아래 ‘목표 후보 만들기’를 누르면 내 프로필로 후보 3개를 만들어요.
      </p>
    );
  else
    body = (
      <>
        {items}
        {g.status === 'default' ? (
          <Note>
            프로필에 본인 입력 정보(업무 설명·경험 요약·기술 스택·프로젝트)가 없어 판단 근거가 부족해요. AI 활용 업무 기본 후보를 보여 드려요. 프로필을 채우면 맞춤 후보를 다시
            만들어요.{' '}
            <button className="link" onClick={() => go(paths.me)}>
              <Icon name="user" />내 정보에서 채우기
            </button>
          </Note>
        ) : g.note ? (
          <p className="small muted gs-note">
            <Icon name="info" />
            {g.note}
          </p>
        ) : null}
      </>
    );
  const used = g && (g.used || []).length ? `참고한 정보 · ${(g.used || []).join(', ')}${g.who ? ` (${g.who})` : ''}` : '';
  const when = g && g.updatedAt && !run ? ` · ${g.updatedAt} 저장` : '';
  return (
    <div className="gsug" id="goalSug">
      <div className="gs-h">
        <b>
          <Icon name="spark" />
          목표 후보
        </b>
        <span className="small muted">{g && g.status === 'default' ? 'AI 활용 업무 기본 후보' : '내 정보·인사 정보 변경 때 미리 준비해요'}</span>
        {tag}
      </div>
      {body}
      {g && g.stale ? (
        <p className="small muted gs-note">
          <Icon name="info" />내 정보가 바뀐 뒤 아직 다시 만들지 않은 후보예요. 다시 만들면 바뀐 정보로 만들어요.
        </p>
      ) : null}
      <p className="small muted gs-f">
        {used}
        {when}
        {used ? ' · ' : ''}적은 목표와 기획서는 보지 않아요.{' '}
        <button className="link quiet" onClick={() => go(paths.me)}>
          내 정보 보기
        </button>
        {g && g.status !== 'loadfail' && !run ? (
          <>
            {' '}
            <button type="button" className="link" onClick={() => void regenGoals()}>
              <Icon name="retry" />
              {list.length ? '목표 후보 다시 만들기' : '목표 후보 만들기'}
            </button>
          </>
        ) : null}
      </p>
    </div>
  );
}

const DOC_STEP: Record<string, string> = {
  extract: '파일을 서버에 올려 글자와 이미지를 꺼내고 있어요',
  vision: '기획서 이미지를 보고 있어요',
  summary: '기획서를 요약하고 있어요',
};

function DocFailBox({ title, c, children }: { title: string; c: Cause; children: React.ReactNode }) {
  return (
    <div className="docbox fail">
      <p className="db-h">
        <Icon name="alert" />
        <b>{title}</b>
      </p>
      <p className="small">{errText(c)}</p>
      <OpsBox items={[['', c]]} cls="sm" />
      <div className="db-act">{children}</div>
    </div>
  );
}

async function docAgain(skipImages: boolean): Promise<void> {
  if (!ws().draft.doc) return;
  updateWs((s) => {
    if (s.draft.doc) {
      s.draft.doc.status = 'reading';
      s.draft.doc.fail = null;
    }
  });
  await draftCall('기획서를 다시 읽지 못했어요', (id) => draftsApi.projectSummary(id, skipImages));
  await pullDraft();
}

function DocBox() {
  const doc = useWs((s) => s.draft.doc);
  const uploading = useWs((s) => !!s.docUpload);
  const status = uploading ? 'reading' : doc?.status;
  const done = docDoneText(doc);
  /* 요약은 이 화면에 보여 주지 않으므로, 이 화면에서 기다리다 끝나면 알림으로도 한 번 알린다(상자와 같은 문구 기준) */
  const prev = useRef(status);
  useEffect(() => {
    if (prev.current === 'reading' && status === 'ok') toast(done.toast);
    prev.current = status;
  }, [status, done.toast]);
  if (uploading || doc?.status === 'reading') {
    const step = doc?.status === 'reading' ? doc.step : 'extract';
    return (
      <div className="docbox">
        <div className="agents">
          <AgentRow st="run" name="진단 에이전트 · 기획서 읽기" sub={runSub(step === 'vision' ? 'vision' : 'default', DOC_STEP[step || ''] || DOC_STEP.extract)} />
        </div>
      </div>
    );
  }
  if (!doc) return null;
  if (doc.status === 'ok')
    return (
      <div className="docbox ok" role="status">
        <p className="db-h">
          <Icon name="check" />
          <b>{done.title}</b>
        </p>
        <p className="small">{done.body}</p>
      </div>
    );
  if (doc.status === 'fail') {
    const c = cause(doc.fail?.cause || {});
    const visionFail = doc.step === 'vision';
    return (
      <DocFailBox title={visionFail ? '기획서 이미지를 보지 못했어요' : doc.step === 'summary' ? '기획서를 요약하지 못했어요' : '기획서를 읽지 못했어요'} c={c}>
        <button type="button" className="btn line sm" onClick={() => void docAgain(false)}>
          <Icon name="retry" />
          다시 시도
        </button>
        {visionFail ? (
          <button type="button" className="btn line sm" onClick={() => void docAgain(true)}>
            이미지 없이 요약
          </button>
        ) : null}
        <span className="small muted">기획서 없이 목표만으로 진행해도 돼요.</span>
      </DocFailBox>
    );
  }
  return null;
}

function ProjectField() {
  const f = useWs((s) => s.draft.project);
  const uploading = useWs((s) => !!s.docUpload);
  const docErr = useGoalStore((s) => s.docErr);
  if (f)
    return (
      <>
        <div className="file-on">
          <Icon name="file" />
          <div className="tx">
            <b>{f.name}</b>
            <small className="muted">{kb(f.size || 0)}</small>
          </div>
          {/* 올리는 중에는 빼거나 다른 파일로 바꾸지 않는다(늦게 끝난 업로드가 바꾼 상태를 덮지 않게) */}
          {uploading ? (
            <span className="small muted">올리는 중…</span>
          ) : (
            <button className="link quiet" onClick={() => void clearProject()}>
              빼기
            </button>
          )}
        </div>
        <DocBox />
      </>
    );
  return (
    <>
      {docErr ? (
        <DocFailBox title={`‘${docErr.name}’을 읽지 못했어요`} c={docErr.cause}>
          <span className="small muted">다른 파일을 고르거나, 기획서 없이 목표만으로 진행해도 돼요.</span>
        </DocFailBox>
      ) : null}
      <label className="drop">
        <input
          type="file"
          accept=".pdf,.docx,.hwp,.hwpx,.pptx,.txt,.md"
          onChange={(e) => {
            const file = e.target.files && e.target.files[0];
            if (!file) return;
            void uploadProject(file);
          }}
        />
        <span className="ico">
          <Icon name="file" />
        </span>
        <span>
          <b>기획서 파일 고르기</b>
          <small>PDF, 한글(HWP·HWPX), 워드(DOCX), 파워포인트(PPTX), TXT · 15MB까지 · 선택</small>
        </span>
      </label>
    </>
  );
}

export function GoalStep() {
  const go = useGo();
  const d = useWs((s) => s.draft);
  const firstGoal = useGoalStore((s) => s.gs && s.gs.owner && s.gs.owner === me()?.id ? s.gs.candidates[0]?.goal?.trim() ?? '' : '');
  const effectiveGoal = resolveGoalInput(d.goal, firstGoal);
  const busy = useWs(docBusy);
  const ok = goalOk({ ...d, goal: effectiveGoal }) && !busy;
  const proceed = () => {
    const current = ws().draft;
    const state = useGoalStore.getState().gs;
    const first = state && state.owner && state.owner === me()?.id ? state.candidates[0]?.goal : '';
    const goal = resolveGoalInput(current.goal, first);
    if (!goalOk({ ...current, goal }) || docBusy(ws())) return;
    if (!current.goal.trim()) setAt('draft.goal', goal);
    go(paths.newDetails);
  };
  useDraftWatch();
  useEffect(() => {
    loadGoalsIfOld();
  }, []);
  return (
    <>
      {/* 기획서를 올리거나 요약하는 중에는 이미 지난 단계로도 옮기지 않는다 */}
      <Stepper cur="goal" busy={busy} />
      <Page
        title="어떤 역량을 키우고 싶나요?"
        lead="목표와, 적용할 프로젝트 기획서가 있으면 함께 알려 주세요. 기획서는 진단 에이전트가 읽고 요약해요. 학습 여건은 다음 단계에서 적어 주세요(모두 선택)."
        foot={
          <button className="btn pri" disabled={!ok} onClick={proceed}>
            다음: 세부 사항
          </button>
        }
      >
        <div className="card">
          <div className="field">
            <label>키우고 싶은 역량</label>
            <BText path="draft.goal" id="goalText" maxLength={300} ariaLabel="키우고 싶은 역량" placeholder={firstGoal || '목표 후보를 불러오거나 직접 작성해 주세요.'} />
            <p className="small muted">입력하지 않으면 첫 번째 목표 후보로 진행해요. 직접 작성하면 입력한 내용을 사용해요.</p>
            <GoalSuggestions />
          </div>
          <hr className="hr" />
          <div className="field">
            <label>
              적용할 프로젝트 기획서 <span className="muted small">선택</span>
            </label>
            <ProjectField />
          </div>
        </div>
        <StaleNote kind="quiz" />
      </Page>
    </>
  );
}
