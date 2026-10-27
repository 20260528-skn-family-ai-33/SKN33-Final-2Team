/* 점검 문항 부품 (사전·사후 같이 씀 · 5차 P.likRow·mcqRow·essayBox·quizBody·deepToggle·deepReveal)
   5점 척도: 1 전혀 아님 · 2 아님 · 3 보통이다 · 4 그렇다 · 5 매우 그렇다.
   심화 질문(10/23 · 고른 사람만): 자가 진단 문항 바로 아래에 같은 개념의 객관식, 영역 카드 끝에 서술형 하나 */
import { Fragment } from 'react';
import type { DeepGrade, DeepJudge, DeepQuiz, QuizQuestion } from '@/api/types/draft';
import { D } from '@/shared/constants/data';
import { ansLabel } from '@/shared/lib/prefs';
import { setAt, useAt } from '@/shared/state/bind';
import { BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';

export function LikRow({ q, path, pre }: { q: QuizQuestion; path: string; pre?: string }) {
  const cur = String(useAt<string>(`${path}.${q.id}`) || '');
  return (
    <div className="qrow">
      <p>
        {q.text}
        {pre ? <small className="muted">사전 응답: {ansLabel(pre)}</small> : null}
      </p>
      <div className="lik" role="radiogroup" aria-label={q.text}>
        {D.answerOpts.map(([v, l]) => (
          <label key={v}>
            <input type="radio" name={`${path}.${q.id}`} value={v} checked={cur === v} onChange={() => setAt(`${path}.${q.id}`, v)} />
            <b>{v}</b>
            <span>{l}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

export function McqRow({ id, m, path }: { id: string; m: DeepQuiz['mcq'][string]; path: string }) {
  const cur = String(useAt<string>(`${path}.${id}`) || '');
  const opt = (v: string, t: string) => (
    <label className={`dq-opt${v === 'dk' ? ' dk' : ''}`} key={v}>
      <input type="radio" name={`${path}.${id}`} value={v} checked={cur === v} onChange={() => setAt(`${path}.${id}`, v)} />
      <span>{t}</span>
    </label>
  );
  return (
    <div className="dq">
      <p className="dq-q">
        <span className="dq-tag">심화 · 객관식</span>
        {m.q}
      </p>
      <div className="dq-opts" role="radiogroup" aria-label={m.q}>
        {m.options.map((o, i) => opt(String(i), o))}
        {opt('dk', '잘 모르겠어요')}
      </div>
    </div>
  );
}

export const EssayBox = ({ e, path }: { e: DeepQuiz['essays'][number]; path: string }) => (
  <div className="dq dq-essay">
    <p className="dq-q">
      <span className="dq-tag">심화 · 서술형</span>
      {e.q}
    </p>
    <BText path={`${path}.${e.id}`} className="textarea sm" maxLength={2000} ariaLabel={e.q} placeholder="2~3문장으로 써 주세요. 비워 두면 ‘답 없음’으로 봐요." />
  </div>
);

/** dq = { quiz: 심화 문항, mcq: 객관식 답 경로, essay: 서술형 답 경로 } (사전은 draft.*, 사후는 plans.<id>.post.deep.*) */
export interface DeepPaths {
  quiz: DeepQuiz;
  mcq: string;
  essay: string;
}

export function QuizBody({ questions, path, preMap, dq }: { questions: QuizQuestion[]; path: string; preMap?: Record<string, string> | null; dq?: DeepPaths | null }) {
  const areas = [...new Set(questions.map((q) => q.area))];
  return (
    <>
      {areas.map((a) => (
        <div className="card qcard" key={a}>
          <h2 className="st">{a}</h2>
          {questions
            .filter((q) => q.area === a)
            .map((q) => (
              <Fragment key={q.id}>
                <LikRow q={q} path={path} pre={preMap ? preMap[q.id] : undefined} />
                {dq && dq.quiz.mcq[q.id] ? <McqRow id={q.id} m={dq.quiz.mcq[q.id]} path={dq.mcq} /> : null}
              </Fragment>
            ))}
          {dq ? dq.quiz.essays.filter((e) => e.area === a).map((e) => <EssayBox key={e.id} e={e} path={dq.essay} />) : null}
        </div>
      ))}
    </>
  );
}

export function DeepToggle({ on, nm, ne, onToggle }: { on: boolean; nm: number; ne: number; onToggle: () => void }) {
  return (
    <div className={`card deep-opt${on ? ' on' : ''}`}>
      <button type="button" className="deep-tg" aria-pressed={on} onClick={onToggle}>
        <span className="box">{on ? <Icon name="check" /> : null}</span>
        <b>심화 질문도 풀어 볼게요</b>
        <span className="muted small">선택</span>
      </button>
      <p className="small muted">
        자가 진단 문항마다 같은 개념을 묻는 객관식 {nm}개와 영역마다 서술형 {ne}개가 더 나와요. 풀면 진단 에이전트가 자기평가와 함께 보고 로드맵을 더 맞춰요. 정답과 모범
        답안은 다음 단계(점검 결과)에서 펼쳐 볼 수 있어요.
      </p>
    </div>
  );
}

/* 정답·해설·모범 답안(접어 둠): 사전은 점검 결과, 사후는 결과 보고서. 문항별 맞음·틀림까지 보여 주고 전체 정답 수는 보여 주지 않는다(10/23) */
const RES_TAG: Record<string, string> = { 맞음: 'ok', 틀림: 'bad', 모름: 'mid', '답 안 함': 'mid' };
const LV_TAG: Record<string, string> = { 충분: 'ok', 부분: 'mid', 부족: 'bad' };

export function DeepReveal(o: {
  questions: QuizQuestion[];
  dq: DeepQuiz | null | undefined;
  mcqAns?: Record<string, string>;
  essayAns?: Record<string, string>;
  grade?: Record<string, DeepGrade> | null;
  judge?: Record<string, DeepJudge> | null;
  title: string;
}) {
  const { dq, grade } = o;
  if (!dq || !grade) return null;
  return (
    <details className="card deep-ans">
      <summary>
        <b>{o.title}</b>
        <span className="small muted">
          객관식 {Object.keys(dq.mcq).length} · 서술형 {dq.essays.length} · 누르면 펼쳐요
        </span>
      </summary>
      <ol className="plain-list dr-list">
        {o.questions
          .filter((q) => dq.mcq[q.id])
          .map((q) => {
            const m = dq.mcq[q.id];
            const g = grade[q.id] || ({} as DeepGrade);
            const v = String((o.mcqAns || {})[q.id] || '');
            const mine = v === 'dk' ? '잘 모르겠어요' : v !== '' ? m.options[+v] : '답 안 함';
            return (
              <li className="dr-item" key={q.id}>
                <p className="dr-q">
                  <span className="small muted">{q.area} · 객관식</span>
                  {m.q}
                </p>
                <p className="small">
                  내 답 · {mine} <span className={`dr-tag ${RES_TAG[g.result] || 'mid'}`}>{g.result || ''}</span>
                </p>
                <p className="small">
                  정답 · <b>{m.options[Number(m.answer)]}</b>
                </p>
                {m.explain ? <p className="small muted">{m.explain}</p> : null}
              </li>
            );
          })}
        {dq.essays.map((e) => {
          const j = (o.judge || {})[e.id] || ({} as DeepJudge);
          return (
            <li className="dr-item" key={e.id}>
              <p className="dr-q">
                <span className="small muted">{e.area} · 서술형</span>
                {e.q}
              </p>
              <p className="small pre">내 답 · {String((o.essayAns || {})[e.id] || '').trim() || '쓰지 않음'}</p>
              <p className="small">
                판단 · <span className={`dr-tag ${LV_TAG[j.level] || 'mid'}`}>{j.level || '판단 못 함'}</span> {j.why || ''}
              </p>
              <p className="small">핵심 요소 · {(e.points || []).join(' / ')}</p>
              {e.model ? <p className="small muted">모범 답안 · {e.model}</p> : null}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
