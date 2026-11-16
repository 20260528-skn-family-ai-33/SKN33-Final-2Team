import './feedback.css';
import { useEffect, useState } from 'react';
import { commentSkillNames } from '@/features/roadmap/roadmapLearningData';
import { trackName } from '@/shared/constants/data';
/* 부서장 (API-55~59 · 5차 gp-parts.js m-list·m-plan·m-road·m-report·m-done)
   부서장 범위(2026-10-27 팀 합의): 자기 부서 직원만(부서장의 계획은 본인만 봄). 서버가 소속 관계를 확인하고 공개 범위만 보낸다.
   공개 범위(설계서 v1.7 1.1): 직원 소속·직급·직위, 확정 로드맵(버전)·활동 진행 상태·결과 보고서(전체)·받은 코멘트 기록. 메모·첨부·진단·작성 중인 로드맵은 보내지 않는다 */
import { Navigate, useParams } from 'react-router';
import { teamApi } from '@/api/endpoints/team';
import { ApiError } from '@/api/client';
import type { Comment, PlanRecord, Report } from '@/api/types/plan';
import type { TeamMember, TeamUser } from '@/api/types/team';
import { paths } from '@/app/paths';
import { ReportBody } from '@/features/report/ReportBody';
import { HeadReportTasks } from '@/features/report/ReportTasks';
import { MemberRoadView } from './MemberRoadView';
import { CmItem, CmTag, cmMine, feedbackReasons, isFreeComment, isSkillFeedback, selectedFeedbackReasons } from '@/features/roadmap/comments';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { count } from '@/shared/lib/plan';
import { cause } from '@/shared/state/ai';
import { setAt, useAt } from '@/shared/state/bind';
import { meLine, useMe } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { newComments, updateWs, useWs, type MgrDraft } from '@/shared/state/workspace';
import { BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { Loading, Note, Page } from '@/shared/ui/parts';
import { mk, useMemberOf, useMemberState, useRefreshTeam, useTeam } from './teamData';
import { arrangeMembers, hasRecords, unseenOf } from './teamList';

const ST_TAG: Record<string, React.ReactNode> = { done: <span className="tag line">마침</span>, archived: <span className="tag line">보관</span> };
const who = (e: TeamUser) => `${e.name} · ${meLine(e)}`;
const Av = ({ e }: { e: TeamUser }) => <span className="avatar">{e.name.slice(1)}</span>;
/** 줄 끝 '보기 >' — 아이콘만 있던 것을 글자와 테두리로 눈에 띄게(#96) */
const Go = () => (
  <span className="team-go" aria-hidden="true">
    보기
    <Icon name="right" />
  </span>
);
const Privacy = () => (
  <Note>
    직원의 소속·직급·직위, 확정한 로드맵, 활동 진행 상태, 결과 보고서(사전→사후 점검 응답 변화 포함)를 볼 수 있어요. 활동 메모·첨부, 진단 수준값, 작성 중인 로드맵은 공개되지 않아요.
  </Note>
);

function TeamRow({ m }: { m: TeamMember }) {
  const go = useGo();
  const e = m.user;
  const tag = e.supervisor ? (
    <>
      {' '}
      <span className="tag line">부서장</span>
    </>
  ) : null;
  if (!hasRecords(m))
    return (
      <div className="li">
        <Av e={e} />
        <div className="tx">
          <b>
            {e.name}
            {tag}
          </b>
          <small>{meLine(e)} · 확정한 로드맵 없음</small>
        </div>
      </div>
    );
  return (
    <button className={`li team-row${unseenOf(m) ? ' has-unseen' : ''}`} onClick={() => go(paths.member(e.id))}>
      <Av e={e} />
      <div className="tx">
        <b>
          {e.name}
          {tag}
        </b>
        <small>
          {meLine(e)} · 진행 중 {m.activePlans}개{m.pastPlans ? ` · 지난 로드맵 ${m.pastPlans}개` : ''}
          {m.reports ? ` · 결과 보고서 ${m.reports}개` : ''}
        </small>
      </div>
      <span className="end">
        {m.unseenPlans ? <span className="tag team-new">새 로드맵 {m.unseenPlans}</span> : null}
        {m.unseenReports ? <span className="tag team-new">새 보고서 {m.unseenReports}</span> : null}
        {m.unreadComments ? <span className="tag acc">코멘트 확인 전 {m.unreadComments}</span> : null}
        <Go />
      </span>
    </button>
  );
}

export function MemberListPage() {
  const me = useMe();
  const t = useTeam();
  const members = t.data?.members || [];
  const { shown, empty } = arrangeMembers(members);
  return (
    <Page eyebrow={`부서장 · ${me?.name} · ${me?.dept || ''}`} title="소속 직원의 성장 로드맵" lead={`소속 직원 ${members.length}명이 확정한 로드맵과 진행 상태, 결과 보고서를 보고 계획 조정 의견을 남길 수 있어요.`}>
      {t.error ? (
        <p className="small" style={{ color: 'var(--warn)' }}>
          {cause(t.error).user}
        </p>
      ) : null}
      {shown.length ? (
        <div className="list">
          {shown.map((m) => (
            <TeamRow key={m.user.id} m={m} />
          ))}
        </div>
      ) : t.data ? (
        <p className="small muted">확정한 로드맵이 있는 직원이 아직 없어요.</p>
      ) : null}
      {empty.length ? (
        <details className="team-empty">
          <summary>
            로드맵·보고서가 없는 직원 <b>{empty.length}명</b>
          </summary>
          <div className="list">
            {empty.map((m) => (
              <TeamRow key={m.user.id} m={m} />
            ))}
          </div>
        </details>
      ) : null}
      <Privacy />
      <Note>소속 직원은 내 부서의 직원이에요. 부서·부서장 권한은 관리자 화면의 인적 데이터 엑셀로 바꿔요.</Note>
    </Page>
  );
}

const MemberLoading = ({ q }: { q: ReturnType<typeof useMemberState> }) =>
  q.isPending ? (
    <Loading text="서버에서 소속 직원의 기록을 불러오는 중…" />
  ) : q.error ? (
    <p className="small" style={{ color: 'var(--warn)' }}>
      {cause(q.error).user}
    </p>
  ) : null;

function MgrRoadRow({ uid, R, unseen = false }: { uid: string; R: PlanRecord; unseen?: boolean }) {
  const go = useGo();
  const me = useMe();
  const pl = R.plan;
  const c = count(pl, R.progress);
  const wait = newComments(R).length;
  const mine = (R.comments || []).filter((x) => x.byCode === me?.code).length;
  return (
    <button className="li" onClick={() => go(paths.memberPlan(uid, R.id))}>
      <span className="idx">
        <Icon name="map" />
      </span>
      <div className="tx">
        <b>{pl.displayTitle || pl.goal}</b>
        <small>
          {trackName(pl.opt, pl.name)} v{pl.version} · 활동 {c.done}/{c.t} 완료{mine ? ` · 보낸 코멘트 ${mine}개` : ''}
        </small>
      </div>
      <span className="end">
        {unseen ? <span className="tag team-new">새 로드맵</span> : null}
        {ST_TAG[R.status] || null}
        {wait ? <span className="tag acc">확인 전 {wait}</span> : null}
        <Go />
      </span>
    </button>
  );
}

function MgrRepRow({ uid, r, unseen = false }: { uid: string; r: Report; unseen?: boolean }) {
  const go = useGo();
  return (
    <button className="li" onClick={() => go(paths.memberReport(uid, r.id))}>
      <span className="idx">
        <Icon name="chart" />
      </span>
      <div className="tx">
        <b>
          결과 보고서 · {trackName(r.opt)} v{r.version}
        </b>
        <small>
          {r.goal} · {r.createdAt}
        </small>
      </div>
      <span className="end">
        {unseen ? <span className="tag team-new">새 보고서</span> : null}
        <Go />
      </span>
    </button>
  );
}

/** 부서장 화면 공통 진입 조건: 소속 직원이 아니면 목록으로 */
function useMemberGate() {
  const { uid = '' } = useParams();
  const { team, member } = useMemberOf(uid);
  const gone = team.isSuccess && !member;
  return { uid, member, gone, teamLoading: team.isPending, team };
}

export function MemberPlansPage() {
  const { uid, member: e, gone, teamLoading, team } = useMemberGate();
  const q = useMemberState(uid);
  if (team.isError && !e) return <Page back={paths.team} title="직원 정보를 불러오지 못했어요"><button className="btn line" onClick={() => void team.refetch()}>다시 시도</button></Page>;
  if (gone) return <Navigate to={paths.team} replace />;
  if (teamLoading || !e) return <Loading text="서버에서 불러오는 중…" />;
  if (!q.data) return <Page back={paths.team} eyebrow={who(e)} title={`${e.name} 님의 로드맵`}><MemberLoading q={q} /></Page>;
  const all = Object.values(q.data.plans);
  const act = all.filter((R) => R.status === 'active');
  const past = all.filter((R) => R.status !== 'active');
  const pastIds = new Set(past.map(roadmap => roadmap.id));
  const reps = q.data.reports.filter(report => !pastIds.has(report.planId));
  const seenNot = q.data.unseen || { plans: [], reports: [] };
  if (!all.length)
    return (
      <Page back={paths.team} eyebrow={who(e)} title="확정한 로드맵이 없어요" lead="직원이 로드맵을 확정하면 여기에서 볼 수 있어요.">
        <Privacy />
      </Page>
    );
  return (
    <Page back={paths.team} eyebrow={who(e)} title={`${e.name} 님의 로드맵`} lead="로드맵마다 진행 상태를 보고 계획 조정 의견을 남길 수 있어요.">
      {act.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">진행 중 {act.length}</h2>
          </div>
          <div className="list">
            {act.map((R) => (
              <MgrRoadRow key={R.id} uid={uid} R={R} unseen={seenNot.plans.includes(R.id)} />
            ))}
          </div>
        </div>
      ) : null}
      {past.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">지난 로드맵 {past.length}</h2>
          </div>
          <div className="list">
            {past.map((R) => {
              const reports = q.data.reports.filter(report => report.planId === R.id);
              return <div key={R.id} className="card flat team-past-roadmap">
                <MgrRoadRow uid={uid} R={R} unseen={seenNot.plans.includes(R.id)} />
                {reports.length ? <div className="list team-past-reports" aria-label="이 로드맵의 결과 보고서">
                  {reports.map(report => <MgrRepRow key={report.id} uid={uid} r={report} unseen={seenNot.reports.includes(report.id)} />)}
                </div> : null}
              </div>;
            })}
          </div>
        </div>
      ) : null}
      {reps.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">결과 보고서 {reps.length}</h2>
          </div>
          <div className="list">
            {reps.map((r) => (
              <MgrRepRow key={r.id} uid={uid} r={r} unseen={seenNot.reports.includes(r.id)} />
            ))}
          </div>
        </div>
      ) : null}
      <Privacy />
    </Page>
  );
}

