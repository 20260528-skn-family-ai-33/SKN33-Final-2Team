/* 관리자 화면 표시 조각 (5차 gp-admin.js 의 failBox·num·uploadList·chgCard·rowCard) */
import type { ReactNode } from 'react';
import type { RowView, UploadSummary } from '@/api/types/admin';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { cause } from '@/shared/state/ai';
import { Icon } from '@/shared/ui/Icon';
import { OpsBox } from '@/shared/ui/parts';
import { ACT, UP_ST, datasetTitle } from './datasets';

export function FailBox({ err, what }: { err: unknown; what: string }) {
  const c = cause(err);
  return (
    <div className="callout soft" role="alert">
      <Icon name="alert" />
      <div>
        <b>{what}</b>
        <br />
        <span className="small">{c.user}</span>
        <OpsBox items={[['', c]]} cls="sm" />
      </div>
    </div>
  );
}

export const Num = ({ l, v }: { l: string; v: ReactNode }) => (
  <div>
    <small>{l}</small>
    <b>{v == null ? '-' : String(v)}</b>
  </div>
);

export function UploadList({ list }: { list: UploadSummary[] | undefined }) {
  const go = useGo();
  if (!list || !list.length) return <p className="muted small">아직 변경 기록이 없어요.</p>;
  return (
    <div className="list">
      {list.map((u) => {
        const [t, c] = UP_ST[u.status] || [u.status, 'line'];
        const sm = u.summary || {};
        const form = sm.source === 'form';
        return (
          <button className="li" key={u.uploadId} onClick={() => go(paths.adminPreview(u.uploadId))}>
            <span className="idx">
              <Icon name={form ? 'edit' : u.fileName.toLowerCase().endsWith('.csv') ? 'file' : 'upload'} />
            </span>
            <div className="tx">
              <b>{u.fileName}</b>
              <small>
                {datasetTitle(u.dataset)} · {u.createdAt}
                {u.admin ? ` · ${u.admin}` : ''}
                {form ? '' : ` · 바뀌는 행 ${sm.changeRows ?? '-'}${sm.errorRows ? ` · 오류 ${sm.errorRows}` : ''}`}
              </small>
            </div>
            <span className="end">
              <span className={`tag ${c}`}>{form ? '저장함' : t}</span>
              <Icon name="right" />
            </span>
          </button>
        );
      })}
    </div>
  );
}

const Changes = ({ r }: { r: RowView }) =>
  (r.changes || []).length ? (
    <ul className="adm-chg">
      {r.changes.map((x, i) => (
        <li key={i}>
          <span className="k">{x.col}</span>
          <span>
            {x.before ? (
              <>
                <s>{x.before}</s> →{' '}
              </>
            ) : null}
            <span className="to">{x.after || '(비움)'}</span>
          </span>
        </li>
      ))}
    </ul>
  ) : null;
const Warnings = ({ r }: { r: RowView }) => (
  <>
    {(r.warnings || []).map((w, i) => (
      <p className="adm-msg w" key={i}>
        <Icon name="info" /> {w}
      </p>
    ))}
  </>
);

/** 한 건 고치기 확인 창의 바뀌는 행 */
export function ChangeCard({ r, delLabel }: { r: RowView; delLabel: string | null }) {
  const [t, c] = r.action === 'delete' && delLabel ? [delLabel, 'warn'] : ACT[r.action] || [r.action, 'line'];
  return (
    <div className="adm-row">
      <div className="adm-row-h">
        <span className={`tag ${c}`}>{t}</span>
        <b>{r.label || r.key}</b>
        <span className="muted">{r.sheet}</span>
        {(r.tags || [])
          .filter((x) => x !== delLabel)
          .map((x) => (
            <span className="tag acc" key={x}>
              {x}
            </span>
          ))}
      </div>
      <Changes r={r} />
      <Warnings r={r} />
    </div>
  );
}

/** 미리보기의 행 (form: 화면에서 고친 기록이라 파일 행 번호가 없음) */
export function RowCard({ r, form }: { r: RowView; form: boolean }) {
  const [t, c] = ACT[r.action] || [r.action, 'line'];
  return (
    <div className={`adm-row ${r.action === 'error' ? 'error' : ''}`}>
      <div className="adm-row-h">
        <span className={`tag ${c}`}>{t}</span>
        <b>{r.label || r.key}</b>
        <span className="muted">
          {r.sheet}
          {form ? '' : ` 시트 · ${r.row}행`} · {r.key}
        </span>
        {(r.tags || []).map((x) => (
          <span className="tag acc" key={x}>
            {x}
          </span>
        ))}
      </div>
      {(r.errors || []).map((e, i) => (
        <p className="adm-msg e" key={i}>
          <Icon name="alert" /> <b>{e.col}</b> · {e.msg}
        </p>
      ))}
      {r.action !== 'error' ? <Changes r={r} /> : null}
      <Warnings r={r} />
    </div>
  );
}
