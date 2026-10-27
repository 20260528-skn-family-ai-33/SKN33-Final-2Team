/* 한 건씩 고치기 (5차 gp-admin.js · 2026-10-22): 오른쪽 패널 → 확인(서버가 엑셀과 같은 검사) → 확인 창 → 저장.
   고칠 때는 바뀐 칸만, 추가할 때는 적은 칸만 보낸다. 확인 창에서 본 내용(token)이 저장 때와 다르면 서버가 저장하지 않는다 */
import { useEffect, useRef, type ReactNode } from 'react';
import { adminApi } from '@/api/endpoints/admin';
import type { AdminColumn, AdminRows, DatasetId, EditCheck, RowView } from '@/api/types/admin';
import { failToast } from '@/shared/lib/fail';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { Note } from '@/shared/ui/parts';
import { refreshAdmin } from './adminData';
import { adm, dirty, editable, editRows, newEdit, placeErrors, setAdm, setChoice, setVal, splitList, useAdmin, type EditState } from './adminStore';
import { DEL_ASK, DS, LONG } from './datasets';
import { ChangeCard } from './parts';

/* ── 저장하지 않은 칸이 있으면 버릴지 먼저 묻는다 ── */
export function guard(fn: () => void): void {
  if (!dirty(adm().edit)) {
    fn();
    return;
  }
  openSheet({
    title: '고친 내용을 버릴까요?',
    body: () => <p style={{ marginTop: 0 }}>오른쪽 패널에 저장하지 않은 내용이 있어요. 버리고 넘어갈까요?</p>,
    foot: () => (
      <>
        <button className="btn line" onClick={closeSheet}>
          계속 고치기
        </button>
        <button
          className="btn pri"
          onClick={() => {
            closeSheet();
            setAdm((s) => void (s.edit = null));
            fn();
          }}
        >
          버리기
        </button>
      </>
    ),
  });
}

export function openEdit(ds: DatasetId, sheet: string, d: AdminRows, r: AdminRows['rows'][number] | null): void {
  const ed = newEdit(ds, sheet, d, r);
  setAdm((s) => void (s.edit = ed));
}

export const closeEdit = () => guard(() => setAdm((s) => void (s.edit = null)));

/* ── 확인 → 확인 창 → 저장 ── */
async function submitEdit(del: boolean): Promise<void> {
  const ed = adm().edit;
  if (!ed || ed.busy) return;
  const rows = editRows(ed, del);
  if (!del && ed.mode === 'edit' && !Object.keys(rows[0].values || {}).length) {
    toast('바뀐 칸이 없어요');
    return;
  }
  const id = ed.id;
  const mine = (f: (e: EditState) => void) =>
    setAdm((s) => {
      if (s.edit?.id === id) f(s.edit);
    });
  mine((e) => void (e.busy = true));
  let r: EditCheck;
  try {
    r = await adminApi.check(ed.ds, rows);
  } catch (err) {
    mine((e) => void (e.busy = false));
    failToast(err, '확인하지 못했어요');
    return;
  }
  if (adm().edit?.id !== id) return;
  mine((e) => {
    e.busy = false;
    placeErrors(e, r.rows || []);
    if (r.errorRows) e.focusErr += 1;
  });
  if (r.errorRows) return;
  if (!r.changeRows) {
    toast('바뀐 내용이 없어요');
    return;
  }
  setAdm((s) => void (s.pending = { editId: id, ds: ed.ds, rows, token: r.token }));
  confirmEdit(adm().edit as EditState, r.rows || [], del);
}

function EditGoalBody() {
  const v = useAdmin((s) => s.choice.editGoal);
  return (
    <div className="stack adm-goal">
      <span className="small muted">저장한 뒤 이 직원의 목표 후보를 다시 만들 때</span>
      <label className="radio">
        <input type="radio" name="admEditGoal" value="employee" checked={v === 'employee'} onChange={() => setChoice('editGoal', 'employee')} />
        <span>
          그 직원이 고른 AI 모드로 만들기 <span className="small muted">· 실제 모델을 한 번 불러요(OpenAI API는 비용이 들어요) · 모드가 설정되지 않았으면 실패로 남아요</span>
        </span>
      </label>
      <label className="radio">
        <input type="radio" name="admEditGoal" value="mock" checked={v === 'mock'} onChange={() => setChoice('editGoal', 'mock')} />
        <span>
          시연용 가데이터로 만들기 <span className="small muted">· 비용 없음 · 화면에 ‘가데이터’로 보여요</span>
        </span>
      </label>
    </div>
  );
}

function SaveButton({ label }: { label: string }) {
  const saving = useAdmin((s) => s.saving);
  return (
    <button className="btn pri" disabled={saving} onClick={() => void saveEdit()}>
      {saving ? (
        <>
          <span className="sp" />
          저장하는 중…
        </>
      ) : (
        <>
          <Icon name="check" />
          {label}
        </>
      )}
    </button>
  );
}

