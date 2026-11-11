/* 에이전트 동작 보기(시연·디버그 전용 · 5차 gp-core.js agent-log) — 누가 호출했든 모든 계정의 호출을 보여 준다.
   목록은 요약만 받고, 한 줄을 펼칠 때 그 기록의 입력·출력과 모델 호출마다 보낸 메시지·받은 원문을 받는다.
   서버가 원문을 자르지 않으므로 화면도 자르지 않는다. 긴 칸은 스크롤·'크게 보기'·'원문 복사'로 끝까지 본다. */
import { useRef, useState } from 'react';
import { aiApi, type AgentLogDetail, type AgentLogEntry, type AgentModelCall } from '@/api/endpoints/account';
import { cause } from '@/shared/state/ai';
import { openSheet, toast } from '@/shared/state/ui';

const LOG_TAG: Record<string, [string, string]> = {
  ollama: ['tag acc', 'RunPod-Ollama'],
  api: ['tag acc', 'OpenAI API'],
  mock: ['tag', '가데이터'],
  error: ['tag fail', '호출 오류 · 실패 안내'],
  sim: ['tag fail', '실패 시연'],
  off: ['tag fail', '모드 사용 불가 · 실패 안내'],
  stop: ['tag', '사용자가 멈춤'],
};

/** JSON 이면 들여쓰기해 읽기 쉽게, 아니면 그대로 보여 준다(복사는 원문 그대로) */
export function readable(text: string): string {
  const t = text.trim();
  if (!t.startsWith('{') && !t.startsWith('[')) return text;
  try {
    return JSON.stringify(JSON.parse(t), null, 2);
  } catch {
    return text;
  }
}

function copy(text: string): void {
  void navigator.clipboard?.writeText(text).then(
    () => toast('원문을 복사했어요'),
    () => toast('복사하지 못했어요 · 칸을 직접 선택해 복사해 주세요'),
  );
}

function TextBlock({ label, text }: { label: string; text: string }) {
  const [big, setBig] = useState(false);
  return (
    <div className="log-text">
      <div className="log-text-h">
        <span className="small muted">
          {label} · {text.length.toLocaleString()}자
        </span>
        <button type="button" className="btn line sm" onClick={() => setBig((v) => !v)}>
          {big ? '줄여 보기' : '크게 보기'}
        </button>
        <button type="button" className="btn line sm" onClick={() => copy(text)}>
          원문 복사
        </button>
      </div>
      <pre className={big ? 'big' : undefined}>{text ? readable(text) : '(비어 있음)'}</pre>
    </div>
  );
}

function ModelCall({ call, n, total }: { call: AgentModelCall; n: number; total: number }) {
  const last = call.messages.length - 1;
  return (
    <div className="log-call">
      <p className="log-call-h">
        <b>모델 호출 {total > 1 ? `${n}/${total}` : ''}</b>
        <span className="small muted">
          {[call.model, `${call.ms}ms`, call.images ? `이미지 ${call.images}장(이미지 내용은 기록하지 않음)` : ''].filter(Boolean).join(' · ')}
        </span>
      </p>
      {call.error ? <p className="small log-err">{call.error}</p> : null}
      <TextBlock label="시스템 지시" text={call.system} />
      {call.messages.map((m, i) => (
        <TextBlock key={i} label={i === last ? '보낸 입력' : `이전 대화 · ${m.role === 'assistant' ? '답변' : '질문'}`} text={m.content} />
      ))}
      <TextBlock label="모델 응답 원문" text={call.output} />
    </div>
  );
}

/** 기록 한 건의 전문. run() 기록은 에이전트 입력·출력과 그 안의 모델 호출, 모델을 바로 부른 기록은 그 호출 하나 */
export function AgentLogBody({ detail }: { detail: AgentLogDetail }) {
  const run = detail.input !== undefined;
  return (
    <>
      {detail.error ? <p className="small log-err">{detail.error}</p> : null}
      {run ? <TextBlock label="에이전트 입력" text={detail.input ?? ''} /> : null}
      {run ? <TextBlock label="에이전트 출력" text={detail.output ?? ''} /> : null}
      {detail.calls.map((c, i) => (
        <ModelCall key={i} call={c} n={i + 1} total={detail.calls.length} />
      ))}
      {run && !detail.calls.length ? <p className="small muted log-call">이 기록에서는 실제 모델을 부르지 않았어요.</p> : null}
    </>
  );
}

function LogItem({ entry }: { entry: AgentLogEntry }) {
  const [detail, setDetail] = useState<AgentLogDetail | null>(null);
  const [error, setError] = useState('');
  const [slow, setSlow] = useState(false);
  const loading = useRef(false);
  const load = () => {
    if (detail || loading.current) return;
    loading.current = true;
    setError('');
    // 바로 오면 아무 문구 없이 내용만 보이고, 0.3초 넘게 걸릴 때만 '불러오는 중'을 보인다
    const timer = window.setTimeout(() => setSlow(true), 300);
    aiApi
      .logEntry(entry.id)
      .then(setDetail, (err: unknown) => setError(cause(err).user))
      .finally(() => {
        loading.current = false;
        window.clearTimeout(timer);
        setSlow(false);
      });
  };
  return (
    <details className="logi" onToggle={(e) => (e.currentTarget.open ? load() : undefined)}>
      <summary>
        <span className="muted small num">{entry.at}</span>
        {entry.employee ? <span className="small">{entry.employee}</span> : null}
        <b>{entry.agent}</b>
        <span className="grow small">
          {entry.task}
          {entry.model && entry.mode !== 'mock' ? ` · ${entry.model}` : ''}
        </span>
        {entry.by ? <span className="tag">{entry.by} 실행</span> : null}
        {entry.callCount > 1 ? <span className="small muted">모델 {entry.callCount}회</span> : null}
        {LOG_TAG[entry.mode] ? <span className={LOG_TAG[entry.mode][0]}>{LOG_TAG[entry.mode][1]}</span> : null}
        <span className="small muted num">{entry.ms}ms</span>
      </summary>
      {detail ? <AgentLogBody detail={detail} /> : null}
      {error ? <p className="small log-err">{error}</p> : null}
      {slow ? <p className="small muted log-call">불러오는 중…</p> : null}
    </details>
  );
}

export function AgentLogList({ entries }: { entries: AgentLogEntry[] }) {
  return entries.length ? (
    <div className="log">
      {entries.map((e) => (
        <LogItem key={e.id} entry={e} />
      ))}
    </div>
  ) : (
    <p className="muted">아직 호출한 에이전트가 없어요.</p>
  );
}

export async function showAgentLog(): Promise<void> {
  let L: AgentLogEntry[] = [];
  try {
    L = (await aiApi.log()).log || [];
  } catch {
    L = [];
  }
  openSheet({
    title: '에이전트 동작 기록',
    sub: '모든 계정의 최근 호출이 위에 보여요(시연·디버그용) · 펼치면 보낸 내용과 응답 전문을 불러와요 · 계정마다 최근 80건까지 서버 메모리에만 있어 서버를 다시 켜면 지워져요 (DB에는 처리 시간·결과 같은 기록만 남아요)',
    wide: true,
    body: () => <AgentLogList entries={L} />,
  });
}
