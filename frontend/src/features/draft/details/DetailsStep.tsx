/* 2. 세부 사항 · 2-1. 세부 사항 확인 (5차 scr['new-details'] · scr['new-details-check'])
   확인 화면은 입력한 내용(빈 칸은 '알아서')과 진단 에이전트 연결 상태를 보여 주고, '다음'을 누르면 사전 점검 문항을 만든다 */
import { Fragment, useEffect } from 'react';
import { paths } from '@/app/paths';
import type { Prefs } from '@/api/types/draft';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { prefAuto, prefText } from '@/shared/lib/prefs';
import { ai, ping, useAi } from '@/shared/state/ai';
import { updateWs, useWs } from '@/shared/state/workspace';
import { ConnBox } from '@/shared/ui/conn';
import { Icon } from '@/shared/ui/Icon';
import { Note, Page } from '@/shared/ui/parts';
import { docSummary, quizKey } from '../model';
import { StaleNote } from '../stale';
import { Stepper } from '../Stepper';
import { DetailsForm } from './DetailsForm';

export function DetailsStep() {
  const go = useGo();
  const hasQuiz = useWs((s) => !!s.draft.quiz);
  return (
    <>
      <Stepper cur="details" />
      <Page
        title="학습 여건을 알려 주세요"
        lead="모두 선택 사항이에요. 비워 둔 칸은 ‘알아서’로 두고 로드맵 계획 에이전트가 목표에 맞게 정해요. 자격증 계획은 고르지 않으면 ‘계획 없음’이에요."
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newGoal)}>
              <Icon name="left" />
              이전
            </button>
            <button className="btn pri" onClick={() => go(paths.newDetailsCheck)}>
              다음: 입력 내용 확인
            </button>
          </>
        }
      >
        <div className="card">
          <DetailsForm path="draft.prefs" />
        </div>
        <StaleNote kind="gen" />
        <StaleNote kind="cert" />
        {hasQuiz ? <Note>사전 점검 문항은 이미 만들었어요. 자격증 계획을 바꾸면 문항부터 다시 만들고, 나머지는 로드맵을 만들 때 반영해요.</Note> : null}
      </Page>
    </>
  );
}

export const DetailsView = ({ p }: { p: Prefs }) => (
  <div className="card acc preview">
    <p className="eyebrow">
      <Icon name="spark" />
      진단 에이전트에게 넘길 세부 사항
    </p>
    <dl className="kv">
      {D.detailFields.map(([k, l]) => (
        <Fragment key={k}>
          <dt>{l}</dt>
          <dd className={`${prefAuto(k as keyof Prefs, p) ? 'auto' : ''}${k === 'etc' ? ' etc' : ''}`}>{prefText(k as keyof Prefs, p)}</dd>
        </Fragment>
      ))}
    </dl>
  </div>
);

export function DetailsCheck() {
  const go = useGo();
  const d = useWs((s) => s.draft);
  const conn = useAi((s) => s.conn);
  const made = !!(d.quiz && d.quiz.key === quizKey(d));
  useEffect(() => {
    if (ai.live() && (conn.provider !== ai.mode() || conn.state === 'idle' || Date.now() - conn.at > 60000)) void ping();
    // 화면에 들어올 때 한 번만 확인한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const sum = docSummary(d);
  return (
    <>
      <Stepper cur="details" />
      <Page
        eyebrow="세부 사항 확인"
        title={made ? '입력한 세부 사항이에요' : '이 내용으로 사전 점검을 만들까요?'}
        lead={
          made
            ? '사전 점검 문항은 이미 만들었어요. ‘다음’을 누르면 사전 점검으로 넘어가요. 여기 내용은 로드맵을 만들 때 반영해요.'
            : '‘다음’을 누르면 진단 에이전트가 목표·기획서 요약·자격증 계획으로 사전 점검 문항을 만들어요. 나머지 항목은 로드맵을 만들 때 반영하고, ‘알아서’인 항목은 로드맵 계획 에이전트가 목표에 맞게 정해요.'
        }
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newDetails)}>
              <Icon name="edit" />
              수정
            </button>
            <button
              className="btn pri"
              onClick={() => {
                updateWs((s) => void (s.draft.detailsOk = true));
                go(paths.newQuiz);
              }}
            >
              다음: 사전 점검
            </button>
          </>
        }
      >
        <p className="small muted goal-line">목표 · {d.goal}</p>
        {sum ? (
          <div className="card flat doc-line">
            <p className="eyebrow">
              <Icon name="file" />
              기획서 요약 · {d.doc?.name}
            </p>
            <p className="pre small">{sum}</p>
          </div>
        ) : null}
        <DetailsView p={d.prefs} />
        <ConnBox />
      </Page>
    </>
  );
}
