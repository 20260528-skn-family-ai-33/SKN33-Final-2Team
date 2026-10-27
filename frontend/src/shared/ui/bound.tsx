/* 작업 공간 상태에 연결된 입력 칸 (5차 data-bind · data-bind-arr) — 경로만 주면 값 읽기·쓰기를 한다 */
import type { ReactNode } from 'react';
import { setAt, toggleIn, useAt } from '@/shared/state/bind';

type TextProps = { path: string; className?: string; maxLength?: number; placeholder?: string; ariaLabel?: string; rows?: number; id?: string };

export function BText({ path, className = 'textarea', ...p }: TextProps) {
  const v = useAt<string>(path) ?? '';
  return (
    <textarea
      className={className}
      id={p.id}
      maxLength={p.maxLength}
      placeholder={p.placeholder}
      aria-label={p.ariaLabel}
      rows={p.rows}
      value={String(v)}
      onChange={(e) => setAt(path, e.target.value, 'input')}
    />
  );
}

export function BInput({ path, className = 'input', ...p }: TextProps) {
  const v = useAt<string>(path) ?? '';
  return (
    <input
      className={className}
      id={p.id}
      maxLength={p.maxLength}
      placeholder={p.placeholder}
      aria-label={p.ariaLabel}
      value={String(v)}
      onChange={(e) => setAt(path, e.target.value, 'input')}
    />
  );
}

/** 숫자 칸: 비우면 '' 를, 아니면 숫자를 저장한다(5차와 같음) */
export function BNum({ path, min, max, step, placeholder, ariaLabel }: { path: string; min?: number; max?: number; step?: number; placeholder?: string; ariaLabel?: string }) {
  const v = useAt<number | string>(path);
  return (
    <input
      className="input num"
      type="number"
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      aria-label={ariaLabel}
      value={v === undefined || v === null ? '' : String(v)}
      onChange={(e) => setAt(path, e.target.value === '' ? '' : Number(e.target.value), 'input')}
    />
  );
}

export function BRadio({ path, value, name, children, onPicked }: { path: string; value: string | number; name: string; children?: ReactNode; onPicked?: () => void }) {
  const v = useAt<string | number>(path);
  return (
    <>
      <input
        type="radio"
        name={name}
        value={String(value)}
        checked={String(v ?? '') === String(value)}
        onChange={() => {
          setAt(path, typeof value === 'number' ? value : value);
          onPicked?.();
        }}
      />
      {children}
    </>
  );
}

export function BCheckArr({ path, value }: { path: string; value: string }) {
  const arr = useAt<string[]>(path) || [];
  return <input type="checkbox" value={value} checked={arr.includes(value)} onChange={(e) => toggleIn(path, value, e.target.checked)} />;
}
