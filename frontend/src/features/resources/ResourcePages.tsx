/* 학습 자료 (API-53·54 · 팀 DB 강좌·도서·자격증, 검색·쪽 나누기 · 5차 scr.resources · scr.res) */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useRef } from 'react';
import { Link, Navigate, useLocation, useParams, useSearchParams } from 'react-router';
import { catalogApi } from '@/api/endpoints/catalog';
import type { Resource, ResourceSort } from '@/api/types/catalog';
import { paths } from '@/app/paths';
import { resourceTime } from '@/shared/lib/resourceTime';
import { courseDifficulty, courseDifficultyLevel } from '@/shared/lib/courseDifficulty';
import { platformLabel, resourceSource } from '@/shared/lib/resourceSource';
import { costSuffix, costText, stageName } from '@/shared/lib/plan';
import { searchTerm } from '@/shared/lib/search';
import { cause } from '@/shared/state/ai';
import { mergeRes, resourceDetailQuery, useRes } from '@/shared/state/catalog';
import { Icon } from '@/shared/ui/Icon';
import { Est, Note, Page, Thumb } from '@/shared/ui/parts';
import { ResourcePagination } from './ResourcePagination';
import './resourceBrowse.css';

const kinds = ['전체', '강좌', '도서', '자격'];
const kindLabel = (kind: string) => kind === '자격' ? '자격증' : kind;

