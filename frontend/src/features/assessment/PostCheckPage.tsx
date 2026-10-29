import { trackName } from '@/shared/constants/data';
/* 사후 점검·결과 보고서 만들기 (5차 scr.post · ensurePostDeep · 저장·보고서 요청은 postActions.ts)
   응답은 고칠 때마다 서버에 저장한다(API-49). 결과물 파일은 서버 폴더에 올린 뒤 이름만 붙인다.
   사후 심화 질문(10/23): 사전에 심화를 고른 로드맵이면 화면에 들어올 때 서버가 같은 개념의 새 문제를 만든다. 실패는 '다시 시도'를 눌러야만 */
import { useEffect } from 'react';
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
import { Icon } from '@/shared/ui/Icon';
import { AgentRow, FailPage, Note, OpsBox, Page, runSub, via } from '@/shared/ui/parts';
import { deepOpen, makeReport, savePost, waitReport } from './postActions';
import { QuizBody } from './quizParts';

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
  return !!R.plan.assess && R.plan.assess.questions.every((q) => p.answers[q.id]) && !!p.goalSelf && deepOk;
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
          사전 점검에서 심화 질문을 골라, 같은 개념을 묻는 새 문제를 냈어요. 객관식은 모두 골라 주세요(‘잘 모르겠어요’도 돼요). 서술형은 비워 둬도 돼요.{' '}
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
      eyebrow={`${trackName(pl.opt, pl.name)} · v${pl.version} · ${pl.goal}`}
      title="사후 점검"
      lead="사전 점검과 같은 문항이에요. 지금 기준으로 1~5점을 골라 주세요. 진단 에이전트가 계산한 수준값은 보여드리지 않아요."
      foot={
        running ? (
          <button className="btn pri" disabled>
            <span className="sp" />
            진단 에이전트가 보고서를 쓰고 있어요…
          </button>
        ) : (
          <button className="btn pri" disabled={!postValid(R)} onClick={() => void makeReport(go, R.id)}>
            결과 보고서 만들기
          </button>
        )
      }
    >
      {left ? <Note>아직 ‘진행 중’인 활동이 {left}개 있어요. 결과 보고서에는 ‘진행 중’으로 남아요. 답한 내용은 서버에 저장되니 활동을 더 한 뒤 이어서 답해도 돼요.</Note> : null}
      <PostDeepCard R={R} />
      <div className="stack">
        <QuizBody
          questions={pl.assess?.questions || []}
          path={`${base}.answers`}
          preMap={pl.assess?.answers}
          dq={deepOpen(dp) && dp?.quiz ? { quiz: dp.quiz, mcq: `${base}.deep.mcq`, essay: `${base}.deep.essay` } : null}
        />
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
