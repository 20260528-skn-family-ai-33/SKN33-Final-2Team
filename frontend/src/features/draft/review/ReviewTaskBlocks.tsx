/* 7단계 스킬 블록(#224): 6단계에서 고른 자료는 요약으로 줄이고, 이 단계에서 정하는 산출물 과제를 크게 보여 준다.
   확정 뒤 화면(내 로드맵·부서장 보기)은 ReviewSkillBlocks 를 그대로 쓴다 */
import { hrs } from '@/shared/lib/format';
import { activityTime } from '@/shared/lib/resourceTime';
import { courseDifficulty } from '@/shared/lib/courseDifficulty';
import { Icon } from '@/shared/ui/Icon';
import { ResourceImage } from '@/shared/ui/ResourceImage';
import { Skeleton } from '@/shared/ui/Skeleton';
import { Wait } from '@/shared/ui/Wait';
import { TaskDescription } from '@/shared/ui/TaskDescription';
import { durationLabel } from '../result/skillOrder';
import type { ReviewMaterials, ReviewResource } from './ReviewSkillBlocks';
import type { ReviewActivity } from './reviewPlan';

type Task = Pick<ReviewActivity, 'id' | 'title' | 'skill' | 'how' | 'hours'>;
type Act = Task & { res?: string | null; hoursEstimated?: boolean; hoursBasis?: string; hoursAllocation?: 'book-week'; catalogHours?: number | null };
export interface TaskOption { proposalId: string; task: Task }

const priceOf = (resource: ReviewResource): string => resource.cost == null ? '가격 확인 필요' : resource.cost === 0 ? '무료' : `${resource.cost.toLocaleString('ko-KR')}원`;

function MaterialRow({ resource, kind, activity }: { resource: ReviewResource; kind: 'course' | 'book'; activity?: Act }) {
  const meta = [
    resource.provider || '출처 미확인',
    priceOf(resource),
    kind === 'course' && resource.difficulty ? courseDifficulty(resource) : null,
    kind === 'book' ? '일정에 넣지 않아요' : activity ? activityTime({ ...activity, res: activity.res ?? null }).text : null,
  ].filter(Boolean).join(' · ');
  return (
    <div className="rv-mini">
      <ResourceImage className="rv-thumb" image={resource.image} type={kind} />
      <span className="rv-mini-tx">
        <b><span className="tag">{kind === 'course' ? '강좌' : '도서'}</span>{resource.title}</b>
        <small>{meta}</small>
      </span>
      {resource.url ? <a className="rv-link" href={resource.url} target="_blank" rel="noreferrer" aria-label={`${resource.title} 원본 보기 (새 창)`}>원본 보기 ↗</a> : null}
    </div>
  );
}

