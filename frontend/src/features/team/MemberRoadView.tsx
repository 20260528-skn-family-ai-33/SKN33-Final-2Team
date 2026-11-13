/* 부서장이 보는 직원 로드맵 본문(#96) — 직원의 '내 로드맵'(roadmap/RoadmapPages RoadView)과 같은 구성을 읽기 전용으로 보여 준다.
   실행 기록 열기·과제물 제출·진행 상태 바꾸기는 두지 않는다. 메모·첨부 등 공개 범위 밖 값은 서버가 보내지 않는다(services/plans.record for_mgr) */
import type { ReactNode } from 'react';
import type { PlanRecord } from '@/api/types/plan';
import { ReviewSkillBlocks, type ReviewMaterials } from '@/features/draft/review/ReviewSkillBlocks';
import { RoadmapActivityList, RoadmapResources } from '@/features/roadmap/RoadmapLearning';
import { commentSkillNames, currentWeekSkillNames } from '@/features/roadmap/roadmapLearningData';
import { SkillMap } from '@/features/skillmap/SkillMap';
import { useCatalog } from '@/shared/state/catalog';
import { useClockRefresh } from '@/shared/state/demoClock';
import { Stats } from '@/shared/ui/parts';
import { PlanSummary } from '@/features/roadmap/PlanSummary';

export function MemberRoadView({ R, skillAction, skillFooter }: { R: PlanRecord; skillAction?: (skill: string) => ReactNode; skillFooter?: (skill: string) => ReactNode }) {
  const resources = useCatalog((state) => state.res);
  const pl = R.plan;
  const learning = pl.def.learningReport as ReviewMaterials | undefined;
  useClockRefresh();
  // 직원 화면처럼 이번 주 스킬을 표시한다(진행 중인 로드맵만 · 완료 여부와 상관없이)
  const current = currentWeekSkillNames(R, resources);
  return (
    <>
      {learning ? <PlanSummary R={R} /> : <Stats pl={pl} periodLabel="기간" />}
      <RoadmapResources R={R} owned={[]} />
      {learning ? (
        <ReviewSkillBlocks
          confirmed
          readOnly
          busy
          materials={learning}
          acts={pl.acts.filter((act): act is typeof act & { skill: string; how: string; hours: number } => !!act.skill).map((act) => ({ ...act, how: act.how || '' }))}
          selectedIds={pl.acts.map((act) => act.id)}
          progress={R.progress}
          currentSkillNames={current}
          skillAction={skillAction}
          skillFooter={skillFooter}
        />
      ) : (
        <>
          <SkillMap pl={pl} owned={[]} />
          {commentSkillNames(pl).map(skill => <div key={skill}>{skillFooter?.(skill)}</div>)}
        </>
      )}
      <RoadmapActivityList R={R} readOnly skipSkillCardDuplicates />
    </>
  );
}
