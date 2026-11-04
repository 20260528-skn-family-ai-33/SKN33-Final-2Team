import { InputSkills } from './InputSkills';
import './detailsCheck.css';
import { canContinueSkills, hasExistingSkillProgress } from './skillInput';
import { flush } from '../draftSync';
import { loadSurvey } from '../quiz/surveyRequest';
import { inputSignature } from '../invalidation';
/* 2. 세부 사항 · 2-1. 세부 사항 확인 (5차 scr['new-details'] · scr['new-details-check'])
   확인 화면은 입력한 내용(빈 칸은 '알아서')과 진단 에이전트 연결 상태를 보여 주고, '다음'을 누르면 역량 테스트 문항을 만든다 */
import { Fragment, useEffect, useState } from 'react';
import { saveProjectSummary } from './projectSummary';
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
import { StaleNote } from '../stale';
import { Stepper } from '../Stepper';
import { DetailsForm } from './DetailsForm';

export function DetailsStep() {
  const go = useGo();
  const draft = useWs(s => s.draft);
  const hasQuiz = !!draft.v2Assessment?.completed;
  return (
    <>
      <Stepper cur="details" />
      <Page
        title="학습 여건과 학습할 스킬을 정해 주세요"
        lead="학습 여건은 비워 두면 알아서 정해요. 학습할 스킬은 하나 이상 선택해 주세요."
        foot={
          <>
            <button className="btn line" onClick={() => go(paths.newGoal)}>
              <Icon name="left" />
              이전
            </button>
            <button className="btn pri" disabled={!canContinueSkills(draft)} onClick={() => { go(paths.newDetailsCheck); }}>
              다음: 입력 내용 확인
            </button>
          </>
        }
      >
        <div className="card">
          <DetailsForm path="draft.prefs" learningConditionsOnly />
        </div>
        <InputSkills />
        <StaleNote kind="gen" />
        {hasQuiz ? <Note>점검 완료 응답은 고정돼요. 목표·세부사항·스킬을 변경하면 새 점검을 진행해요.</Note> : null}
      </Page>
    </>
  );
}

