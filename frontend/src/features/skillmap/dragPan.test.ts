/* 스킬 지도가 칸보다 클 때의 끌어 밀기(#324): 조금 움직인 누르기는 점 누르기로 두고, 끌면 칸을 밀고 끝난 뒤의 click 하나만 버린다.
   칸이 위아래로 넘치지 않으면(화면에 맞추기에서 Ctrl + 스크롤 확대) 위아래는 페이지를 민다 */
import { describe, expect, it, vi } from 'vitest';
import { createDragPan, DRAG_PX } from './dragPan';

/** 칸: 화면 (100, 50)에 놓인 800×500 칸, 그림은 1300×1000 이고 처음에 (300, 200)만큼 밀려 있다 */
function box(content: { scrollWidth?: number; scrollHeight?: number } = {}) {
  const held = new Set<number>();
  return {
    scrollLeft: 300,
    scrollTop: 200,
    scrollWidth: 1300,
    scrollHeight: 1000,
    ...content,
    clientLeft: 0,
    clientTop: 0,
    clientWidth: 800,
    clientHeight: 500,
    getBoundingClientRect: () => ({ left: 100, top: 50 }),
    setPointerCapture: (id: number) => void held.add(id),
    hasPointerCapture: (id: number) => held.has(id),
    releasePointerCapture: (id: number) => void held.delete(id),
    held,
  };
}
type Box = ReturnType<typeof box>;
const at = (b: Box, clientX: number, clientY: number, more: Partial<{ pointerType: string; button: number; buttons: number }> = {}) => ({
  pointerId: 1,
  pointerType: 'mouse',
  button: 0,
  buttons: 1,
  clientX,
  clientY,
  currentTarget: b,
  preventDefault: () => {},
  ...more,
});
const click = () => ({ preventDefault: vi.fn(), stopPropagation: vi.fn() });

/** 페이지: 처음에 1000만큼 내려와 있다 */
function page() {
  const p = { y: 1000, top: () => p.y, scrollTo: (top: number) => void (p.y = top) };
  return p;
}

function setup(content?: Parameters<typeof box>[0]) {
  const onDragging = vi.fn();
  const pg = page();
  return { b: box(content), pg, pan: createDragPan(onDragging, pg), onDragging };
}

