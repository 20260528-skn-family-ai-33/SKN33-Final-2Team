import { ReviewSkillBlocks, type ReviewMaterials } from '@/features/draft/review/ReviewSkillBlocks';
import { CmItem, CommentRevisionButton, ConfirmComments } from './comments';
import { openRecord } from './RecordSheet';
import { trackName, trackTrait } from '@/shared/constants/data';
import { PlanSummary } from './PlanSummary';
/* 내 로드맵: 목록(진행 중 · 지난 로드맵) → 로드맵 하나 · 확정 완료 화면 (5차 scr.roadmap · scr.confirmed) */
import { Navigate, useLocation, useParams } from 'react-router';
import type { PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { RoadmapResources, RoadmapActivityList } from './RoadmapLearning';
import { useGo } from '@/shared/hooks/useGo';
import { count, isPlanComplete } from '@/shared/lib/plan';
import { monthDay, planStart, startsLater } from '@/features/home/ganttCalc';
import { currentWeekSkillNames } from './roadmapLearningData';
import { useCatalog } from '@/shared/state/catalog';
import { useClockRefresh } from '@/shared/state/demoClock';
import { useMe } from '@/shared/state/session';
import { closeSheet, openSheet } from '@/shared/state/ui';
import { newComments, planReports, recs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note, Page, Stats } from '@/shared/ui/parts';
import { Alerts, NoPlan, openPreAnswers, openVersions, PlanGate, postStart } from './parts';
import { archivePlan, resumePlan, startRevise } from './planActions';
import { useEffect, useRef, useState } from 'react';
import { won } from '@/shared/lib/format';

function commentCounts(comments: NonNullable<PlanRecord['comments']>) {
  const deleted = comments.filter(comment => comment.deleted).length;
  const received = `받은 코멘트 ${comments.length - deleted}개`;
  return <span title={`${received} · 삭제된 코멘트 ${deleted}개`}>{received}</span>;
}



function RoadLi({ R }: { R: PlanRecord }) {
  useClockRefresh();
  const go = useGo();
  const [open, setOpen] = useState(false);
  const reports = useWs(state => state.reports);
  const linkedReports = R.status === 'active' ? [] : planReports({ reports }, R);
  const pl = R.plan;
  const c = count(pl, R.progress);
  const n = newComments(R).length;
  const detailId = `roadmap-preview-${R.id}`;

  const isDoneComplete = R.status === 'done' && isPlanComplete(pl, R.progress);
  const statusText =
  R.status === 'done'
    ? isDoneComplete ? '완료' : '조기 종료'
    : R.status === 'archived'
      ? '보관'
      : startsLater(R)
        ? `${monthDay(planStart(R))} 시작`
        : '진행 중';
  const statusTone = R.status === 'done' ? (isDoneComplete ? ' done' : ' early') : '';

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
              <span className={`roadmap-info-badge${statusTone}`}>{statusText}</span>
              {n > 0 && <span className="tag acc">새 코멘트 {n}</span>}
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
      {linkedReports.length > 0 && <section className="roadmap-preview-reports" aria-label="이 로드맵의 결과 보고서">
        <h3 className="st">결과 보고서</h3>
        <div className="list">
          {linkedReports.map(report => <button type="button" className="li" key={report.id} onClick={() => go(paths.report(report.id))}>
            <span className="idx"><Icon name="chart" /></span>
            <span className="tx"><b>학습 결과 보고서 · v{report.version}</b>
              <small>{report.createdAt}{report.confirmed ? ' · 확인함' : R.status !== 'done' ? ' · 확인 전' : ''}</small></span>
            <span className="end"><Icon name="right" /></span>
          </button>)}
        </div>
      </section>}
    </div>
  );
}