export const DetailsView = ({ p }: { p: Prefs }) => (
  <div className="card acc preview">
    <p className="eyebrow">
      세부사항
    </p>
    <dl className="kv">
      {D.detailFields.filter(([key]) => key !== 'format' && key !== 'cert').map(([k, l]) => (
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

  const draftId = useWs(s => s.draftId);
  const [summaryEdit, setSummaryEdit] = useState<{scope:string;value:string}|null>(null);
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [summaryError, setSummaryError] = useState('');
  useEffect(() => {
    if (ai.live() && (conn.provider !== ai.mode() || conn.state === 'idle' || Date.now() - conn.at > 60000)) void ping();
    // 화면에 들어올 때 한 번만 확인한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const owner = useWs(s => s.owner);
  const summaryScope = JSON.stringify([owner,draftId,d.doc?.name,d.doc?.summary]);
  const editingSummary = summaryEdit?.scope === summaryScope;
  async function saveSummary() {
    if (!editingSummary || !summaryEdit || summaryBusy) return;
    setSummaryBusy(true); setSummaryError('');
    try {
      const changed = await saveProjectSummary(summaryEdit.value);
      setSummaryEdit(null);
      if (changed) go(paths.newDetails);
    } catch (error) {
      setSummaryError(error instanceof Error ? error.message : '요약을 저장하지 못했어요. 다시 시도해 주세요.');
    } finally { setSummaryBusy(false); }
  }
  const signature = inputSignature(d);
  const preserveLegacy=hasExistingSkillProgress(d)&&!d.v2Assessment;
  useEffect(()=>{
    if(preserveLegacy)return;
    void (async()=>{await flush();return loadSurvey(`${owner}:${signature}`);})().catch(()=>{});
  },[owner,signature,preserveLegacy]);
  return (
    <>
      <Stepper cur="check" busy={summaryBusy || editingSummary} />
      <Page
        eyebrow="세부 사항 확인"
        title="학습 목표·프로젝트 요약과 선택한 스킬을 확인해 주세요"
        lead="입력한 학습 목표·프로젝트 요약과 선택한 스킬을 확인해 주세요."
        foot={
          <>
            <button className="btn line" disabled={summaryBusy || editingSummary} onClick={() => go(paths.newDetails)}>
              <Icon name="edit" />
              수정
            </button>
            <button
              className="btn pri"
              disabled={summaryBusy || editingSummary}
              onClick={() => {
                updateWs((s) => void (s.draft.detailsOk = true));
                go(paths.newQuiz);
              }}
            >
              다음: 역량 테스트
            </button>
          </>
        }
      >
        <div className="card input-confirm-box">
        <section className="card check-goal" aria-labelledby="checkGoalTitle"><h2 id="checkGoalTitle">학습 목표</h2><p>{d.goal}</p></section>
        <details className="card check-goal check-project">
          <summary><span>프로젝트 요약</span><span className="check-project-more">더보기</span><span className="check-project-less">접기</span></summary>
          {d.doc?.name && <p className="small muted">첨부 파일 · {d.doc.name}</p>}
          {editingSummary && summaryEdit ? <div className="project-summary-editor">
            <label htmlFor="projectSummaryEdit">프로젝트 요약 수정</label>
            <textarea id="projectSummaryEdit" className="textarea" rows={10} maxLength={1500} value={summaryEdit.value} disabled={summaryBusy} onChange={event=>setSummaryEdit({scope:summaryScope,value:event.target.value})} />
            <p className="small muted">{summaryEdit.value.length.toLocaleString()} / 1,500자 · 내용을 바꿔 저장하면 스킬을 다시 확인하고 역량 테스트·로드맵을 새로 준비합니다.</p>
            <div className="btns"><button type="button" className="btn pri small" disabled={summaryBusy || !summaryEdit.value.trim()} onClick={()=>void saveSummary()}>{summaryBusy?'저장 중…':'저장 후 스킬 확인'}</button><button type="button" className="btn line small" disabled={summaryBusy} onClick={()=>{setSummaryEdit(null);setSummaryError('');}}>취소</button></div>
          </div> : <>
            <ProjectSummary text={d.doc?.status==='reading'?'프로젝트 요약을 준비하고 있어요.':d.doc?.summary?.trim()||'등록된 프로젝트 요약이 없어요.'} />
            {d.doc?.status==='ok' && <button type="button" className="btn line small" onClick={()=>{setSummaryEdit({scope:summaryScope,value:d.doc?.summary||''});setSummaryError('');}}><Icon name="edit" />요약 수정</button>}
          </>}
          {summaryError && <p role="alert" className="small">{summaryError}</p>}
        </details>
        <DetailsView p={d.prefs} />
        <section className="card skill-confirm" aria-labelledby="confirmedSkillsTitle">
          <header className="skill-confirm-header"><h2 id="confirmedSkillsTitle">선택한 스킬 · 학습 순서</h2><span>{d.selectedSkills?.length||0}개 스킬</span></header>
          <ol className="skill-confirm-list">{d.selectedSkills?.map((row,index)=><li key={row.name}>
            <span className="skill-confirm-number" aria-hidden="true">{String(index+1).padStart(2,'0')}</span>
            <div><h3>{row.name}</h3><p>{row.application}</p></div>
          </li>)}</ol>
        </section>
        </div>
        <ConnBox />
      </Page>
    </>
  );
}

function ProjectSummary({text}:{text:string}) {
  const lines=text.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
  return <dl className="check-project-summary">{lines.map((line,index)=>{
    const match=line.match(/^(목적|다룰 데이터|기술·도구|기술 및 도구|일정|제약)\s*[:：]\s*(.*)$/);
    return match?<div key={index}><dt>{match[1]}</dt><dd>{match[2]}</dd></div>:<div className="summary-paragraph" key={index}><dd>{line}</dd></div>;
  })}</dl>;
}