/** 부서장이 쓰는 중인 코멘트 칸 (5차 P.mgrCommentFields · nm: 같은 화면에 새 칸과 고치는 칸이 함께 있을 때 라디오 이름 꼬리) */
function hasComment(draft?: MgrDraft) {
  return !!draft && [draft.fit, draft.level, draft.fitText, draft.levelText, draft.free].some(value => value?.trim());
}

function CommentFields({ k, nm = '' }: { k: string; nm?: string }) {
  const b = `mgr.${k}`;
  const fit = useAt<string>(`${b}.fit`);
  const level = useAt<string>(`${b}.level`);
  return (
    <>
      <div className="field">
        <label>
          업무 적합성 <span className="muted small">선택 · 담당 업무와 맞나요?</span>
        </label>
        <div className="chips">
          {D.commentFit.map(([v, l]) => (
            <label className="chip" key={v}>
              <input type="radio" name={`mfit${nm}`} value={v} checked={fit === v} onChange={() => setAt(`${b}.fit`, v)} />
              {l}
            </label>
          ))}
        </div>
        <BText path={`${b}.fitText`} className="textarea sm" placeholder="한두 문장으로 적어 주세요 (선택)" />
      </div>
      <div className="field">
        <label>
          수준·기간·분량 <span className="muted small">선택 · 난이도와 기간이 적절한가요?</span>
        </label>
        <div className="chips">
          {D.commentLevel.map(([v, l]) => (
            <label className="chip" key={v}>
              <input type="radio" name={`mlevel${nm}`} value={v} checked={level === v} onChange={() => setAt(`${b}.level`, v)} />
              {l}
            </label>
          ))}
        </div>
        <BText path={`${b}.levelText`} className="textarea sm" placeholder="조정이 필요하면 무엇을 어떻게 (선택)" />
      </div>
      <div className="field">
        <label>
          자유 의견 <span className="muted small">선택</span>
        </label>
        <BText path={`${b}.free`} className="textarea sm" placeholder="계획 조정에 도움이 될 의견" />
      </div>
    </>
  );
}

