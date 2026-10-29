/* 여러 화면이 함께 쓰는 표시 조각 (5차 gp-parts.js·gp-app.js 의 P.page·P.note·P.opsBox·P.agentRow·P.failPage·P.stats·P.thumb … 를 옮김).
   CSS 클래스와 구조는 5차와 같다(화면 모양 유지) */
import type { ReactNode } from 'react';
import type { Resource } from '@/api/types/catalog';
import type { Activity, PlanContent } from '@/api/types/plan';
import { ai, connFor, PROV, type Cause, type ModelRole } from '@/shared/state/ai';
import { resOf } from '@/shared/state/catalog';
import { useGo } from '@/shared/hooks/useGo';
import { Icon } from './Icon';

export function Page(o: { back?: string; eyebrow?: ReactNode; title: ReactNode; lead?: ReactNode; children?: ReactNode; foot?: ReactNode }) {
  const go = useGo();
  return (
    <>
      {o.back ? (
        <div className="wtop">
          <button className="back" aria-label="이전 화면" onClick={() => go(o.back as string)}>
            <Icon name="left" />
          </button>
          <div className="wprog" />
        </div>
      ) : null}
      {o.eyebrow ? <p className="eyebrow">{o.eyebrow}</p> : null}
      <h1 className="t">{o.title}</h1>
      {o.lead ? <p className="lead">{o.lead}</p> : null}
      {o.children}
      {o.foot ? <div className="actions">{o.foot}</div> : null}
    </>
  );
}

export const Note = ({ children, className }: { children: ReactNode; className?: string }) => (
  <p className={`note${className ? ' ' + className : ''}`}>
    <Icon name="info" />
    <span>{children}</span>
  </p>
);

export const Loading = ({ text, style }: { text: ReactNode; style?: React.CSSProperties }) => (
  <div className="loading" style={style}>
    <span className="sp" />
    <span>{text}</span>
  </div>
);

export const Hero = ({ title, lead, foot }: { title: ReactNode; lead: ReactNode; foot?: ReactNode }) => (
  <div className="hero">
    <h1 className="t">{title}</h1>
    <p className="lead" style={{ marginBottom: 0 }}>
      {lead}
    </p>
    {foot ? <div className="actions">{foot}</div> : null}
  </div>
);

type OpsCause = Partial<Pick<Cause, 'text' | 'hint' | 'raw'>>;

