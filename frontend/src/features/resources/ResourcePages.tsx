/* 학습 자료 (API-53·54 · 팀 DB 강좌·도서·자격증, 검색·쪽 나누기 · 5차 scr.resources · scr.res) */
import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { catalogApi } from '@/api/endpoints/catalog';
import type { Resource } from '@/api/types/catalog';
import { paths } from '@/app/paths';
import { resourceTime } from '@/shared/lib/resourceTime';
import { resourceSource } from '@/shared/lib/resourceSource';
import { costText, stageName } from '@/shared/lib/plan';
import { searchTerm } from '@/shared/lib/search';
import { cause } from '@/shared/state/ai';
import { mergeRes, resourceDetailQuery, useRes } from '@/shared/state/catalog';
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
      {!r.detailsLoaded ? (
        <>
          <dt>상세</dt>
          <dd><Link className="link" to={paths.resource(r.id)}>전체 소개·상세 보기</Link></dd>
        </>
      ) : null}
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
            ) : r.curriculum?.item_count ? (
              <span className="small muted">공개 목차 {r.curriculum.item_count}개 · 전체 소개·상세 보기에서 확인할 수 있어요.</span>
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

/* 고른 종류·입력한 검색어는 화면을 오가도 남겨 둔다(5차 resState). 받은 목록은 서버 데이터 캐시(TanStack Query)가 남긴다 */
const keep = { kind: '전체', q: '' };
const PAGE_SIZE = 30;
const listKey = (kind: string, q: string) => ['resources', kind, q] as const;

export function ResourcesPage() {
  const qc = useQueryClient();
  const [kind, setKind] = useState(keep.kind);
  /** 입력 칸 글자 · 목록에 쓰는 검색어(글자를 칠 때마다 바로 따라온다 · #102) */
  const [q, setQ] = useState(keep.q);
  const [term, setTerm] = useState(() => searchTerm(keep.q));
  const res = useInfiniteQuery({
    queryKey: listKey(kind, term),
    queryFn: async ({ pageParam, signal }) => {
      const r = await catalogApi.resources({ kind: kind === '전체' ? '' : kind, q: term, limit: PAGE_SIZE, offset: pageParam }, signal);
      mergeRes(Object.fromEntries(r.items.map((x) => [x.id, x])));
      /* 어떤 조건의 결과인지 함께 담아, 새 결과를 기다리는 동안 결과 수 줄이 보이는 목록과 어긋나지 않게 한다 */
      return { ...r, kind, q: term };
    },
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const n = pages.reduce((s, p) => s + p.items.length, 0);
      return n < last.total ? n : undefined;
    },
    /* 새 검색어 결과가 올 때까지 앞 결과를 그대로 두어 목록이 비었다 찼다 하며 깜박이지 않게 한다.
       결과는 검색어별로 따로 담기므로 늦게 온 앞 검색 응답이 지금 목록을 덮지 않는다 */
    placeholderData: keepPreviousData,
  });
  /** 종류·검색어를 정하면 첫 쪽부터 다시 받는다(같은 조건이어도 다시 받음 · 5차와 같음) */
  const reload = (k: string, query: string) => {
    setKind(k);
    setTerm(query);
    void qc.resetQueries({ queryKey: listKey(k, query), exact: true });
  };
  /** 입력하는 대로 찾기: 검색어가 달라지면 그 자리에서 바로 찾는다(조합 중 낱자만 바뀐 입력은 건너뜀) */
  const onInput = (text: string) => {
    keep.q = text;
    setQ(text);
    const next = searchTerm(text);
    if (next !== term) reload(kind, next);
  };
  /** Enter·찾기·종류 칩·다시 시도: 지금 입력으로 다시 받는다 */
  const search = (k = kind) => reload(k, searchTerm(q));
  const items = res.data ? res.data.pages.flatMap((p) => p.items) : null;
  const total = res.data ? res.data.pages[res.data.pages.length - 1].total : 0;
  /** 지금 보이는 목록의 조건(새 결과를 기다리는 동안에는 앞 검색어) */
  const shown = res.data?.pages[0];
  const searching = res.isFetching && !res.isFetchingNextPage;
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
            onClick={() => {
              keep.kind = k;
              search(k);
            }}
          >
            {k}
          </button>
        ))}
      </div>
      <div className="addrow" style={{ marginBottom: 16 }}>
        <input
          className="input"
          id="resQ"
          autoComplete="off"
          aria-label="학습 자료 검색"
          value={q}
          placeholder="제목·제공처·스킬로 찾기 (예: RAG, Python, SQL)"
          onChange={(e) => onInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) search();
          }}
        />
        <button className="btn line sm" onClick={() => search()}>
          찾기
        </button>
      </div>
      {/* 결과 수는 결과가 올 때만 바뀌고, 찾는 중 표시는 응답이 늦을 때만 뒤에 붙는다(빠르게 칠 때 줄이 깜박이지 않게) */}
      <p className={`search-status${searching ? ' is-busy' : ''}`} role="status" aria-live="polite">
        {shown && !err ? <span>{shown.q ? `‘${shown.q}’ 검색 결과 ${total}건` : `${shown.kind === '전체' ? '전체 자료' : shown.kind} ${total}건`}</span> : null}
        <span className="search-busy" aria-hidden={!searching}>
          <span className="sp" aria-hidden="true" />
          {items ? '찾는 중…' : '불러오는 중…'}
        </span>
      </p>
      {err ? (
        <p className="small" role="alert" style={{ color: 'var(--warn)' }}>
          {err.user}{' '}
          <button type="button" className="btn line sm" onClick={() => search()}>
            다시 시도
          </button>
        </p>
      ) : null}
      {shown && !items?.length && !err ? (
        <p className="muted">{shown.q ? '맞는 자료가 없어요. 다른 검색어나 자료 종류로 찾아 보세요.' : '보여 줄 자료가 없어요.'}</p>
      ) : null}
      <div className="list" aria-busy={searching}>
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
      {res.isFetchingNextPage ? (
        <Loading text="불러오는 중…" />
      ) : !items || !items.length ? null : items.length < total ? (
        <div className="actions">
          {/* 새 검색 결과를 기다리는 동안은 앞 검색어의 다음 쪽을 받지 않는다(버튼은 남겨 높이를 유지) */}
          <button className="btn line" disabled={res.isPlaceholderData} onClick={() => void res.fetchNextPage()}>
            더 보기 ({items.length} / {total})
          </button>
        </div>
      ) : (
        <p className="small muted">{total}건</p>
      )}
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
  /* 저장된 상세가 있어도 재진입 때 최신 내용을 받는다. */
  useQuery(resourceDetailQuery(id));
  if (!r?.detailsLoaded) return <Page back={paths.resources} title="자료를 불러오는 중이에요" />;
  return (
    <Page back={paths.resources} eyebrow={`${r.kind} · ${r.real ? '실제 자료' : '가상 자료'}`} title={r.title} lead={resourceSource(r)}>
      <div className={`card res-card ${r.type || ''}`}>
        <Thumb r={r} size="lg" />
        <ResKv r={r} />
      </div>
    </Page>
  );
}