function sortNewestFirst(items: PlanRecord[]): PlanRecord[] {
  return items
    .map((R, idx) => ({ R, idx }))
    .sort((a, b) => {
      const aTime = Date.parse(a.R.createdAt || a.R.plan.confirmedAt || '');
      const bTime = Date.parse(b.R.createdAt || b.R.plan.confirmedAt || '');
      if (!Number.isFinite(aTime)) return Number.isFinite(bTime) ? 1 : b.idx - a.idx;
      if (!Number.isFinite(bTime)) return -1;
      if (aTime !== bTime) return bTime - aTime;
      const aDone = Date.parse(a.R.doneAt || '');
      const bDone = Date.parse(b.R.doneAt || '');
      if (Number.isFinite(aDone) && Number.isFinite(bDone) && aDone !== bDone) {
        return bDone - aDone;
      }
      return b.idx - a.idx;
    })
    .map(({ R }) => R);
}

export function RoadmapList() {
  const all = useWs((s) => s.plans);
  const act = recs({ plans: all }, 'active');
  const archived = recs({ plans: all }, 'archived');
  const completed = sortNewestFirst(recs({ plans: all }, 'done'));
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
          중지 후 보관하기
        </button>
      </>
    ),
  });
}

export function focusSkillCommentTrigger(skill: string, root: Pick<Document, 'getElementById'> = document): boolean {
  const trigger = root.getElementById(`skill-${skill}`)?.querySelector<HTMLElement>('.received-comment-trigger');
  trigger?.focus();
  return !!trigger;
}

export function closeSkillCommentOnEscape(
  event: Pick<KeyboardEvent, 'key'>,
  skill: string,
  close: (closedSkill: string) => void,
  root: Pick<Document, 'getElementById'> = document,
): boolean {
  if (event.key !== 'Escape') return false;
  focusSkillCommentTrigger(skill, root);
  close(skill);
  return true;
}

