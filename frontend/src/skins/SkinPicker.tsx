/* 화면 테마 고르기 상자(비교 브랜치 전용) — 왼쪽 아래에 늘 떠 있고, 고르면 바로 바뀐다.
   네 칸을 따로 고른다: 템플릿 묶음(education 태그 · 그 외) → 테마 → 메뉴 위치(상단 · 좌측) → 본문 폭(넓게 · 이전 폭).
   제목을 누르면 접고 편다. 좁은 화면(휴대폰)에서는 본문을 가리지 않게 접힌 채로 시작한다 */
import { useState } from 'react';
import { currentChoice, GROUPS, setChoice, type SkinGroup, SKINS } from '@/skins';
import type { Choice } from './pick';
import './picker.css';

const groupOf = (id: string): SkinGroup => SKINS.find((s) => s.id === id)?.group ?? 'education';

export function SkinPicker() {
  const [choice, setPicked] = useState(currentChoice);
  const group = groupOf(choice.skin);
  const [open, setOpen] = useState(() => !window.matchMedia?.('(max-width: 600px)').matches);
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
          {/* 묶음을 바꾸면 그 묶음의 첫 테마를 바로 보여 준다(테마가 없는 묶음은 고를 수 없게 막음) */}
          <select
            aria-label="템플릿 묶음"
            value={group}
            onChange={(e) => {
              const first = SKINS.find((s) => s.group === e.target.value);
              if (first) change({ skin: first.id });
            }}
          >
            {GROUPS.map((g) => {
              const n = SKINS.filter((s) => s.group === g.id).length;
              return (
                <option key={g.id} value={g.id} disabled={!n}>
                  {g.name} ({n ? `${n}개` : '준비 중'})
                </option>
              );
            })}
          </select>
          <select aria-label="테마" value={choice.skin} onChange={(e) => change({ skin: e.target.value })}>
            {SKINS.filter((s) => s.group === group).map((s) => (
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
