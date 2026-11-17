/* 스킬 지도가 칸보다 클 때(크게 보기 · Ctrl + 스크롤 확대) 마우스로 끌어 지도를 민다(#324). 일정표(Gantt.tsx)의 끌어 밀기와 같은 방식으로,
   조금(DRAG_PX) 움직이기 전까지는 점 누르기로 두고, 끌기로 바뀐 뒤 따라오는 click 하나는 버려 놓은 자리의 점이 눌리지 않게 한다.
   칸이 위아래로는 넘치지 않으면(화면에 맞추기에서 확대하면 칸이 함께 길어진다) 위아래 끌기는 페이지를 민다.
   손가락·펜은 브라우저가 원래 밀어 주므로 마우스 왼쪽 버튼만 다룬다 */

export const DRAG_PX = 5;

/** 끌어 미는 칸(.sm-wrap). 테스트에서 가짜로 바꿔 끼울 수 있게 쓰는 것만 적는다 */
interface PanBox {
  scrollLeft: number;
  scrollTop: number;
  scrollWidth: number;
  scrollHeight: number;
  clientLeft: number;
  clientTop: number;
  clientWidth: number;
  clientHeight: number;
  getBoundingClientRect(): { left: number; top: number };
  setPointerCapture(pointerId: number): void;
  hasPointerCapture(pointerId: number): boolean;
  releasePointerCapture(pointerId: number): void;
}
interface PanPointer {
  pointerId: number;
  pointerType: string;
  button: number;
  buttons: number;
  clientX: number;
  clientY: number;
  currentTarget: PanBox;
  preventDefault(): void;
}
interface PanClick {
  preventDefault(): void;
  stopPropagation(): void;
}
/** 칸이 위아래로 넘치지 않을 때 위아래 끌기를 넘겨받는 페이지 */
export interface PanPage {
  top(): number;
  scrollTo(top: number): void;
}

/** 칸에 그대로 펼쳐 붙이는 이벤트 처리기 */
export interface DragPan {
  onPointerDown(e: PanPointer): void;
  onPointerMove(e: PanPointer): void;
  onPointerUp(e: PanPointer): void;
  onPointerCancel(): void;
  onLostPointerCapture(): void;
  onClickCapture(e: PanClick): void;
}

const windowPage: PanPage = {
  top: () => window.scrollY,
  scrollTo: (top) => window.scrollTo(window.scrollX, top),
};

/** 지도가 칸보다 커서 밀어 볼 데가 있는지. 화면의 손바닥 커서도 이것으로 정한다 */
export const overflowsX = (box: Pick<PanBox, 'scrollWidth' | 'clientWidth'>) => box.scrollWidth > box.clientWidth + 1;
export const overflowsY = (box: Pick<PanBox, 'scrollHeight' | 'clientHeight'>) => box.scrollHeight > box.clientHeight + 1;

// 칸의 스크롤 막대를 누른 것은 브라우저에 맡긴다
function onScrollbar(e: PanPointer): boolean {
  const box = e.currentTarget;
  const r = box.getBoundingClientRect();
  return e.clientX - r.left - box.clientLeft >= box.clientWidth || e.clientY - r.top - box.clientTop >= box.clientHeight;
}

/** onDragging: 끌기가 시작되면 true, 끝나면 false (손 모양 커서를 쥔 손으로 바꾸는 데 쓴다) */
export function createDragPan(onDragging: (dragging: boolean) => void, page: PanPage = windowPage): DragPan {
  let start: { pointer: number; x: number; y: number; left: number; top: number; inBox: boolean; moved: boolean } | null = null;
  let swallowClick = false;
  const stop = () => {
    if (start?.moved) onDragging(false);
    start = null;
  };
  return {
    onPointerDown(e) {
      swallowClick = false;
      start = null;
      const box = e.currentTarget;
      if (e.pointerType !== 'mouse' || e.button !== 0 || onScrollbar(e)) return;
      const inBox = overflowsY(box);
      if (!inBox && !overflowsX(box)) return;
      start = { pointer: e.pointerId, x: e.clientX, y: e.clientY, left: box.scrollLeft, top: inBox ? box.scrollTop : page.top(), inBox, moved: false };
    },
    onPointerMove(e) {
      if (!start || start.pointer !== e.pointerId) return;
      // 칸 밖에서 버튼을 떼면 pointerup 이 오지 않으므로, 버튼 없이 움직이면 여기서 끝낸다
      if (!(e.buttons & 1)) {
        stop();
        return;
      }
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      if (!start.moved) {
        if (Math.hypot(dx, dy) < DRAG_PX) return;
        start.moved = true;
        swallowClick = true;
        onDragging(true);
        // 끄는 동안 칸 밖으로 나가도 계속 따라오게 붙잡는다(누르기 전에 붙잡으면 점의 click 이 칸으로 가 버려 끌기로 바뀐 뒤에만)
        e.currentTarget.setPointerCapture(e.pointerId);
      }
      e.preventDefault();
      e.currentTarget.scrollLeft = start.left - dx;
      if (start.inBox) e.currentTarget.scrollTop = start.top - dy;
      else page.scrollTo(start.top - dy);
    },
    onPointerUp(e) {
      if (start && start.pointer !== e.pointerId) return;
      stop();
      if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    },
    onPointerCancel() {
      swallowClick = false;
      stop();
    },
    onLostPointerCapture() {
      stop();
    },
    onClickCapture(e) {
      if (!swallowClick) return;
      swallowClick = false;
      e.preventDefault();
      e.stopPropagation();
    },
  };
}
