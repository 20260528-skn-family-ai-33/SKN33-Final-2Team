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
import { CmItem, CmTag, cmMine } from '@/features/roadmap/comments';
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
import { Loading, Note, Page, Stats } from '@/shared/ui/parts';
import { StagesView } from '@/shared/ui/StagesView';
import { mk, useMemberOf, useMemberState, useRefreshTeam, useTeam } from './teamData';

const ST_TAG: Record<string, React.ReactNode> = { done: <span className="tag line">마침</span>, archived: <span className="tag line">보관</span> };
const who = (e: TeamUser) => `${e.name} · ${meLine(e)}`;
const Av = ({ e }: { e: TeamUser }) => <span className="avatar">{e.name.slice(1)}</span>;
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
  if (!(m.activePlans + m.pastPlans))
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
    <button className="li" onClick={() => go(paths.member(e.id))}>
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
        {m.unreadComments ? <span className="tag acc">코멘트 확인 전 {m.unreadComments}</span> : null}
        <Icon name="right" />
      </span>
    </button>
  );
}

export function MemberListPage() {
  const me = useMe();
  const t = useTeam();
  const members = t.data?.members || [];
  return (
    <Page eyebrow={`부서장 · ${me?.name} · ${me?.dept || ''}`} title="소속 직원의 성장 로드맵" lead={`소속 직원 ${members.length}명이 확정한 로드맵과 진행 상태, 결과 보고서를 보고 계획 조정 의견을 남길 수 있어요.`}>
      {t.error ? (
        <p className="small" style={{ color: 'var(--warn)' }}>
          {cause(t.error).user}
        </p>
      ) : null}
      <div className="list">
        {members.map((m) => (
          <TeamRow key={m.user.id} m={m} />
        ))}
      </div>
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

function MgrRoadRow({ uid, R }: { uid: string; R: PlanRecord }) {
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
        <b>{pl.goal}</b>
        <small>
          {pl.name} v{pl.version} · 활동 {c.done}/{c.t} 완료{mine ? ` · 보낸 코멘트 ${mine}개` : ''}
        </small>
      </div>
      <span className="end">
        {ST_TAG[R.status] || null}
        {wait ? <span className="tag acc">확인 전 {wait}</span> : null}
        <Icon name="right" />
      </span>
    </button>
  );
}

function MgrRepRow({ uid, r }: { uid: string; r: Report }) {
  const go = useGo();
  return (
    <button className="li" onClick={() => go(paths.memberReport(uid, r.id))}>
      <span className="idx">
        <Icon name="chart" />
      </span>
      <div className="tx">
        <b>
          결과 보고서 · {r.opt} v{r.version}
        </b>
        <small>
          {r.goal} · {r.createdAt} · {r.confirmed ? '직원 확인함' : '직원 확인 전'}
        </small>
      </div>
      <span className="end">
        <Icon name="right" />
      </span>
    </button>
  );
}

/** 부서장 화면 공통 진입 조건: 소속 직원이 아니면 목록으로 */
function useMemberGate() {
  const { uid = '' } = useParams();
  const { team, member } = useMemberOf(uid);
  const gone = !team.isPending && !member;
  return { uid, member, gone, teamLoading: team.isPending };
}

export function MemberPlansPage() {
  const { uid, member: e, gone, teamLoading } = useMemberGate();
  const q = useMemberState(uid);
  if (gone) return <Navigate to={paths.team} replace />;
  if (teamLoading || !e) return <Loading text="서버에서 불러오는 중…" />;
  if (!q.data) return <Page back={paths.team} eyebrow={who(e)} title={`${e.name} 님의 로드맵`}><MemberLoading q={q} /></Page>;
  const all = Object.values(q.data.plans);
  const act = all.filter((R) => R.status === 'active');
  const past = all.filter((R) => R.status !== 'active');
  const reps = q.data.reports;
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
              <MgrRoadRow key={R.id} uid={uid} R={R} />
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
            {past.map((R) => (
              <MgrRoadRow key={R.id} uid={uid} R={R} />
            ))}
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
              <MgrRepRow key={r.id} uid={uid} r={r} />
            ))}
          </div>
        </div>
      ) : null}
      <Privacy />
    </Page>
  );
}