/* 보낸 코멘트 고치기(10/23 사용자 요청): 내가 보낸 코멘트를 직원이 반영하기 전(새·확인함)까지 그 자리에서 고친다. 고치면 직원에게 다시 '새 코멘트'.
   이전 내용은 남기지 않고(덮어쓰기) '수정됨 · 날짜'만 보인다. 지우기는 직원의 로드맵 수정에 혼선을 줘서 두지 않는다 */
const cmChanged = (m: MgrDraft) => {
  const o = m.orig || {};
  return (['fit', 'fitText', 'level', 'levelText', 'free'] as const).some((k) => String(m[k] || '').trim() !== String(o[k] || '').trim());
};
const endEdit = (key: string) =>
  updateWs((s) => {
    delete s.mgr[key];
    if (s.mcEdit === key) s.mcEdit = null;
  });

function MgrCmItem({ uid, pid, c, live }: { uid: string; pid: string; c: Comment; live: boolean }) {
  const refresh = useRefreshTeam();
  const key = mk(mk(uid, pid), c.id);
  const editing = useWs((s) => s.mcEdit === key);
  const m = useWs((s) => s.mgr[key]);
  if (!live || !cmMine(c) || c.deleted) return <CmItem c={c} mgr />;
  if (c.status === 'applied') return <CmItem c={c} mgr foot={<p className="small muted cm-act">v{c.appliedVersion || ''}에 반영된 코멘트라 고칠 수 없어요.</p>} />;
  if (!editing)
    return (
      <CmItem
        c={c}
        mgr
        foot={
          <div className="actions cm-act feedback-history-actions">
            <button
              className="btn line sm"
              onClick={() =>
                updateWs((s) => {
                  if (s.mcEdit && s.mcEdit !== key) delete s.mgr[s.mcEdit]; // 한 번에 하나만 고친다
                  const v = { fit: c.fit, fitText: c.fitText, level: c.level, levelText: c.levelText, free: c.free };
                  s.mgr[key] = { ...v, orig: v };
                  s.mcEdit = key;
                })
              }
            >
              <Icon name="edit" />
              수정
            </button>
            <button className="btn line sm" onClick={async event => {
              if (!window.confirm('이 코멘트를 삭제할까요? 삭제 표시는 남아요.')) return;
              const button = event.currentTarget;
              button.disabled = true;
              try {
                await teamApi.commentDelete(pid, c.id);
                await refresh(uid);
              } catch (error) {
                failToast(error, '코멘트를 삭제하지 못했어요');
              } finally {
                button.disabled = false;
              }
            }}>삭제</button>
          </div>
        }
      />
    );
  // 고치는 칸은 보낼 때와 같은 모양으로: 스킬 피드백은 '좋아요 · 보완 필요'(+ 이유 · 메모), 전체 코멘트는 글 칸 하나, 예전 세 칸 코멘트만 세 칸
  const kind = isSkillFeedback(c) ? 'skill' : isFreeComment(c) ? 'free' : 'fields';
  const filled = !!m && (kind === 'skill' ? m.fit === 'good' || m.fit === 'partial' : kind === 'free' ? !!m.free?.trim() : hasComment(m));
  const ok = !!m && filled && cmChanged(m);
  const save = async (btn: HTMLButtonElement) => {
    if (!m || !ok) return;
    btn.disabled = true;
    try {
      const r = await teamApi.commentEdit(pid, c.id, { fit: m.fit || '', fitText: m.fitText || '', level: m.level || '', levelText: m.levelText || '', free: m.free || '' });
      endEdit(key);
      await refresh(uid);
      toast(r.changed ? '코멘트를 고쳤어요 · 직원에게 ‘새 코멘트’로 보여요' : '바뀐 내용이 없어 저장하지 않았어요');
    } catch (err) {
      failToast(err, '코멘트를 고치지 못했어요');
      const code = err instanceof ApiError ? err.code : undefined;
      if (code !== 'COMMENT_APPLIED' && code !== 'NOT_ACTIVE') {
        btn.disabled = false;
        return;
      }
      // 그사이 직원이 반영했거나 로드맵을 마쳤으면 고치는 칸을 닫고 지금 상태를 다시 읽는다
      endEdit(key);
      await refresh(uid);
    }
  };
  return (
    <div className="cm-item cm-edit">
      <div className="cm-h">
        <b>보낸 코멘트 고치기</b>
        <span className="small muted">
          {c.at}
          {c.editedAt ? ` · 수정됨 ${c.editedAt}` : ''}
        </span>
        <CmTag c={c} mgr />
      </div>
      {kind === 'skill' && c.skill ? (
        <SkillFeedback draftKey={key} skill={c.skill} />
      ) : kind === 'free' ? (
        <div className="field">
          <label>전체 코멘트</label>
          <BText path={`mgr.${key}.free`} className="textarea sm" placeholder="계획 조정에 도움이 될 의견" />
        </div>
      ) : (
        <CommentFields k={key} nm="-e" />
      )}
      <p className="small muted" style={{ margin: 0 }}>
        {c.status === 'read' ? '직원이 확인한 코멘트예요. 저장하면 직원에게 다시 ‘새 코멘트’로 알려요.' : '직원이 아직 확인하지 않은 코멘트예요. 저장하면 고친 내용으로 보여요.'} 고치기 전 내용은
        남지 않고 ‘수정됨’과 날짜만 보여요.
      </p>
      <div className="actions cm-act">
        <button className="btn pri sm" disabled={!ok} onClick={(e) => void save(e.currentTarget)}>
          저장
        </button>
        <button className="btn line sm" onClick={() => endEdit(key)}>
          취소
        </button>
      </div>
    </div>
  );
}

