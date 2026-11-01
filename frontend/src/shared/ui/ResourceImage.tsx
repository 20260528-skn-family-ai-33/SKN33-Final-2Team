import { useState } from 'react';

export function ResourceImage({ image, type, alt = '', className }: {
  image?: string | null; type: string; alt?: string; className?: string;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const original = image && /^https?:\/\//i.test(image) ? image : '';
  const kind = type === 'book' || type === 'cert' ? type : 'course';
  const fallback = `/images/resource-${kind}.svg?v=20261101`;
  const src = original && failed !== original ? original : fallback;
  return <img className={className} src={src} alt={alt} loading="lazy" decoding="async" referrerPolicy="no-referrer"
    data-fallback={src === fallback ? kind : undefined} draggable={false}
    onError={() => { if (src !== fallback) setFailed(original); }} />;
}
