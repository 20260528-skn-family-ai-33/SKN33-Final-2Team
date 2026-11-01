/* 화면 테마 고르기 상자(비교 브랜치 전용) — 왼쪽 아래에 늘 떠 있고, 고르면 바로 바뀐다 */
import { useState } from 'react';
import { currentSkin, setSkin, SKINS } from '@/skins';
import { BASE, SIDE } from './pick';
import './picker.css';

export function SkinPicker() {
  const [skin, setPicked] = useState(currentSkin);
  return (
    <label className="skin-pick">
      <span>화면 테마</span>
      <select
        value={skin}
        onChange={(e) => {
          setSkin(e.target.value);
          setPicked(e.target.value);
        }}
      >
        <option value={BASE}>원래 화면</option>
        {SKINS.flatMap((s) => [
          <option key={s.id} value={s.id}>
            {s.name} · 상단 메뉴
          </option>,
          <option key={s.id + SIDE} value={s.id + SIDE}>
            {s.name} · 좌측 메뉴
          </option>,
        ])}
      </select>
    </label>
  );
}
