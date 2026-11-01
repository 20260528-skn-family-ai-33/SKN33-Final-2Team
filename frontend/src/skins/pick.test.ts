import { describe, expect, it } from 'vitest';
import { BASE, pickSkin, splitChoice } from './pick';

const ids = ['tm464', 'tm590'];

describe('pickSkin', () => {
  it('주소의 ?skin= 이 기억한 값보다 먼저', () => {
    expect(pickSkin('tm590', 'tm464', ids)).toBe('tm590');
  });
  it('주소에서 원래 화면(base)을 고르면 기억한 테마보다 먼저', () => {
    expect(pickSkin(BASE, 'tm464', ids)).toBe(BASE);
  });
  it('주소의 이름이 없는 테마면 무시하고 기억한 값', () => {
    expect(pickSkin('tm999', 'tm464', ids)).toBe('tm464');
  });
  it('기억한 테마 폴더를 지웠으면 원래 화면', () => {
    expect(pickSkin(null, 'tm999', ids)).toBe(BASE);
  });
  it('아무것도 없으면 원래 화면', () => {
    expect(pickSkin(null, null, ids)).toBe(BASE);
    expect(pickSkin('', '', [])).toBe(BASE);
  });
  it('좌측 메뉴 버전(:side)도 있는 테마면 그대로 고른다', () => {
    expect(pickSkin('tm464:side', 'tm590', ids)).toBe('tm464:side');
    expect(pickSkin(null, 'tm590:side', ids)).toBe('tm590:side');
  });
  it('없는 테마의 좌측 메뉴 버전이나 원래 화면의 좌측 메뉴 버전은 무시', () => {
    expect(pickSkin('tm999:side', 'tm464', ids)).toBe('tm464');
    expect(pickSkin('base:side', null, ids)).toBe(BASE);
  });
});

describe('splitChoice', () => {
  it('테마 id 와 좌측 메뉴 여부로 나눈다', () => {
    expect(splitChoice('tm464')).toEqual({ skin: 'tm464', side: false });
    expect(splitChoice('tm464:side')).toEqual({ skin: 'tm464', side: true });
    expect(splitChoice(BASE)).toEqual({ skin: BASE, side: false });
  });
});
