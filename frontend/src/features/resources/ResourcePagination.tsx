import { Fragment } from 'react';
import { Icon } from '@/shared/ui/Icon';

interface Props {
  page: number;
  pages: number;
  label: string;
  disabled: boolean;
  onChange: (page: number) => void;
}

export function ResourcePagination({ page, pages, label, disabled, onChange }: Props) {
  if (pages < 2) return null;
  const first = Math.max(1, Math.min(page - 2, pages - 4));
  const numbers = Array.from({ length: Math.min(5, pages) }, (_, i) => first + i);
  if (first > 1) numbers.unshift(1);
  if (numbers[numbers.length - 1] < pages) numbers.push(pages);
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
