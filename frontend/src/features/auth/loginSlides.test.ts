import { describe, expect, it } from 'vitest';
import { LOGIN_SLIDES, slideSrc } from './loginSlides';

const SKIN_IDS = Object.keys(import.meta.glob('../../skins/*/index.ts')).map((p) => p.split('/').at(-2) as string);

describe('로그인 화면에 넘겨 보여 주는 화면 그림', () => {
  it('그림마다 이름이 다르고 읽어 줄 화면 이름과 설명 문구가 있다', () => {
    expect(new Set(LOGIN_SLIDES.map((s) => s.id)).size).toBe(LOGIN_SLIDES.length);
    expect(LOGIN_SLIDES.filter((s) => !s.name || !s.text)).toEqual([]);
  });

  it('모든 테마에 모든 장이 있다', () => {
    // 테마를 추가하거나 장을 바꾸고 그림을 다시 찍지 않으면 다른 테마 그림이 대신 보인다
    expect(SKIN_IDS.length).toBeGreaterThan(0);
    const missing = SKIN_IDS.flatMap((skin) =>
      LOGIN_SLIDES.filter((s) => !slideSrc(skin, s.id).includes(`/${skin}/`)).map((s) => `${skin}/${s.id}`));
    expect(missing).toEqual([]);
  });

  it('모르는 테마는 기본 테마 그림으로 그린다', () => {
    expect(slideSrc('없는테마', LOGIN_SLIDES[0].id)).toBe(slideSrc('tm612', LOGIN_SLIDES[0].id));
    expect(slideSrc('tm612', '없는그림')).toBe('');
  });
});
