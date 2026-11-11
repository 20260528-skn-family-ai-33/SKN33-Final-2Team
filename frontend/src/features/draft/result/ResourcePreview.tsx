import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { resourceDetailQuery } from '@/shared/state/catalog';
import { courseDifficulty } from '@/shared/lib/courseDifficulty';
import { resourceSource } from '@/shared/lib/resourceSource';
import { hrs } from '@/shared/lib/format';
import { ResourceImage } from '@/shared/ui/ResourceImage';
import { paths } from '@/app/paths';
import type { Resource } from './materialRequests';
import './resourcePreview.css';

type Props = { resource: Resource; kind: 'course' | 'book' };
const detailQuery = (id: string) => ({ ...resourceDetailQuery(id), staleTime: 5 * 60_000, refetchOnMount: true });

function bookCredits(author: string): string {
  return author.split(/[;；]/).map(part => part.trim()).filter(Boolean).map((part, index) => {
    const credit = /^([가-힣]+)\s*[:：]\s*(.+)$/s.exec(part);
    if (!credit) return index === 0 ? `지은이 - ${part}` : part;
    const [, role, name] = credit;
    const label = role === '저자' ? '지은이' : role === '역자' ? '옮긴이' : role;
    return `${label} - ${name}`;
  }).join(', ');
}

export function ResourcePreviewButton({ resource, kind, preload }: Props & { preload: boolean }) {
  const client = useQueryClient();
  const trigger = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const internal = kind === 'course' && resource.provider === '사내교육';
  useEffect(() => {
    if (preload && internal) void client.prefetchQuery(detailQuery(resource.id));
  }, [client, internal, preload, resource.id]);
  const label = internal ? '사내교육 안내' : kind === 'book' ? '도서 미리보기' : '강좌 미리보기';
  return <>
    <button ref={trigger} type="button" className="v2-resource-link" aria-haspopup="dialog"
      aria-label={`${resource.title} ${label}`} onClick={event => setAnchor(event.currentTarget.closest('article') ?? event.currentTarget)}>{label}</button>
    {anchor && createPortal(<PreviewPanel resource={resource} kind={kind} label={label} anchor={anchor} onDismiss={() => {
      setAnchor(null);
      trigger.current?.focus({ preventScroll: true });
    }} />, document.body)}
  </>;
}

function positionPanel(panel: HTMLDialogElement, card: HTMLElement) {
  const gap = 12;
  const { width, height } = panel.getBoundingClientRect();
  const rect = card.getBoundingClientRect();
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;
  const right = rect.right + gap;
  const left = rect.left - gap - width;
  const beside = right + width <= vw - gap ? right : left >= gap ? left : null;
  const top = beside === null ? (vh - height) / 2 : Math.max(gap, Math.min(vh - height - gap, rect.top + (rect.height - height) / 2));
  panel.style.left = `${beside ?? (vw - width) / 2}px`;
  panel.style.top = `${top}px`;
}

function CourseIntro({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  const chars = Array.from(text.trim());
  const limit = 180;
  const long = chars.length > limit;
  return <section><h3>과정 소개</h3>
    <p id={id}>{long && !expanded ? chars.slice(0, limit).join('').trimEnd() + '…' : text}</p>
    {long && <button className="resource-preview-more" type="button" aria-controls={id} aria-expanded={expanded}
      onClick={() => setExpanded(value => !value)}>{expanded ? '접기' : '더보기'}</button>}
  </section>;
}

function PreviewPanel({ resource, kind, label, anchor, onDismiss }: Props & { label: string; anchor: HTMLElement; onDismiss: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useId();
  const { data, isError, refetch } = useQuery(detailQuery(resource.id));
  useLayoutEffect(() => {
    const el = dialog.current!;
    el.showModal();
    const place = () => positionPanel(el, anchor);
    place();
    const observer = new ResizeObserver(place);
    observer.observe(el);
    observer.observe(anchor);
    window.addEventListener('resize', place);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', place);
      el.close();
    };
  }, [anchor]);
  const internal = data?.platform === '사내교육' || resource.provider === '사내교육';
  const href = (data?.url || resource.url || '').trim() || (internal ? paths.resourceCurriculum(resource.id) : '');
  const original = /^(https?:\/\/|\/(?!\/))/.test(href) ? URL.parse(href, window.location.href) : null;
  const outline = data?.curriculum;
  const hours = data?.hours ?? resource.hours;
  const cost = data ? data.cost : resource.cost;
  const meta = [
    resourceSource(data) || resource.provider,
    kind === 'book' && data?.author ? bookCredits(data.author) : null,
    kind === 'course' && (data?.difficulty || resource.difficulty) ? courseDifficulty(data ?? resource) : null,
    kind === 'course' && hours && hours > 0 ? hrs(hours) + ((data?.timeStatus ?? resource.timeStatus) === 'estimated' ? ' (추정)' : '') : null,
    cost == null ? null : cost === 0 ? '무료' : `${cost.toLocaleString('ko-KR')}원`,
  ].filter(Boolean);
  // 포털은 카드 아래의 React 트리에 있으므로 패널 안 조작은 카드 선택으로 전달하지 않는다.
  function dismiss() { dialog.current?.close(); onDismiss(); }
  return <dialog ref={dialog} className="roadmap-resource-preview" aria-labelledby={heading}
    onCancel={event => { event.preventDefault(); dismiss(); }} onKeyDown={event => event.stopPropagation()}
    onClick={event => {
      event.stopPropagation();
      if (event.target !== event.currentTarget) return;
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dismiss();
    }}>
    <header><span>{label}</span><button type="button" aria-label="미리보기 닫기" onClick={dismiss}>닫기</button></header>
    <div className="resource-preview-body">
      <div className="resource-preview-title">
        <ResourceImage image={data?.image || resource.image} type={kind} />
        <div><h2 id={heading}>{data?.title || resource.title}</h2><p>{meta.join(' · ')}</p></div>
      </div>
      {data?.content && (kind === 'course' ? <CourseIntro text={data.content} /> : <section><h3>도서 소개</h3><p>{data.content}</p></section>)}
      {resource.knowledge && <section><h3>배울 내용</h3><p>{resource.knowledge}</p></section>}
      {!!outline?.items?.length && <section><h3>{internal ? '실습 목차' : outline.coverage === 'sample' ? '샘플 목차' : '공개 목차'}</h3>
        <ol>{outline.items.map((item, i) => <li key={i}>{item.title}{item.suspended ? ' (제공 중단)' : ''}
          {item.description && <p>{item.description}</p>}</li>)}</ol></section>}
      {isError && <p role="status">상세 정보를 가져오지 못했어요. <button type="button" className="link" onClick={() => void refetch()}>다시 시도</button></p>}
    </div>
    {original && <footer><a href={original.href} target="_blank" rel="noopener noreferrer" aria-label="원본 보기 (새 탭)">원본 보기 <span aria-hidden="true">↗</span></a></footer>}
  </dialog>;
}
