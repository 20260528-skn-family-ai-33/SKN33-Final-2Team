/* 자료 고르기 (5차 P.resPicker · rp-search): 팀 DB 자료가 수천 건이라 검색해서 고른다(관련 스킬 순 · 고른 것은 위에 고정).
   점검 결과 수정(듣게 될 강좌·자료)과 수정 요청(활동 추가)에서 쓴다 */
import { useState } from 'react';
import { catalogApi } from '@/api/endpoints/catalog';
import type { Resource } from '@/api/types/catalog';
import { hrs } from '@/shared/lib/format';
import { costText } from '@/shared/lib/plan';
import { cause } from '@/shared/state/ai';
import { useAt } from '@/shared/state/bind';
import { mergeRes, useCatalog } from '@/shared/state/catalog';
import { BCheckArr } from './bound';
import { Icon } from './Icon';
import { Est, Loading, Thumb } from './parts';

export function ResPicker({ path, stage, exclude }: { path: string; stage?: number; exclude?: string[] }) {
  const picked = useAt<string[]>(path) || [];
  const res = useCatalog((s) => s.res);
  const [q, setQ] = useState('');
  const [list, setList] = useState<{ items: Resource[]; total: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const search = async () => {
    setLoading(true);
    setErr('');
    try {
      const r = await catalogApi.resources({ q: q.trim(), stage: stage || 0, exclude: (exclude || []).join(','), certs: 0, limit: 15 });
      mergeRes(Object.fromEntries(r.items.map((x) => [x.id, x])));
      setList(r);
    } catch (e) {
      setErr(cause(e).user);
    }
    setLoading(false);
  };
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
                  <small>{x ? `${x.stage || '-'}단계 · ${x.kind} · ${x.provider} · ${hrs(x.hours || 0)} · ${costText(x)}` : ''}</small>
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
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void search();
            }
          }}
        />
        <button type="button" className="btn line sm" onClick={() => void search()}>
          검색
        </button>
      </div>
      <div className="choices rp-list">
        {loading ? (
          <Loading text="찾는 중…" />
        ) : err ? (
          <p className="small" style={{ color: 'var(--warn)' }}>
            {err}
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
                      <Est r={x} k="stage" /> · {x.kind} · {x.provider} · {hrs(x.hours || 0)}
                      <Est r={x} k="hours" /> · {costText(x)}
                    </small>
                  </span>
                  <span className="ck">
                    <Icon name="check" />
                  </span>
                </label>
              ))}
            <p className="small muted">
              {list.total}건 중 {list.items.length}건{list.total > list.items.length ? ' · 검색어를 더 적으면 좁혀져요' : ''}
            </p>
          </>
        ) : (
          <p className="muted small">검색하면 등록 자료(팀 DB 강좌·도서·공식 자료)가 보여요. 시작 단계 이후 자료만 보여요.</p>
        )}
      </div>
    </div>
  );
}