function CommentSendButton({ uid, R }: { uid: string; R: PlanRecord }) {
  const refresh = useRefreshTeam();
  const drafts = useWs(state => state.mgr);
  const [sending, setSending] = useState(false);
  const key = mk(uid, R.id);
  const entries = [undefined, ...commentSkillNames(R.plan)].flatMap(skill => {
    const draftKey = skill ? mk(key, skill) : key;
    const draft = drafts[draftKey];
    if (!draft || (skill ? draft.fit !== 'good' && draft.fit !== 'partial' : !draft.free?.trim())) return [];
    return [{ draftKey, draft, body: { skill, fit: skill ? draft.fit || '' : '',
      fitText: skill && draft.fit === 'partial' ? draft.fitText || '' : '',
      level: '', levelText: '', free: !skill || draft.fit === 'partial' ? draft.free?.trim() || '' : '' } }];
  });

  async function send() {
    if (sending || !entries.length) return;
    setSending(true);
    try {
      await teamApi.commentsSend(R.id, entries.map(entry => entry.body));
      updateWs(state => {
        for (const entry of entries) {
          if (useWs.getState().mgr[entry.draftKey] === entry.draft) delete state.mgr[entry.draftKey];
        }
      });
      toast('코멘트를 보냈어요');
      await refresh(uid);
    } catch (error) {
      failToast(error, '코멘트를 보내지 못했어요');
    } finally {
      setSending(false);
    }
  }

  return <button type="button" className="btn pri" disabled={sending || !entries.length}
    onClick={() => void send()}>{sending ? '보내는 중…' : '피드백 보내기'}</button>;
}

