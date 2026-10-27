/* 데이터 화면 (5차 gp-admin.js dataset): 지금 데이터 표(행을 누르면 오른쪽 패널에서 고치기) · 시트 탭 · 찾기 · 쪽 넘기기
   · 여러 건은 엑셀·CSV로 내려받아 고친 파일을 올리면 미리보기 화면으로 간다 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { adminApi } from '@/api/endpoints/admin';
import type { AdminRows, DatasetId } from '@/api/types/admin';
import { queryClient } from '@/app/queryClient';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { openSheet } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { Loading, Note, Page } from '@/shared/ui/parts';
import { adminKeys, useRows } from './adminData';
import { adm, curSheet, keyOf, qKey, sameKey, setAdm, useAdmin, type EditState } from './adminStore';
import { DS, PAGE, isDataset } from './datasets';
import { EditPanel, guard, openEdit } from './EditPanel';
import { FailBox } from './parts';

function Table({ d, ed, onPick }: { d: AdminRows; ed: EditState | null; onPick: (i: number) => void }) {
  const cols = d.columns;
  const on = ed && ed.mode === 'edit' && ed.sheet === d.sheet ? ed : null;
  return (
    <div className="adm-tbl">
      <table>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.field} className={`${c.readonly ? 'ro' : ''}${c.key ? ' key' : ''}`} title={c.help || ''}>
                {c.header}
                {c.required && !c.key ? ' *' : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {d.rows.length ? (
            d.rows.map((r, i) => (
              <tr
                key={i}
                tabIndex={0}
                title="눌러서 고치기"
                className={on && sameKey(on.key, keyOf(cols, r)) ? 'on' : ''}
                onClick={() => onPick(i)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onPick(i);
                  }
                }}
              >
                {cols.map((c) => {
                  const v = r[c.field] || '';
                  return (
                    <td key={c.field} className={`${c.readonly ? 'ro' : ''}${c.key ? ' key' : ''}`}>
                      <span className="clip" title={v}>
                        {v}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={cols.length} className="muted">
                행이 없어요
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** 엑셀·CSV 파일을 올려 미리보기를 만든다(바로 바뀌지 않음) */
async function upload(ds: DatasetId, file: File, sheet: string, go: (to: string) => void): Promise<void> {
  if (adm().busy) return;
  setAdm((s) => void (s.busy = true));
  try {
    const r = await adminApi.preview(ds, file, sheet);
    queryClient.setQueryData(adminKeys.upload(r.uploadId), { ...r, status: 'previewed' });
    setAdm((s) => {
      s.busy = false;
      s.filter = r.errorRows ? 'error' : 'all';
    });
    go(paths.adminPreview(r.uploadId));
  } catch (err) {
    setAdm((s) => void (s.busy = false));
    openSheet({ title: '미리보기를 만들지 못했어요', body: () => <FailBox err={err} what="파일을 읽지 못했어요" /> });
  }
}

