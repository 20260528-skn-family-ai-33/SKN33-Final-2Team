import type { MaterialResource } from '@/api/types/draft';

export function UnverifiedTargets({ topics }: { topics?: MaterialResource['unverifiedTargetTopics'] }) {
  return topics?.length ? <p className="small muted material-reason">확인되지 않은 범위: {topics.join(', ')}</p> : null;
}

export function OutdatedRecommendations({ outdated, courseId }: { outdated?: boolean; courseId?: string }) {
  if (!outdated) return null;
  return <p className="small muted material-reason" role="status">이전 기준으로 추천된 자료예요. {courseId ? '코스 카드의 ‘다르게 다시 만들기’를 이용하면 새 자료 추천에 현재 기준이 적용돼요.' : '‘이전: 로드맵·자료 선택’으로 돌아가 ‘다르게 다시 만들기’를 이용하면 새 자료 추천에 현재 기준이 적용돼요.'}</p>;
}
