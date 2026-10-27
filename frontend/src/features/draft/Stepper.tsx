/* 새 로드맵 작성 단계 표시 (5차 GP.stepper) — 앞 단계를 다 마치지 않은 단계는 잠근다 */
import { useGo } from '@/shared/hooks/useGo';
import { useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { blockedTo, STEPS, stepDone, type StepKey } from './model';

export function Stepper({ cur }: { cur: StepKey }) {
  const go = useGo();
  const s = useWs();
  return (
    <nav className="stepper" aria-label="새 로드맵 작성 단계">
      <ol>
        {STEPS.map(([k, l, r], i) => {
          const st = k === cur ? 'cur' : stepDone(s, k) ? 'done' : !blockedTo(s, k) ? 'open' : 'lock';
          return (
            <li className={st} key={k}>
              <button disabled={st === 'lock'} aria-current={k === cur ? 'step' : undefined} onClick={() => go(r)}>
                <span className="sn">{st === 'done' ? <Icon name="check" /> : i + 1}</span>
                <span className="sl">{l}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
