/* 세부 사항 입력 폼 (5차 P.detailsForm): 학습 선호 5가지 + 기타 고려 사항. 모두 선택 사항이고, 비워 둔 칸은 흐린 회색 기본값.
   같은 폼을 점검 결과 수정 화면에서도 쓴다(경로만 다름) */
import { D } from '@/shared/constants/data';
import { fieldLabel } from '@/shared/lib/prefs';
import { setAt, useAt } from '@/shared/state/bind';
import { useCatalog } from '@/shared/state/catalog';
import { BNum, BText } from '@/shared/ui/bound';
import type { Prefs } from '@/api/types/draft';
import { CertPicker } from './CertPicker';

function Field({ k, wide, help, children }: { k: string; wide?: boolean; help: string; children: React.ReactNode }) {
  return (
    <div className={`field${wide ? ' wide' : ''}`}>
      <label>{fieldLabel(k)}</label>
      {children}
      <small className="muted df-help">{help}</small>
    </div>
  );
}

function Sel({ path, k, opts }: { path: string; k: string; opts: [string, string][] }) {
  const v = useAt<string>(`${path}.${k}`) || '';
  return (
    <select className={`input df-sel ${v ? '' : 'empty'}`} aria-label={fieldLabel(k)} value={String(v)} onChange={(e) => setAt(`${path}.${k}`, e.target.value)}>
      <option value="">알아서</option>
      {opts.map(([x, l]) => (
        <option value={x} key={x}>
          {l}
        </option>
      ))}
    </select>
  );
}

const Num = ({ path, k, unit, min, max, step }: { path: string; k: keyof Prefs; unit: string; min: number; max?: number; step: number }) => (
  <div className="unit">
    <BNum path={`${path}.${k}`} min={min} max={max} step={step} placeholder="알아서" ariaLabel={fieldLabel(k)} />
    <span>{unit}</span>
  </div>
);

export function DetailsForm({ path }: { path: string }) {
  const n = useCatalog((s) => s.certGroups.reduce((a, g) => a + g.certs.length, 0));
  return (
    <div className="dform">
      <Field k="format" help="비워 두면 목표와 자료에 맞게 정해요">
        <Sel path={path} k="format" opts={D.formatOpts} />
      </Field>
      <Field k="cert" help={`분야를 고른 뒤 자격을 골라 주세요(${n}종). 고르지 않으면 자격 준비는 넣지 않아요`}>
        <CertPicker path={`${path}.cert`} />
      </Field>
      <Field k="hours" help="비워 두면 로드맵 계획 에이전트가 목표와 기간에 맞게 정해요">
        <Num path={path} k="hours" unit="시간 / 주" min={0.5} max={40} step={0.5} />
      </Field>
      <Field k="weeks" help="비워 두면 기간을 정하지 않아요">
        <Num path={path} k="weeks" unit="주 안에" min={1} max={52} step={1} />
      </Field>
      <Field k="budget" help="0을 넣으면 무료 자료만 써요. 비워 두면 알아서 골라요">
        <Num path={path} k="budget" unit="원" min={0} step={10000} />
      </Field>
      <Field k="etc" wide help="로드맵을 만들 때 고려할 상황을 자유롭게 적어 주세요. 로드맵 계획 에이전트에게 그대로 전달해요">
        <BText
          path={`${path}.etc`}
          className="textarea sm"
          maxLength={500}
          ariaLabel={fieldLabel('etc')}
          placeholder="예: 다음 달 둘째 주는 출장이 많아요. 영상 강의는 사내망에서 열리지 않아요."
        />
      </Field>
    </div>
  );
}