export function ResKv({ r, showCurriculum = false, listSearch }: { r: Resource; showCurriculum?: boolean; listSearch?: string }) {
  const guideUrl = r.platform === '사내교육' && r.url === paths.resourceCurriculum(r.id) ? r.url : null;
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
          <dd><Link className="link" to={paths.resource(r.id)} state={{ listSearch }}>전체 소개·상세 보기</Link></dd>
        </>
      ) : null}
      {r.type === 'course' ? (
        <>
          <dt>난이도</dt><dd>{courseDifficultyLevel(r.difficulty)}</dd>
          <dt>커리큘럼</dt>
          <dd>
            {r.curriculum?.items?.length ? (
              <details open={showCurriculum || undefined}>
                <summary className="link">
                  {r.platform === '사내교육' ? '실습 목차' : r.curriculum.coverage === 'sample' ? '확인용 샘플' : r.curriculum.coverage === 'partial_outline' ? '일부 공개 목차' : '공개 목차'} {r.curriculum.items.length}개 보기
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
      <dt>{costText(r) ? '시간·비용' : '시간'}</dt>
      <dd>
        <span title={r.timeNote || undefined}>{resourceTime(r)}</span>{costSuffix(r)}
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
        {guideUrl ? (!showCurriculum && <><br /><Link className="link" to={guideUrl} state={{ listSearch }}>사내교육 안내 보기</Link></>) : r.url ? (
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

const PAGE_SIZE = 30;

export function ResourcesPage() {
  const [params, setParams] = useSearchParams();
  const resultsTop = useRef<HTMLParagraphElement>(null);
  const requestedKind = params.get('kind') || '전체';
  const kind = kinds.includes(requestedKind) ? requestedKind : '전체';
  const q = params.get('q') || '';
  const term = searchTerm(q);
  const platform = kind === '강좌' ? params.get('platform') || '' : '';
  const requestedSort = params.get('sort');
  const sort: ResourceSort = requestedSort === 'title_asc' || requestedSort === 'title_desc' ? requestedSort : 'default';
  const requestedPage = Number(params.get('page'));
  const page = Number.isSafeInteger(requestedPage * PAGE_SIZE) && requestedPage > 0 && Number.isInteger(requestedPage) ? requestedPage : 1;
  const res = useQuery({
    queryKey: ['resource-browser', kind, term, platform, sort, page],
    queryFn: async ({ signal }) => {
      const r = await catalogApi.resources({
        kind: kind === '전체' ? '' : kind, q: term, platform, sort, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE,
      }, signal);
      mergeRes(Object.fromEntries(r.items.map((x) => [x.id, x])));
      return { ...r, kind, term, page };
    },
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
  // 상세 화면과 브라우저 뒤로 가기에서 검색 조건과 페이지를 복원한다.
  function update(changes: Record<string, string>, replace = false) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace, preventScrollReset: true });
  }
  function goToPage(n: number) {
    if (n === page) return;
    update({ page: n === 1 ? '' : String(n) });
    resultsTop.current?.scrollIntoView({ block: 'start' });
  }
  const shown = res.data;
  const total = shown?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  // 오래된 링크를 열었거나 결과 수가 줄었다면 마지막 유효 페이지를 다시 요청한다.
  if (shown && !res.isPlaceholderData && page > pages) {
    const next = new URLSearchParams(params);
    if (pages === 1) next.delete('page');
    else next.set('page', String(pages));
    return <Navigate replace to={{ search: next.toString() }} />;
  }
  const sites = shown?.platforms || [];
  const err = res.error ? cause(res.error) : null;
  const searching = res.isFetching;
  const pagination = { page: shown?.page ?? page, pages, disabled: res.isPlaceholderData, onChange: goToPage };
  return (
    <Page
      eyebrow="부록"
      title="학습 자료"
      lead="로드맵에 쓰는 등록 강좌·도서·자격증 중 추천 가능한 자료예요. 강좌별 출처·학습 시간·공개 목차를 확인할 수 있어요. 직접 수행하는 실습 과제는 여기 없어요."
    >
      <div className="resource-toolbar">
        <div className="chips">
          {kinds.map((k) => (
            <button
              key={k}
              className={`chip ${kind === k ? 'on' : ''}`}
              aria-pressed={kind === k}
              onClick={() => { if (k !== kind) update({ kind: k === '전체' ? '' : k, platform: '', page: '' }); }}
            >
              {kindLabel(k)}
            </button>
          ))}
        </div>
        <div className="resource-selects">
          {kind === '강좌' && (
            <select className="input" aria-label="강좌 사이트" value={platform} onChange={(e) => update({ platform: e.target.value, page: '' })}>
              <option value="">모든 강좌 사이트</option>
              {platform && !sites.includes(platform) && <option value={platform}>{platformLabel(platform)}</option>}
              {sites.map((site) => <option key={site} value={site}>{platformLabel(site)}</option>)}
            </select>
          )}
          <select className="input" aria-label="정렬" value={sort} onChange={(e) => update({ sort: e.target.value === 'default' ? '' : e.target.value, page: '' })}>
            <option value="default">기본순</option>
            <option value="title_asc">제목 오름차순</option>
            <option value="title_desc">제목 내림차순</option>
          </select>
        </div>
      </div>
      <form className="addrow" style={{ marginBottom: 16 }} onSubmit={(e) => {
        e.preventDefault();
        if (page === 1) void res.refetch();
        else goToPage(1);
      }}>
        <input
          className="input"
          id="resQ"
          autoComplete="off"
          aria-label="학습 자료 검색"
          value={q}
          placeholder="제목·제공처·스킬로 찾기 (예: RAG, Python, SQL)"
          onChange={(e) => update({ q: e.target.value, ...(searchTerm(e.target.value) !== term && { page: '' }) }, true)}
          onKeyDown={(e) => { if (e.key === 'Enter' && e.nativeEvent.isComposing) e.preventDefault(); }}
        />
        <button className="btn line sm" type="submit">
          찾기
        </button>
      </form>
      {/* 결과 수는 결과가 올 때만 바뀌고, 찾는 중 표시는 응답이 늦을 때만 뒤에 붙는다(빠르게 칠 때 줄이 깜박이지 않게) */}
      <p ref={resultsTop} className={`search-status${searching ? ' is-busy' : ''}`} role="status" aria-live="polite">
        {shown && !err ? <span>{shown.term ? `‘${shown.term}’ 검색 결과` : shown.kind === '전체' ? '전체 자료' : kindLabel(shown.kind)} {total}건{total > 0 && ` · ${shown.page} / ${pages}페이지`}</span> : null}
        <span className="search-busy" aria-hidden={!searching}>
          <span className="sp" aria-hidden="true" />
          {shown ? '찾는 중…' : '불러오는 중…'}
        </span>
      </p>
      {err ? (
        <p className="small" role="alert" style={{ color: 'var(--warn)' }}>
          {err.user}{' '}
          <button type="button" className="btn line sm" onClick={() => void res.refetch()}>
            다시 시도
          </button>
        </p>
      ) : null}
      <div style={{ minHeight: "65vh" }} aria-busy={searching}>
        {shown && !shown.items.length && !err ? (
          <p className="muted">맞는 자료가 없어요. 검색어나 필터를 바꿔 주세요.</p>
        ) : null}
        <div className="list">
          {shown?.items.map((r) => (
            <div className="li" style={{ display: 'block' }} key={r.id}>
              <details className="more">
                <summary style={{ color: 'var(--ink)', fontSize: 15, display: 'flex', width: '100%', gap: 12, alignItems: 'center' }}>
                  <Thumb r={r} />
                  <span className="grow">
                    <b>{r.title}</b>
                    <small className="muted" style={{ display: 'block', fontWeight: 400, fontSize: 13 }}>
                      {kindLabel(r.kind)} · {resourceSource(r)}{r.type === 'course' && ` · ${courseDifficulty(r)}`} · <span title={r.timeNote || undefined}>{resourceTime(r)}</span>{costSuffix(r)}
                    </small>
                  </span>
                  {r.platform !== '사내교육' && (r.real ? <span className="tag line">실제 자료</span> : <span className="tag dash">가상</span>)}
                </summary>
                <ResKv r={r} listSearch={params.toString()} />
              </details>
            </div>
          ))}
        </div>
      </div>
      <ResourcePagination {...pagination} label="페이지 이동" />
      <Note>
        강좌는 제공처의 영상·학습 시간을 사용해요. 총시간을 확보하지 못한 강좌는 공개 커리큘럼 기준의 ‘계획 예상’ 시간을 일정에 사용하며 상세 화면에 근거를 표시해요. 관리자 화면에서 조정할 수 있어요. 응시료·K-MOOC 수강료는 확인이 필요해요. 도서는
        가격을 표시하지 않아요.
      </Note>
    </Page>
  );
}

export function ResourcePage() {
  const { id = '' } = useParams();
  const [params] = useSearchParams();
  const listSearch = useLocation().state?.listSearch;
  const back = listSearch ? `${paths.resources}?${listSearch}` : paths.resources;
  const r = useRes(id);
  /* 저장된 상세가 있어도 재진입 때 최신 내용을 받는다. */
  useQuery(resourceDetailQuery(id));
  if (!r?.detailsLoaded) return <Page back={back} title="자료를 불러오는 중이에요" />;
  const guide = r.platform === '사내교육' && params.get('view') === 'curriculum';
  return (
    <Page back={back} eyebrow={guide ? '사내교육 안내' : r.platform === '사내교육' ? kindLabel(r.kind) : `${kindLabel(r.kind)} · ${r.real ? '실제 자료' : '가상 자료'}`} title={r.title} lead={resourceSource(r)}>
      {guide && <p className="muted">이 과정은 사내교육입니다. 아래 교육비·학습 시간·실습 목차를 확인하고 교육 담당자에게 수강 방법을 문의해 주세요.</p>}
      <div className={`card res-card ${r.type || ''}`}>
        <Thumb r={r} size="lg" />
        <ResKv r={r} showCurriculum={guide} listSearch={listSearch} />
      </div>
    </Page>
  );
}
