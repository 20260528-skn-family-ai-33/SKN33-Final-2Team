import type { PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { actMeta, range, st } from '@/shared/lib/plan';
import { activityTime } from '@/shared/lib/resourceTime';
import { useCatalog } from '@/shared/state/catalog';
import { useMe } from '@/shared/state/session';
import { ActThumb, Stt } from '@/shared/ui/parts';
import { ActRow } from './parts';
import { activityAnchor, groupLearningActivities, matchingCertificates } from './roadmapLearningData';
import './roadmapLearning.css';
import { weekNow } from '@/features/home/ganttCalc';
import { ResourceImage } from '@/shared/ui/ResourceImage';

/** owned: 이미 가진 자격증(추천에서 뺀다). 기본은 로그인한 본인 것 · 부서장이 직원 로드맵을 볼 때는 직원 보유 자격증을 받지 않으므로 [] */
export function RoadmapResources({ R, owned }: { R: PlanRecord; owned?: string[] }) {
  const resources = useCatalog(state => state.res);
  const certificates = useCatalog(state => state.certById);
  const me = useMe();
  const go = useGo();
  const groups = groupLearningActivities(R.plan, resources);
  const certs = matchingCertificates(Object.values(certificates), groups.map(group => group.name), owned ?? me?.certs);
  const jump = (id: string) => {
    const element = document.getElementById(activityAnchor(id));
    let parent = element?.parentElement;
    while (parent) { if (parent instanceof HTMLDetailsElement) parent.open = true; parent = parent.parentElement; }
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    element?.focus({ preventScroll: true });
  };
  return <details className="card roadmap-resource-index-box"><summary><span>도서 · 강좌 · 추천 자격증</span><span className="resource-index-more">더보기</span><span className="resource-index-less">접기</span></summary><section className="roadmap-resource-index" aria-label="로드맵 학습 자료와 추천 자격증">
    {(['도서', '강좌'] as const).map(kind => {
      const entries = R.plan.acts.filter(activity => {
        const resource = activity.res ? resources[activity.res] : undefined;
        return kind === '도서' ? resource?.type === 'book' || resource?.kind === '도서' : resource?.type === 'course' || resource?.kind === '강좌';
      });
      return <section className="roadmap-resource-category" key={kind}>
        <h2>{kind}<span className="small muted">{entries.length}개</span></h2>
        {entries.length ? <ul>{entries.map(activity => {
          const resource = resources[activity.res!];
          return <li key={activity.id}><button type="button" onClick={() => jump(activity.id)} aria-label={`${resource.title} 학습 활동으로 이동`}>
            <ResourceImage image={resource.image} type={kind === '도서' ? 'book' : 'course'} />
            <span><b>{resource.title}</b><small>{activity.skill || groups.find(group => group.activities.includes(activity))?.name}</small></span>
          </button></li>;
        })}</ul> : <p className="small muted">선택한 {kind}가 없어요.</p>}
      </section>;
    })}
    <section className="roadmap-resource-category">
      <h2>추천 자격증<span className="small muted">{certs.length}개</span></h2>
      {certs.length ? <ul>{certs.map(cert => <li key={cert.res}><button type="button" onClick={() => go(paths.resource(cert.res))}>
        <ResourceImage image={cert.image} type="cert" />
        <span><b>{cert.name}</b><small>{cert.issuer}</small></span>
      </button></li>)}</ul> : <p className="small muted">선택한 스킬에 맞는 추천 자격증이 없어요.</p>}
    </section>
  </section></details>;
}

/** readOnly: 부서장이 보는 직원 로드맵(#96) — 진행 중이어도 실행 기록을 열지 않고 상태만 보여 준다 */
export function RoadmapActivityList({ R, readOnly = false }: { R: PlanRecord; readOnly?: boolean }) {
  const week = weekNow(R);
  const due = (activity: PlanRecord['plan']['acts'][number]) => R.status === 'active' && activity.wFrom <= week && week <= activity.wTo && st(R.progress, activity.id) !== 'done';
  const resources = useCatalog(state => state.res);
  const groups = groupLearningActivities(R.plan, resources);
  return <div className="roadmap-learning-groups">{groups.map((group, index) => <details open className={`card roadmap-learning-group${R.status === 'active' && group.activities.some(a => a.wFrom <= week && week <= a.wTo) && group.activities.some(a => st(R.progress, a.id) !== 'done') ? ' is-current-week' : ''}`} key={group.name}>
    <summary><span className="no">{index + 1}</span><h2>{group.name}</h2><span className="small muted">{range(group.activities)} · {group.activities.filter(activity => st(R.progress, activity.id) === 'done').length}/{group.activities.length} 완료</span><span className="learning-toggle-more">펼치기</span><span className="learning-toggle-less">접기</span></summary>
    {[{ title: '자료 학습', acts: group.materials }, { title: '산출물', acts: group.tasks }].filter(category => category.acts.length).map(category => <div className="roadmap-learning-category" key={category.title}>
      <h3>{category.title}</h3><ul className="acts">{category.acts.map(activity => <li id={activityAnchor(activity.id)} tabIndex={-1} className={`roadmap-learning-anchor${due(activity) ? ' is-current-week' : ''}`} key={activity.id}>
        {R.status === 'active' && !readOnly ? <ul className="acts"><ActRow a={activity} R={R} /></ul> : <div className="roadmap-learning-readonly">
          <Stt done={st(R.progress, activity.id) === 'done'} /><ActThumb a={activity} /><span className="tx">{activity.title}<small>{actMeta(activity)} · {activity.wFrom === activity.wTo ? `${activity.wFrom}주차` : `${activity.wFrom}~${activity.wTo}주차`}</small>{R.progress[activity.id]?.memo && <small>메모 · {R.progress[activity.id].memo}</small>}</span><span className="small muted" title={activityTime(activity).title}>{activityTime(activity).text}</span>
        </div>}
      </li>)}</ul>
    </div>)}
  </details>)}</div>;
}
