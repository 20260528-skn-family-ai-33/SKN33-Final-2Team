import { Fragment, type ReactNode } from 'react';
import type { PlanRecord } from '@/api/types/plan';
import { Stt } from '@/shared/ui/parts';
import { activityTime } from '@/shared/lib/resourceTime';
import { hrs } from '@/shared/lib/format';
import './reviewSkills.css';
import './reviewStep.css';
import { ResourceImage } from '@/shared/ui/ResourceImage';
import { TaskDescription } from '@/shared/ui/TaskDescription';
import { activityAnchor } from '@/features/roadmap/roadmapLearningData';
import { durationLabel, type DurationEstimate } from '../result/skillOrder';
import { courseDifficulty } from '@/shared/lib/courseDifficulty';
import type { MaterialResource } from '@/api/types/draft';
export type ReviewResource = MaterialResource & { provider?: string; image?: string; url?: string; cost?: number | null; timeNote?: string; knowledge?: string; competencySummary?: string[]; content?: string };
export type ReviewMaterials = { recommendations: { skills: { name: string; courses: ReviewResource[]; books: ReviewResource[] }[] } | null; choices: Record<string, { course: string | null; courses?: string[]; books: string[]; enabled?: boolean }>; skillOrder?: string[]; skillDetails?: { name: string; application: string; competencySummary?: string[] }[]; durationEstimates?: Record<string, DurationEstimate> };
type Act = { id: string; title: string; skill: string; how: string; hours: number; res?: string | null; hoursEstimated?: boolean; hoursBasis?: string; hoursAllocation?: 'book-week'; catalogHours?: number | null };
export function ReviewResourceCard({ resource, kind, activity, anchor, progress, onOpenResource }: {
  resource: ReviewResource; kind: '강좌' | '도서'; activity?: Act; anchor?: boolean;
  progress?: PlanRecord['progress']; onOpenResource?: () => void;
}) {
  return <article id={anchor && activity ? activityAnchor(activity.id) : undefined} tabIndex={anchor && activity ? -1 : undefined} className="review-resource-card" data-kind={kind === '강좌' ? 'course' : 'book'}>
            <div className="review-material">
              {resource.url ? <a className="review-cover-link" href={resource.url} target="_blank" rel="noreferrer" aria-label={`${resource.title} ${kind} 바로가기 (새 창)`}>
                <ResourceImage image={resource.image} type={kind === '도서' ? 'book' : 'course'} alt={`${resource.title} 표지`} />
              </a> : <ResourceImage image={resource.image} type={kind === '도서' ? 'book' : 'course'} alt={`${resource.title} 표지`} />}
              <div><span className="small muted"><span className="review-kind-badge">{kind}</span> · {resource.provider || '출처 미확인'}{kind === '강좌' && resource.difficulty && ` · ${courseDifficulty(resource)}`}</span><h4>{onOpenResource ? <button type="button" className="review-resource-title" aria-label={`${resource.title} 실행 기록 열기`} onClick={() => onOpenResource()}>{resource.title}</button> : resource.title}</h4>
                <span className="small muted">{resource.cost == null ? '가격 미확인' : resource.cost === 0 ? '무료' : `${resource.cost.toLocaleString()}원`}</span>
                {kind === '도서' ? <div className="small muted">일정 산정 제외</div> : activity && <div className="small muted" title={activityTime(activity).title}>{activityTime(activity).text}</div>}
                {activity && progress?.[activity.id]?.memo && <p className="small muted">메모 · {progress[activity.id].memo}</p>}
                {resource.url && <a href={resource.url} target="_blank" rel="noreferrer" className="review-material-link">{resource.provider === '사내교육' ? '사내교육 안내 보기' : '바로가기'} ↗</a>}
              </div>
            </div>

          </article>;
}

export function ReviewTaskCopy({ task, memo }: { task: Act; memo?: string }) {
  return <span className="review-task-copy"><span className="review-task-title">
    <b>{task.title}</b><span className="small muted">예상 {hrs(task.hours)} · 자료 학습 기간에서 제외</span>
  </span><TaskDescription text={task.how} />{memo && <span className="small muted">메모 · {memo}</span>}</span>;
}

