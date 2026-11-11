/* 화면 테마 고르기 상자(비교 브랜치 전용) — 왼쪽 아래에 늘 떠 있고, 고르면 바로 바뀐다.
   세 칸을 따로 고른다: 테마 → 메뉴 위치(상단 · 좌측) → 본문 폭(넓게 · 이전 폭).
   본문을 가리지 않게 화면 폭과 상관없이 접힌 채로 시작하고, 제목을 누르면 접고 편다 */
import { useState } from 'react';
import { currentChoice, setChoice, SKINS } from '@/skins';
import type { Choice } from './pick';
import './picker.css';

export function SkinPicker() {
  const [choice, setPicked] = useState(currentChoice);
  const [open, setOpen] = useState(false);
  const change = (next: Partial<Choice>) => {
    const c = { ...choice, ...next };
    setChoice(c);
    setPicked(c);
  };

  return (
    <div className={'skin-pick' + (open ? ' open' : '')}>
      <button type="button" className="skin-pick-t" aria-expanded={open} onClick={() => setOpen(!open)}>
        화면 테마
      </button>
      {open && (
        <div className="skin-pick-g">
          <select aria-label="테마" value={choice.skin} onChange={(e) => change({ skin: e.target.value })}>
            {SKINS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <select aria-label="메뉴 위치" value={choice.side ? 'side' : 'top'} onChange={(e) => change({ side: e.target.value === 'side' })}>
            <option value="top">상단 메뉴</option>
            <option value="side">좌측 메뉴</option>
          </select>
          <select
            aria-label="본문 폭"
            value={choice.narrow ? 'narrow' : 'wide'}
            onChange={(e) => change({ narrow: e.target.value === 'narrow' })}
          >
            <option value="wide">넓은 본문 폭</option>
            <option value="narrow">이전 본문 폭</option>
          </select>
        </div>
      )}
    </div>
  );
}
