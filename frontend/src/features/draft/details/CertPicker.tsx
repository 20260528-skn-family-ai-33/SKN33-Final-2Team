/* 자격증 계획 드롭다운: 분야 → 자격 2단계 (5차 P.certPick · cp-*)
   팀 DB 자격증 · 폐지·폐지 예정·상태 미확인 제외(2026-10-21 사용자 결정). 분야를 누르면 같은 창이 그 분야의 자격 목록으로 바뀌고 '‹ 분야'로 돌아온다.
   PC·모바일 같은 모양 · 키보드 ↑↓ → ← Esc */
import { Fragment, useEffect, useRef, useState } from 'react';
import { setAt, useAt } from '@/shared/state/bind';
import { useCatalog } from '@/shared/state/catalog';
import { toast } from '@/shared/state/ui';
import { fieldLabel } from '@/shared/lib/prefs';
import { Icon } from '@/shared/ui/Icon';
import { Thumb } from '@/shared/ui/parts';

const Mark = ({ on }: { on: boolean }) => <span className="cp-ck">{on ? <Icon name="check" /> : null}</span>;

export function CertPicker({ path }: { path: string }) {
  const v = useAt<string>(path) || '';
  const groups = useCatalog((s) => s.certGroups);
  const byId = useCatalog((s) => s.certById);
  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState('');
  const [from, setFrom] = useState('');
  const box = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const cur = byId[v];

  const close = (refocus?: boolean) => {
    setOpen(false);
    if (refocus) btn.current?.focus();
  };
  const show = (g: string, back?: string) => {
    setLevel(g);
    setFrom(back || '');
  };
  /* 단계 그리기: 고른 항목(또는 고른 자격이 든 분야)에, 없으면 첫 항목에 초점. 분야 목록으로 돌아올 때는 방금 본 분야에 */
  useEffect(() => {
    if (!open || !pop.current) return;
    pop.current.scrollTop = 0;
    const p = pop.current;
    const t =
      (from && p.querySelector<HTMLButtonElement>(`.cp-it.grp[data-arg="${CSS.escape(from)}"]`)) ||
      p.querySelector<HTMLButtonElement>('.cp-it.on, .cp-it.has') ||
      p.querySelector<HTMLButtonElement>('.cp-it');
    t?.focus();
  }, [open, level, from]);
  /* 바깥을 누르면 닫기 */
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (box.current && !e.composedPath().includes(box.current)) setOpen(false);
    };
    document.addEventListener('click', h);
    return () => document.removeEventListener('click', h);
  }, [open]);

  const pick = (id: string) => {
    setAt(path, id);
    close(true);
  };
  const onKey = (e: React.KeyboardEvent) => {
    const items = [...(pop.current?.querySelectorAll<HTMLButtonElement>('button') || [])];
    const t = e.target as HTMLElement;
    const i = items.indexOf(t as HTMLButtonElement);
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      close(true);
    } else if (e.key === 'Tab') close();
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const n = items.length;
      const j = i < 0 ? 0 : (i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n;
      items[j]?.focus();
    } else if (e.key === 'ArrowRight' && t.matches('.cp-it.grp')) {
      e.preventDefault();
      t.click();
    } else if (e.key === 'ArrowLeft' && level) {
      e.preventDefault();
      show('', level);
    }
  };

  let content: React.ReactNode = null;
  if (open && !level)
    content = (
      <>
        <button type="button" className={`cp-it${cur ? '' : ' on'}`} data-arg="" onClick={() => pick('')}>
          <Mark on={!cur} />
          <span className="cp-tx">
            계획 없음<small>자격 준비를 넣지 않아요</small>
          </span>
        </button>
        <div className="cp-sep" />
        {groups.map((x) => (
          <button type="button" key={x.key} className={`cp-it grp${cur && cur.group === x.key ? ' has' : ''}`} data-arg={x.key} onClick={() => show(x.key)}>
            <Mark on={!!cur && cur.group === x.key} />
            <span className="cp-tx">
              {x.label}
              {cur && cur.group === x.key ? <small>{cur.name}</small> : null}
            </span>
            <span className="cp-n">{x.certs.length}</span>
            <Icon name="right" />
          </button>
        ))}
      </>
    );
  else if (open && level) {
    const grp = groups.find((x) => x.key === level);
    /* 시행 기관이 하나인 분야는 기관을 맨 위에 한 번만 쓴다(앞 자격과 기관이 바뀔 때만 머리글) */
    const vendorHead = (grp?.certs || []).map((c, i, all) => {
      const prev = all
        .slice(0, i)
        .map((x) => x.vendor)
        .filter(Boolean)
        .pop();
      return !!c.vendor && c.vendor !== prev;
    });
    content = grp ? (
      <>
        <button type="button" className="cp-back" onClick={() => show('', level)}>
          <Icon name="left" />
          <span>
            {grp.label}
            {grp.issuer ? <small>{grp.issuer}</small> : null}
          </span>
        </button>
        {grp.certs.map((c, i) => {
          const head = vendorHead[i] ? <p className="cp-sub">{c.vendor}</p> : null;
          const meta = c.vendor ? '' : [c.sub, grp.issuer ? '' : c.issuer].filter(Boolean).join(' · ');
          return (
            <Fragment key={c.id}>
              {head}
              <button type="button" className={`cp-it${c.id === v ? ' on' : ''}`} data-arg={c.id} onClick={() => pick(c.id)}>
                <Mark on={c.id === v} />
                <Thumb r={{ type: 'cert', image: c.image }} size="xs" />
                <span className="cp-tx">
                  {c.short}
                  {meta ? <small>{meta}</small> : null}
                </span>
              </button>
            </Fragment>
          );
        })}
      </>
    ) : null;
  }

  return (
    <div className={`cpick${open ? ' open' : ''}`} ref={box} onKeyDownCapture={open ? onKey : undefined}>
      <button
        type="button"
        ref={btn}
        className={`input cp-btn${cur ? '' : ' empty'}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={fieldLabel('cert')}
        onClick={() => {
          if (open) return close();
          if (!groups.length) {
            toast('자격증 목록을 불러오지 못했어요 · 서버 연결을 확인해 주세요');
            return;
          }
          show(cur ? cur.group || '' : '');
          setOpen(true);
        }}
      >
        <span className="cp-v">{cur ? cur.name : '계획 없음'}</span>
      </button>
      <div className="cp-pop" hidden={!open} ref={pop} data-level={level}>
        {content}
      </div>
    </div>
  );
}