function ManagerCommentHistory({ uid, R, comments }: { uid: string; R: PlanRecord; comments: Comment[] }) {
  return <>{(['보낸 코멘트', '삭제된 코멘트'] as const).map((title, index) => {
    const entries = comments.filter(comment => Boolean(comment.deleted) === (index === 1));
    return entries.length > 0 && <details key={title}>
      <summary className="st">{title} {entries.length}개</summary>
      {entries.map(comment => <MgrCmItem key={comment.id} uid={uid} pid={R.id} c={comment} live={R.status === 'active'} />)}
    </details>;
  })}</>;
}

/** 스킬 하나의 '좋아요 · 보완 필요'(+ 보완 이유 · 메모). draftKey: 새로 쓰는 칸은 (직원 · 로드맵 · 스킬), 보낸 코멘트를 고칠 때는 그 코멘트의 칸 */
function SkillFeedback({ draftKey: key, skill }: { draftKey: string; skill: string }) {
  const draft = useWs(state => state.mgr[key]);
  const reasons = selectedFeedbackReasons(draft?.fitText);
  function change(fields: Partial<MgrDraft>) {
    updateWs(state => { state.mgr[key] = { ...state.mgr[key], ...fields }; });
  }
  return <div className="feedback-skill" role="group" aria-label={skill}>
    <b>{skill}</b>
    <div className="feedback-controls">
      {([['good', '좋아요'], ['partial', '보완 필요']] as const).map(([fit, label]) =>
        <button key={fit} type="button" className="btn line sm feedback-choice" aria-pressed={draft?.fit === fit}
          onClick={() => change({ fit: draft?.fit === fit ? '' : fit, fitText: '', free: '' })}>{label}</button>)}
    </div>
    {draft?.fit === 'partial' && <div className="feedback-reasons stack">
      <div className="feedback-controls" role="group" aria-label="보완 이유">
        {Object.keys(feedbackReasons).map(reason => <button key={reason} type="button"
          className="btn line sm feedback-choice" aria-pressed={reasons.includes(reason)}
          onClick={() => change({ fitText: (reasons.includes(reason) ? reasons.filter(value => value !== reason) : [...reasons, reason]).join(' / ') })}>{reason}</button>)}
        {!reasons.length && <span className="small muted">보완 이유 · 선택</span>}
      </div>
      <label className="feedback-note">스킬 메모 · 선택
        <input className="input" value={draft.free || ''} onChange={event => change({ free: event.target.value })} />
      </label>
    </div>}
  </div>;
}

