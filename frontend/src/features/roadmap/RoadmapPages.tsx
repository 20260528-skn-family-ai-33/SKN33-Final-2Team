/* 내 로드맵: 목록(진행 중 · 지난 로드맵) → 로드맵 하나 · 확정 완료 화면 (5차 scr.roadmap · scr.confirmed) */
import { Navigate, useParams } from 'react-router';
import type { PlanRecord } from '@/api/types/plan';
import { newIdToPath, paths } from '@/app/paths';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { count, range, st, stageActs } from '@/shared/lib/plan';
import { useMe } from '@/shared/state/session';
import { closeSheet, openSheet } from '@/shared/state/ui';
import { draftActive, newComments, planReports, recs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note, Page, Stats } from '@/shared/ui/parts';
import { StagesView } from '@/shared/ui/StagesView';
import { ActRow, Alerts, NoPlan, openPreAnswers, openVersions, PlanGate, postStart } from './parts';
import { archivePlan, resumePlan, startRevise } from './planActions';

function RoadLi({ R }: { R: PlanRecord }) {
  const go = useGo();
  const pl = R.plan;
  const c = count(pl, R.progress);
  const n = newComments(R).length;
  const tag = R.status === 'done' ? <span className="tag line">마침 {R.doneAt || ''}</span> : R.status === 'archived' ? <span className="tag line">보관 {R.archivedAt || ''}</span> : null;
  return (
    <button className="li" onClick={() => go(paths.roadmap(R.id))}>
      <span className="idx">
        <Icon name="map" />
      </span>
      <div className="tx">
        <b>{pl.goal}</b>
        <small>
          {pl.opt} {pl.name} · v{pl.version} · {pl.weeks}주 · 주 {pl.hours}시간 · 활동 {c.done}/{c.t} 완료
        </small>
      </div>
      <span className="end">
        {tag}
        {n ? <span className="tag acc">새 코멘트 {n}</span> : null}
        <Icon name="right" />
      </span>
    </button>
  );
}

export function RoadmapList() {
  const go = useGo();
  const all = useWs((s) => s.plans);
  const drafting = useWs((s) => draftActive(s));
  const lastNew = useWs((s) => s.lastNew);
  const act = recs({ plans: all }, 'active');
  const past = recs({ plans: all }).filter((R) => R.status !== 'active');
  if (!act.length && !past.length)
    return (
      <Page title="내 로드맵">
        <NoPlan />
      </Page>
    );
  return (
    <Page
      title="내 로드맵"
      lead={act.length > 1 ? `로드맵 ${act.length}개를 함께 진행하고 있어요. 눌러서 활동을 보고 기록해요.` : '확정한 로드맵이에요. 눌러서 활동을 보고 기록해요.'}
      foot={
        <button className="btn line sm" onClick={() => go(drafting ? newIdToPath(lastNew) : paths.newGoal)}>
          <Icon name="pen" />
          {drafting ? '작성 중인 새 로드맵 이어서' : '새 로드맵 작성'}
        </button>
      }
    >
      <div className="sec">
        <div className="sec-h">
          <h2 className="st">진행 중 {act.length}</h2>
        </div>
        {act.length ? (
          <div className="list">
            {act.map((R) => (
              <RoadLi key={R.id} R={R} />
            ))}
          </div>
        ) : (
          <p className="muted small">진행 중인 로드맵이 없어요. 새 로드맵을 작성하거나, 보관한 로드맵을 다시 진행할 수 있어요.</p>
        )}
      </div>
      {past.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">지난 로드맵 {past.length}</h2>
            <span className="small muted" style={{ marginLeft: 'auto' }}>
              마친 로드맵 · 보관한 로드맵
            </span>
          </div>
          <div className="list">
            {past.map((R) => (
              <RoadLi key={R.id} R={R} />
            ))}
          </div>
        </div>
      ) : null}
    </Page>
  );
}

