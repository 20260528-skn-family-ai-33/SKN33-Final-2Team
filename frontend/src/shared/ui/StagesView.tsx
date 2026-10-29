/* 단계별 활동 목록 (5차 P.stagesView) — 검토·확정 · 내 로드맵 · 부서장 화면이 같이 쓴다 */
import type { PlanContent, Progress } from '@/api/types/plan';
import { D } from '@/shared/constants/data';
import { activityTime } from '@/shared/lib/resourceTime';
import { actMeta, range, st, stageActs } from '@/shared/lib/plan';
import { useCatalog } from '@/shared/state/catalog';
import { ActThumb, Stt } from './parts';

export function StagesView({ pl, progress, status, memo }: { pl: PlanContent; progress?: Record<string, Progress>; status?: boolean; memo?: boolean }) {
  useCatalog((s) => s.res);
  return (
    <>
      {D.stages
        .filter((s) => s.n >= pl.start)
        .map((s) => {
          const acts = stageActs(pl, s.n);
          if (!acts.length) return null;
          return (
            <div className="stage" key={s.n}>
              <div className="stage-h">
                <span className="no">{s.n}</span>
                <b>{s.name}</b>
                <span className="end">
                  {range(acts)}
                  {status ? ` · ${acts.filter((a) => st(progress, a.id) === 'done').length}/${acts.length} 완료` : ''}
                </span>
              </div>
              <ul className="acts">
                {acts.map((a) => {
                  const m = memo && progress?.[a.id]?.memo;
                  const timing = activityTime(a);
                  return (
                    <li key={a.id}>
                      {status ? <Stt done={st(progress, a.id) === 'done'} /> : null}
                      <ActThumb a={a} />
                      <div className="tx">
                        {a.title}
                        <small>{actMeta(a)}</small>
                        {m ? <small className="memo">메모 · {m}</small> : null}
                      </div>
                      <span className="h">
                        <span title={timing.title}>{timing.text}</span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
    </>
  );
}
