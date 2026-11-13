import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Wait } from './Wait';

describe('대기 문구의 점', () => {
  it.each(['계산 중…', '계산 중...'])('%s 는 글자를 그대로 두고 끝의 말줄임표만 점 세 개로 바꾼다', (text) => {
    const html = renderToStaticMarkup(<Wait>{text}</Wait>);
    expect(html).toBe('<span class="wait-text">계산 중<span class="wait-dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span></span>');
  });

  it('말줄임표로 끝나지 않는 문구는 그대로 보여 준다', () => {
    expect(renderToStaticMarkup(<Wait>준비 실패</Wait>)).toBe('준비 실패');
    expect(renderToStaticMarkup(<Wait>다시 제안받기</Wait>)).toBe('다시 제안받기');
  });
});
