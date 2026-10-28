/* 학습 자료 (API-53·54 · 팀 DB 강좌·도서·자격증, 검색·쪽 나누기 · 5차 scr.resources · scr.res) */
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useParams } from 'react-router';
import { catalogApi } from '@/api/endpoints/catalog';
import type { Resource } from '@/api/types/catalog';
import { paths } from '@/app/paths';
import { resourceTime } from '@/shared/lib/resourceTime';
import { resourceSource } from '@/shared/lib/resourceSource';
import { costText, stageName } from '@/shared/lib/plan';
import { cause } from '@/shared/state/ai';
import { mergeRes, useRes } from '@/shared/state/catalog';
import { Icon } from '@/shared/ui/Icon';
import { Est, Loading, Note, Page, Thumb } from '@/shared/ui/parts';

export function ResKv({ r }: { r: Resource }) {
  return (
    <dl className="kv" style={{ marginTop: 4 }}>
      {r.audience ? (
        <>
          <dt>대상</dt>
          <dd>{r.audience}</dd>
        </>
      ) : null}
      {r.prereq ? (
        <>
          <dt>선수지식</dt>
          <dd>{r.prereq}</dd>
        </>
      ) : null}
      <dt>내용</dt>
      <dd style={{ whiteSpace: 'pre-line', maxHeight: 240, overflowY: 'auto' }}>{r.content || '내용 소개가 없어요'}</dd>
      {r.type === 'course' ? (
        <>
          <dt>커리큘럼</dt>
          <dd>
            {r.curriculum?.items?.length ? (
              <details>
                <summary className="link">
                  {r.curriculum.coverage === 'sample' ? '확인용 샘플' : r.curriculum.coverage === 'partial_outline' ? '일부 공개 목차' : '공개 목차'} {r.curriculum.items.length}개 보기
                </summary>
                <ol style={{ maxHeight: 360, overflowY: 'auto', paddingLeft: 24, marginTop: 8 }}>
                  {r.curriculum.items.map((item, index) => (
                    <li key={index} style={{ marginBottom: 8 }}>
                      {item.section ? <span className="small muted">{item.section} · </span> : null}
                      {item.title}{item.suspended ? ' (제공 중단 표기)' : ''}
                      {item.description ? <small className="muted" style={{ display: 'block' }}>{item.description}</small> : null}
                    </li>
                  ))}
                </ol>
              </details>
            ) : <span className="small muted">별도 목차 미확보 · 소개와 학습 목표를 참고해 주세요.</span>}
          </dd>
        </>
      ) : null}
      <dt>단계·형식</dt>
      <dd>
        {r.stage ? `${r.stage}단계 ${stageName(r.stage)}` : '-'}
        <Est r={r} k="stage" /> · {r.format || '-'}
        <Est r={r} k="format" />
      </dd>
      <dt>시간·비용</dt>
      <dd>
        <span title={r.timeNote || undefined}>{resourceTime(r)}</span> · {costText(r)}
        {r.timeNote ? <><br /><span className="small muted">{r.timeNote}</span></> : null}
        {r.note ? (
          <>
            <br />
            <span className="small muted">{r.note}</span>
          </>
        ) : null}
      </dd>
      {(r.skills || []).length ? (
        <>
          <dt>스킬</dt>
          <dd>{(r.skills || []).join(', ')}</dd>
        </>
      ) : null}
      <dt>출처</dt>
      <dd>{resourceSource(r)}</dd>
      <dt>확인 정보</dt>
      <dd>
        {r.source}
        {r.checked ? ` · 확인일 ${r.checked}` : ''}
        {r.url ? (
          <>
            <br />
            <a className="link" href={r.url} target="_blank" rel="noopener">
              원문 열기 <Icon name="out" />
            </a>
          </>
        ) : null}
      </dd>
    </dl>
  );
}

/* 고른 종류·검색어는 화면을 오가도 남겨 둔다(5차 resState). 받은 목록은 서버 데이터 캐시(TanStack Query)가 남긴다 */
const keep = { kind: '전체', q: '' };
const remember = (kind: string, q: string) => Object.assign(keep, { kind, q });
const PAGE_SIZE = 30;
const listKey = (kind: string, q: string) => ['resources', kind, q] as const;