/** 진행 중이면 기록할 수 있고, 마쳤거나 보관한 로드맵은 읽기 전용(활동·완료·메모·버전·보고서·받은 코멘트) */
function RoadView({ R }: { R: PlanRecord }) {
  const { hash } = useLocation();
  useEffect(() => {
    if (!hash.startsWith('#skill-')) return;
    let id: string;
    try { id = decodeURIComponent(hash.slice(1)); } catch { return; }
    const target = document.getElementById(id);
    const card = target?.closest('details');
    if (card) card.open = true;
    target?.scrollIntoView({ block: 'center' });
  }, [hash, R.id]);
  useClockRefresh();
  const resources = useCatalog(state => state.res);
  const go = useGo();
  const reports = useWs((s) => s.reports);
  const reps = planReports({ reports }, R);
  const pl = R.plan;
  const live = R.status === 'active';
  const cs = R.comments || [];
  const [commentSkill, setCommentSkill] = useState<string | null>(null);
  const restoreFocusSkill = useRef<string | null>(null);
  useEffect(() => {
    if (commentSkill || !restoreFocusSkill.current) return;
    const skill = restoreFocusSkill.current;
    restoreFocusSkill.current = null;
    focusSkillCommentTrigger(skill);
  }, [commentSkill]);
  useEffect(() => {
    if (!commentSkill) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Element && !event.target.closest('.received-comment-popup, .received-comment-trigger')) setCommentSkill(null);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      closeSkillCommentOnEscape(event, commentSkill, (closed) => {
        restoreFocusSkill.current = closed;
        setCommentSkill(null);
      });
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [commentSkill]);
  const cmBtn = cs.length ? (
    <button className="btn ghost sm" onClick={() => go(paths.comments(R.id))}>
      <Icon name="chat" />
      {commentCounts(cs)}
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
        중지 후 보관하기
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
        역량 테스트 응답
      </button>
      {cmBtn}
    </>
  );
  return (
    <Page
      back={paths.roadmaps}
      eyebrow={[trackName(pl.opt, pl.name), trackTrait(pl.opt)].filter(Boolean).join(' · ')}
      title={pl.displayTitle || pl.goal}
      lead={pl.goal}
      foot={foot}
    >
      {live ? (
        <>
          {startsLater(R) ? <Note>이 로드맵은 {monthDay(planStart(R))}부터 시작해요.</Note> : null}
          <Alerts R={R} />
        </>
      ) : (
        <Note>
          {R.status === 'done' ? '마친 로드맵이에요. 기록은 읽기만 할 수 있어요.' : '보관한 로드맵이에요. 기록은 읽기만 할 수 있고, ‘다시 진행하기’를 누르면 이어서 기록할 수 있어요.'}
        </Note>
      )}
      {cs.length > 0 && <div className="actions">
        <button className="btn line sm" onClick={() => go(paths.comments(R.id))}>받은 코멘트 보기</button>
      </div>}
      {pl.def.learningReport ? <PlanSummary R={R} /> : <Stats pl={pl} periodLabel="기간" />}
      <RoadmapResources R={R} />
      {pl.def.learningReport ? <ReviewSkillBlocks confirmed materials={pl.def.learningReport as ReviewMaterials}
        acts={pl.acts.filter((act): act is typeof act & { skill: string; how: string; hours: number } => !!act.skill).map(act => ({ ...act, how: act.how || '' }))}
        selectedIds={pl.acts.map(act => act.id)} progress={R.progress} busy={!live}
        currentSkillNames={currentWeekSkillNames(R, resources)}
        skillAction={skill => <span id={'skill-' + skill}>
          {cs.some(comment => comment.skill === skill && !comment.deleted) && (
            <button type="button" className="link quiet small feedback-trigger received-comment-trigger" aria-expanded={commentSkill === skill} onClick={event => {
              event.preventDefault();
              event.stopPropagation();
              const card = event.currentTarget.closest('details');
              if (card && commentSkill !== skill) card.open = true;
              setCommentSkill(commentSkill === skill ? null : skill);
            }}>코멘트 보기</button>
          )}
        </span>}
        skillFooter={skill => commentSkill === skill ? (
          <aside className="feedback-popup card received-comment-popup" aria-label={skill + ' 받은 코멘트'}>
            {cs.filter(comment => comment.skill === skill && !comment.deleted).map(comment => (
              <CmItem key={comment.id} c={comment} foot={<div className="actions cm-act" style={{ justifyContent: 'flex-end' }}>
                <CommentRevisionButton R={R} c={comment} />
                <ConfirmComments R={R} commentId={comment.id} />
              </div>} />
            ))}
          </aside>
        ) : null}
        onOpenResource={(skill, resourceId) => { const activity = pl.acts.find(act => act.skill === skill && act.res === resourceId) || pl.acts.find(act => act.res === resourceId); if (activity) openRecord(R.id, activity.id); }}
        onSubmit={name => { const task = pl.acts.find(act => act.skill === name && !act.res); if (task) openRecord(R.id, task.id); }} /> : <SkillMap pl={pl} progress={R.progress} /> }
      <RoadmapActivityList R={R} skipSkillCardDuplicates />
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
                    {r.createdAt}{r.confirmed ? ' · 확인함' : R.status !== 'done' ? ' · 확인 전' : ''}
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
  const later = startsLater(R);
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
      <p className="lead">{first ? (later ? '시작일이 되면 첫 활동부터 진행해 보세요. 실행한 만큼 기록하면 돼요.' : '첫 활동부터 시작해 보세요. 실행한 만큼 기록하면 돼요.') : `${pl.why} 내용을 새 버전으로 저장했어요. 이전 버전도 남아 있어요.`}</p>
      <div className="card flat">
        <div className="stack">
          {pl.selection ? (
            <div className="row top">
              <Icon name="spark" />
              <span>
                이 로드맵은{' '}
                <b>
                  {trackName(pl.selection.perspective, pl.selection.name)}
                </b>{' '}
                방식으로 만들었어요.
              </span>
            </div>
          ) : null}
          {first && others ? (
            <div className="row top">
              <Icon name="map" />
              <span>{later ? <><b>{monthDay(planStart(R))}</b>부터 시작해요. 진행 중인 로드맵이 끝난 다음 주예요.</> : `진행 중인 다른 로드맵 ${others}개도 그대로 함께 진행돼요.`}</span>
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
        <button className="btn pri" onClick={() => go(later ? paths.home : paths.roadmap(R.id))}>
          {later ? '홈으로' : '로드맵 시작하기'}
        </button>
        <button className="btn line" onClick={() => go(paths.roadmaps)}>
          모든 로드맵 보기
        </button>
      </div>
    </>
  );
}
