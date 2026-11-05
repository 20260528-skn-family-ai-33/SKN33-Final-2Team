/* 사후 점검·결과 보고서 만들기 (5차 scr.post · ensurePostDeep · 저장·보고서 요청은 postActions.ts)
   응답은 고칠 때마다 서버에 저장한다(API-49). 결과물 파일은 서버 폴더에 올린 뒤 이름만 붙인다.
   사후 심화 질문(10/23): 사전에 심화를 고른 로드맵이면 화면에 들어올 때 서버가 같은 개념의 새 문제를 만든다. 실패는 '다시 시도'를 눌러야만 */
import { useEffect, useState } from 'react';
import { plansApi } from '@/api/endpoints/plans';
import { waitJob } from '@/api/jobs';
import type { PlanRecord, PostDeep } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { PlanGate } from '@/features/roadmap/parts';
import { pullPlan } from '@/features/roadmap/planActions';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { st } from '@/shared/lib/plan';
import { ai, cause, errText } from '@/shared/state/ai';
import { setAt } from '@/shared/state/bind';
import { updateWs, ws } from '@/shared/state/workspace';
import { toast } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { AgentRow, FailPage, Note, OpsBox, Page, runSub, via } from '@/shared/ui/parts';
import { deepOpen, ensurePostQuiz, makeReport, savePost, waitReport } from './postActions';
import { QuizBody } from './quizParts';
import { PostQuiz } from './PostQuiz';
import { fillRandomPost } from './postRandom';

const POST_DEEP_AGENT = '진단 에이전트 · 사후 심화 질문 생성';
const pdAsk = new Set<string>();
const pdStop = new Set<string>();

async function ensurePostDeep(pid: string): Promise<void> {
  const dp = ws().plans[pid]?.post.deep;
  if (!dp || dp.status === 'ready' || dp.status === 'fail' || pdAsk.has(pid) || pdStop.has(pid)) return;
  pdAsk.add(pid);
  try {
    const j = dp.status === 'run' && dp.jobId ? { jobId: dp.jobId } : await plansApi.postDeep(pid);
    if (j && j.jobId) {
      try {
        await waitJob(j.jobId);
      } catch {
        /* 실패 원인은 서버(post.deep.fail)에 남아 있다 */
      }
    }
  } catch (err) {
    pdStop.add(pid); // 요청 자체가 거절되면 자동으로 다시 부르지 않는다
    failToast(err, '사후 심화 질문을 만들지 못했어요');
  }
  pdAsk.delete(pid);
  await pullPlan(pid);
}

const postValid = (R: PlanRecord): boolean => {
  const p = R.post;
  const dp = p.deep;
  const mcqDone = (mcq: Record<string, unknown>, ans?: Record<string, string>) => Object.keys(mcq).every((k) => (ans || {})[k]);
  const deepOk = !dp || !!(dp.status === 'ready' && dp.quiz && (dp.judge || mcqDone(dp.quiz.mcq, dp.mcq)));
  return !!R.plan.assess && R.plan.assess.questions.every((q) => p.answers[q.id]) && !!p.goalSelf && deepOk && (!R.plan.assess.v2 || !!p.quizSurvey) && (p.quizSurvey?.groups || []).every(group => group.quizzes.every(q => Object.hasOwn(p.quizAnswers || {}, q.id)));
};

function PostDeepCard({ R }: { R: PlanRecord }) {
  const dp = R.post.deep;
  if (!dp) return null;
  if (dp.status === 'ready' && dp.quiz)
    return (
      <div className="card deep-opt on">
        <p className="eyebrow">
          <Icon name="spark" />
          심화 질문 · 사후
        </p>
        <p className="small muted">
          역량 테스트에서 심화 질문을 골라, 같은 개념을 묻는 새 문제를 냈어요. 객관식은 모두 골라 주세요(‘잘 모르겠어요’도 돼요). 서술형은 비워 둬도 돼요.{' '}
          {dp.judge ? '보고서를 만들어 답이 고정됐어요. 정답과 모범 답안은 결과 보고서에서 펼쳐 볼 수 있어요.' : '정답과 모범 답안은 결과 보고서에서 펼쳐 볼 수 있어요.'}
        </p>
        {((dp.notes as string[] | undefined) || []).map((n, i) => (
          <p className="small muted" key={i}>
            {n}
          </p>
        ))}
      </div>
    );
  if (dp.status === 'fail') {
    const c = cause(dp.fail?.cause || {});
    return (
      <div className="agents">
        <AgentRow
          st="fail"
          name={POST_DEEP_AGENT}
          sub={errText(c)}
          tag="오류 발생"
          tagCls="fail"
          onRetry={() => {
            pdStop.delete(R.id);
            updateWs((s) => void (s.plans[R.id].post.deep = { ...(s.plans[R.id].post.deep as PostDeep), status: 'none', fail: null }));
            void ensurePostDeep(R.id);
          }}
        />
      </div>
    );
  }
  return (
    <div className="agents">
      <AgentRow st="run" name={POST_DEEP_AGENT} sub={runSub('default', '같은 개념을 묻는 새 심화 질문을 만들고 있어요')} />
    </div>
  );
}

