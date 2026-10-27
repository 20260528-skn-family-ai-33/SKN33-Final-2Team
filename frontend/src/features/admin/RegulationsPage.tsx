/* 규정 데이터 (2026-10-26 사용자 결정) — 관리자는 규정을 고치지 않고 원문 PDF 만 올리고 내려받는다.
   규정은 벡터 DB 를 거친 RAG 에 쓰여서, 올린 PDF 는 서비스 운영팀(시스템 관리자)이 내려받아 임베딩·벡터 DB 를 갱신한다(처리 상태 없음).
   지금 규정은 조항 표 대신 원문 PDF 를 내려받아 본다. 잘못 올린 PDF 는 확인 창을 거쳐 파일과 기록을 함께 지운다(되돌릴 수 없음) */
import { useState } from 'react';
import { adminApi } from '@/api/endpoints/admin';
import type { RegulationDoc, RegulationUpload } from '@/api/types/admin';
import { failToast } from '@/shared/lib/fail';
import { kb } from '@/shared/lib/format';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { Loading, Note, Page } from '@/shared/ui/parts';
import { refreshRegulationUploads, useRegulationUploads, useRegulations } from './adminData';
import { REG } from './datasets';
import { FailBox } from './parts';

/** 서버와 같은 한도(backend app/regfiles.py) */
const MAX = 20_000_000;
const MEMO_MAX = 500;
const size = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : kb(n));

function UploadForm() {
  const [file, setFile] = useState<File | null>(null);
  const [memo, setMemo] = useState('');
  const [busy, setBusy] = useState(false);
  const pick = (f: File | undefined) => {
    if (!f) return;
    if (!/\.pdf$/i.test(f.name)) toast('PDF 파일만 올릴 수 있어요');
    else if (f.size > MAX) toast('파일이 너무 커요(20MB까지)');
    else setFile(f);
  };
  const send = async () => {
    if (!file || busy) return;
    setBusy(true);
    try {
      await adminApi.uploadRegulation(file, memo.trim());
      setFile(null);
      setMemo('');
      refreshRegulationUploads();
      toast('올렸어요. 서비스 운영팀이 받아 도우미 검색에 반영해요');
    } catch (err) {
      failToast(err, 'PDF를 올리지 못했어요');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card">
      <h2 className="st">새 규정 PDF 올리기</h2>
      <p className="small muted" style={{ margin: '4px 0 14px' }}>
        새로 생긴 규정이나 개정된 규정의 원문 PDF를 올려요. 바로 반영되지 않고, 반영되기 전까지 도우미는 지금 규정으로 답해요.
      </p>
      {file ? (
        <div className="file-on">
          <Icon name="file" />
          <div className="tx">
            <b>{file.name}</b>
            <small className="muted">{size(file.size)}</small>
          </div>
          <button className="link quiet" disabled={busy} onClick={() => setFile(null)}>
            빼기
          </button>
        </div>
      ) : (
        <label className="drop">
          <input
            type="file"
            accept=".pdf,application/pdf"
            onChange={(e) => {
              pick(e.target.files?.[0]);
              e.target.value = ''; // 같은 파일을 다시 골라도 올라가게
            }}
          />
          <span className="ico">
            <Icon name="upload" />
          </span>
          <span>
            <b>규정 PDF 고르기</b>
            <small>PDF 파일 하나 · 20MB까지</small>
          </span>
        </label>
      )}
      <div className="field" style={{ marginTop: 16 }}>
        <label htmlFor="admRegMemo">
          메모 <span className="muted small">선택 · 서비스 운영팀이 읽어요</span>
        </label>
        <textarea
          id="admRegMemo"
          className="textarea sm"
          rows={3}
          maxLength={MEMO_MAX}
          value={memo}
          placeholder="예: 인사규정 65차 개정본이에요. 일반직에 적용하고 2026-11-01부터 시행해요."
          onChange={(e) => setMemo(e.target.value)}
        />
      </div>
      <div className="actions" style={{ marginTop: 14 }}>
        <button className="btn pri" disabled={!file || busy} onClick={() => void send()}>
          <Icon name="upload" />
          {busy ? '올리는 중…' : '올리기'}
        </button>
      </div>
    </div>
  );
}

function DeleteButton({ u }: { u: RegulationUpload }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await adminApi.deleteRegulationUpload(u.id);
      closeSheet();
      refreshRegulationUploads();
      toast('올린 PDF를 삭제했어요');
    } catch (err) {
      setBusy(false);
      failToast(err, 'PDF를 삭제하지 못했어요');
      refreshRegulationUploads(); // 다른 창에서 이미 지웠을 수 있어 목록을 다시 받는다
    }
  };
  return (
    <button className="btn pri" disabled={busy} onClick={() => void run()}>
      {busy ? '삭제하는 중…' : '삭제하기'}
    </button>
  );
}

