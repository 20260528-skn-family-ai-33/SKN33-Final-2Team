import type { PlanContent } from '@/api/types/plan';
import { hrs } from '@/shared/lib/format';

export function MaterialBasis({ plan }: { plan?: Pick<PlanContent, 'materialHours' | 'taskHours' | 'totalHUnknown'> }) {
  return <p className="small muted material-basis">
    산출물 과제 시간 제외 · 같은 자료는 한 번만 합산 · 도서 1권 = 1주 배정(실제 독서시간 아님)
    {plan?.materialHours != null && <> · 자료 배정 {hrs(plan.materialHours)}{plan.totalHUnknown ? ' (시간 미확인 강좌는 각 1주 가정)' : ''}</>}
    {plan?.taskHours != null && <> · 과제 별도 {hrs(plan.taskHours)}</>}
  </p>;
}