function openArchive(go: ReturnType<typeof useGo>, R: PlanRecord): void {
  if (R.status !== 'active') return;
  openSheet({
    title: '이 로드맵을 보관할까요?',
    sub: R.plan.goal,
    body: () => (
      <>
        <p style={{ marginTop: 0 }}>진행 기록·메모·버전·받은 코멘트는 그대로 남고, 내 로드맵의 ‘지난 로드맵’에서 볼 수 있어요.</p>
        <ul className="plain-list small">
          <li>홈과 진행 중 목록에서 빠져요.</li>
          <li>부서장 화면에는 ‘보관’으로 보이고, 보관한 로드맵에는 새 코멘트를 받지 않아요.</li>
          <li>언제든 ‘다시 진행하기’로 이어서 할 수 있어요.</li>
        </ul>
        {R.pending ? <Note>만들어 둔 수정안은 보관할 때 버려요.</Note> : null}
      </>
    ),
    foot: () => (
      <>
        <button className="btn line" onClick={closeSheet}>
          취소
        </button>
        <button
          className="btn pri"
          onClick={() => {
            closeSheet();
            void archivePlan(go, R.id);
          }}
        >
          보관하기
        </button>
      </>
    ),
  });
}

/** 진행 중이면 기록할 수 있고, 마쳤거나 보관한 로드맵은 읽기 전용(활동·완료·메모·버전·보고서·받은 코멘트) */
function RoadView({ R }: { R: PlanRecord }) {
  const go = useGo();
  const reports = useWs((s) => s.reports);
  const reps = planReports({ reports }, R);
  const pl = R.plan;
  const live = R.status === 'active';
  const cs = R.comments || [];
  const stTag = live ? '' : R.status === 'done' ? ` · 마침 ${R.doneAt || ''}` : ` · 보관 ${R.archivedAt || ''}`;
  const cmBtn = cs.length ? (
    <button className="btn ghost sm" onClick={() => go(paths.comments(R.id))}>
      <Icon name="chat" />
      받은 코멘트 {cs.length}
    </button>
  ) : null;
  const foot = live ? (
    <>
      <button className="btn line sm" onClick={() => startRevise(go, R.id)}>
        수정 요청
      </button>
      <button className="btn ghost sm" onClick={() => openVersions(R.id)}>
        <Icon name="history" />
        버전 이력
      </button>
      <button className="btn ghost sm" onClick={() => postStart(go, R.id)}>
        사후 점검
      </button>
      {cmBtn}
      <button className="btn ghost sm rm-arch" onClick={() => openArchive(go, R)}>
        보관하기
      </button>
    </>
  ) : (
    <>
      {R.status === 'archived' ? (
        <button className="btn pri sm" onClick={() => void resumePlan(go, R.id)}>
          다시 진행하기
        </button>
      ) : null}
      <button className="btn ghost sm" onClick={() => openVersions(R.id)}>
        <Icon name="history" />
        버전 이력
      </button>
      <button className="btn ghost sm" onClick={() => openPreAnswers(R.id)}>
        사전 점검 응답
      </button>
      {cmBtn}
    </>
  );
  return (
    <Page back={paths.roadmaps} eyebrow={`${pl.opt} ${pl.name} · v${pl.version}${stTag}`} title="내 로드맵" lead={pl.goal} foot={foot}>
      {live ? (
        <Alerts R={R} />
      ) : (
        <Note>
          {R.status === 'done' ? '마친 로드맵이에요. 기록은 읽기만 할 수 있어요.' : '보관한 로드맵이에요. 기록은 읽기만 할 수 있고, ‘다시 진행하기’를 누르면 이어서 기록할 수 있어요.'}
        </Note>
      )}
      <Stats pl={pl} />
      <SkillMap pl={pl} />
      <div className="sec">
        {live ? (
          D.stages
            .filter((s) => s.n >= pl.start)
            .map((s) => {
              const acts = stageActs(pl, s.n);
              if (!acts.length) return null;
              return (
                <div className="stage" key={s.n}>
                  <div className="stage-h">
                    <span className="no">{s.n}</span>
                    <b>{s.name}</b>
                    <span className="end">
                      {range(acts)} · {acts.filter((a) => st(R.progress, a.id) === 'done').length}/{acts.length} 완료
                    </span>
                  </div>
                  <ul className="acts" style={{ gap: 12, marginTop: 14 }}>
                    {acts.map((a) => (
                      <ActRow key={a.id} a={a} R={R} />
                    ))}
                  </ul>
                </div>
              );
            })
        ) : (
          <StagesView pl={pl} progress={R.progress} status memo />
        )}
      </div>
      {reps.length ? (
        <div className="sec">
          <div className="sec-h">
            <h2 className="st">결과 보고서</h2>
          </div>
          <div className="list">
            {reps.map((r) => (
              <button className="li" key={r.id} onClick={() => go(paths.report(r.id))}>
                <span className="idx">
                  <Icon name="chart" />
                </span>
                <div className="tx">
                  <b>결과 보고서 · v{r.version}</b>
                  <small>
                    {r.createdAt} · {r.confirmed ? '확인함' : '확인 전'}
                  </small>
                </div>
                <span className="end">
                  <Icon name="right" />
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </Page>
  );
}

export function RoadmapPage() {
  const { pid } = useParams();
  const R = useWs((s) => (pid ? s.plans[pid] : undefined));
  if (pid && !R) return <Navigate to={paths.roadmaps} replace />;
  if (!R) return <RoadmapList />;
  return <RoadView R={R} />;
}

export function ConfirmedPage() {
  return (
    <PlanGate make={paths.confirmed} fallback={paths.roadmaps}>
      {(R) => <Confirmed R={R} />}
    </PlanGate>
  );
}

function Confirmed({ R }: { R: PlanRecord }) {
  const go = useGo();
  const me = useMe();
  const others = useWs((s) => recs(s, 'active').filter((x) => x.id !== R.id).length);
  const pl = R.plan;
  const first = pl.version === 1;
  const sup = me?.mySupervisor;
  return (
    <>
      <div className="badge-ico">
        <Icon name="check" />
      </div>
      <p className="eyebrow">
        {pl.name} · v{pl.version}
      </p>
      <h1 className="t lg">{first ? '로드맵을 확정했어요' : '수정안을 확정했어요'}</h1>
      <p className="lead">{first ? '첫 활동부터 시작해 보세요. 실행한 만큼 기록하면 돼요.' : `${pl.why} 내용을 새 버전으로 저장했어요. 이전 버전도 남아 있어요.`}</p>
      <div className="card flat">
        <div className="stack">
          {pl.selection ? (
            <div className="row top">
              <Icon name="spark" />
              <span>
                고른 안은{' '}
                <b>
                  {pl.selection.perspective} {pl.selection.name}
                </b>
                이에요. 로드맵 계획 에이전트의 {pl.selection.perspective} 하위 에이전트가 썼어요. 이 선택만 저장하고, 고르지 않은 두 안은 저장하지 않아요.
              </span>
            </div>
          ) : null}
          {first && others ? (
            <div className="row top">
              <Icon name="map" />
              <span>진행 중인 다른 로드맵 {others}개도 그대로 함께 진행돼요.</span>
            </div>
          ) : null}
          <div className="row top">
            <Icon name="users" />
            <span>
              {sup ? (
                <>
                  내 계획을 보는 부서장 {sup.name} 님은 <b>확정한 로드맵, 진행 상태, 결과 보고서</b>를 볼 수 있어요.
                </>
              ) : (
                '내 계획을 보는 부서장이 없어 로드맵과 보고서는 나만 봐요.'
              )}
            </span>
          </div>
          <div className="row top">
            <Icon name="lock" />
            <span>
              점검 응답 원본·진단 결과·활동 메모·첨부와 작성 중인 로드맵은 나만 봐요.
              {sup ? ' 결과 보고서에 들어 있는 문항별 사전→사후 응답 변화는 부서장도 볼 수 있어요.' : ''}
            </span>
          </div>
          <div className="row top">
            <Icon name="db" />
            <span>확정한 로드맵은 팀 DB에 저장돼요(로드맵·단계·자료 연결). 다른 PC에서 로그인해도 같은 기록이 보여요.</span>
          </div>
        </div>
      </div>
      <div className="actions">
        <button className="btn pri" onClick={() => go(paths.home)}>
          로드맵 시작하기
        </button>
        <button className="btn line" onClick={() => go(paths.roadmap(R.id))}>
          로드맵 보기
        </button>
      </div>
      {first && sup ? (
        <Note>
          시연: 로그아웃한 뒤 부서장 {sup.name}(사번 {sup.code})으로 로그인하면 이 로드맵에 코멘트를 남길 수 있어요.
        </Note>
      ) : null}
    </>
  );
}
