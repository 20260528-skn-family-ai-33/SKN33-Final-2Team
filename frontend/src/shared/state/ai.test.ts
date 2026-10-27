/* 실패 원인 바꾸기: 서버 오류 본문·작업에 저장된 원인·네트워크 오류를 화면이 쓰는 한 모양(Cause)으로 */
import { describe, expect, it } from 'vitest';
import { ApiError } from '@/api/client';
import { cause } from './ai';

describe('cause', () => {
  it('서버 오류 본문의 사용자 문구·원인·조치를 그대로 쓴다', () => {
    const c = cause(new ApiError(409, { code: 'STALE_EDIT', kind: 'other', message: '확인한 뒤 데이터가 바뀌었어요', hint: '저장을 다시 눌러 주세요', retryable: false }));
    expect(c).toMatchObject({ kind: 'other', user: '확인한 뒤 데이터가 바뀌었어요', hint: '저장을 다시 눌러 주세요', code: 'STALE_EDIT', retryable: false });
  });

  it('로그인이 끊긴 오류는 서버 문제로 분류한다', () => {
    expect(cause(new ApiError(401, { code: 'AUTH_REQUIRED', message: '로그인이 필요해요' })).kind).toBe('server');
  });

  it('작업에 저장된 원인(kind·text)은 그대로 살린다', () => {
    const c = cause({ kind: 'timeout', text: '응답이 늦어요', hint: '잠시 뒤 다시', raw: 'ReadTimeout' });
    expect(c).toMatchObject({ kind: 'timeout', text: '응답이 늦어요', raw: 'ReadTimeout' });
    expect(c.user).toBeTruthy();
  });

  it('네트워크 오류처럼 모르는 오류는 서버 연결 문제로 보고 원문을 남긴다', () => {
    const c = cause(new TypeError('Failed to fetch'));
    expect(c).toMatchObject({ kind: 'server', raw: 'Failed to fetch' });
  });
});