export function ResourcesPage() {
  const qc = useQueryClient();
  const [kind, setKind] = useState(keep.kind);
  /** 입력 칸 글자 · 찾기를 누른 검색어 */
  const [q, setQ] = useState(keep.q);
  const [term, setTerm] = useState(keep.q);
  const res = useInfiniteQuery({
    queryKey: listKey(kind, term),
    queryFn: async ({ pageParam }) => {
      const r = await catalogApi.resources({ kind: kind === '전체' ? '' : kind, q: term, limit: PAGE_SIZE, offset: pageParam });
      mergeRes(Object.fromEntries(r.items.map((x) => [x.id, x])));
      return r;
    },
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const n = pages.reduce((s, p) => s + p.items.length, 0);
      return n < last.total ? n : undefined;
    },
  });
  /** 종류·검색어를 바꾸면 처음부터 다시 받는다(같은 조건이어도 다시 받음 · 5차와 같음) */
  const reload = (k: string, query: string) => {
    remember(k, query);
    setKind(k);
    setTerm(query);
    void qc.resetQueries({ queryKey: listKey(k, query), exact: true });
  };
  const search = () => reload(kind, q.trim());
  const items = res.data ? res.data.pages.flatMap((p) => p.items) : null;
  const total = res.data ? res.data.pages[res.data.pages.length - 1].total : 0;
  const loading = res.isFetching;
  const err = res.error ? cause(res.error) : null;
  const list = items || [];
  return (
    <Page
      eyebrow="부록"
      title="학습 자료"
      lead="로드맵에 쓰는 등록 강좌·도서·자격증 중 추천 가능한 자료예요. 강좌별 출처·학습 시간·공개 목차를 확인할 수 있어요. 직접 수행하는 실습 과제는 여기 없어요."
    >
      <div className="chips" style={{ marginBottom: 12 }}>
        {['전체', '강좌', '도서', '자격'].map((k) => (
          <button
            key={k}
            className={`chip ${kind === k ? 'on' : ''}`}
            onClick={() => reload(k, q.trim())}
          >
            {k}
          </button>
        ))}
      </div>
      <div className="addrow" style={{ marginBottom: 16 }}>
        <input
          className="input"
          id="resQ"
          value={q}
          placeholder="제목·제공처·스킬로 찾기 (예: RAG, Python, SQL)"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) search();
          }}
        />
        <button className="btn line sm" onClick={search}>
          찾기
        </button>
      </div>
      {err ? (
        <p className="small" style={{ color: 'var(--warn)' }}>
          {err.user}
        </p>
      ) : null}
      <div className="list">
        {list.map((r) => (
          <div className="li" style={{ display: 'block' }} key={r.id}>
            <details className="more">
              <summary style={{ color: 'var(--ink)', fontSize: 15, display: 'flex', width: '100%', gap: 12, alignItems: 'center' }}>
                <Thumb r={r} />
                <span className="grow">
                  <b>{r.title}</b>
                  <small className="muted" style={{ display: 'block', fontWeight: 400, fontSize: 13 }}>
                    {r.kind} · {resourceSource(r)} · <span title={r.timeNote || undefined}>{resourceTime(r)}</span> · {costText(r)}
                  </small>
                </span>
                {r.real ? <span className="tag line">실제 자료</span> : <span className="tag dash">가상</span>}
              </summary>
              <ResKv r={r} />
            </details>
          </div>
        ))}
      </div>
      {loading ? (
        <Loading text="불러오는 중…" />
      ) : items && items.length < total ? (
        <div className="actions">
          <button className="btn line" onClick={() => void res.fetchNextPage()}>
            더 보기 ({items.length} / {total})
          </button>
        </div>
      ) : items ? (
        <p className="small muted">{total}건</p>
      ) : null}
      <Note>
        강좌는 제공처의 영상·학습 시간을 사용해요. 총시간을 확보하지 못한 강좌는 공개 커리큘럼 기준의 ‘계획 예상’ 시간을 일정에 사용하며 상세 화면에 근거를 표시해요. 관리자 화면에서 조정할 수 있어요. 도서 가격·응시료·K-MOOC 수강료는 확인이
        필요해요.
      </Note>
    </Page>
  );
}

export function ResourcePage() {
  const { id = '' } = useParams();
  const r = useRes(id);
  /* 목록을 거치지 않고 들어오면(새로 고침 등) 그 자료만 받아 온다. 못 받으면 5차처럼 '불러오는 중'에 머문다 */
  useQuery({
    queryKey: ['resource', id],
    queryFn: async () => {
      const m = await catalogApi.lookup([id]);
      mergeRes(m);
      return m[id] || null;
    },
    enabled: !r,
  });
  if (!r) return <Page back={paths.resources} title="자료를 불러오는 중이에요" />;
  return (
    <Page back={paths.resources} eyebrow={`${r.kind} · ${r.real ? '실제 자료' : '가상 자료'}`} title={r.title} lead={resourceSource(r)}>
      <div className={`card res-card ${r.type || ''}`}>
        <Thumb r={r} size="lg" />
        <ResKv r={r} />
      </div>
    </Page>
  );
}