describe('createDragPan', () => {
  it('조금만 움직이고 떼면 밀지 않고 점 누르기(click)를 그대로 둔다', () => {
    const { b, pan, onDragging } = setup();
    pan.onPointerDown(at(b, 400, 300));
    pan.onPointerMove(at(b, 400 + DRAG_PX - 2, 301));
    pan.onPointerUp(at(b, 400 + DRAG_PX - 2, 301, { buttons: 0 }));
    const c = click();
    pan.onClickCapture(c);
    expect([b.scrollLeft, b.scrollTop]).toEqual([300, 200]);
    expect(onDragging).not.toHaveBeenCalled();
    expect(c.preventDefault).not.toHaveBeenCalled();
    expect(c.stopPropagation).not.toHaveBeenCalled();
  });

  it('끌면 마우스와 반대로 칸을 밀고, 끝난 뒤 따라오는 click 하나만 버린다', () => {
    const { b, pg, pan, onDragging } = setup();
    pan.onPointerDown(at(b, 400, 300));
    pan.onPointerMove(at(b, 430, 280));
    expect([b.scrollLeft, b.scrollTop]).toEqual([270, 220]);
    expect(b.held.has(1)).toBe(true);
    expect(onDragging.mock.calls).toEqual([[true]]);
    pan.onPointerMove(at(b, 380, 330));
    expect([b.scrollLeft, b.scrollTop]).toEqual([320, 170]);
    // 칸이 위아래로도 넘치면 페이지는 그대로
    expect(pg.y).toBe(1000);
    pan.onPointerUp(at(b, 380, 330, { buttons: 0 }));
    expect(b.held.size).toBe(0);
    expect(onDragging.mock.calls).toEqual([[true], [false]]);
    const after = click();
    pan.onClickCapture(after);
    expect(after.preventDefault).toHaveBeenCalled();
    expect(after.stopPropagation).toHaveBeenCalled();
    const next = click();
    pan.onClickCapture(next);
    expect(next.stopPropagation).not.toHaveBeenCalled();
  });

  it('Ctrl + 스크롤로 확대해 옆으로만 넘치면 좌우는 칸을, 위아래는 페이지를 민다', () => {
    // 화면에 맞추기에서 확대하면 칸이 그림 높이만큼 길어져 위아래로는 넘치지 않는다
    const { b, pg, pan, onDragging } = setup({ scrollHeight: 500 });
    pan.onPointerDown(at(b, 400, 300));
    pan.onPointerMove(at(b, 430, 280));
    expect([b.scrollLeft, b.scrollTop, pg.y]).toEqual([270, 200, 1020]);
    pan.onPointerMove(at(b, 380, 340));
    expect([b.scrollLeft, b.scrollTop, pg.y]).toEqual([320, 200, 960]);
    pan.onPointerUp(at(b, 380, 340, { buttons: 0 }));
    expect(onDragging.mock.calls).toEqual([[true], [false]]);
  });

  it('지도가 칸에 다 들어가면 끌지 않고 페이지도 건드리지 않는다', () => {
    const { b, pg, pan, onDragging } = setup({ scrollWidth: 800, scrollHeight: 500 });
    pan.onPointerDown(at(b, 400, 300));
    pan.onPointerMove(at(b, 300, 200));
    pan.onPointerUp(at(b, 300, 200, { buttons: 0 }));
    const c = click();
    pan.onClickCapture(c);
    expect([b.scrollLeft, b.scrollTop, pg.y]).toEqual([300, 200, 1000]);
    expect(onDragging).not.toHaveBeenCalled();
    expect(c.stopPropagation).not.toHaveBeenCalled();
  });

  it('손가락·펜·오른쪽 버튼은 브라우저에 맡긴다', () => {
    const { b, pan, onDragging } = setup();
    for (const more of [{ pointerType: 'touch' }, { pointerType: 'pen' }, { button: 2, buttons: 2 }]) {
      pan.onPointerDown(at(b, 400, 300, more));
      pan.onPointerMove(at(b, 300, 200, more));
      pan.onPointerUp(at(b, 300, 200, { ...more, buttons: 0 }));
    }
    expect([b.scrollLeft, b.scrollTop]).toEqual([300, 200]);
    expect(onDragging).not.toHaveBeenCalled();
  });

  it('스크롤 막대를 누른 것은 끌기로 보지 않는다', () => {
    const { b, pan } = setup();
    // 칸 오른쪽 끝(100 + 800)과 아래쪽 끝(50 + 500)부터는 스크롤 막대 자리
    for (const [x, y] of [
      [900, 300],
      [400, 550],
    ]) {
      pan.onPointerDown(at(b, x, y));
      pan.onPointerMove(at(b, x - 100, y - 100));
    }
    expect([b.scrollLeft, b.scrollTop]).toEqual([300, 200]);
  });

  it('칸 밖에서 버튼을 뗀 뒤 다시 들어와 움직여도 끌지 않는다', () => {
    const { b, pan, onDragging } = setup();
    pan.onPointerDown(at(b, 400, 300));
    pan.onPointerMove(at(b, 600, 300, { buttons: 0 }));
    pan.onPointerMove(at(b, 700, 300));
    expect([b.scrollLeft, b.scrollTop]).toEqual([300, 200]);
    expect(onDragging).not.toHaveBeenCalled();
  });

  it('끄는 중에 취소되면 쥔 손을 풀고 다음 click 은 버리지 않는다', () => {
    const { b, pan, onDragging } = setup();
    pan.onPointerDown(at(b, 400, 300));
    pan.onPointerMove(at(b, 450, 300));
    pan.onPointerCancel();
    expect(onDragging.mock.calls).toEqual([[true], [false]]);
    const c = click();
    pan.onClickCapture(c);
    expect(c.stopPropagation).not.toHaveBeenCalled();
    // 취소 뒤 움직임은 무시
    pan.onPointerMove(at(b, 600, 300));
    expect(b.scrollLeft).toBe(250);
  });
});