export function ReviewTaskBlocks({ materials, acts, options, selectedIds, busy, proposeDisabled = false, generating = false, generatingSkill, onToggle, onPick, onPropose, onChangeMaterials }: {
  materials: ReviewMaterials;
  /** 지금 계획에 들어가 있는 활동(자료 + 스킬별 과제) */
  acts: Act[];
  /** 스킬별로 지금까지 제안받은 과제 전부(다시 제안받을 때마다 늘어난다) */
  options: Record<string, TaskOption[]>;
  selectedIds: string[];
  busy: boolean;
  proposeDisabled?: boolean;
  generating?: boolean;
  generatingSkill?: string | null;
  onToggle: (id: string) => void;
  onPick: (skill: string, proposalId: string) => void;
  onPropose: (skill: string) => void;
  onChangeMaterials: () => void;
}) {
  const skills = materials.recommendations?.skills || [];
  const names = (materials.skillOrder || skills.map(skill => skill.name)).filter(name => materials.choices[name]?.enabled !== false);
  return (
    <div className="rv-skills">
      {names.map((name, index) => {
        const skill = skills.find(row => row.name === name);
        if (!skill) return null;
        const choice = materials.choices[name];
        const courses = skill.courses.filter(row => row.id === choice?.course || choice?.courses?.includes(row.id));
        const books = skill.books.filter(row => choice?.books.includes(row.id));
        const outcomes = materials.skillDetails?.find(row => row.name === name)?.competencySummary || [];
        const estimate = materials.durationEstimates?.[name];
        const applied = acts.filter(act => act.skill === name && !act.res);
        // 계산이 끝난 계획의 과제(시간이 반영된 값)를 우선 쓰고, 나머지는 제안받은 그대로 보여 준다
        const list = (options[name]?.length ? options[name] : applied.map(task => ({ proposalId: '', task })))
          .map(option => ({ ...option, task: applied.find(task => task.id === option.task.id) || option.task }));
        const multi = list.length > 1;
        const chosen = list.find(option => selectedIds.includes(option.task.id));
        const proposing = generatingSkill === name;
        return (
          <article className="rv-skill" key={name}>
            <header>
              <span className="rv-skill-n">{String(index + 1).padStart(2, '0')}</span>
              <h3>{name}</h3>
              {estimate?.weeks != null ? <span className="tag line">{durationLabel(estimate)}</span> : null}
            </header>
            <div className="rv-learn">
              <div>
                <h4>배울 자료</h4>
                {courses.map(resource => <MaterialRow key={resource.id} resource={resource} kind="course" activity={acts.find(act => act.skill === name && act.res === resource.id)} />)}
                {books.map(resource => <MaterialRow key={resource.id} resource={resource} kind="book" />)}
                {!courses.length && !books.length ? <p className="rv-muted">선택한 자료가 없어요.</p> : null}
                <button type="button" className="rv-link" disabled={busy} onClick={onChangeMaterials}>자료 바꾸기</button>
              </div>
              <div>
                <h4>이 스킬을 마치면</h4>
                {outcomes.length ? <ul className="rv-outcomes">{outcomes.map((line, i) => <li key={i}>{line}</li>)}</ul>
                  : generating ? <Skeleton kind="lines" /> : <p className="rv-muted">얻게 될 역량 요약이 아직 없어요.</p>}
              </div>
            </div>
            <div className="rv-tasks">
              <div className="rv-tasks-head">
                <h4>산출물 과제</h4>
                <span>{multi ? '제안받은 과제 중 하나를 골라 주세요' : ''}</span>
                <button type="button" className="btn sm line" aria-busy={proposing} disabled={busy || proposeDisabled} onClick={() => onPropose(name)}>
                  {proposing ? <><span className="sp" aria-hidden="true" /><span role="status"><Wait>제안받는 중…</Wait></span></> : <><Icon name="retry" /> {list.length ? '다른 과제 제안받기' : '과제 제안받기'}</>}
                </button>
              </div>
              {list.length ? (
                <div className={`rv-task-grid${multi ? ' is-multi' : ''}`} role={multi ? 'radiogroup' : undefined} aria-label={multi ? `${name} 산출물 과제` : undefined}>
                  {list.map(({ proposalId, task }, order) => {
                    const on = selectedIds.includes(task.id);
                    return (
                      <label className={`rv-task${on ? ' is-on' : ''}`} key={task.id}>
                        <input type={multi ? 'radio' : 'checkbox'} name={multi ? `rv-task-${index}` : undefined} checked={on} disabled={busy}
                          onChange={() => { if (multi) { if (!on) onPick(name, proposalId); } else onToggle(task.id); }} />
                        <span className="rv-task-tx">
                          <span className="rv-task-kicker">{multi ? `제안 ${order + 1}${on ? ' · 선택됨' : ''}` : '산출물 과제'}</span>
                          <b>{task.title}</b>
                          <TaskDescription text={task.how} />
                        </span>
                        <em>약 {hrs(task.hours)}</em>
                      </label>
                    );
                  })}
                  {proposing ? <Skeleton kind="cards" count={1} /> : null}
                </div>
              ) : generating || proposing ? <Skeleton kind="cards" count={1} />
                : <p className="rv-muted">아직 제안된 과제가 없어요. ‘과제 제안받기’를 눌러 주세요.</p>}
              {list.length && (multi || !chosen) ? (
                <p className="rv-task-foot">
                  {chosen ? <button type="button" className="rv-link" disabled={busy} onClick={() => onToggle(chosen.task.id)}>이 스킬은 과제 없이 진행하기</button>
                    : '이 스킬은 과제 없이 진행해요.'}
                </p>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}
