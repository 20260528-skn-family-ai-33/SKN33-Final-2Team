import { describe, expect, it } from 'vitest';
import { BASE, formatChoice, parseChoice, pickChoice } from './pick';

const ids = ['tm464', 'tm590'];
const plain = (skin: string) => ({ skin, side: false, narrow: false });

describe('pickChoice', () => {
  it('주소의 ?skin= 이 기억한 값보다 먼저', () => {
    expect(pickChoice('tm590', 'tm464', ids)).toEqual(plain('tm590'));
  });
  it('주소에서 원래 화면(base)을 고르면 기억한 테마보다 먼저', () => {
    expect(pickChoice(BASE, 'tm464', ids)).toEqual(plain(BASE));
  });
  it('주소의 이름이 없는 테마면 무시하고 기억한 값', () => {
    expect(pickChoice('tm999', 'tm464', ids)).toEqual(plain('tm464'));
    expect(pickChoice('tm999:side:narrow', 'tm464', ids)).toEqual(plain('tm464'));
  });
  it('기억한 테마 폴더를 지웠으면 원래 화면', () => {
    expect(pickChoice(null, 'tm999', ids)).toEqual(plain(BASE));
  });
  it('아무것도 없으면 원래 화면 · 상단 메뉴 · 넓은 본문 폭', () => {
    expect(pickChoice(null, null, ids)).toEqual(plain(BASE));
    expect(pickChoice('', '', [])).toEqual(plain(BASE));
  });
  it('예전 형식(꼬리표 없음 · :side)도 그대로 고른다', () => {
    expect(pickChoice('tm464:side', 'tm590', ids)).toEqual({ skin: 'tm464', side: true, narrow: false });
    expect(pickChoice(null, 'tm590', ids)).toEqual(plain('tm590'));
  });
  it('좌측 메뉴 · 이전 폭 꼬리표는 순서와 상관없이 읽는다', () => {
    const both = { skin: 'tm464', side: true, narrow: true };
    expect(pickChoice('tm464:side:narrow', null, ids)).toEqual(both);
    expect(pickChoice('tm464:narrow:side', null, ids)).toEqual(both);
  });
  it('원래 화면에도 꼬리표를 기억해 둔다(좌측 메뉴는 다음에 고를 테마에 이어 쓴다)', () => {
    expect(pickChoice('base:side:narrow', 'tm464', ids)).toEqual({ skin: BASE, side: true, narrow: true });
  });
});

describe('parseChoice · formatChoice', () => {
  it('글자 ↔ 고른 값이 서로 되돌아간다', () => {
    for (const v of ['tm464', 'tm464:side', 'tm464:narrow', 'tm464:side:narrow', BASE, 'base:narrow']) {
      expect(formatChoice(parseChoice(v))).toBe(v);
    }
  });
  it('모르는 꼬리표는 버린다', () => {
    expect(parseChoice('tm464:wide')).toEqual(plain('tm464'));
  });
});
