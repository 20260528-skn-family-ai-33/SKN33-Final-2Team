import type { ReactNode } from 'react';
import type { PlanRecord } from '@/api/types/plan';
import { Stt } from '@/shared/ui/parts';
import { activityTime } from '@/shared/lib/resourceTime';
import { hrs } from '@/shared/lib/format';
import './reviewSkills.css';
import { ResourceImage } from '@/shared/ui/ResourceImage';
import { TaskDescription } from '@/shared/ui/TaskDescription';
import { Skeleton } from '@/shared/ui/Skeleton';
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

export function ReviewSkillBlocks({ materials, acts, selectedIds, busy, onToggle, onPropose, confirmed = false, readOnly = false, onSubmit, onOpenResource, progress, skillAction, skillFooter, currentSkillNames = [], proposeDisabled = false, alternatives, onPick, generatingSkill, generating = false }: { readOnly?: boolean; proposeDisabled?: boolean; generating?: boolean; generatingSkill?: string | null; alternatives?: Record<string, { proposalId: string; task: Act }[]>; onPick?: (skill: string, proposalId: string) => void; materials: ReviewMaterials; acts: Act[]; selectedIds: string[]; busy: boolean; onToggle?: (id: string) => void; onPropose?: (skill: string) => void; confirmed?: boolean; onSubmit?: (skill: string) => void; onOpenResource?: (skill: string, resourceId: string) => void; progress?: PlanRecord['progress']; skillAction?: (skill: string) => ReactNode; skillFooter?: (skill: string) => ReactNode; currentSkillNames?: string[] }) {
  const skills = materials.recommendations?.skills || [];
  const names = (materials.skillOrder || skills.map(s => s.name)).filter(name => materials.choices[name]?.enabled !== false);
  return <div className="review-skill-blocks">{names.map((name, index) => {
    const skill = skills.find(s => s.name === name); if (!skill) return null;
    const choice = materials.choices[name];
    const rows = [...skill.courses.filter(r => r.id === choice?.course || choice?.courses?.includes(r.id)), ...skill.books.filter(r => choice?.books.includes(r.id))];
    const outcomes = materials.skillDetails?.find(s => s.name === name)?.competencySummary || [];
    const tasks = acts.filter(a => a.skill === name && !a.res);
    const latest = alternatives?.[name]?.filter(item => !tasks.some(task => task.id === item.task.id)).slice(-1) || [];
    return <details open className={`card review-skill-block${currentSkillNames.includes(name) ? ' is-current-week' : ''}`} key={name}>
      <summary><span className="review-skill-number">{index + 1}</span><h2>{name}</h2>{materials.durationEstimates?.[name]?.weeks != null && <span className="tag">{durationLabel(materials.durationEstimates[name])}</span>}{skillAction?.(name)}<span className="review-skill-toggle-more">펼치기</span><span className="review-skill-toggle-less">접기</span></summary>
      <div className="review-combined-learning"><div className="review-resource-rows">
        {rows.length ? rows.map(resource => {
          const kind = skill.books.includes(resource) ? '도서' : '강좌';
          const activity = acts.find(a => a.skill === name && a.res === resource.id);
          return <ReviewResourceCard key={resource.id} resource={resource} kind={kind} activity={activity} anchor={confirmed}
            progress={progress} onOpenResource={confirmed && onOpenResource && !busy ? () => onOpenResource(name, resource.id) : undefined} />;
        }) : <p className="small muted">선택한 외부 자료가 없어요.</p>}
      </div><div className="review-outcomes review-combined-outcomes"><h3>다음 활동을 얻을 수 있는 역량</h3>
        {outcomes.length ? <ul>{outcomes.map((line, i) => <li key={i}>{line}</li>)}</ul> : generating ? <Skeleton kind="lines" /> : <p className="small muted">선택한 자료를 함께 학습했을 때의 역량 요약이 아직 없어요.</p>}
      </div></div>
      <div className="review-tasks">
        <div><h3>산출물</h3>{tasks.length ? tasks.map(act => <label className="review-task" key={act.id}>{progress && <Stt done={progress[act.id]?.status === 'done'} />}
          {!confirmed && <input type="checkbox" checked={selectedIds.includes(act.id)} disabled={busy} onChange={() => onToggle?.(act.id)} />}
          <ReviewTaskCopy task={act} memo={progress?.[act.id]?.memo} />
        </label>) : generating || generatingSkill === name ? <Skeleton kind="cards" count={1} /> : <p className="small muted">산출물을 제안받으면 이 스킬의 과제가 표시돼요.</p>}</div>
        {!readOnly && <div className="review-submit"><button type="button" className="btn line" aria-busy={generatingSkill === name} disabled={busy || (!confirmed && proposeDisabled) || (confirmed && (!tasks.length || !onSubmit))} onClick={() => confirmed ? onSubmit?.(name) : onPropose?.(name)}>{generatingSkill === name ? <><span className="review-proposal-spinner" aria-hidden="true" /><span role="status">제안 생성 중…</span></> : confirmed ? '과제물 제출' : tasks.length ? '과제 다시 제안받기' : '과제 제안받기'}</button></div>}
      </div>
      {!confirmed && latest.length > 0 && <div className="review-task-alternatives" aria-label={`${name} 산출물 선택`}>
        <h3>새로운 제안</h3>
        {latest.map(({ proposalId, task }) => <label className="review-task-choice" key={task.id}>
          <input type="checkbox" checked={selectedIds.includes(task.id)} disabled={busy} onChange={() => selectedIds.includes(task.id) ? onToggle?.(task.id) : onPick?.(name, proposalId)} />
          <span><span className="review-task-title"><b>{task.title}</b><span className="small muted">예상 {hrs(task.hours)} · 자료 학습 기간에서 제외</span></span><TaskDescription text={task.how} /></span>
        </label>)}
      </div>}
      {skillFooter?.(name)}
    </details>;
  })}</div>;
}