/** 확정한 로드맵의 스킬 블록(내 로드맵 · 부서장 보기). 작성 7단계(ReviewTaskBlocks)와 같은 구성으로 보여 준다(#224 후속):
    배울 자료(눌러서 실행 기록) · 이 스킬을 마치면 · 산출물 과제(상태와 제출). 작성 단계의 선택·제안 기능은 ReviewTaskBlocks 가 맡는다.
    여러 스킬이 같이 고른 자료(공통 강좌·도서)는 그 스킬들 위에 한 번만 보여 주고, 걸린 활동이 모두 끝나야 완료로 표시한다 */
export function ReviewSkillBlocks({ materials, acts, busy, readOnly = false, onSubmit, onOpenResource, progress, skillAction, skillFooter, currentSkillNames = [] }: {
  materials: ReviewMaterials; acts: Act[];
  /** 이전 호출부와 맞추기 위해 받기만 한다(확정 뒤에는 모든 활동이 선택된 상태다) */
  selectedIds?: string[]; confirmed?: boolean;
  /** 진행 중이 아니면(읽기 전용) 실행 기록을 열지 않는다 */
  busy: boolean; readOnly?: boolean;
  onSubmit?: (skill: string) => void; onOpenResource?: (skill: string, resourceId: string) => void;
  progress?: PlanRecord['progress']; skillAction?: (skill: string) => ReactNode; skillFooter?: (skill: string) => ReactNode; currentSkillNames?: string[];
}) {
  const skills = materials.recommendations?.skills || [];
  const names = (materials.skillOrder || skills.map(s => s.name)).filter(name => materials.choices[name]?.enabled !== false);
  const done = (id: string) => progress?.[id]?.status === 'done';
  const picked = (name: string) => {
    const skill = skills.find(s => s.name === name);
    const choice = materials.choices[name];
    if (!skill) return [];
    return [
      ...skill.courses.filter(r => r.id === choice?.course || choice?.courses?.includes(r.id)).map(resource => ({ resource, kind: 'course' as const })),
      ...skill.books.filter(r => choice?.books.includes(r.id)).map(resource => ({ resource, kind: 'book' as const })),
    ];
  };
  const owners = new Map<string, string[]>();
  for (const name of names) for (const { resource } of picked(name)) owners.set(resource.id, [...(owners.get(resource.id) || []), name]);
  const shared = (id: string) => (owners.get(id) || []).length > 1;
  const number = (name: string) => String(names.indexOf(name) + 1).padStart(2, '0');
  const row = (resource: ReviewResource, kind: 'course' | 'book', owning: string[]) => {
    const activities = acts.filter(a => a.res === resource.id && owning.includes(a.skill));
    const activity = activities[0];
    const open = onOpenResource && !busy ? () => onOpenResource(owning[0], resource.id) : undefined;
    const meta = [
      resource.provider || '출처 미확인',
      resource.cost == null ? '가격 확인 필요' : resource.cost === 0 ? '무료' : `${resource.cost.toLocaleString('ko-KR')}원`,
      kind === 'course' && resource.difficulty ? courseDifficulty(resource) : null,
      kind === 'book' ? '일정에 넣지 않아요' : activity ? activityTime(activity).text : null,
    ].filter(Boolean).join(' · ');
    const memo = activities.map(a => progress?.[a.id]?.memo).find(Boolean);
    return <div className="rv-mini" key={resource.id} id={activity ? activityAnchor(activity.id) : undefined} tabIndex={activity ? -1 : undefined}>
      {/* 완료 표시가 없는 줄(도서)도 같은 자리를 비워 표지와 글이 한 줄로 맞게 한다 */}
      {progress ? activity && kind === 'course' ? <Stt done={activities.every(a => done(a.id))} /> : <span className="rv-stt-gap" aria-hidden="true" /> : null}
      <ResourceImage className="rv-thumb" image={resource.image} type={kind} alt="" />
      <span className="rv-mini-tx">
        <b><span className="tag">{kind === 'course' ? '강좌' : '도서'}</span>{open ? <button type="button" className="rv-title-btn" aria-label={`${resource.title} 실행 기록 열기`} onClick={open}>{resource.title}</button> : resource.title}</b>
        <small>{meta}</small>
        {memo ? <small>메모 · {memo}</small> : null}
      </span>
      {resource.url ? <a className="rv-link" href={resource.url} target="_blank" rel="noreferrer" aria-label={`${resource.title} ${resource.provider === '사내교육' ? '사내교육 안내' : '원본'} 보기 (새 창)`}>{resource.provider === '사내교육' ? '안내 보기' : '원본 보기'} ↗</a> : null}
    </div>;
  };
  return <div className="rv-skills">{names.map((name, index) => {
    const skill = skills.find(s => s.name === name); if (!skill) return null;
    const mine = picked(name);
    const own = mine.filter(({ resource }) => !shared(resource.id));
    const common = mine.filter(({ resource }) => shared(resource.id));
    // 공통 자료 카드는 그 자료를 쓰는 첫 스킬 바로 위에 한 번만 둔다
    const lead = common.filter(({ resource }) => owners.get(resource.id)![0] === name);
    const leadSkills = [...new Set(lead.flatMap(({ resource }) => owners.get(resource.id)!))];
    const outcomes = materials.skillDetails?.find(s => s.name === name)?.competencySummary || [];
    const tasks = acts.filter(a => a.skill === name && !a.res);
    const estimate = materials.durationEstimates?.[name];
    const current = currentSkillNames.includes(name);
    return <Fragment key={name}>
      {lead.length ? <section className="rv-shared" aria-label="함께 배우는 자료">
        <header><h3>함께 배우는 자료</h3><span className="tag acc">스킬 {leadSkills.map(number).join(' · ')} 공통</span></header>
        {lead.map(({ resource, kind }) => row(resource, kind, owners.get(resource.id)!))}
      </section> : null}
      <details open className={`rv-skill review-skill-block${current ? ' is-current-week' : ''}`}>
        <summary>
          <span className="rv-skill-n">{String(index + 1).padStart(2, '0')}</span>
          <h3>{name}</h3>
          {current ? <span className="tag acc">이번 주</span> : null}
          {estimate?.weeks != null ? <span className="tag line">{durationLabel(estimate)}</span> : null}
          {skillAction?.(name)}
          <span className="review-skill-toggle-more">펼치기</span><span className="review-skill-toggle-less">접기</span>
        </summary>
        <div className="rv-learn">
          <div>
            <h4>배울 자료</h4>
            {common.length ? <p className="rv-shared-ref"><span className="tag acc">공통</span>{common.map(({ resource }) => resource.title).join(' · ')}</p> : null}
            {own.map(({ resource, kind }) => row(resource, kind, [name]))}
            {!mine.length ? <p className="rv-muted">선택한 외부 자료가 없어요.</p> : null}
          </div>
          <div>
            <h4>이 스킬을 마치면</h4>
            {outcomes.length ? <ul className="rv-outcomes">{outcomes.map((line, i) => <li key={i}>{line}</li>)}</ul>
              : <p className="rv-muted">얻게 될 역량 요약이 아직 없어요.</p>}
          </div>
        </div>
        {tasks.length ? <div className="rv-tasks">
          <div className="rv-tasks-head">
            <h4>산출물 과제</h4>
            <span />
            {!readOnly ? <button type="button" className="btn sm line" disabled={busy || !onSubmit} onClick={() => onSubmit?.(name)}>과제물 제출</button> : null}
          </div>
          <div className="rv-task-grid">
            {tasks.map(task => <div className={`rv-task is-static${done(task.id) ? ' is-on' : ''}`} key={task.id} id={activityAnchor(task.id)} tabIndex={-1}>
              {progress ? <Stt done={done(task.id)} /> : null}
              <span className="rv-task-tx">
                {/* 저장되는 것은 활동의 완료 여부뿐이라(첨부 없이 완료하거나 첨부하고 진행 중일 수 있다) 제출 여부로 적지 않는다 */}
                <span className="rv-task-kicker">{progress ? done(task.id) ? '산출물 과제 · 완료' : '산출물 과제 · 미완료' : '산출물 과제'}</span>
                <b>{task.title}</b>
                <TaskDescription text={task.how} />
                {progress?.[task.id]?.memo ? <span className="rv-muted">메모 · {progress[task.id].memo}</span> : null}
              </span>
              <em>약 {hrs(task.hours)}</em>
            </div>)}
          </div>
        </div> : null}
        {skillFooter?.(name)}
      </details>
    </Fragment>;
  })}</div>;
}