/* 여러 건 고치기(엑셀·CSV): 한 건은 표에서 고치므로 접어 둔다. 펼친 상태는 기억한다 */
function Bulk({ ds, sheet }: { ds: DatasetId; sheet: string }) {
  const go = useGo();
  const open = useAdmin((s) => s.bulk || s.busy);
  const busy = useAdmin((s) => s.busy);
  /* CSV로 내려받을 시트: 고르지 않았으면 지금 보는 시트(시트 탭을 바꾸면 따라간다) */
  const [csvPick, setCsvPick] = useState<{ for: string; v: string } | null>(null);
  const csvSheet = csvPick && csvPick.for === sheet ? csvPick.v : sheet;
  const [upSheet, setUpSheet] = useState('');
  const D = DS[ds];
  return (
    <details className="card adm-bulk" id="admBulk" open={open} onToggle={(e) => setAdm((s) => void (s.bulk = (e.currentTarget as HTMLDetailsElement).open))}>
      <summary>
        <span className="adm-bulk-t">
          <Icon name="upload" />
          <b>엑셀·CSV로 여러 건 한꺼번에 고치기</b>
        </span>
        <span className="small muted">내려받아 고친 파일을 올리면 미리보기를 거쳐 반영해요</span>
      </summary>
      <div className="adm-bulk-b">
        <h3 className="adm-h3">1. 내려받기</h3>
        <div className="adm-bar">
          <a className="btn pri sm" href={adminApi.downloadUrl(ds, 'xlsx')} download>
            <Icon name="download" />
            엑셀로 내려받기 (시트 {D.sheets.length}개)
          </a>
          <a className="btn line sm" href={adminApi.templateUrl(ds, 'xlsx')} download>
            빈 양식
          </a>
          <span className="grow" />
          <select className="input" id="admCsvSheet" aria-label="CSV로 내려받을 시트" value={csvSheet} onChange={(e) => setCsvPick({ for: sheet, v: e.target.value })}>
            {D.sheets.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <button className="btn line sm" onClick={() => (location.href = adminApi.downloadUrl(ds, 'csv', csvSheet))}>
            <Icon name="download" />
            CSV로 내려받기
          </button>
        </div>
        <p className="small muted" style={{ margin: '8px 0 0' }}>
          엑셀 첫 시트 ‘안내’에 열 설명과 규칙이 있어요. 초록 머리글은 꼭 적는 열, 회색 머리글은 참고용이에요. CSV는 시트 하나씩이에요.
        </p>
        <h3 className="adm-h3">2. 고친 파일 올리기</h3>
        <label className="drop adm-drop">
          <input
            type="file"
            id="admFile"
            accept=".xlsx,.csv"
            onChange={(e) => {
              const f = e.target.files && e.target.files[0];
              e.target.value = ''; // 같은 파일을 다시 골라도 올라가게
              if (f) void upload(ds, f, upSheet, go);
            }}
          />
          <span className="ico">
            <Icon name="upload" />
          </span>
          <span>
            <b>엑셀(.xlsx) 또는 CSV 파일 고르기</b>
            <small>올리면 바로 바뀌지 않고 미리보기를 먼저 보여 줘요 · 20MB까지</small>
          </span>
        </label>
        <div className="adm-bar" style={{ marginTop: 8 }}>
          <span className="small muted">CSV의 시트</span>
          <select className="input" id="admUpSheet" aria-label="CSV 시트" value={upSheet} onChange={(e) => setUpSheet(e.target.value)}>
            <option value="">머리글로 알아서 찾기</option>
            {D.sheets.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          {busy ? (
            <span className="small">
              <Loading text="미리보기를 만드는 중…" />
            </span>
          ) : null}
        </div>
        <Note>파일에 없는 행은 그대로 둬요. 지우려면 ‘삭제’ 열에 Y를 적어요. 오류가 하나라도 있으면 반영할 수 없어요.</Note>
      </div>
    </details>
  );
}

function Dataset({ ds }: { ds: DatasetId }) {
  const sheet = useAdmin((s) => curSheet(s, ds));
  const k = qKey(ds, sheet);
  const q = useAdmin((s) => s.q[k] || '');
  const pg = useAdmin((s) => s.page[k] || 0);
  const edit = useAdmin((s) => s.edit);
  /* 찾기 칸: 쓰는 중인 글자는 이 시트·검색어에서만 남긴다(시트를 바꾸거나 찾으면 그 검색어로) */
  const [draft, setDraft] = useState<{ k: string; q: string; v: string } | null>(null);
  const qIn = draft && draft.k === k && draft.q === q ? draft.v : q;
  const setQIn = (v: string) => setDraft({ k, q, v });
  const rows = useRows(ds, sheet, q, pg);
  const D = DS[ds];
  const ed = edit && edit.ds === ds && edit.sheet === sheet ? edit : null;
  const d = rows.data;
  const ready = !!d && !rows.isError;
  /* 그 데이터 화면을 떠나면 패널을 닫는다(5차와 같이 묻지 않음) */
  useEffect(() => () => setAdm((s) => void (s.edit = null)), [ds]);

  const search = () =>
    setAdm((s) => {
      s.q[k] = qIn.trim();
      s.page[k] = 0;
    });
  const turn = (dir: number) => setAdm((s) => void (s.page[k] = Math.max(0, (s.page[k] || 0) + dir)));
  const pickTab = (x: string) =>
    guard(() =>
      setAdm((s) => {
        s.tab[ds] = x;
        if (s.edit && s.edit.ds === ds) s.edit = null;
      }),
    );
  const pickRow = (i: number) => {
    const r = d?.rows[i];
    if (!d || !r) return;
    const cur = adm().edit;
    if (cur && cur.mode === 'edit' && cur.ds === ds && sameKey(cur.key, keyOf(d.columns, r))) return;
    guard(() => openEdit(ds, sheet, d, r));
  };
  const addRow = () => {
    if (!d || !d.columns) return;
    guard(() => openEdit(ds, sheet, d, null));
  };

  const body = rows.isPending ? (
    <Loading text="불러오는 중…" />
  ) : rows.isError ? (
    <FailBox err={rows.error} what="데이터를 불러오지 못했어요" />
  ) : (
    <>
      <Table d={rows.data} ed={ed} onPick={pickRow} />
      <div className="adm-pager">
        <span className="grow small">행을 누르면 오른쪽에서 고칠 수 있어요</span>
        {rows.data.total}행 중 {rows.data.total ? pg * PAGE + 1 : 0}~{Math.min(rows.data.total, (pg + 1) * PAGE)}
        <button className="btn line sm" disabled={!pg} aria-label="이전 쪽" onClick={() => turn(-1)}>
          <Icon name="left" />
        </button>
        <button className="btn line sm" disabled={(pg + 1) * PAGE >= rows.data.total} aria-label="다음 쪽" onClick={() => turn(1)}>
          <Icon name="right" />
        </button>
      </div>
    </>
  );
  return (
    <Page eyebrow="관리자 · 데이터 관리" title={D.title} lead={D.lead}>
      <div className={`adm-split${ed ? ' has-panel' : ''}`}>
        <div className="adm-main">
          <Bulk ds={ds} sheet={sheet} />
          <div className="sec">
            <div className="sec-h">
              <h2 className="st">지금 데이터</h2>
              <button className="btn pri sm" disabled={!ready} onClick={addRow}>
                <Icon name="plus" />
                {sheet} 추가
              </button>
            </div>
            <div className="adm-tabs">
              {D.sheets.map((s) => (
                <button key={s} className={`chip ${s === sheet ? 'on' : ''}`} onClick={() => pickTab(s)}>
                  {s}
                </button>
              ))}
            </div>
            <div className="adm-bar" style={{ marginBottom: 10 }}>
              <input
                className="input sm"
                id="admQ"
                value={qIn}
                placeholder="이 시트에서 찾기"
                aria-label="찾기"
                onChange={(e) => setQIn(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) search();
                }}
              />
              <button className="btn line sm" onClick={search}>
                찾기
              </button>
            </div>
            {body}
          </div>
        </div>
        {ed ? <EditPanel key={ed.id} ed={ed} /> : null}
      </div>
    </Page>
  );
}

export function DatasetPage() {
  const { ds } = useParams();
  if (!isDataset(ds)) return <Page title="없는 데이터예요" />;
  return <Dataset key={ds} ds={ds} />;
}