function Post({ R }: { R: PlanRecord }) {
  const go = useGo();
  const pl = R.plan;
  const [quizError, setQuizError] = useState('');
  const [quizAttempt, setQuizAttempt] = useState(0);
  const [phase, setPhase] = useState<'surveys' | 'quizzes'>('surveys');
  const hasQuiz = !!pl.assess?.v2;
  const quizPending = !!pl.assess?.v2 && !R.post.quizSurvey;
  useEffect(() => {
    if (!quizPending) return;
    let active = true;
    void ensurePostQuiz(R.id).catch(error => { if (active) setQuizError(error instanceof Error ? error.message : '사후 퀴즈를 준비하지 못했어요.'); });
    return () => { active = false; };
  }, [R.id, quizPending, quizAttempt]);
  const running = !!R.post.running;
  const jobId = R.post.jobId;
  /* 새로 고침·재접속: 쓰던 보고서는 서버 작업을 이어서 기다린다(새 작업을 만들지 않음 · 10/20) */
  useEffect(() => {
    if (running && jobId) void waitReport(go, R.id, jobId);
  }, [running, jobId, go, R.id]);
  const deepStatus = R.post.deep?.status;
  useEffect(() => {
    void ensurePostDeep(R.id);
  }, [R.id, deepStatus]);
  /* 보고서 작성 실패: 가데이터로 대신하지 않고 안내한다. 응답은 그대로 두고, '다시 시도하기'를 눌러야만 다시 쓴다(10/14) */
  const f = R.post.fail;
  if (f && !running) {
    const c = cause(f.cause || {});
    return (
      <FailPage
        title="결과 보고서를 만드는 중 문제가 발생했어요"
        desc="진단 에이전트가 결과 보고서를 쓰지 못했어요. 사후 점검 응답과 목표 달성도, 결과물은 그대로 남아 있어요."
        cause={errText(c)}
        body={
          <div className="agents">
            <AgentRow st="fail" name="진단 에이전트 · 결과 보고서 작성" sub={ai.live() ? via('default') : ''} tag="오류 발생" tagCls="fail" />
          </div>
        }
        ops={<OpsBox items={[['', c]]} />}
        foot={
          <>
            <button
              className="btn line"
              onClick={async () => {
                if (await savePost(R.id, { clearFail: true })) updateWs((s) => void (s.plans[R.id].post.fail = null));
              }}
            >
              <Icon name="left" />
              사후 점검 응답 보기
            </button>
            <button className="btn pri" onClick={() => void makeReport(go, R.id)}>
              <Icon name="retry" />
              다시 시도하기
            </button>
          </>
        }
      />
    );
  }
  const left = pl.acts.filter((a) => st(R.progress, a.id) !== 'done').length;
  const dp = R.post.deep;
  const base = `plans.${R.id}.post`;
  return (
    <Page
      back={paths.checks}
      title={<span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>사후 점검<button type="button" className="btn line" style={{ height: 26, minHeight: 0, padding: '3px 9px', fontSize: 11 }} disabled={running} onClick={() => {
        updateWs(state => {
          fillRandomPost(state.plans[R.id]);
        });
        if (quizPending) toast('설문과 목표 달성 응답을 선택했어요. 퀴즈가 준비되면 무작위 선택을 한 번 더 눌러 주세요.');
        void savePost(R.id);
      }}>test용으로 삭제예정 · 무작위 선택</button></span>}
      lead="설문은 사전과 같은 문항이고, 퀴즈는 같은 스킬·개념의 새 문제예요. 지금 기준으로 답해 주세요. 설문은 1~5점, 퀴즈는 보기 중 하나를 선택해요."
      foot={
        running ? (
          <button className="btn pri" disabled>
            <span className="sp" />
            진단 에이전트가 보고서를 쓰고 있어요…
          </button>
        ) : hasQuiz && phase === 'surveys' ? (
          <button type="button" className="btn pri" onClick={() => { setPhase('quizzes'); window.scrollTo(0, 0); }}>다음: 퀴즈<Icon name="right" /></button>
        ) : (
          <>
          {hasQuiz && <button type="button" className="btn line" onClick={() => { setPhase('surveys'); window.scrollTo(0, 0); }}>이전: 설문</button>}
          <button className="btn pri" disabled={!postValid(R)} onClick={() => void makeReport(go, R.id)}>
            결과 보고서 만들기
          </button>
          </>
        )
      }
    >
      {hasQuiz && <div className="v2-survey"><nav aria-label="사후 점검 순서">
        <button type="button" disabled={running} aria-current={phase === 'surveys' ? 'step' : undefined} onClick={() => setPhase('surveys')}>1. 설문</button>
        <button type="button" disabled={running} aria-current={phase === 'quizzes' ? 'step' : undefined} onClick={() => setPhase('quizzes')}>2. 퀴즈</button>
      </nav></div>}
      {left ? <Note>아직 ‘진행 중’인 활동이 {left}개 있어요. 결과 보고서에는 ‘진행 중’으로 남아요. 답한 내용은 서버에 저장되니 활동을 더 한 뒤 이어서 답해도 돼요.</Note> : null}
      {phase === 'surveys' && <PostDeepCard R={R} />}
      <div className="stack">
        {phase === 'surveys' && <QuizBody
          questions={pl.assess?.questions || []}
          path={`${base}.answers`}
          preMap={pl.assess?.answers}
          dq={deepOpen(dp) && dp?.quiz ? { quiz: dp.quiz, mcq: `${base}.deep.mcq`, essay: `${base}.deep.essay` } : null}
        />}
        {phase === 'quizzes' && quizPending && (quizError ? <div className="card" role="alert"><p>{quizError}</p><button className="btn line small" onClick={() => { setQuizError(''); setQuizAttempt(value => value + 1); }}>퀴즈 다시 준비하기</button></div> : <div className="loading" role="status" aria-live="polite"><span className="sp" aria-hidden="true" /><span>퀴즈를 준비하고 있어요.</span></div>)}
        {phase === 'quizzes' && <PostQuiz R={R} disabled={running} />}
        {phase === 'surveys' && <>
        <div className="card">
          <h2 className="st">처음 목표를 얼마나 이뤘나요?</h2>
          <div className="chips">
            {D.goalSelf.map((l, i) => (
              <label className="chip" key={l}>
                <input type="radio" name="goalSelf" value={i + 1} checked={String(R.post.goalSelf) === String(i + 1)} onChange={() => setAt(`${base}.goalSelf`, String(i + 1))} />
                {l}
              </label>
            ))}
          </div>
        </div>
        <div className="card">
          <h2 className="st">
            결과물·수료증{' '}
            <span className="muted small" style={{ fontWeight: 400 }}>
              선택
            </span>
          </h2>
          {R.post.file ? (
            <div className="file-on">
              <Icon name="file" />
              <div className="tx">
                <b>{R.post.file.name}</b>
                <small className="muted">서버에 보관 · 내용은 검증하지 않아요</small>
              </div>
            </div>
          ) : (
            <label className="drop">
              <input
                type="file"
                onChange={async (e) => {
                  const file = e.target.files && e.target.files[0];
                  if (!file) return;
                  updateWs((s) => void (s.plans[R.id].post.file = { name: file.name, size: file.size }));
                  try {
                    const up = await plansApi.attach(R.id, 'post', file);
                    // 저장이 실패하면(알림은 savePost 가 띄움) 붙인 것처럼 보이지 않게 되돌린다
                    if (!(await savePost(R.id, { file: { fileId: up.fileId, name: up.name, size: up.size } }))) updateWs((s) => void (s.plans[R.id].post.file = null));
                  } catch (err) {
                    updateWs((s) => void (s.plans[R.id].post.file = null));
                    failToast(err, '결과물을 올리지 못했어요');
                  }
                }}
              />
              <span className="ico">
                <Icon name="file" />
              </span>
              <span>
                <b>결과물·수료증 고르기</b>
                <small>내지 않아도 기록은 그대로예요</small>
              </span>
            </label>
          )}
        </div>
        </>}
      </div>
    </Page>
  );
}

export function PostCheckPage() {
  return (
    <PlanGate make={paths.post} fallback={paths.checks} needActive>
      {(R) => <Post R={R} />}
    </PlanGate>
  );
}