function FeedbackForm({ uid, R, summary = false }: { uid: string; R: PlanRecord; summary?: boolean }) {
  const key = mk(uid, R.id);
  const drafts = useWs(state => state.mgr);
  return <section className="sec" aria-label={summary ? '피드백 요약' : '로드맵 피드백'}>
    <div className="sec-h"><h2 className="st">{summary ? '피드백 요약' : '로드맵 피드백'}</h2></div>
    <div className="card feedback-form">
      {commentSkillNames(R.plan).map(skill => {
        if (!summary) return <SkillFeedback key={skill} draftKey={mk(key, skill)} skill={skill} />;
        const draft = drafts[mk(key, skill)];
        if (draft?.fit !== 'good' && draft?.fit !== 'partial') return null;
        return <div key={skill} className="feedback-summary-row">
          <button type="button" className="link quiet small feedback-remove" aria-label={skill + ' 피드백 삭제'}
            onClick={() => updateWs(state => { delete state.mgr[mk(key, skill)]; })}>×</button>
          <div className="feedback-summary-content"><b>{skill}</b> <span className={draft.fit === 'good' ? 'tag ok' : 'tag acc'}>{draft.fit === 'good' ? '좋아요' : '보완 필요'}</span>
          {draft.fit === 'partial' && <>
            {(selectedFeedbackReasons(draft.fitText).length ? selectedFeedbackReasons(draft.fitText) : ['이유 없음']).map(reason => <span className="tag line" key={reason}>{reason}</span>)}
            {draft.free?.trim() && <div>{draft.free.trim()}</div>}
          </>}</div>
        </div>;
      })}
      <label className="feedback-note"><b>전체 코멘트 <span className="small muted">· 선택</span></b>
        <textarea className="textarea sm" value={drafts[key]?.free || ''} onChange={event => {
          const free = event.target.value;
          updateWs(state => { state.mgr[key] = { ...state.mgr[key], free }; });
        }} />
      </label>
      <div className="feedback-submit"><CommentSendButton uid={uid} R={R} /></div>
    </div>
  </section>;
}