function confirmEdit(ed: EditState, rows: RowView[], del: boolean): void {
  const newEmp = rows.some((x) => x.sheet === '직원' && x.action === 'add');
  const regen = ed.ds === 'hr' && !newEmp && rows.some((x) => x.sheet === '평정' || (x.sheet === '직원' && x.action === 'update' && !(x.tags || []).includes('퇴직')));
  const title = del ? DEL_ASK[ed.info.deleteLabel] || '삭제할까요?' : ed.mode === 'add' ? '이대로 추가할까요?' : '이대로 저장할까요?';
  const delLabel = del ? ed.info.deleteLabel : null;
  setChoice('editGoal', 'employee');
  setAdm((s) => void (s.saving = false));
  openSheet({
    title,
    sub: `${DS[ed.ds].title} · 저장하면 바로 반영되고 변경 이력에 남아요`,
    body: () => (
      <>
        <div className="adm-rows">
          {rows
            .filter((x) => x.action !== 'same')
            .map((x, i) => (
              <ChangeCard key={i} r={x} delLabel={delLabel} />
            ))}
        </div>
        {regen ? (
          <EditGoalBody />
        ) : newEmp ? (
          <Note>
            새 직원은 본인 입력(업무 설명·경험 요약·기술 스택)이 없어 AI 활용 업무 기본 후보가 들어가요. 직원이 내 정보를 채우면 그 직원이 고른 AI 모드로 다시 만들어요. 처음 비밀번호는
            시연 초기 비밀번호예요.
          </Note>
        ) : del && ed.sheet === '직원' ? (
          <Note>재직 상태를 퇴직, 계정 상태를 중지로 바꾸고 로그인을 끊어요. 부서장이면 부서장도 해제해요. 직원 기록은 지우지 않고 남겨요.</Note>
        ) : null}
      </>
    ),
    foot: () => (
      <>
        <button className="btn line" onClick={closeSheet}>
          취소
        </button>
        <SaveButton label={del ? ed.info.deleteLabel || '삭제' : ed.mode === 'add' ? '추가하기' : '저장하기'} />
      </>
    ),
    onClose: () => setAdm((s) => void (s.pending = null)),
  });
}

async function saveEdit(): Promise<void> {
  const { pending: p, choice } = adm();
  if (!p) return;
  setAdm((s) => void (s.saving = true));
  try {
    const r = await adminApi.save(p.ds, p.rows, p.token, choice.editGoal === 'mock' ? 'mock' : null);
    setAdm((s) => {
      s.saving = false;
      if (s.edit?.id === p.editId) s.edit = null;
    });
    closeSheet();
    refreshAdmin(p.ds);
    toast(`저장했어요${r.goalCount ? ' · 목표 후보를 다시 만들어요' : ''}`);
  } catch (err) {
    setAdm((s) => void (s.saving = false));
    closeSheet();
    failToast(err, '저장하지 못했어요');
  }
}

/* ── 칸 하나 (칸 종류마다 입력 방식이 다르다) ── */
function Field({ c, v, err }: { c: AdminColumn; v: string; err?: string }) {
  const id = `ef-row-${c.field}`;
  const name = `row.${c.field}`;
  const o = c.options || { items: [] };
  const items = o.items || [];
  const set = (x: string) => setVal(c.field, c.header, x);
  let input: ReactNode;
  let labelFor = true;
  if (c.kind === 'bool') {
    labelFor = false;
    input = (
      <div className="chips" role="radiogroup" aria-label={c.header}>
        {(
          [
            ['Y', '예'],
            ['N', '아니요'],
          ] as const
        ).map(([x, l]) => (
          <label className="chip" key={x}>
            <input type="radio" name={id} data-ef={name} value={x} checked={v === x} onChange={() => set(x)} />
            {l}
          </label>
        ))}
      </div>
    );
  } else if (c.kind === 'list' && o.strict) {
    labelFor = false;
    const on = splitList(v);
    const known = new Set(items.map((x) => x.value));
    const all = items.concat(on.filter((x) => !known.has(x)).map((x) => ({ value: x })));
    const toggle = (x: string, yes: boolean) => set(all.map((a) => a.value).filter((a) => (a === x ? yes : on.includes(a))).join('; '));
    input = (
      <div className="chips adm-multi" role="group" aria-label={c.header}>
        {all.map((x) => (
          <label className="chip" key={x.value}>
            <input type="checkbox" data-ef={name} value={x.value} checked={on.includes(x.value)} onChange={(e) => toggle(x.value, e.target.checked)} />
            {x.label || x.value}
          </label>
        ))}
      </div>
    );
  } else if (c.kind === 'choice' || (o.strict && items.length)) {
    const opts = c.kind === 'choice' ? c.choices.map((x) => ({ value: x, label: '' })) : items;
    const has = opts.some((x) => x.value === v);
    input = (
      <select className="input" id={id} data-ef={name} value={v} onChange={(e) => set(e.target.value)}>
        {!c.required || !v ? <option value="">{c.required ? '골라 주세요' : '(비움)'}</option> : null}
        {v && !has ? <option value={v}>{v}</option> : null}
        {opts.map((x) => (
          <option value={x.value} key={x.value}>
            {x.label ? `${x.value} · ${x.label}` : x.value}
          </option>
        ))}
      </select>
    );
  } else if (c.kind === 'date') {
    input = <input className="input" type="date" id={id} data-ef={name} value={v} onChange={(e) => set(e.target.value)} />;
  } else if (LONG[c.field] || c.kind === 'list') {
    input = <textarea className="textarea" id={id} data-ef={name} rows={LONG[c.field] || 2} value={v} onChange={(e) => set(e.target.value)} />;
  } else {
    input = (
      <>
        <input
          className="input"
          id={id}
          data-ef={name}
          value={v}
          autoComplete="off"
          inputMode={c.kind === 'int' || c.kind === 'num' ? 'decimal' : undefined}
          list={items.length ? `${id}-dl` : undefined}
          onChange={(e) => set(e.target.value)}
        />
        {items.length ? (
          <datalist id={`${id}-dl`}>
            {items.map((x) => (
              <option value={x.value} key={x.value}>
                {x.label || ''}
              </option>
            ))}
          </datalist>
        ) : null}
      </>
    );
  }
  const help = [c.help, c.kind === 'list' && !o.strict ? '여러 개는 세미콜론(;)으로 구분해요' : ''].filter(Boolean).join(' · ');
  const lab = (
    <>
      {c.header}
      {c.required || c.key ? (
        <>
          {' '}
          <span className="req" aria-hidden="true">
            *
          </span>
        </>
      ) : null}
    </>
  );
  return (
    <div className={`adm-f${err ? ' bad' : ''}`}>
      {labelFor ? <label htmlFor={id}>{lab}</label> : <span className="flabel">{lab}</span>}
      {input}
      {err ? (
        <p className="adm-ferr">
          <Icon name="alert" />
          {err}
        </p>
      ) : null}
      {help ? <p className="adm-fhelp">{help}</p> : null}
    </div>
  );
}

