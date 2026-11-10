import { useId, useLayoutEffect, useRef, useState } from 'react';
import './taskDescription.css';

export function TaskDescription({ text }: { text: string }) {
  const id = useId();
  const content = useRef<HTMLSpanElement>(null);
  const [expandedText, setExpandedText] = useState<string | null>(null);
  const [overflows, setOverflows] = useState(false);
  const expanded = expandedText === text;
  const headings = [...text.matchAll(/(?:^|\n|\s)(만들\s*것|필수\s*항목|제출물|평가\s*기준)\s*[:：]/g)];
  const sections = headings.map((heading, index) => ({
    label: heading[1].replace(/\s+/g, '') === '만들것' ? '만들 것' : heading[1].replace(/\s+/g, '') === '필수항목' ? '필수 항목' : heading[1].replace(/\s+/g, '') === '평가기준' ? '평가 기준' : '제출물',
    body: text.slice(heading.index! + heading[0].length, headings[index + 1]?.index ?? text.length).trim().replace(/[;；]+$/, '.'),
  }));
  const introduction = headings.length ? text.slice(0, headings[0].index).trim() : '';
  const creation = sections.find(section => section.label === '만들 것');
  const preview = creation ? `만들 것: ${creation.body}` : text;
  const hasHiddenSections = !!creation && (sections.length > 1 || !!introduction);
  useLayoutEffect(() => {
    const element = content.current;
    if (!element) return;
    const measure = () => setOverflows(element.scrollHeight > parseFloat(getComputedStyle(element).lineHeight) * 3 + 1);
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    measure();
    return () => observer.disconnect();
  }, [text]);
  return <span className="task-description">
    <span ref={content} id={id} className={`task-description-text${expanded ? ' is-expanded' : ''}`}>
      {expanded && sections.length ? <>
        {introduction && <span className="task-description-intro">{introduction}</span>}
        {sections.map((section, index) => <span className="task-description-section" key={index}>
          <b className="task-description-heading">{section.label}</b>
          <span className="task-description-body">{section.body}</span>
        </span>)}
      </> : preview}
    </span>
    {(overflows || hasHiddenSections) && <button type="button" className="link task-description-toggle" aria-label={expanded ? '산출물 설명 접기' : '산출물 설명 더보기'} aria-expanded={expanded} aria-controls={id}
      onClick={event => { event.preventDefault(); event.stopPropagation(); setExpandedText(expanded ? null : text); }}>
      {expanded ? '접기' : '더보기'}
    </button>}
  </span>;
}
