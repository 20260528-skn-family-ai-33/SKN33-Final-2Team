/* 자료 고르기 (5차 P.resPicker · rp-search): 팀 DB 자료가 수천 건이라 검색해서 고른다(관련 스킬 순 · 고른 것은 위에 고정).
   점검 결과 수정(듣게 될 강좌·자료)과 수정 요청(활동 추가)에서 쓴다. 입력하는 대로 바로 찾는다(#102) */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { catalogApi } from '@/api/endpoints/catalog';
import { resourceTime } from '@/shared/lib/resourceTime';
import { resourceSource } from '@/shared/lib/resourceSource';
import { costText } from '@/shared/lib/plan';
import { pickerTerm, searchTerm } from '@/shared/lib/search';
import { cause } from '@/shared/state/ai';
import { useAt } from '@/shared/state/bind';
import { mergeRes, useCatalog } from '@/shared/state/catalog';
import { BCheckArr } from './bound';
import { Icon } from './Icon';
import { Est, Loading, Thumb } from './parts';

const PICK_SIZE = 15;

export function ResPicker({ path, stage, exclude }: { path: string; stage?: number; exclude?: string[] }) {
  const picked = useAt<string[]>(path) || [];
  const res = useCatalog((s) => s.res);
  const [q, setQ] = useState('');
  /** 찾은 검색어. null 은 아직 찾지 않음(안내만 보임), 빈 글자는 검색을 눌러 전체를 본 것 */
  const [term, setTerm] = useState<string | null>(null);
  const skip = (exclude || []).join(',');
  const found = useQuery({
    queryKey: ['resourcePicker', term, stage || 0, skip] as const,
    queryFn: async ({ signal }) => {
      const r = await catalogApi.resources({ q: term || '', stage: stage || 0, exclude: skip, certs: 0, limit: PICK_SIZE }, signal);
      mergeRes(Object.fromEntries(r.items.map((x) => [x.id, x])));
      return r;
    },
    enabled: term !== null,
    /* 새 결과가 올 때까지 앞 결과를 그대로 둔다. 결과는 검색어별로 따로 담기므로 늦게 온 앞 검색 응답이 지금 목록을 덮지 않는다 */
    placeholderData: keepPreviousData,
  });
  /** 입력하는 대로 찾기(#102): 검색어가 달라지면 그 자리에서 바로 찾는다.
   *  조합 중 낱자만 바뀐 입력은 건너뛰고, 입력을 완전히 비우면 처음 안내로 돌아간다(pickerTerm) */
  const onInput = (text: string) => {
    setQ(text);
    const next = pickerTerm(text, term);
    if (next !== term) setTerm(next);
  };
  /** Enter·검색·다시 시도: 지금 입력으로 다시 받는다(빈 칸이면 전체 · 같은 검색어면 다시 받음) */
  const search = () => {
    const next = searchTerm(q);
    if (next === term) void found.refetch();
    else setTerm(next);
  };
  const busy = found.isFetching;
  const list = term === null ? null : found.data;
  const pickedSet = new Set(picked);
  return (
    <div className="rpick">
      {picked.length ? (
        <div className="choices">
          {picked.map((id) => {
            const x = res[id];
            return (
              <label className="choice" key={id}>
                <BCheckArr path={path} value={id} />
                <Thumb r={x} />
                <span className="tx">
                  {x ? x.title : id}
                  <small>{x ? `${x.stage || '-'}단계 · ${x.kind} · ${resourceSource(x)} · ${resourceTime(x)} · ${costText(x)}` : ''}</small>
                </span>
                <span className="ck">
                  <Icon name="check" />
                </span>
              </label>
            );
          })}
        </div>
      ) : null}
      <div className="addrow">
        <input
          className="input"
          placeholder="자료 검색 (예: RAG, Python, 프롬프트)"
          autoComplete="off"
          aria-label="학습 자료 검색"
          value={q}
          onChange={(e) => onInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
              e.preventDefault();
              search();
            }
          }}
        />
        <button type="button" className="btn line sm" onClick={search}>
          검색
        </button>
      </div>
      {/* 찾는 중 표시는 응답이 늦을 때만 보인다(빠르게 칠 때 깜박이지 않게) */}
      <p className={`search-status${busy && list ? ' is-busy' : ''}`} role="status" aria-live="polite" style={{ margin: '6px 0 4px' }}>
        <span className="search-busy" aria-hidden={!(busy && list)}>
          <span className="sp" aria-hidden="true" />
          찾는 중…
        </span>
      </p>
      <div className="choices rp-list" aria-busy={busy}>
        {found.isError ? (
          <p className="small" role="alert" style={{ color: 'var(--warn)' }}>
            {cause(found.error).user}{' '}
            <button type="button" className="btn line sm" onClick={search}>
              다시 시도
            </button>
          </p>
        ) : list ? (
          <>
            {list.items
              .filter((x) => !pickedSet.has(x.id))
              .map((x) => (
                <label className="choice" key={x.id}>
                  <BCheckArr path={path} value={x.id} />
                  <Thumb r={x} />
                  <span className="tx">
                    {x.title}
                    <small>
                      {x.stage || '-'}단계
                      <Est r={x} k="stage" /> · {x.kind} · {resourceSource(x)} · {resourceTime(x)} · {costText(x)}
                    </small>
                  </span>
                  <span className="ck">
                    <Icon name="check" />
                  </span>
                </label>
              ))}
            <p className="small muted">
              {list.total
                ? `${list.total}건 중 ${list.items.length}건${list.total > list.items.length ? ' · 검색어를 더 적으면 좁혀져요' : ''}`
                : '맞는 자료가 없어요. 다른 검색어로 찾아 보세요.'}
            </p>
          </>
        ) : busy ? (
          <Loading text="찾는 중…" />
        ) : (
          <p className="muted small">검색어를 입력하면 바로 등록 자료(팀 DB 강좌·도서·공식 자료)가 보여요. 시작 단계 이후 자료만 보여요.</p>
        )}
      </div>
    </div>
  );
}