/* ── 오른쪽 패널 ── */
export function EditPanel({ ed }: { ed: EditState }) {
  const ref = useRef<HTMLElement>(null);
  const keyCols = ed.cols.filter((c) => c.key);
  const add = ed.mode === 'add';
  const short = (v: string) => (String(v).length > 20 ? String(v).slice(0, 8) + '…' : v);
  const title = add ? `${ed.sheet} 추가` : [ed.orig.no, ed.orig.name, ed.orig.title].filter(Boolean).join(' · ') || `${ed.sheet} 고치기`;
  const sub = add
    ? `${ed.info.autoKey ? `${keyCols.map((c) => c.header).join(' · ')}는 저장할 때 정해져요 · ` : ''}* 표시 칸은 꼭 적어요`
    : `${ed.sheet} · ${keyCols.map((c) => `${c.header} ${short(ed.orig[c.field])}`).join(' · ')}`;
  const fields = editable(ed);
  const ro = add ? [] : ed.cols.filter((c) => c.readonly && ed.orig[c.field]);
  /* 열릴 때 첫 칸으로 */
  useEffect(() => {
    (ref.current?.querySelector('[data-ef]') as HTMLElement | null)?.focus({ preventScroll: true });
  }, []);
  /* 오류가 생기면 첫 오류 칸으로 */
  useEffect(() => {
    if (!ed.focusErr) return;
    const b = ref.current?.querySelector('.adm-f.bad [data-ef], .adm-msg') as HTMLElement | null;
    if (b) {
      b.scrollIntoView({ block: 'center' });
      b.focus?.({ preventScroll: true });
    }
  }, [ed.focusErr]);
  return (
    <aside className="adm-panel enter" aria-label={title} ref={ref}>
      <div className="adm-ph">
        <div className="grow">
          <b>{title}</b>
          <small>{sub}</small>
        </div>
        <button className="x" aria-label="패널 닫기" onClick={closeEdit}>
          <Icon name="x" />
        </button>
      </div>
      <div className="adm-pb">
        {ed.msgs.map((m, i) => (
          <p className="adm-msg e" key={i}>
            <Icon name="alert" /> {m}
          </p>
        ))}
        {ro.length ? (
          <dl className="adm-ro">
            {ro.map((c) => (
              <RoItem key={c.field} dt={c.header} dd={ed.orig[c.field]} />
            ))}
          </dl>
        ) : null}
        {fields.map((c) => (
          <Field key={c.field} c={c} v={ed.vals[c.field] || ''} err={ed.errs[c.header]} />
        ))}
      </div>
      <div className="adm-pf">
        {!add && ed.info.deletable ? (
          <button className="btn line sm adm-del" onClick={() => void submitEdit(true)}>
            {ed.info.deleteLabel || '삭제'}
          </button>
        ) : null}
        <span className="grow" />
        <button className="btn line sm" onClick={closeEdit}>
          취소
        </button>
        <button className="btn pri sm" disabled={ed.busy} onClick={() => void submitEdit(false)}>
          {ed.busy ? (
            <>
              <span className="sp" />
              확인하는 중…
            </>
          ) : (
            <>
              <Icon name="check" />
              {add ? '추가' : '저장'}
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

/** 고칠 수 없는 참고 칸 */
const RoItem = ({ dt, dd }: { dt: string; dd: string }) => (
  <>
    <dt>{dt}</dt>
    <dd>{dd}</dd>
  </>
);
