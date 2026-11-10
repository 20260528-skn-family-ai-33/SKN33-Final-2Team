import type { PlanContent } from '@/api/types/plan';
import { hrs } from '@/shared/lib/format';

export function MaterialBasis({ plan }: { plan?: Pick<PlanContent, 'materialHours' | 'taskHours' | 'otherMaterialHours' | 'totalHUnknown'> }) {
  return <p className="small muted material-basis">
    강좌 시간 기준{plan?.materialHours != null && <> · {hrs(plan.materialHours)}</>}
  </p>;
}