export function MemberRoadPage() {
  const [feedback, setFeedback] = useState<{ planId: string; skill: string } | null>(null);
  useEffect(() => {
    if (!feedback) return;
    function dismissOutside(event: PointerEvent) {
      if (event.target instanceof Element && !event.target.closest('.feedback-popup, .feedback-trigger')) {
        setFeedback(null);
      }
    }
    function dismissOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setFeedback(null);
    }
    document.addEventListener('pointerdown', dismissOutside);
    document.addEventListener('keydown', dismissOnEscape);
    return () => {
      document.removeEventListener('pointerdown', dismissOutside);
      document.removeEventListener('keydown', dismissOnEscape);
    };
  }, [feedback]);
  const { pid = '' } = useParams();
  const { uid, member: e, gone, teamLoading, team } = useMemberGate();
  const q = useMemberState(uid, !gone && !teamLoading && !!e);
  if (team.isError && !e) return <Page back={paths.team} title="직원 정보를 불러오지 못했어요"><button className="btn line" onClick={() => void team.refetch()}>다시 시도</button></Page>;
  if (gone) return <Navigate to={paths.team} replace />;
  if (teamLoading || !e) return <Loading text="서버에서 불러오는 중…" />;
  if (!q.data) return <Page back={paths.member(uid)} eyebrow={who(e)} title="확정한 로드맵"><MemberLoading q={q} /></Page>;
  const R = q.data.plans[pid];
  // 알림으로 새 로드맵에 들어오면 캐시의 옛 기록에는 아직 없다. 새로 받는 중이면 기다리고, 받은 뒤에도 없을 때만 목록으로(#82)
  if (!R) return q.isFetching ? <Loading text="서버에서 소속 직원의 기록을 불러오는 중…" /> : <Navigate to={paths.member(uid)} replace />;
  const pl = R.plan;
  const live = R.status === 'active';
  const cs = (R.comments || []).slice().reverse();
  const activeSkill = live && feedback?.planId === R.id && commentSkillNames(pl).includes(feedback.skill) ? feedback.skill : null;
  const feedbackButton = (skill: string) => <button type="button" className="link quiet small feedback-trigger"
    aria-expanded={activeSkill === skill} onClick={event => {
      event.preventDefault();
      event.stopPropagation();
      const card = event.currentTarget.closest('details');
      if (card && activeSkill !== skill) card.open = true;
      setFeedback(activeSkill === skill ? null : { planId: R.id, skill });
    }}>피드백</button>;
  const reps = q.data.reports.filter((r) => r.planId === R.id);
  return (
    <Page
      back={paths.member(uid)}
      eyebrow={`${who(e)} · ${trackName(pl.opt, pl.name)} v${pl.version} · ${R.createdAt} 확정${live ? '' : R.status === 'done' ? ' · 마침' : ' · 보관'}`}
      title={pl.displayTitle || pl.goal}
      lead={pl.displayTitle ? pl.goal : undefined}

    >
      {/* 직원의 '내 로드맵'과 같은 구성(#96) — 읽기 전용 */}
      <MemberRoadView R={R} skillAction={live ? feedbackButton : undefined}
        skillFooter={pl.def.learningReport ? skill => activeSkill === skill
          ? <aside className="feedback-popup card" aria-label="스킬 피드백">
              <SkillFeedback draftKey={mk(mk(uid, R.id), skill)} skill={skill} />
            </aside> : null : undefined} />
      {reps.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">결과 보고서</h2>
          </div>
          <div className="list">
            {reps.map((r) => (
              <MgrRepRow key={r.id} uid={uid} r={r} unseen={!!q.data.unseen?.reports.includes(r.id)} />
            ))}
          </div>
        </div>
      ) : null}
      <Privacy />
      {cs.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">코멘트 기록 {cs.length} <span className="small muted">(보낸 {cs.filter(c => !c.deleted).length} · 삭제 {cs.filter(c => c.deleted).length})</span></h2>
          </div>
          <div className="stack">
            <ManagerCommentHistory uid={uid} R={R} comments={cs} />
          </div>
        </div>
      ) : null}
      {live ? <FeedbackForm uid={uid} R={R} summary={Boolean(pl.def.learningReport)} /> : (
        <Note>피드백은 진행 중인 로드맵에만 보낼 수 있어요.</Note>
      )}
    </Page>
  );
}

