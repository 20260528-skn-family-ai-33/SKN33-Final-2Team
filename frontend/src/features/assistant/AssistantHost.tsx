/* 사내 생활 도우미 (우측 하단 · API-09 · 5차 gp-reg.js)
   서버의 규정 에이전트가 LLM 지시문으로 질문을 분류해 유형에 맞게만 답한다.
     규정 질문 → 내 직원 구분의 팀 DB 규정 근거 조항과 함께(규정에 없으면 답하지 않고 담당 부서 안내) · 맞는 규정 묶음이 없으면 '적용 대상 아님'
     일반 질문 → 사내 생활은 가상 사내 홈페이지 메뉴 안내, 업무·학습은 일반 답변, 앱 사용법은 메뉴 안내
     범위 밖(주식·날씨·스포츠 등) → 답하지 않음 · 애매하면 되묻기 */
import { useEffect, useRef } from 'react';
import type { AssistantAnswer } from '@/api/endpoints/assistant';
import type { Article } from '@/api/types/catalog';
import { legacyToPath } from '@/app/paths';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { article, missLabel, regOf, regSet } from '@/shared/lib/reg';
import { ai, errText, type Cause } from '@/shared/state/ai';
import { useCatalog } from '@/shared/state/catalog';
import { toast } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { OpsBox } from '@/shared/ui/parts';
import { ask, clearLog, closeAssistant, openAssistant, pick, retry, setInput, stop, useAssistant, type Msg } from './assistantStore';

const SUGS = ['교육비 지원을 받을 수 있나요?', '통근버스 시간표는 어디서 봐요?', '승진 기준이 궁금해요', '근무성적평정은 언제 하나요?', 'RAG가 뭐예요?', '로드맵 기간을 바꾸고 싶어요'];
/** 대화가 이만큼 길어지면 '새 대화'를 권한다(넘기는 양은 줄이지 않음) */
const LONG_TURNS = 10;
const LV: Record<string, [string, string]> = { ok: ['근거 확인', 'acc'], missing: ['관련 자료 미확보', 'warn'], unclear: ['일부만 확인', 'warn'] };

const setLabel = () => regSet()?.label || '규정';
const artHead = (a: Article, lead?: string) =>
  `${lead ? `${lead} · ` : ''}「${regOf(a.reg)?.name || ''}」 ${a.no}(${a.title})${a.chapter ? ` · ${a.chapter}` : ''}`;
/** 출처 줄: 근거 조항이 나온 규정마다 이름 · 개정 차수 · 원문 쪽 */
const srcLine = (arts: Article[]) => {
  const by = new Map<string, number[]>();
  arts.forEach((a) => {
    if (!by.has(a.reg)) by.set(a.reg, []);
    by.get(a.reg)!.push(a.page);
  });
  return [...by.entries()]
    .map(([k, pages]) => {
      const r = regOf(k);
      return `「${r?.name || ''}」 ${r?.rev || ''}${r?.effective ? ` · 시행 ${r.effective}` : ''} · 원문 ${[...new Set(pages)].join('·')}쪽`;
    })
    .join(' / ');
};
const List = ({ h, arr }: { h: string; arr?: string[] }) =>
  arr && arr.length ? (
    <>
      <h4>{h}</h4>
      <ul>
        {arr.map((m, i) => (
          <li key={i}>{m}</li>
        ))}
      </ul>
    </>
  ) : null;
/** 받침에 맞는 조사 (은/는) */
const eun = (w: string) => {
  const c = String(w).charCodeAt(String(w).length - 1);
  return c >= 0xac00 && c <= 0xd7a3 ? ((c - 0xac00) % 28 ? '은' : '는') : '은(는)';
};

