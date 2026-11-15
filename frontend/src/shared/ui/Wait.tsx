/* 기다리는 동안 보이는 짧은 문구('계산 중…')의 말줄임표를 점 세 개로 바꿔 차례로 오르내리게 한다(#227).
   스켈레톤을 넣기에는 작은 칸에서, 멈춘 화면이 아니라는 것만 알린다. 글자는 그대로 두고 점만 움직인다.
   금방 끝나는 대기에서는 깜박여 보이지 않게 처음 잠깐은 멈춰 있고(wait.css), '움직임 줄이기' 설정에서는 계속 멈춰 있다 */
import './wait.css';

const TAIL = /(…|\.{3})$/;

/** 끝이 '…'인 문구만 점을 움직인다. 그렇지 않은 문구('준비 실패' 등)는 그대로 보여 준다.
    글자와 점을 한 덩어리로 묶어, 버튼처럼 안의 항목 사이를 띄우는 곳에서도 점이 글자에서 떨어지지 않는다 */
export function Wait({ children }: { children: string }) {
  if (!TAIL.test(children)) return <>{children}</>;
  return (
    <span className="wait-text">
      {children.replace(TAIL, '')}
      <span className="wait-dots" aria-hidden="true">
        <i>.</i>
        <i>.</i>
        <i>.</i>
      </span>
    </span>
  );
}
