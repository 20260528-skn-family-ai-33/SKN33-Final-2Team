import { trackName } from '@/shared/constants/data';
/* 내 로드맵: 목록(진행 중 · 지난 로드맵) → 로드맵 하나 · 확정 완료 화면 (5차 scr.roadmap · scr.confirmed) */
import { Navigate, useParams } from 'react-router';
import type { PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { count, range, st, stageActs } from '@/shared/lib/plan';
import { useMe } from '@/shared/state/session';
import { closeSheet, openSheet } from '@/shared/state/ui';
import { newComments, planReports, recs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note, Page, Stats } from '@/shared/ui/parts';
import { StagesView } from '@/shared/ui/StagesView';
import { ActRow, Alerts, NoPlan, openPreAnswers, openVersions, PlanGate, postStart } from './parts';
import { archivePlan, resumePlan, startRevise } from './planActions';
import { useState } from 'react';
import { won } from '@/shared/lib/format';

function RoadLi({ R }: { R: PlanRecord }) {
  const go = useGo();
  const [open, setOpen] = useState(false);
  const pl = R.plan;
  const c = count(pl, R.progress);
  const n = newComments(R).length;
  const detailId = `roadmap-preview-${R.id}`;

  const statusText =
  R.status === 'done'
    ? c.t > 0 && c.done === c.t ? '완료' : '조기 종료'
    : R.status === 'archived'
      ? '보관'
      : '진행 중';

  const confirmedDate = (R.createdAt || pl.confirmedAt || '').slice(0, 10).replace(/-/g, '.');

  return (
    <div className="roadmap-preview">
      <div className="roadmap-preview-head">
        <button
          type="button"
          className="roadmap-preview-toggle"
          aria-expanded={open}
          aria-controls={detailId}
          onClick={() => setOpen((value) => !value)}
        >
          <Icon name="map" />
          <span className="roadmap-preview-title">
            <span className="roadmap-title-line">
              <b>{pl.displayTitle || pl.goal}</b>

              <span className="roadmap-info-badge">
                {confirmedDate || '날짜 미확인'}
              </span>

              <span className="roadmap-info-badge">{statusText}</span>
            </span>
            <small>
              {trackName(pl.opt, pl.name)} · 활동 {c.done}/{c.t} 완료
            </small>
          </span>
          <span aria-hidden="true">{open ? '▴' : '▾'}</span>
        </button>

        <button
          type="button"
          className="btn line sm"
          aria-label={`${pl.displayTitle || pl.goal} 바로가기`}
          onClick={() => go(paths.roadmap(R.id))}
        >
          바로가기
          <Icon name="right" />
        </button>
      </div>

      {n ? (
          <div className="roadmap-preview-tags">
            <span className="tag acc">새 코멘트 {n}</span>
          </div>
      ) : null}

      <div id={detailId} hidden={!open}>
        <div className="roadmap-preview-body">
          <dl className="roadmap-preview-stats">
            <div>
              <dt>기간</dt>
              <dd>{pl.weeks}주</dd>
            </div>
            <div>
              <dt>주당 학습시간</dt>
              <dd>{pl.hours}시간</dd>
            </div>
            <div>
              <dt>예상 비용</dt>
              <dd>
                {won(pl.cost)}
                {pl.costUnknown ? ' + 미확인 비용' : ''}
              </dd>
            </div>
          </dl>

          <div className="roadmap-preview-request">
            <b>요청 내용</b>
            <p>{pl.goal}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function RoadmapList() {
  const all = useWs((s) => s.plans);
  const act = recs({ plans: all }, 'active');
  const archived = recs({ plans: all }, 'archived');
  const completed = recs({ plans: all }, 'done');
  if (!act.length && !archived.length && !completed.length)
    return (
      <Page title="내 로드맵">
        <NoPlan />
      </Page>
    );
  return (
    <Page
      title="내 로드맵"
      lead="로드맵 제목을 눌러 정보를 펼쳐 비교해 보세요. 바로가기를 누르면 전체 로드맵을 볼 수 있어요."
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
      {[
        { title: '보관 중인 로드맵', items: archived },
        { title: '완료한 로드맵', items: completed },
      ].map(({ title, items }) => items.length ? (
        <div className="sec" key={title}>
          <div className="sec-h">
            <h2 className="st">{title} {items.length}</h2>
          </div>
          <div className="list">
            {items.map((R) => (
              <RoadLi key={R.id} R={R} />
            ))}
          </div>
        </div>
      ) : null)}
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
    <Page
      back={paths.roadmaps}
      eyebrow={trackName(pl.opt, pl.name)}
      title={pl.displayTitle || pl.goal}
      lead={pl.goal}
      foot={foot}
    >
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
        {trackName(pl.opt, pl.name)} · v{pl.version}
      </p>
      <h1 className="t lg">{first ? '로드맵을 확정했어요' : '수정안을 확정했어요'}</h1>
      <p className="lead">{first ? '첫 활동부터 시작해 보세요. 실행한 만큼 기록하면 돼요.' : `${pl.why} 내용을 새 버전으로 저장했어요. 이전 버전도 남아 있어요.`}</p>
      <div className="card flat">
        <div className="stack">
          {pl.selection ? (
            <div className="row top">
              <Icon name="spark" />
              <span>
                해당 로드맵은{' '}
                <b>
                  {trackName(pl.selection.perspective, pl.selection.name)}
                </b>
                을(를) 토대로 계획되었습니다.
              </span>
            </div>
          ) : null}
          {first && others ? (
            <div className="row top">
              <Icon name="map" />
              <span>진행 중인 다른 로드맵 {others}개도 그대로 함께 진행돼요.</span>
            </div>
          ) : null}
          {sup ? (
            <div className="row top">
              <Icon name="users" />
              <span>
                <b>확정한 로드맵, 진행 상태, 결과 보고서</b>는 나와 부서장만 볼 수 있어요.
              </span>
            </div>
          ) : null}
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