function RegCard({ a }: { a: AssistantAnswer }) {
  const go = useGo();
  useCatalog((s) => s.articles);
  const { summary, apply, more } = a;
  if (a.kind === 'out')
    return (
      <div className="ans">
        <div className="who">
          <Icon name="chat" />
          사내 생활 도우미 <span className="tag line">범위 밖</span>
        </div>
        <p className="sum">업무·사내 생활과 관련 없는 질문이라 답하지 않아요.</p>
        <p className="small muted">규정, 사내 생활(사내 홈페이지 안내), 업무·학습, GrowPath 사용법에 대해 물어봐 주세요.</p>
      </div>
    );
  if (a.kind === 'clarify')
    return (
      <div className="ans">
        <div className="who">
          <Icon name="chat" />
          사내 생활 도우미 <span className="tag">확인 필요</span>
        </div>
        <p className="sum">{a.question}</p>
        {a.options && a.options.length ? (
          <div className="clar">
            {a.options.map((o) => (
              <button className="chip" key={o} onClick={() => pick(o)}>
                {o}
              </button>
            ))}
          </div>
        ) : null}
        <p className="small muted">아니면 조금 더 구체적으로 적어 주세요.</p>
      </div>
    );
  if (a.kind === 'regulation' && a.level === 'scope') {
    const refs = (a.ref || []).map(article).filter(Boolean) as Article[];
    return (
      <div className="ans">
        <div className="who">
          <Icon name="scale" />
          규정 에이전트 <span className="tag warn">적용 대상 아님</span>
        </div>
        <h4>답변 요약</h4>
        <p className="sum">{summary}</p>
        {apply ? <p>{apply}</p> : null}
        {refs.length ? (
          <details>
            <summary>
              <Icon name="right" />
              참고로 찾은 조항 (적용 대상 아님)
            </summary>
            <div className="basis">
              {refs.map((x) => (
                <div className="art" key={x.id}>
                  <b>{artHead(x)}</b>
                  {x.text}
                </div>
              ))}
              <p className="src">{srcLine(refs)}</p>
            </div>
          </details>
        ) : null}
        <p className="src">등록된 규정의 적용 대상이 아닌 직원에게는 그 규정으로 답하지 않아요.</p>
      </div>
    );
  }
  if (a.kind === 'regulation' && a.level === 'none')
    return (
      <div className="ans">
        <div className="who">
          <Icon name="scale" />
          규정 에이전트 <span className="tag warn">등록된 규정에서 확인 불가</span>
        </div>
        <p className="sum">{summary || `등록된 ${setLabel()}에 이 내용이 명시돼 있지 않아 답하지 않아요.`}</p>
        <p>인사 제도에 관한 내용은 인사 담당 부서(인재경영실)에 문의해 주세요.</p>
        <p className="src">등록된 규정 원문에 있는 내용에만 답해요. 짐작이나 다른 기관 사례로 답하지 않아요.</p>
      </div>
    );
  if (a.kind === 'general' && a.source === 'intranet') {
    /* 사내 생활: 가상 사내 홈페이지 메뉴 안내만 보여 준다(구체적인 값은 지어내지 않음) */
    const items = (a.intranet || []).map((id) => D.intranet.find((x) => x.id === id)).filter(Boolean) as typeof D.intranet;
    return (
      <div className="ans">
        <div className="who">
          <Icon name="chat" />
          사내 생활 도우미 <span className="tag">사내 생활 안내</span>
        </div>
        {items.length ? (
          <>
            <h4>답변 요약</h4>
            <p className="sum">
              {items[0].title}
              {eun(items[0].title)} 사내 홈페이지(가상) › {items[0].menu}에서 확인할 수 있어요.
            </p>
            <ul className="intra">
              {items.map((x) => (
                <li key={x.id}>
                  <b>{x.menu}</b>
                  <span>{x.covers}</span>
                  <small>문의 · {x.dept}</small>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <p className="sum">사내 홈페이지(가상) 안내 자료에서 맞는 메뉴를 찾지 못했어요.</p>
            <p>공지사항을 확인하거나 담당 부서에 문의해 주세요.</p>
          </>
        )}
        <p className="src">가상 사내 홈페이지의 메뉴 안내예요. 식단·시간표·금액 같은 실제 내용은 사내 홈페이지에서 확인해 주세요.</p>
      </div>
    );
  }
  if (a.kind === 'general') {
    /* 일반 답변 카드: 규정 근거 없이 요약 → 설명 → 더 볼 것 → 바로 가기(서버가 5차 화면 ID 로 줌) */
    const links = a.links || [];
    return (
      <div className="ans">
        <div className="who">
          <Icon name="chat" />
          사내 생활 도우미 <span className="tag">{a.source === 'app' ? '사용법 안내' : '일반 답변'}</span>
        </div>
        <h4>답변 요약</h4>
        <p className="sum">{summary}</p>
        {apply ? <p>{apply}</p> : null}
        <List h="더 알아볼 것" arr={more} />
        {links.length ? (
          <p className="go">
            {links.map(([r, l]) => (
              <button className="link" key={r} onClick={() => go(legacyToPath(r))}>
                {l} <Icon name="right" />
              </button>
            ))}
          </p>
        ) : null}
        <p className="src">규정 근거가 아닌 일반 답변이에요. 기관 기준이 필요한 내용은 담당 부서에 확인해 주세요.</p>
      </div>
    );
  }
  const [lvT, lvC] = LV[a.level] || LV.unclear;
  const arts = (a.basis || []).map(article).filter(Boolean) as Article[];
  /* 실무직 관리규정 제3조(다른 규정과의 관계)는 근거에 있으면 '기본 원칙'으로 표시한다 */
  const base = arts.find((x) => x.no === '제3조' && regOf(x.reg)?.name === '실무직 관리규정') || null;
  return (
    <div className="ans">
      <div className="who">
        <Icon name="scale" />
        규정 에이전트 <span className={`tag ${lvC}`}>{lvT}</span>
      </div>
      <h4>답변 요약</h4>
      <p className="sum">{summary}</p>
      {apply ? (
        <>
          <h4>내 상황에 적용</h4>
          <p>{apply}</p>
        </>
      ) : null}
      <List h="추가로 확인할 것" arr={more} />
      {arts.length ? (
        <details>
          <summary>
            <Icon name="right" />
            규정 근거 보기
          </summary>
          <div className="basis">
            {arts.map((x) => (
              <div className="art" key={x.id}>
                <b>{artHead(x, base && x.id === base.id ? '기본 원칙' : '')}</b>
                {x.text}
              </div>
            ))}
            {a.missing && a.missing.length ? (
              <div className="art">
                <b>등록되지 않은 기준</b>
                {a.missing.map(missLabel).join(', ')} — 원문·별표가 등록되지 않아 내용은 답할 수 없어요.
              </div>
            ) : null}
            <p className="src">
              {regSet()?.org || '한국수자원공사'} {srcLine(arts)}
            </p>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function Bubble({ m, i }: { m: Msg; i: number }) {
  if (m.me) return <div className="msg me">{m.t}</div>;
  return (
    <div className="msg bot">
      {m.a ? (
        <RegCard a={m.a} />
      ) : m.fail ? (
        <div className="ans fail">
          <div className="who">
            <Icon name="alert" />
            사내 생활 도우미 <span className="tag fail">답변 실패</span>
          </div>
          <p className="sum">답변을 받지 못했어요.</p>
          <p>{errText(m.fail as Cause)}</p>
          <OpsBox items={[['', m.fail]]} />
          <p className="go">
            <button className="btn line sm" onClick={() => retry(i)}>
              <Icon name="retry" />
              다시 시도
            </button>
          </p>
        </div>
      ) : m.stop ? (
        <div className="ans stop">
          <p className="sum">{m.cut ? '답을 받는 중에 페이지를 새로 고쳐 답이 끊겼어요.' : '답변을 멈췄어요.'}</p>
          <p className="go">
            <button className="btn line sm" onClick={() => retry(i)}>
              <Icon name="retry" />
              다시 시도
            </button>
          </p>
        </div>
      ) : (
        <div className="plain muted wait">{ai.live() ? '답을 쓰고 있어요. 규정 질문이면 원문도 찾아볼게요…' : '답변을 찾고 있어요…'}</div>
      )}
    </div>
  );
}

export function AssistantHost() {
  const st = useAssistant();
  const logRef = useRef<HTMLDivElement>(null);
  const inRef = useRef<HTMLInputElement>(null);
  /* 말풍선이 늘거나 안내 줄이 생기면 마지막 말풍선이 가려지지 않게 아래로 맞춘다 */
  useEffect(() => {
    const b = logRef.current;
    if (b) b.scrollTop = b.scrollHeight;
  }, [st.log, st.hint, st.open]);
  const turns = st.log.filter((m) => !m.me && m.a).length;
  return (
    <>
      <button
        className={`fab${st.fresh ? ' new' : ''}`}
        id="regFab"
        aria-label="사내 생활 도우미 열기"
        hidden={st.open}
        onClick={() => {
          openAssistant();
          setTimeout(() => inRef.current?.focus(), 30);
        }}
      >
        <Icon name="chat" />
        <span>사내 생활 도우미</span>
      </button>
      <section className="regp" id="regPanel" hidden={!st.open} aria-label="사내 생활 도우미">
        <div className="sheet-h">
          <span className="avatar">
            <Icon name="chat" />
          </span>
          <div>
            <b>사내 생활 도우미</b>
            <small id="regSub">업무·사내 생활 질문에 답해요 · 규정 질문은 등록된 규정 원문에서 근거를 찾아요</small>
          </div>
          <button
            className="btn ghost sm reg-new"
            title="지금 대화를 지우고 새로 시작"
            onClick={() => {
              if (!st.log.length) {
                toast('이미 새 대화예요');
                return;
              }
              useAssistant.setState({ confirm: true });
            }}
          >
            <Icon name="plus" />새 대화
          </button>
          <button className="x" aria-label="닫기" onClick={closeAssistant}>
            <Icon name="x" />
          </button>
        </div>
        <div className="reg-confirm" id="regConfirm" hidden={!st.confirm} role="alert">
          <p>지금 대화를 지우고 새로 시작할까요? 지운 대화는 다시 볼 수 없어요.</p>
          <div>
            <button className="btn line sm" onClick={() => useAssistant.setState({ confirm: false })}>
              취소
            </button>
            <button
              className="btn pri sm"
              onClick={() => {
                useAssistant.setState({ confirm: false });
                clearLog();
                toast('새 대화를 시작했어요');
                inRef.current?.focus();
              }}
            >
              새로 시작
            </button>
          </div>
        </div>
        <div className="chat-b" id="regLog" aria-live="polite" ref={logRef}>
          <div className="msg bot">
            <div className="plain">
              업무·학습·사내 생활에 대해 물어보세요. 교육 지원·근무시간·보수처럼 규정에 관한 질문은 등록된 원문의 근거 조항과 함께, 식당·통근버스·복지몰 같은 사내 생활은 사내
              홈페이지(가상) 메뉴로 안내해 드려요. 업무와 관계없는 질문(주식·날씨·스포츠 등)에는 답하지 않아요. 앞 이야기에 이어서 물어봐도 돼요.
            </div>
          </div>
          {st.log.map((m, i) => (
            <Bubble key={i} m={m} i={i} />
          ))}
        </div>
        <div className="chat-f">
          <p className="reg-long" id="regLong" hidden={turns < LONG_TURNS}>
            대화가 길어졌어요. 앞 대화를 모두 함께 보내서 답이 느려질 수 있고, 모델에 따라 앞부분을 놓칠 수 있어요. 주제가 바뀌었다면 ‘새 대화’로 시작해 보세요.
          </p>
          <div className="sugs">
            {SUGS.map((s) => (
              <button className="chip" key={s} disabled={st.running} onClick={() => !st.running && ask(s)}>
                {s}
              </button>
            ))}
          </div>
          <form
            className="chat-in"
            id="regForm"
            onSubmit={(e) => {
              e.preventDefault();
              if (ask(st.input)) setInput('');
            }}
          >
            <input className="input" id="regIn" ref={inRef} placeholder="업무·사내 생활에 대해 물어보세요" autoComplete="off" aria-label="질문" value={st.input} onChange={(e) => setInput(e.target.value)} />
            <button className="btn pri" id="regSend" aria-label="보내기" hidden={st.running}>
              <Icon name="send" />
            </button>
            <button type="button" className="btn line stop" id="regStop" aria-label="답변 멈추기" title="답변 멈추기" hidden={!st.running} onClick={stop}>
              <Icon name="stop" />
            </button>
          </form>
          <p className="reg-hint" id="regHint" role="status" hidden={!st.hint}>
            {st.hint}
          </p>
        </div>
      </section>
    </>
  );
}
