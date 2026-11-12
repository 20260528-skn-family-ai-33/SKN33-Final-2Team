import { describe, expect, it } from 'vitest';
import { DEFAULT_SKIN, formatChoice, parseChoice, pickChoice } from './pick';

const ids = ['tm464', 'tm590', 'tm612'];
const plain = (skin: string) => ({ skin, side: false, narrow: false });

describe('pickChoice', () => {
  it('주소의 ?skin= 이 기억한 값보다 먼저', () => {
    expect(pickChoice('tm590', 'tm464', ids)).toEqual(plain('tm590'));
  });
  it('주소의 이름이 없는 테마면 무시하고 기억한 값', () => {
    expect(pickChoice('tm999', 'tm590', ids)).toEqual(plain('tm590'));
    expect(pickChoice('tm999:side:narrow', 'tm590', ids)).toEqual(plain('tm590'));
  });
  it('아무것도 없으면 기본 테마(612) · 상단 메뉴 · 넓은 본문 폭', () => {
    expect(DEFAULT_SKIN).toBe('tm612');
    expect(pickChoice(null, null, ids)).toEqual(plain('tm612'));
    expect(pickChoice('', '', ids)).toEqual(plain('tm612'));
  });
  it('예전 기본 테마(464)를 기억한 브라우저는 그대로 464', () => {
    expect(pickChoice(null, 'tm464', ids)).toEqual(plain('tm464'));
  });
  it('기억한 테마 폴더를 지웠으면 기본 테마', () => {
    expect(pickChoice(null, 'tm999', ids)).toEqual(plain('tm612'));
  });
  it('예전의 원래 화면(base)은 주소 · 기억 모두 기본 테마로', () => {
    expect(pickChoice('base', null, ids)).toEqual(plain('tm612'));
    expect(pickChoice(null, 'base:side:narrow', ids)).toEqual(plain('tm612'));
    expect(pickChoice('base', 'tm590:side', ids)).toEqual({ skin: 'tm590', side: true, narrow: false });
  });
  it('기본 테마 폴더도 없으면 남은 테마 중 첫 번째', () => {
    expect(pickChoice(null, null, ['tm590', 'tm606'])).toEqual(plain('tm590'));
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
});

describe('parseChoice · formatChoice', () => {
  it('글자 ↔ 고른 값이 서로 되돌아간다', () => {
    for (const v of ['tm464', 'tm464:side', 'tm464:narrow', 'tm464:side:narrow', 'tm590:narrow']) {
      expect(formatChoice(parseChoice(v))).toBe(v);
    }
  });
  it('모르는 꼬리표는 버린다', () => {
    expect(parseChoice('tm464:wide')).toEqual(plain('tm464'));
  });
});
