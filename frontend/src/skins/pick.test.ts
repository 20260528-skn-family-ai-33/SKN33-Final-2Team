import { describe, expect, it } from 'vitest';
import { choiceToRemember, DEFAULT_SKIN, formatChoice, MODE_SKIN, modeOf, parseChoice, pickChoice } from './pick';

const ids = ['tm464', 'tm612'];
const plain = (skin: string) => ({ skin, narrow: false, lowContrast: false });

describe('화면 모드', () => {
  it('라이트는 464 · 다크는 612', () => {
    expect(MODE_SKIN).toEqual({ light: 'tm464', dark: 'tm612' });
    expect(modeOf('tm464')).toBe('light');
    expect(modeOf('tm612')).toBe('dark');
  });
});

describe('pickChoice', () => {
  it('주소의 ?skin= 이 기억한 값보다 먼저', () => {
    expect(pickChoice('tm464', 'tm612', ids)).toEqual(plain('tm464'));
  });
  it('주소의 이름이 없는 테마면 무시하고 기억한 값', () => {
    expect(pickChoice('tm999', 'tm464', ids)).toEqual(plain('tm464'));
    expect(pickChoice('tm999:narrow', 'tm464', ids)).toEqual(plain('tm464'));
  });
  it('아무것도 없으면 기본(다크 모드 612) · 넓은 본문 폭', () => {
    expect(DEFAULT_SKIN).toBe('tm612');
    expect(pickChoice(null, null, ids)).toEqual(plain('tm612'));
    expect(pickChoice('', '', ids)).toEqual(plain('tm612'));
  });
  it('직접 골라 기억한 테마는 기본 테마보다 먼저', () => {
    expect(pickChoice(null, 'tm464', ids)).toEqual(plain('tm464'));
  });
  it('지운 테마(486 · 503 · 557 · 590 · 606)나 예전 원래 화면(base)을 기억한 브라우저는 기본으로', () => {
    for (const v of ['tm486', 'tm503:side', 'tm557:narrow', 'tm590:side:narrow', 'tm606', 'base:side:narrow']) {
      expect(pickChoice(null, v, ids)).toEqual(plain('tm612'));
    }
  });
  it('기본 테마 폴더도 없으면 남은 테마 중 첫 번째', () => {
    expect(pickChoice(null, null, ['tm464'])).toEqual(plain('tm464'));
  });
  it('예전 좌측 메뉴 꼬리표(:side)는 버리고 테마와 본문 폭은 그대로', () => {
    expect(pickChoice(null, 'tm464:side', ids)).toEqual(plain('tm464'));
    expect(pickChoice('tm464:side:narrow', null, ids)).toEqual({ skin: 'tm464', narrow: true, lowContrast: false });
    expect(pickChoice('tm612:narrow:side', null, ids)).toEqual({ skin: 'tm612', narrow: true, lowContrast: false });
  });
});

describe('parseChoice · formatChoice', () => {
  it('글자 ↔ 고른 값이 서로 되돌아간다', () => {
    for (const v of ['tm464', 'tm464:narrow', 'tm612', 'tm612:narrow', 'tm464:low', 'tm612:low', 'tm612:narrow:low']) {
      expect(formatChoice(parseChoice(v))).toBe(v);
    }
  });
  it('저대비 꼬리표(:low)는 테마·본문 폭과 따로 읽고, 적는 순서는 narrow 다음', () => {
    expect(parseChoice('tm612:low')).toEqual({ skin: 'tm612', narrow: false, lowContrast: true });
    expect(parseChoice('tm464:low:narrow')).toEqual({ skin: 'tm464', narrow: true, lowContrast: true });
    expect(formatChoice(parseChoice('tm464:low:narrow'))).toBe('tm464:narrow:low');
    expect(pickChoice(null, 'tm464:low', ids)).toEqual({ skin: 'tm464', narrow: false, lowContrast: true });
  });
  it('모르는 꼬리표와 예전 :side 는 버린다', () => {
    expect(parseChoice('tm464:wide')).toEqual(plain('tm464'));
    expect(formatChoice(parseChoice('tm464:side:narrow'))).toBe('tm464:narrow');
  });
});

describe('choiceToRemember', () => {
  it('열기만 한 때(주소에 ?skin= 없음)는 기억하지 않는다 → 기본 테마가 바뀌면 따라간다', () => {
    expect(choiceToRemember(null, ids)).toBeNull();
    expect(choiceToRemember('', ids)).toBeNull();
  });
  it('주소의 테마를 모르면 기억하지 않는다', () => {
    expect(choiceToRemember('tm999', ids)).toBeNull();
    expect(choiceToRemember('tm590:side', ids)).toBeNull();
  });
  it('주소로 아는 테마를 열면 정리한 형식으로 기억한다', () => {
    expect(choiceToRemember('tm464', ids)).toBe('tm464');
    expect(choiceToRemember('tm464:narrow:side', ids)).toBe('tm464:narrow');
    expect(choiceToRemember('tm612:wide', ids)).toBe('tm612');
    expect(choiceToRemember('tm612:low:side', ids)).toBe('tm612:low');
  });
});