/** 잘못 올린 PDF 지우기 확인 창 */
function askDelete(u: RegulationUpload) {
  openSheet({
    title: '올린 PDF를 삭제할까요?',
    body: () => (
      <>
        <p style={{ marginTop: 0 }}>
          <b>{u.fileName}</b>
          <br />
          <span className="small muted">
            {u.createdAt}
            {u.admin ? ` · ${u.admin}` : ''} · {size(u.size)}
          </span>
        </p>
        {u.memo ? <p className="small" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{u.memo}</p> : null}
        <Note>
          서버에 있는 파일과 올린 기록이 함께 지워지고 되돌릴 수 없어요. 서비스 운영팀이 이미 받아 반영했다면 도우미 검색에서는 빠지지 않으니 운영팀에 알려 주세요.
        </Note>
      </>
    ),
    foot: () => (
      <>
        <button className="btn line" onClick={closeSheet}>
          취소
        </button>
        <DeleteButton u={u} />
      </>
    ),
  });
}

function Uploads() {
  const q = useRegulationUploads();
  if (q.isPending) return <Loading text="불러오는 중…" />;
  if (q.isError) return <FailBox err={q.error} what="올린 PDF 목록을 불러오지 못했어요" />;
  if (!q.data.length) return <p className="muted small">아직 올린 PDF가 없어요.</p>;
  return (
    <div className="list">
      {q.data.map((u) => (
        <div className="li" key={u.id}>
          <span className="idx">
            <Icon name="file" />
          </span>
          <div className="tx">
            <b>{u.fileName}</b>
            <small>
              {u.createdAt}
              {u.admin ? ` · ${u.admin}` : ''} · {size(u.size)}
            </small>
            {u.memo ? <small className="adm-reg-memo">{u.memo}</small> : null}
          </div>
          <span className="adm-reg-acts">
            <a className="btn line sm" href={adminApi.regulationUploadPdfUrl(u.id)} download aria-label={`${u.fileName} 내려받기`}>
              <Icon name="download" />
              내려받기
            </a>
            <button className="btn line sm adm-del" onClick={() => askDelete(u)} aria-label={`${u.fileName} 삭제`}>
              삭제
            </button>
          </span>
        </div>
      ))}
    </div>
  );
}

function Current() {
  const q = useRegulations();
  if (q.isPending) return <Loading text="불러오는 중…" />;
  if (q.isError) return <FailBox err={q.error} what="지금 규정을 불러오지 못했어요" />;
  if (!q.data.length) return <p className="muted small">등록된 규정이 없어요.</p>;
  /* 적용 직원 구분별로 묶는다(서버가 규정이 많은 구분부터 → 이름 순으로 준다) */
  const groups = new Map<string, RegulationDoc[]>();
  q.data.forEach((r) => {
    const g = r.group || '직원 구분 없음';
    groups.set(g, [...(groups.get(g) || []), r]);
  });
  return (
    <>
      {[...groups].map(([g, list]) => (
        <div key={g} className="adm-reg-group">
          <h3 className="adm-h3">
            {g} <span className="muted small">{list.length}건</span>
          </h3>
          <div className="list">
            {list.map((r) => (
              <div className="li" key={r.id}>
                <span className="idx">
                  <Icon name="scale" />
                </span>
                <div className="tx">
                  <b>{r.name}</b>
                  <small>
                    {[r.version, r.effective && `${r.effective} 시행`, r.category, r.overseas && '국외근무 전용', r.available && size(r.size)].filter(Boolean).join(' · ')}
                  </small>
                </div>
                {r.available ? (
                  <a className="btn line sm" href={adminApi.regulationPdfUrl(r.id)} download aria-label={`${r.name} 원문 PDF 내려받기`}>
                    <Icon name="download" />
                    내려받기
                  </a>
                ) : (
                  <span className="tag line" title="서버에 원문 PDF가 없어요. 서비스 운영팀에 알려 주세요">
                    원문 없음
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

export function RegulationsPage() {
  return (
    <Page eyebrow="관리자 · 데이터 관리" title={REG.title} lead={REG.lead}>
      <UploadForm />
      <div className="sec">
        <div className="sec-h">
          <h2 className="st">올린 PDF</h2>
        </div>
        <Uploads />
      </div>
      <div className="sec">
        <div className="sec-h">
          <h2 className="st">지금 규정</h2>
        </div>
        <p className="small muted" style={{ margin: '0 0 10px' }}>
          도우미가 지금 근거로 쓰는 규정이에요. 몇 조 몇 항이 무슨 내용인지는 원문 PDF를 내려받아 확인해요.
        </p>
        <Current />
      </div>
    </Page>
  );
}
