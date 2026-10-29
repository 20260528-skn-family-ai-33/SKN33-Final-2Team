/* 3. 사전 점검 (5차 scr['new-quiz'] · ensureQuiz)
   문항 생성(API-23): 서버 작업으로 만들고, 진행 상태(quizRun)·실패(quizFail)는 서버 작성 문서에 남는다.
   실패는 가데이터로 대신하지 않고, '다시 시도하기'를 눌러야만 다시 만든다(10/14) */
import { useEffect } from 'react';
import { draftsApi } from '@/api/endpoints/drafts';
import { paths } from '@/app/paths';
import { DeepToggle, QuizBody } from '@/features/assessment/quizParts';
import { useGo } from '@/shared/hooks/useGo';
import { ai, cause, errText } from '@/shared/state/ai';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { AgentRow, FailPage, OpsBox, Page, runSub, via } from '@/shared/ui/parts';
import { draftCall, pullDraft } from '../draftSync';
import { deepOnOf, quizDone, quizKey } from '../model';
import { StaleNote } from '../stale';
import { Stepper } from '../Stepper';
import { useDraftWatch } from '../useDraftWatch';
import { toast } from '@/shared/state/ui';

const QUIZ_AGENT = '진단 에이전트 · 사전 점검 문항 생성';
let quizAsk = '';

async function ensureQuiz(retry = false): Promise<void> {
  const d = ws().draft;
  const key = quizKey(d);
  if ((d.quiz && d.quiz.key === key) || (d.quizRun && d.quizRun.key === key)) return;
  if (quizAsk === key || (!retry && d.quizFail && d.quizFail.key === key)) return;
  quizAsk = key;
  const r = await draftCall('사전 점검 문항을 만들지 못했어요', (id) => draftsApi.assessment(id));
  quizAsk = '';
  if (!r) return;
  await pullDraft();
}

export function QuizStep() {
  const go = useGo();
  const d = useWs((s) => s.draft);
  const key = quizKey(d);
  const ready = !!(d.quiz && d.quiz.key === key);
  const failKey = d.quizFail?.key;
  const running = !!d.quizRun;
  useDraftWatch();
  useEffect(() => {
    void ensureQuiz();
  }, [key, ready, running, failKey]);

  const err = !ready && !d.quizRun && d.quizFail && d.quizFail.key === key ? cause(d.quizFail.cause) : null;
  if (err)
    return (
      <>
        <Stepper cur="quiz" />
        <FailPage
          title="사전 점검 문항을 만드는 중 문제가 발생했어요"
          desc="진단 에이전트가 목표와 세부 사항으로 점검 문항을 만들지 못했어요. 입력한 목표와 세부 사항은 그대로 남아 있어요."
          cause={errText(err)}
          body={
            <div className="agents">
              <AgentRow st="fail" name={QUIZ_AGENT} sub={ai.live() ? via('default') : ''} tag="오류 발생" tagCls="fail" />
            </div>
          }
          ops={<OpsBox items={[['', err]]} />}
          foot={
            <>
              <button className="btn line" onClick={() => go(paths.newGoal)}>
                <Icon name="left" />
                목표·기획서 고치기
              </button>
              <button
                className="btn pri"
                onClick={() => {
                  updateWs((s) => void (s.draft.quizFail = null));
                  void ensureQuiz(true);
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

  const quiz = d.quiz;
  const deepKs = deepOnOf(d) && quiz?.deep ? Object.keys(quiz.deep.mcq) : [];
  return (
    <>
      <Stepper cur="quiz" />
      <Page
        title={ready && quiz ? `사전 점검 · ${quiz.questions.length}문항` : '사전 점검'}
        lead="목표와 세부 사항을 바탕으로 진단 에이전트가 만든 문항이에요. 문장마다 나에게 맞는 정도를 1~5점으로 골라 주세요. 진단 에이전트가 계산한 수준값은 보여드리지 않아요."
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newDetailsCheck)}>
              <Icon name="left" />
              이전
            </button>
            <button
              className="btn pri"
              disabled={!ready}
              onClick={() => {
                if (!quizDone(d)) {
                  toast('모든 문항 선택을 완료해 주세요.');
                  return;
                }

                go(paths.newResult);
              }}
            >
              다음: 점검 결과
            </button>
          </>
        }
      >
        {ready && quiz ? (
          <>
            {quiz.deep ? (
              <DeepToggle on={!!d.deepOn} nm={Object.keys(quiz.deep.mcq).length} ne={quiz.deep.essays.length} onToggle={() => updateWs((s) => void (s.draft.deepOn = !s.draft.deepOn))} />
            ) : ai.live() ? (
              <p className="small muted">이번 문항에는 심화 질문이 만들어지지 않았어요. 자가 진단만으로 진행해요.</p>
            ) : null}
            <p className="small muted" style={{ margin: `${quiz.deep ? '0' : '-14px'} 0 16px` }}>
              답한 문항{' '}
              <b id="qCount" className="num">
                {quiz.questions.filter((q) => d.answers[q.id]).length} / {quiz.questions.length}
              </b>
              <span id="dqCount">{deepKs.length ? ` · 심화 객관식 ${deepKs.filter((k) => (d.deepMcq || {})[k]).length} / ${deepKs.length}` : ''}</span>
            </p>
            <div className="stack">
              <QuizBody
                questions={quiz.questions}
                path="draft.answers"
                dq={deepOnOf(d) && quiz.deep ? { quiz: quiz.deep, mcq: 'draft.deepMcq', essay: 'draft.deepEssay' } : null}
              />
            </div>
            <StaleNote kind="diag" />
          </>
        ) : (
          <div className="agents">
            <AgentRow st="run" name={QUIZ_AGENT} sub={runSub('default', '목표와 세부 사항을 바탕으로 문항을 만들고 있어요')} />
          </div>
        )}
      </Page>
    </>
  );
}
