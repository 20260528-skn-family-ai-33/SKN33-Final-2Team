/* 부서장이 보는 직원 로드맵 본문(#96) — 직원의 '내 로드맵'(roadmap/RoadmapPages RoadView)과 같은 구성을 읽기 전용으로 보여 준다.
   실행 기록 열기·과제물 제출·진행 상태 바꾸기는 두지 않는다. 메모·첨부 등 공개 범위 밖 값은 서버가 보내지 않는다(services/plans.record for_mgr) */
import type { PlanRecord } from '@/api/types/plan';
import { ReviewSkillBlocks, type ReviewMaterials } from '@/features/draft/review/ReviewSkillBlocks';
import { weekNow } from '@/features/home/ganttCalc';
import { RoadmapActivityList, RoadmapResources } from '@/features/roadmap/RoadmapLearning';
import { groupLearningActivities } from '@/features/roadmap/roadmapLearningData';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { st } from '@/shared/lib/plan';
import { useCatalog } from '@/shared/state/catalog';
import { Stats } from '@/shared/ui/parts';

export function MemberRoadView({ R }: { R: PlanRecord }) {
  const resources = useCatalog((state) => state.res);
  const pl = R.plan;
  const learning = pl.def.learningReport as ReviewMaterials | undefined;
  const week = weekNow(R);
  // 직원 화면처럼 이번 주에 할 스킬을 표시한다(진행 중인 로드맵만)
  const current =
    R.status === 'active'
      ? groupLearningActivities(pl, resources)
          .filter((group) => group.activities.some((a) => a.wFrom <= week && week <= a.wTo) && group.activities.some((a) => st(R.progress, a.id) !== 'done'))
          .map((group) => group.name)
      : [];
  return (
    <>
      <Stats pl={pl} periodLabel={learning ? '자료 학습 예상 기간' : '기간'} />
      <RoadmapResources R={R} owned={[]} />
      {learning ? (
        <ReviewSkillBlocks
          confirmed
          readOnly
          busy
          materials={learning}
          acts={pl.acts.filter((act): act is typeof act & { skill: string; how: string; hours: number } => !!act.skill).map((act) => ({ ...act, how: act.how || '' }))}
          selectedIds={pl.acts.map((act) => act.id)}
          currentSkillNames={current}
        />
      ) : (
        <SkillMap pl={pl} />
      )}
      <div className="sec">
        <RoadmapActivityList R={R} readOnly />
      </div>
    </>
  );
}
