import { Fragment, useSyncExternalStore } from 'react';
import { Icon } from '@/shared/ui/Icon';
import { pageNumbers } from './resourceBrowse';

interface Props {
  page: number;
  pages: number;
  label: string;
  disabled: boolean;
  onChange: (page: number) => void;
}

/* 좁은 화면에서는 현재 페이지 양옆 번호를 하나씩만 보여 이전·다음 버튼이 화면 밖으로 밀리지 않게 한다(resourceBrowse.css와 같은 폭) */
const NARROW = '(max-width: 480px)';
const subscribeNarrow = (notify: () => void) => {
  const query = window.matchMedia(NARROW);
  query.addEventListener('change', notify);
  return () => query.removeEventListener('change', notify);
};
const useNarrow = () => useSyncExternalStore(subscribeNarrow, () => window.matchMedia(NARROW).matches, () => false);

export function ResourcePagination({ page, pages, label, disabled, onChange }: Props) {
  const narrow = useNarrow();
  if (pages < 2) return null;
  const numbers = pageNumbers(page, pages, narrow ? 1 : 2);
  return <nav aria-label={label} className="resource-pager">
    <div className="resource-pager-nums">
      <button type="button" className="btn line sm" aria-label="이전 페이지" disabled={disabled || page === 1} onClick={() => onChange(page - 1)}>
        <Icon name="left" />
      </button>
      {numbers.map((n, i) => <Fragment key={n}>
        {i > 0 && n - numbers[i - 1] > 1 && <span aria-hidden="true" className="resource-pager-gap">…</span>}
        <button type="button" className={n === page ? 'btn pri sm' : 'btn ghost sm'} aria-label={`${n}페이지`}
          aria-current={n === page ? 'page' : undefined} disabled={disabled} onClick={() => onChange(n)}>{n}</button>
      </Fragment>)}
      <button type="button" className="btn line sm" aria-label="다음 페이지" disabled={disabled || page === pages} onClick={() => onChange(page + 1)}>
        <Icon name="right" />
      </button>
    </div>
    <form key={page} className="resource-pager-jump" onSubmit={(e) => {
      e.preventDefault();
      const n = Number(new FormData(e.currentTarget).get('page'));
      if (Number.isInteger(n) && n >= 1 && n <= pages) onChange(n);
    }}>
      <input type="number" name="page" className="input" aria-label="이동할 페이지" min={1} max={pages} required defaultValue={page} />
      <span>/ {pages}</span>
      <button className="btn line sm" disabled={disabled}>이동</button>
    </form>
  </nav>;
}
