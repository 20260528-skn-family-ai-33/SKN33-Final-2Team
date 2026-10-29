/* 1. 목표·기획서 (5차 scr['new-goal'] · P.goalField·goalSug·projectField·docBox)
   기획서 읽기: 파일을 서버에 올리면 서버가 글자를 꺼내고(API-20) 이미지 보기·요약을 작업으로 이어 한다(API-21).
   요약은 화면에서 고칠 수 있고, 요약만 문항·진단·로드맵 에이전트에게 넘긴다. 실패하면 '다시 시도'를 눌러야만 다시 읽는다 */
import { useEffect } from 'react';
import { draftsApi } from '@/api/endpoints/drafts';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { kb } from '@/shared/lib/format';
import { cause, DOC_CHARS, errText, PROV, type Cause } from '@/shared/state/ai';
import { setAt } from '@/shared/state/bind';
import { toast } from '@/shared/state/ui';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import type { DocState } from '@/api/types/draft';
import { BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { AgentRow, Note, OpsBox, Page, runSub } from '@/shared/ui/parts';
import { DraftSaveError, draftCall, ensureDraft, pullDraft, takeDraft } from '../draftSync';
import { docIdle, goalOk } from '../model';
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
          <AgentRow st="run" name="진단 에이전트 · 목표 후보 만들기" sub={runSub('default', '내 프로필(직급·직무·담당 업무·본인 입력)만 보고 지금과 다른 후보를 만들고 있어요')} />
        </div>
        {list.length ? items : null}
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
            프로필에 본인 입력 정보(업무 설명·경험 요약·기술 스택)가 없어 판단 근거가 부족해요. AI 활용 업무 기본 후보를 보여 드려요. 프로필을 채우면 맞춤 후보를 다시
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
        <span className="small muted">{g && g.status === 'default' ? 'AI 활용 업무 기본 후보' : '내 정보가 바뀔 때 미리 만들어 둬요'}</span>
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

/** 이미지 안내: 읽은 이미지 / 읽지 않은 이유 (비전 모델 없음·가데이터·작은 아이콘 등) */
function imageLine(doc: DocState): string {
  const sk = doc.imageSkipped || {};
  const other = (sk.small || 0) + (sk.big || 0) + (sk.format || 0) + (sk.more || 0);
  if (!doc.imageTotal) return '';
  const why = [
    sk.small && `작은 아이콘 ${sk.small}`,
    sk.big && `1.5MB가 넘는 이미지 ${sk.big}`,
    sk.format && `EMF·WMF 같은 형식 ${sk.format}`,
    sk.more && `4장을 넘는 이미지 ${sk.more}`,
  ]
    .filter(Boolean)
    .join(', ');
  if (doc.imagesRead) return `이미지 ${doc.imagesRead}장을 비전 모델이 보고 요약에 합쳤어요.${other ? ` 그 밖의 ${other}개(${why})는 보지 않았어요.` : ''}`;
  const base =
    (
      {
        mock: '가데이터 모드라 이미지는 보지 않았어요.',
        novision: '이미지를 볼 수 있는 AI 모델이 설정되지 않아 이미지는 보지 않았어요.',
        skip: '이미지는 건너뛰고 글자만 요약했어요.',
        lost: '서버를 다시 켜 이미지는 보지 못했어요. 이미지까지 보려면 파일을 다시 골라 주세요.',
        none: '읽을 수 있는 크기·형식의 이미지가 없어 보지 않았어요.',
      } as Record<string, string>
    )[doc.visionWhy || ''] || '이미지는 보지 않았어요.';
  return `이미지 ${doc.imageTotal}개 · ${base}${doc.visionWhy === 'none' && why ? ` (${why})` : ''} 그림·도표의 중요한 내용은 요약에 직접 적어 주세요.`;
}

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
  if (!doc) return null;
  if (doc.status === 'reading')
    return (
      <div className="docbox">
        <div className="agents">
          <AgentRow st="run" name="진단 에이전트 · 기획서 읽기" sub={runSub(doc.step === 'vision' ? 'vision' : 'default', DOC_STEP[doc.step || ''] || DOC_STEP.extract)} />
        </div>
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
  const meta = [
    doc.format,
    doc.pages ? `${doc.pages}쪽` : '',
    `글자 ${(doc.chars || 0).toLocaleString('ko-KR')}자`,
    (doc.chars || 0) > DOC_CHARS ? `앞 ${DOC_CHARS.toLocaleString('ko-KR')}자로 요약` : '',
  ]
    .filter(Boolean)
    .join(' · ');
  const real = doc.source && doc.source !== 'mock';
  const img = imageLine(doc);
  return (
    <div className="docbox">
      <div className="db-top">
        <p className="eyebrow">
          <Icon name="spark" />
          기획서 요약 · 진단 에이전트
        </p>
        <span className={`tag ${real ? 'acc' : ''}`}>{real ? `${PROV[doc.source as string]} 요약` : '가데이터 요약'}</span>
      </div>
      <p className="small muted db-meta">{meta}</p>
      {(doc.warnings || []).map((w, i) => (
        <p className="small warn-t" key={i}>
          <Icon name="info" />
          {w}
        </p>
      ))}
      {doc.summary || doc.text ? (
        <>
          <BText path="draft.doc.summary" className="textarea sm" maxLength={1500} ariaLabel="기획서 요약" rows={6} />
          <p className="small muted">틀리거나 빠진 내용은 직접 고쳐 주세요. 이 요약만 사전 점검·진단·로드맵 에이전트에게 넘어가요.</p>
        </>
      ) : (
        <p className="small muted">요약할 글자를 찾지 못했어요. 기획서 없이 목표만으로 진행해요.</p>
      )}
      {img ? (
        <>
          <p className="small db-img">
            <Icon name="file" />
            {img}
          </p>
          {doc.visionWhy === 'novision' ? (
            <OpsBox
              items={[
                [
                  '',
                  {
                    text: '비전 모델 설정 없음',
                    hint: 'RunPod-Ollama 팀 모델은 이미지를 읽지 않아요. OpenAI API 모드에서 .env에 OPENAI_VISION_MODEL을 넣고 서버를 다시 실행하면 이미지도 읽어요',
                  },
                ],
              ]}
              cls="sm"
            />
          ) : null}
        </>
      ) : null}
    </div>
  );
}

async function uploadProject(file: File): Promise<void> {
  const owner = ws().owner;
  useGoalStore.setState({ docErr: null });
  try {
    const id = await ensureDraft();
    const r = await draftsApi.projectFile(id, file);
    if (ws().owner !== owner) return;
    takeDraft(r, true);
  } catch (err) {
    if (ws().owner !== owner) return;
    updateWs((s) => {
      s.draft.project = null;
      s.draft.doc = null;
    });
    useGoalStore.setState({ docErr: { name: file.name, cause: cause(err instanceof DraftSaveError ? err.original : err) } });
  }
}

async function clearProject(): Promise<void> {
  useGoalStore.setState({ docErr: null });
  updateWs((s) => {
    s.draft.project = null;
    s.draft.doc = null;
  });
  if (ws().draftId) await draftCall('기획서를 빼지 못했어요', (id) => draftsApi.projectClear(id), { soft: true });
  setAt('draft.project', null);
}

function ProjectField() {
  const f = useWs((s) => s.draft.project);
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
          <button className="link quiet" onClick={() => void clearProject()}>
            빼기
          </button>
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
            setAt('draft.project', { name: file.name, size: file.size });
            updateWs((s) => void (s.draft.doc = { name: file.name, status: 'reading', step: 'extract' }));
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
  const ok = useWs((s) => goalOk(s.draft) && docIdle(s.draft));
  useDraftWatch();
  useEffect(() => {
    loadGoalsIfOld();
  }, []);
  return (
    <>
      <Stepper cur="goal" />
      <Page
        title="어떤 역량을 키우고 싶나요?"
        lead="목표와, 적용할 프로젝트 기획서가 있으면 함께 알려 주세요. 기획서는 진단 에이전트가 읽고 요약해요. 학습 여건은 다음 단계에서 적어 주세요(모두 선택)."
        foot={
          <button className="btn pri" disabled={!ok} onClick={() => go(paths.newDetails)}>
            다음: 세부 사항
          </button>
        }
      >
        <div className="card">
          <div className="field">
            <label>키우고 싶은 역량</label>
            <BText path="draft.goal" id="goalText" maxLength={300} ariaLabel="키우고 싶은 역량" placeholder="예: 사내 규정 문서로 질의응답 시제품을 만들고 싶어요." />
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
