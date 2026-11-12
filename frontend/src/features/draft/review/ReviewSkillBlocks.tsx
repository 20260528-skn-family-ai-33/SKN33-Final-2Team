import type { ReactNode } from 'react';
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
    배울 자료(눌러서 실행 기록) · 이 스킬을 마치면 · 산출물 과제(상태와 제출). 작성 단계의 선택·제안 기능은 ReviewTaskBlocks 가 맡는다 */
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
  return <div className="rv-skills">{names.map((name, index) => {
    const skill = skills.find(s => s.name === name); if (!skill) return null;
    const choice = materials.choices[name];
    const rows = [...skill.courses.filter(r => r.id === choice?.course || choice?.courses?.includes(r.id)), ...skill.books.filter(r => choice?.books.includes(r.id))];
    const outcomes = materials.skillDetails?.find(s => s.name === name)?.competencySummary || [];
    const tasks = acts.filter(a => a.skill === name && !a.res);
    const estimate = materials.durationEstimates?.[name];
    const current = currentSkillNames.includes(name);
    return <details open className={`rv-skill review-skill-block${current ? ' is-current-week' : ''}`} key={name}>
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
          {rows.length ? rows.map(resource => {
            const kind = skill.books.includes(resource) ? 'book' : 'course';
            const activity = acts.find(a => a.skill === name && a.res === resource.id);
            const open = onOpenResource && !busy ? () => onOpenResource(name, resource.id) : undefined;
            const meta = [
              resource.provider || '출처 미확인',
              resource.cost == null ? '가격 확인 필요' : resource.cost === 0 ? '무료' : `${resource.cost.toLocaleString('ko-KR')}원`,
              kind === 'course' && resource.difficulty ? courseDifficulty(resource) : null,
              kind === 'book' ? '일정에 넣지 않아요' : activity ? activityTime(activity).text : null,
            ].filter(Boolean).join(' · ');
            return <div className="rv-mini" key={resource.id} id={activity ? activityAnchor(activity.id) : undefined} tabIndex={activity ? -1 : undefined}>
              {progress && activity && kind === 'course' ? <Stt done={done(activity.id)} /> : null}
              <ResourceImage className="rv-thumb" image={resource.image} type={kind} alt="" />
              <span className="rv-mini-tx">
                <b><span className="tag">{kind === 'course' ? '강좌' : '도서'}</span>{open ? <button type="button" className="rv-title-btn" aria-label={`${resource.title} 실행 기록 열기`} onClick={open}>{resource.title}</button> : resource.title}</b>
                <small>{meta}</small>
                {activity && progress?.[activity.id]?.memo ? <small>메모 · {progress[activity.id].memo}</small> : null}
              </span>
              {resource.url ? <a className="rv-link" href={resource.url} target="_blank" rel="noreferrer" aria-label={`${resource.title} ${resource.provider === '사내교육' ? '사내교육 안내' : '원본'} 보기 (새 창)`}>{resource.provider === '사내교육' ? '안내 보기' : '원본 보기'} ↗</a> : null}
            </div>;
          }) : <p className="rv-muted">선택한 외부 자료가 없어요.</p>}
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
              <span className="rv-task-kicker">{/* 저장되는 것은 활동의 완료 여부뿐이라(첨부 없이 완료하거나 첨부하고 진행 중일 수 있다) 제출 여부로 적지 않는다 */}
              {progress ? done(task.id) ? '산출물 과제 · 완료' : '산출물 과제 · 미완료' : '산출물 과제'}</span>
              <b>{task.title}</b>
              <TaskDescription text={task.how} />
              {progress?.[task.id]?.memo ? <span className="rv-muted">메모 · {progress[task.id].memo}</span> : null}
            </span>
            <em>약 {hrs(task.hours)}</em>
          </div>)}
        </div>
      </div> : null}
      {skillFooter?.(name)}
    </details>;
  })}</div>;
}