/** 자세히 보기(운영자용 · 접힘): 원인·조치·원문 */
export function OpsBox({ items, cls }: { items: [ReactNode, OpsCause | null | undefined][]; cls?: string }) {
  return (
    <details className={`ops ${cls || ''}`}>
      <summary>
        <Icon name="right" />
        자세히 보기 (운영자용)
      </summary>
      <div className="ops-b">
        {items.map(([name, c], i) => (
          <div className="ops-i" key={i}>
            {name ? <b>{name}</b> : null}
            {c && c.text ? (
              <p>
                <span>원인</span>
                {c.text}
              </p>
            ) : null}
            {c && c.hint ? (
              <p>
                <span>조치</span>
                {c.hint}
              </p>
            ) : null}
            {c && c.raw ? (
              <p className="raw">
                <span>원문</span>
                {c.raw}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </details>
  );
}

/** 에이전트 진행 줄: run 작성 중(회전) / ok 완료(체크) / fail 실패(빨간 X · 원인 · 다시 시도) */
export function AgentRow(o: {
  st: 'run' | 'ok' | 'fail' | string;
  name: ReactNode;
  sub?: ReactNode;
  tag?: ReactNode;
  tagCls?: string;
  warn?: boolean;
  failLabel?: string;
  onRetry?: () => void;
  detail?: ReactNode;
}) {
  return (
    <div className={`agent ${o.st}${o.warn ? ' warn' : ''}`}>
      <span className="sp">{o.st === 'ok' ? <Icon name="check" /> : o.st === 'fail' ? <Icon name="x" /> : null}</span>
      <div className="ag-tx">
        <b>{o.name}</b>
        {o.st === 'fail' ? <span className="fl">{o.failLabel || '생성 실패'}</span> : null}
        {o.sub ? <small>{o.sub}</small> : null}
      </div>
      {o.tag ? <span className={`tag ${o.tagCls || ''}`}>{o.tag}</span> : null}
      {o.onRetry ? (
        <button className="btn line sm" onClick={o.onRetry}>
          <Icon name="retry" />
          다시 시도
        </button>
      ) : null}
      {o.st === 'fail' && o.detail ? <div className="detail">{o.detail}</div> : null}
    </div>
  );
}

/** 모드·모델 이름 */
export const via = (role: ModelRole = 'default'): string => `${PROV[ai.mode()]} · ${ai.modelName(role)}`;

/** 생성 중 줄의 설명: 실제 모델이면 모드·모델 이름을, Ollama 모델이 아직 GPU에 없으면 첫 호출이 느리다는 안내를 붙인다 */
export const runSub = (role: ModelRole, t: string): string =>
  !ai.live() ? `${t}…` : connFor(role).state === 'cold' ? `AI 모델을 준비하는 중이에요. 첫 생성은 1~2분 걸릴 수 있어요 · ${via(role)}` : `${t} · ${via(role)}`;

/** 생성 실패 안내: 빨간 안내 → 오류 원인(쉬운 말과 할 일) → 에이전트별 상태 → 자세히 보기(운영자용) → 버튼 */
export function FailPage(o: { title: ReactNode; desc: ReactNode; cause: ReactNode; body?: ReactNode; ops?: ReactNode; foot: ReactNode; hint?: ReactNode }) {
  return (
    <>
      <section className="fail-card" role="alert">
        <span className="ico">
          <Icon name="alert" />
        </span>
        <div>
          <h1>{o.title}</h1>
          <p>{o.desc}</p>
        </div>
      </section>
      <div className="cause">
        <Icon name="info" />
        <p>
          <b>오류 원인 안내:</b> {o.cause}
        </p>
      </div>
      {o.body}
      {o.ops}
      <div className="actions">{o.foot}</div>
      {o.hint ? <p className="small muted fail-hint">{o.hint}</p> : null}
    </>
  );
}

export const CostB = ({ c, unk }: { c: number; unk?: boolean }) => (
  <>
    {c ? c.toLocaleString('ko-KR') : 0}
    <em>원{unk ? '+' : ''}</em>
  </>
);

export const Stats = ({ pl, bare }: { pl: Pick<PlanContent, 'weeks' | 'hours' | 'cost' | 'costUnknown'>; bare?: boolean }) => (
  <div className={`stats ${bare ? 'bare' : ''}`}>
    <div>
      <small>기간</small>
      <b>
        {pl.weeks}
        <em>주</em>
      </b>
    </div>
    <div>
      <small>주당</small>
      <b>
        {pl.hours}
        <em>시간</em>
      </b>
    </div>
    <div>
      <small>예상 비용{pl.costUnknown ? ' · 일부 비용 확인 필요' : ''}</small>
      <b>
        <CostB c={pl.cost} unk={pl.costUnknown} />
      </b>
    </div>
  </div>
);

/** 규칙으로 채운 값(시간·단계·형식)은 '추정'으로 표시한다(팀 DB에 값이 없음 · 2026-10-21 사용자 결정) */
export const Est = ({ r, k }: { r: Resource | null | undefined; k: string }) =>
  r && (r.estimated || []).includes(k) ? (
    <span className="est" title="팀 DB에 값이 없어 규칙으로 정한 추정값이에요">
      추정
    </span>
  ) : null;

/* 자료 그림(팀 DB image_url · 2026-10-22 사용자 결정): 원본 주소에서 바로 불러온다. 화면에 보일 때만 불러오고(lazy) 리퍼러는 보내지 않는다.
   주소가 없거나 못 불러오면 종류 아이콘(강좌·도서·자격·공식 문서·직접 수행 과제)을 보여 준다 */
const TH_TYPE: Record<string, string> = { 강좌: 'course', 도서: 'book', 자격: 'cert', '공식 문서': 'doc' };
const TH_ICON: Record<string, string> = { course: 'play', book: 'book', cert: 'award', doc: 'file', task: 'flag' };

export function Thumb({ r, size, type }: { r?: Partial<Resource> | null; size?: 'xs' | 'md' | 'lg'; type?: string }) {
  const t = type || (r && (r.type || TH_TYPE[r.kind || ''])) || 'doc';
  const src = r && /^https?:\/\//i.test(r.image || '') ? (r.image as string) : '';
  return (
    <span className={`rthumb ${t}${size ? ' ' + size : ''}${src ? '' : ' none'}`} aria-hidden="true">
      {src ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={(e) => {
            const im = e.currentTarget;
            im.parentElement?.classList.add('none');
            im.remove();
          }}
        />
      ) : null}
      <Icon name={TH_ICON[t] || 'file'} />
    </span>
  );
}

export const ActThumb = ({ a, size }: { a: Pick<Activity, 'task' | 'res'>; size?: 'xs' | 'md' | 'lg' }) =>
  a.task ? <Thumb type="task" size={size} /> : <Thumb r={resOf(a.res)} size={size} />;

/** 활동 완료 표시 */
export const Stt = ({ done }: { done: boolean }) => (
  <span className={`stt ${done ? 'done' : 'doing'}`} aria-label={done ? '완료' : '진행 중'}>
    {done ? <Icon name="check" /> : null}
  </span>
);

/** 화면 위쪽 빨간 글자 안내 */
export const WarnText = ({ children }: { children: ReactNode }) => (
  <p className="small" style={{ color: 'var(--warn)' }}>
    {children}
  </p>
);