/** 부서장이 쓰는 중인 코멘트 칸 (5차 P.mgrCommentFields · nm: 같은 화면에 새 칸과 고치는 칸이 함께 있을 때 라디오 이름 꼬리) */
function CommentFields({ k, nm = '' }: { k: string; nm?: string }) {
  const b = `mgr.${k}`;
  const fit = useAt<string>(`${b}.fit`);
  const level = useAt<string>(`${b}.level`);
  return (
    <>
      <div className="field">
        <label>
          업무 적합성 <span className="muted small">담당 업무·부서 AI 사업과 맞나요?</span>
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
          수준·기간·분량 <span className="muted small">난이도와 기간이 적절한가요?</span>
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
  if (!live || !cmMine(c)) return <CmItem c={c} mgr />;
  if (c.status === 'applied') return <CmItem c={c} mgr foot={<p className="small muted cm-act">v{c.appliedVersion || ''}에 반영된 코멘트라 고칠 수 없어요.</p>} />;
  if (!editing)
    return (
      <CmItem
        c={c}
        mgr
        foot={
          <div className="actions cm-act">
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
          </div>
        }
      />
    );
  const ok = !!(m && m.fit && m.level && cmChanged(m));
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
      <CommentFields k={key} nm="-e" />
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

export function MemberRoadPage() {
  const go = useGo();
  const refresh = useRefreshTeam();
  const { pid = '' } = useParams();
  const { uid, member: e, gone, teamLoading } = useMemberGate();
  const q = useMemberState(uid);
  const key = mk(uid, pid);
  const draft = useWs((s) => s.mgr[key]);
  if (gone) return <Navigate to={paths.team} replace />;
  if (teamLoading || !e) return <Loading text="서버에서 불러오는 중…" />;
  if (!q.data) return <Page back={paths.member(uid)} eyebrow={who(e)} title="확정한 로드맵"><MemberLoading q={q} /></Page>;
  const R = q.data.plans[pid];
  if (!R) return <Navigate to={paths.member(uid)} replace />;
  const pl = R.plan;
  const live = R.status === 'active';
  const cs = (R.comments || []).slice().reverse();
  const reps = q.data.reports.filter((r) => r.planId === R.id);
  const okNew = !!(draft && draft.fit && draft.level);
  const send = async () => {
    if (!draft || !okNew) return;
    try {
      await teamApi.comment(pid, { fit: draft.fit || '', fitText: draft.fitText || '', level: draft.level || '', levelText: draft.levelText || '', free: draft.free || '' });
      updateWs((s) => void (s.mgr[key] = {}));
      await refresh(uid);
      go(paths.commentSent(uid, pid));
    } catch (err) {
      failToast(err, '코멘트를 보내지 못했어요');
    }
  };
  return (
    <Page
      back={paths.member(uid)}
      eyebrow={who(e)}
      title="확정한 로드맵"
      foot={
        live ? (
          <button className="btn pri" disabled={!okNew} onClick={() => void send()}>
            코멘트 보내기
          </button>
        ) : undefined
      }
    >
      <div className="card">
        <p className="eyebrow">
          {pl.name} · v{pl.version} · {R.createdAt} 확정{live ? '' : R.status === 'done' ? ' · 마침' : ' · 보관'}
        </p>
        <p style={{ fontWeight: 650, fontSize: 16 }}>{pl.goal}</p>
        <div style={{ marginTop: 16 }}>
          <Stats pl={pl} bare />
        </div>
      </div>
      <div className="sec">
        <div className="sec-h">
          <h2 className="st">단계별 진행</h2>
        </div>
        <StagesView pl={pl} progress={R.progress} status />
      </div>
      {reps.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">결과 보고서</h2>
          </div>
          <div className="list">
            {reps.map((r) => (
              <MgrRepRow key={r.id} uid={uid} r={r} />
            ))}
          </div>
        </div>
      ) : null}
      <Privacy />
      {cs.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">코멘트 기록 {cs.length}</h2>
          </div>
          <div className="stack">
            {cs.map((c) => (
              <MgrCmItem key={c.id} uid={uid} pid={pid} c={c} live={live} />
            ))}
          </div>
        </div>
      ) : null}
      {live ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">{cs.length ? '새 코멘트' : '계획 조정 의견'}</h2>
            <button
              className="link quiet"
              onClick={() => {
                const c = D.commentSample;
                updateWs((s) => void (s.mgr[key] = { ...(s.mgr[key] || {}), fit: c.fit, fitText: c.fitText, level: c.level, levelText: c.levelText, free: c.free }));
              }}
            >
              시연용 예시 문장
            </button>
          </div>
          <div className="card">
            <CommentFields k={key} />
          </div>
          <Note>
            새 코멘트는 앞서 보낸 코멘트를 덮어쓰지 않고 쌓여요(팀 DB 부서장 코멘트 표). 보낸 코멘트는 직원이 로드맵에 반영하기 전까지 ‘수정’으로 고칠 수 있고, 지울 수는 없어요.
            직원이 확인했는지, 몇 번째 버전에 반영했는지 여기서 볼 수 있어요. 직원이 반영을 요청해 수정안을 확정해야 로드맵이 바뀌어요.
          </Note>
        </div>
      ) : (
        <Note>직원이 {R.status === 'done' ? '마친' : '보관한'} 로드맵이에요. 코멘트는 진행 중인 로드맵에만 보낼 수 있어요.</Note>
      )}
    </Page>
  );
}

export function MemberReportPage() {
  const { rid = '' } = useParams();
  const { uid, member: e, gone, teamLoading } = useMemberGate();
  const q = useMemberState(uid);
  if (gone) return <Navigate to={paths.team} replace />;
  if (teamLoading || !e) return <Loading text="서버에서 불러오는 중…" />;
  if (!q.data) return <Page back={paths.member(uid)} eyebrow={who(e)} title="학습 결과 보고서"><MemberLoading q={q} /></Page>;
  const r = q.data.reports.find((x) => x.id === rid);
  if (!r) return <Navigate to={paths.member(uid)} replace />;
  const R = q.data.plans[r.planId];
  return (
    <Page back={R ? paths.memberPlan(uid, R.id) : paths.member(uid)} eyebrow={`${who(e)} · 결과 보고서 · ${r.opt} v${r.version} · ${r.createdAt}`} title="학습 결과 보고서" lead={r.goal}>
      <ReportBody r={r} />
      <Note>
        {e.name} 님이 {r.confirmed ? '확인한' : '아직 확인하지 않은'} 보고서예요. 부서장은 읽기만 할 수 있어요.
      </Note>
    </Page>
  );
}

export function CommentSentPage() {
  const go = useGo();
  const { pid = '' } = useParams();
  const { uid, member: e, gone } = useMemberGate();
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
      <Note>
        시연: 로그아웃한 뒤 {e.name}(사번 {e.code})으로 로그인하면 받은 코멘트를 볼 수 있어요.
      </Note>
    </>
  );
}