export function MemberReportPage() {
  const { rid = '' } = useParams();
  const { uid, member: e, gone, teamLoading, team } = useMemberGate();
  const q = useMemberState(uid, !gone && !teamLoading && !!e);
  if (team.isError && !e) return <Page back={paths.team} title="직원 정보를 불러오지 못했어요"><button className="btn line" onClick={() => void team.refetch()}>다시 시도</button></Page>;
  if (gone) return <Navigate to={paths.team} replace />;
  if (teamLoading || !e) return <Loading text="서버에서 불러오는 중…" />;
  if (!q.data) return <Page back={paths.member(uid)} eyebrow={who(e)} title="학습 결과 보고서"><MemberLoading q={q} /></Page>;
  const r = q.data.reports.find((x) => x.id === rid);
  // 다시 만든 보고서는 id 가 바뀐다. 새로 받는 중이면 기다리고, 받은 뒤에도 없을 때만 목록으로(#82)
  if (!r) return q.isFetching ? <Loading text="서버에서 소속 직원의 기록을 불러오는 중…" /> : <Navigate to={paths.member(uid)} replace />;
  const R = q.data.plans[r.planId];
  return (
    <Page back={R ? paths.memberPlan(uid, R.id) : paths.member(uid)} eyebrow={`${who(e)} · 결과 보고서 · ${trackName(r.opt)} v${r.version} · ${r.createdAt}`} title="학습 결과 보고서" lead={r.goal}>
      <ReportBody r={r} />
      {R?.comments?.length ? <ManagerCommentHistory uid={uid} R={R} comments={R.comments} /> : null}
      {R?.status === 'active' && <FeedbackForm uid={uid} R={R} />}
      <Note>
        {e.name} 님의 결과 보고서예요. 보고서 내용은 읽기만 할 수 있어요.
      </Note>
      {/* 같은 화면을 재사용해 다른 보고서로 옮겨도 쓰던 과제가 넘어가지 않게 로드맵별로 분리한다(PR #140 리뷰) */}
      <HeadReportTasks key={r.planId} planId={r.planId} memberName={e.name} />
    </Page>
  );
}

export function CommentSentPage() {
  const go = useGo();
  const { pid = '' } = useParams();
  const { uid, member: e, gone, team } = useMemberGate();
  if (team.isError && !e) return <Page back={paths.team} title="직원 정보를 불러오지 못했어요"><button className="btn line" onClick={() => void team.refetch()}>다시 시도</button></Page>;
  if (gone) return <Navigate to={paths.team} replace />;
  if (!e) return <Loading text="서버에서 불러오는 중…" />;
  return (
    <>
      <div className="badge-ico">
        <Icon name="send" />
      </div>
      <h1 className="t lg">{e.name} 님에게 코멘트를 보냈어요</h1>
      <p className="lead">직원이 반영을 요청하고 수정안을 확정해야 로드맵이 바뀌어요. 직원이 확인했는지와 반영했는지는 이 로드맵의 ‘코멘트 기록’에서 볼 수 있어요.</p>
      <div className="actions">
        <button className="btn pri" onClick={() => go(paths.memberPlan(uid, pid))}>
          코멘트 기록 보기
        </button>
        <button className="btn line" onClick={() => go(paths.team)}>
          소속 직원 계획으로
        </button>
      </div>
    </>
  );
}
