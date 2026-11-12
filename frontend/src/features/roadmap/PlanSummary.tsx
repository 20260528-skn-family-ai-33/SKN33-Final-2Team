/* 확정한 로드맵의 요약(내 로드맵 · 부서장 보기). 작성 7단계의 요약과 같은 칸에 진행 상황을 더한다 */
import type { PlanRecord } from '@/api/types/plan';
import '@/features/draft/review/reviewStep.css';
import { addDays, md, planStart, planWeeks, weekNow } from '@/features/home/ganttCalc';
import { hrs } from '@/shared/lib/format';
import { count } from '@/shared/lib/plan';
import { useClockRefresh } from '@/shared/state/demoClock';

export function PlanSummary({ R }: { R: PlanRecord }) {
  useClockRefresh();
  const pl = R.plan;
  const weeks = planWeeks(pl);
  const start = planStart(R);
  const week = weekNow(R);
  const progress = count(pl, R.progress);
  const cost = pl.cost === 0 ? (pl.costUnknown ? '가격 확인 필요' : '무료') : `${pl.cost.toLocaleString('ko-KR')}원${pl.costUnknown ? '+' : ''}`;
  const now = R.status !== 'active' ? '' : week < 1 ? ' · 시작 전' : week <= weeks ? ` · 지금 ${week}주차` : ' · 기간 지남';
  return (
    <section className="card rv-summary" aria-label="로드맵 요약">
      <dl className="rv-stats is-5">
        <div>
          <dt>진행</dt>
          <dd><b>{progress.done} / {progress.t}</b><span>완료한 활동</span></dd>
        </div>
        <div>
          <dt>기간</dt>
          <dd><b>{weeks}주</b><span>{md(start)} ~ {md(addDays(start, weeks * 7 - 1))}{now}</span></dd>
        </div>
        <div>
          <dt>주당 학습</dt>
          <dd><b>{pl.hours}시간</b><span>{' '}</span></dd>
        </div>
        <div>
          <dt>총 학습 시간</dt>
          <dd><b>약 {hrs(pl.totalH)}</b>
            <span>{pl.materialHours != null ? `강좌 ${hrs(pl.materialHours)} + 과제 ${hrs(pl.taskHours ?? 0)}` : ' '}{pl.totalHUnknown ? ' · 시간 미확인 자료 있음' : ''}</span></dd>
        </div>
        <div>
          <dt>예상 비용</dt>
          <dd><b>{cost}</b><span>{pl.costUnknown ? '일부 자료는 가격 확인 필요' : ' '}</span></dd>
        </div>
      </dl>
    </section>
  );
}
