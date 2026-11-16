/* 로그인 화면 우측 블록: 라벨·제목 아래에 서비스 화면 그림을 넘겨 보여 준다 (#282).
   그림 위에는 글자를 올리지 않고, 설명 문구 한 줄을 그림 아래에 둔다.
   넘기는 방법은 양옆 화살표 · 그림 끌기 · 아래 눈금(몇 번째 장인지도 보여 준다) · 좌우 화살표 키.
   가만히 두면 4초마다 저절로 넘어간다. 직접 넘기면 멈췄다가, 10초 동안 조작이 없으면 다음 장으로 넘어가고 다시 4초마다 넘어간다.
   마우스를 올려 두기만 한 것은 조작으로 치지 않는다(버튼을 누른 자리에 마우스를 둔 채로도 다시 넘어가야 하므로).
   그림을 끄는 동안 · 탭이 가려진 동안 · 움직임 줄이기 설정에서는 넘어가지 않는다 */
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react';
import { Icon } from '@/shared/ui/Icon';
import { DEFAULT_SKIN } from '@/skins/pick';
import { LOGIN_SLIDES, slideSrc } from './loginSlides';

const AUTO_MS = 4000;
/** 직접 넘긴 뒤 이만큼 조작이 없으면 다시 저절로 넘긴다 */
const RESUME_MS = 10000;
/** 이만큼(px) 넘게 끌어야 다음 장으로 넘긴다. 그보다 짧으면 제자리로 돌아온다 */
const DRAG_MIN = 40;

/* 지금 테마: 로그인 화면의 '화면 테마' 상자로 바꾸면 <html data-skin> 이 바뀐다 → 그 테마로 찍은 그림으로 바꾼다 */
function watchSkin(onChange: () => void): () => void {
  const o = new MutationObserver(onChange);
  o.observe(document.documentElement, { attributes: true, attributeFilter: ['data-skin'] });
  return () => o.disconnect();
}
const readSkin = (): string => document.documentElement.dataset.skin || DEFAULT_SKIN;

export function LoginFlow() {
  const skin = useSyncExternalStore(watchSkin, readSkin, () => DEFAULT_SKIN);
  const [at, setAt] = useState(0);
  const [auto, setAuto] = useState(true);
  const [failed, setFailed] = useState<string[]>([]);
  /** 끄는 중이면 끈 거리(px), 아니면 null */
  const [drag, setDrag] = useState<number | null>(null);
  const dragFrom = useRef(0);
  const count = LOGIN_SLIDES.length;

  /** 쉬는 시간이 끝나 다시 넘기기 시작하는 참인지(그때는 4초를 더 기다리지 않고 바로 한 장 넘긴다) */
  const resumed = useRef(false);
  const dragging = drag !== null;
  useEffect(() => {
    if (!auto || dragging || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const next = (): void => {
      if (!document.hidden) setAt((n) => (n + 1) % count);
    };
    if (resumed.current) {
      resumed.current = false;
      next();
    }
    const t = window.setInterval(next, AUTO_MS);
    return () => window.clearInterval(t);
  }, [auto, dragging, count]);

  // 직접 넘길 때마다 쉬는 시간을 처음부터 다시 센다
  const resume = useRef(0);
  useEffect(() => () => window.clearTimeout(resume.current), []);
  const pick = (n: number): void => {
    setAuto(false);
    window.clearTimeout(resume.current);
    resume.current = window.setTimeout(() => {
      resumed.current = true;
      setAuto(true);
    }, RESUME_MS);
    setAt((n + count) % count);
  };
  const onKey = (e: KeyboardEvent<HTMLElement>): void => {
    const move = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!move) return;
    e.preventDefault();
    pick(at + move);
  };

  const onDown = (e: PointerEvent<HTMLDivElement>): void => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragFrom.current = e.clientX;
    setDrag(0);
  };
  const onMove = (e: PointerEvent<HTMLDivElement>): void => {
    if (drag !== null) setDrag(e.clientX - dragFrom.current);
  };
  const onUp = (): void => {
    if (drag === null) return;
    if (Math.abs(drag) >= DRAG_MIN) pick(at + (drag < 0 ? 1 : -1));
    setDrag(null);
  };

  /* 처음에는 지금 장과 양옆 장만 받고, 첫 그림이 뜬 뒤에 나머지를 받는다(로그인 화면이 뜨는 것을 늦추지 않게).
     나머지도 받아 두어야 끝에서 처음으로 돌아가거나 눈금으로 여러 장을 건너뛸 때 지나가는 장이 빈 틀로 보이지 않는다 */
  const [warm, setWarm] = useState(false);
  const near = (n: number): boolean => warm || [0, 1, count - 1].includes((n - at + count) % count);

  return (
    <aside className="login-side">
      <div className="lf-head">
        <span className="pill">
          <Icon name="spark" />
          개발·운영 직원 AI 역량 성장지원
        </span>
        <h2>
          AI가 추천하는,
          <br />
          나에게 최적화된 성장 로드맵
        </h2>
      </div>
      <div className="lf" role="group" aria-roledescription="carousel" aria-label="서비스 화면 미리 보기" onKeyDown={onKey}>
        <button type="button" className="lf-arrow" aria-label="이전 화면" onClick={() => pick(at - 1)}>
          <Icon name="left" />
        </button>
        <div
          className={`lf-shot${drag !== null ? ' is-drag' : ''}`}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={() => setDrag(null)}
        >
          <div className="lf-track" style={{ transform: `translateX(calc(${-at * 100}% + ${drag ?? 0}px))` }}>
            {LOGIN_SLIDES.map((s, n) => {
              const src = slideSrc(skin, s.id);
              return (
                <div key={s.id} aria-hidden={n !== at}>
                  {near(n) && src && !failed.includes(src) ? (
                    <img src={src} alt={`${s.name} 화면`} width={1280} height={960} draggable={false} onLoad={() => setWarm(true)} onError={() => setFailed((f) => [...f, src])} />
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
        <button type="button" className="lf-arrow" aria-label="다음 화면" onClick={() => pick(at + 1)}>
          <Icon name="right" />
        </button>
        <ol className="lf-rule" style={{ '--lf-n': count, '--lf-i': at } as CSSProperties}>
          {LOGIN_SLIDES.map((s, n) => (
            <li key={s.id}>
              <button type="button" title={s.name} aria-label={`${n + 1} / ${count} · ${s.name}`} aria-current={n === at ? 'step' : undefined} onClick={() => pick(n)} />
            </li>
          ))}
          <li className="lf-mark" aria-hidden="true" />
        </ol>
        <p className="lf-cap" aria-live={auto ? 'off' : 'polite'}>
          {LOGIN_SLIDES[at].text}
        </p>
      </div>
    </aside>
  );
}
