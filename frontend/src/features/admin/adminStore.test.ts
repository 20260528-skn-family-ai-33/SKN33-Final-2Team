/* 관리자 한 건 고치기: 서버에 보낼 값(고칠 때는 바뀐 칸만, 추가할 때는 적은 칸만)과 오류 붙이기 */
import { describe, expect, it } from 'vitest';
import type { AdminColumn, AdminRows } from '@/api/types/admin';
import { dirty, editRows, newEdit, norm, placeErrors } from './adminStore';

const col = (field: string, header: string, o: Partial<AdminColumn> = {}): AdminColumn => ({
  field,
  header,
  readonly: false,
  key: false,
  required: false,
  kind: 'text',
  help: '',
  choices: [],
  default: '',
  options: null,
  ...o,
});
const rows = (sheet: string, columns: AdminColumn[], autoKey = false): AdminRows => ({
  dataset: 'hr',
  sheet,
  columns,
  sheetInfo: { autoKey, deletable: true, help: '', deleteLabel: '퇴직 처리' },
  total: 1,
  rows: [],
});
const emp = rows('직원', [col('code', '사번', { key: true }), col('name', '이름', { required: true }), col('task', '주요 담당 업무', { kind: 'list' }), col('dept_name', '부서 이름', { readonly: true })]);
const row = { code: '20220001', name: '조은호', task: 'RAG; 문서 검색', dept_name: '업무시스템팀' };

describe('norm', () => {
  it('세미콜론·줄바꿈 목록과 공백 차이는 같은 값으로 본다', () => {
    expect(norm('RAG;문서 검색 ')).toBe('RAG; 문서 검색');
    expect(norm('RAG\n문서 검색')).toBe('RAG; 문서 검색');
    expect(norm(null)).toBe('');
  });
});

describe('editRows', () => {
  it('고칠 때는 바뀐 칸만 열쇠와 함께 보낸다(목록 표기 차이는 바뀐 것이 아님)', () => {
    const ed = newEdit('hr', '직원', emp, row);
    ed.vals.task = 'RAG;문서 검색';
    ed.vals.name = '조은호2';
    expect(editRows(ed, false)).toEqual([{ sheet: '직원', key: { code: '20220001' }, values: { name: '조은호2' } }]);
    expect(dirty(ed)).toBe(true);
  });

  it('바꾸지 않았으면 저장할 것이 없다', () => {
    const ed = newEdit('hr', '직원', emp, row);
    expect(dirty(ed)).toBe(false);
    expect(editRows(ed, false)[0].values).toEqual({});
  });

  it('삭제(퇴직 처리)는 열쇠만 보낸다', () => {
    const ed = newEdit('hr', '직원', emp, row);
    expect(editRows(ed, true)).toEqual([{ sheet: '직원', key: { code: '20220001' }, delete: true }]);
  });

  it('추가할 때는 적은 칸만, 번호를 서버가 정하는 열쇠는 빼고 보낸다', () => {
    const course = rows('강좌', [col('id', '강좌 ID', { key: true }), col('title', '강좌 이름', { required: true }), col('provider', '제공 기관'), col('url', '주소')], true);
    const ed = newEdit('education', '강좌', course, null);
    ed.vals.title = '새 강좌';
    ed.vals.provider = 'K-MOOC';
    expect(editRows(ed, false)).toEqual([{ sheet: '강좌', key: null, values: { title: '새 강좌', provider: 'K-MOOC' } }]);
  });
});

describe('placeErrors', () => {
  it('패널에 있는 칸의 오류는 칸 옆에, 없는 칸(열쇠 등)의 오류는 위에 모은다', () => {
    const ed = newEdit('hr', '직원', emp, row);
    placeErrors(ed, [
      {
        sheet: '직원',
        row: 0,
        key: '20220001',
        label: '조은호',
        action: 'error',
        changes: [],
        warnings: [],
        tags: [],
        errors: [
          { col: '이름', msg: '비울 수 없어요' },
          { col: '사번', msg: '이미 있는 사번이에요' },
        ],
      },
    ]);
    expect(ed.errs).toEqual({ 이름: '비울 수 없어요' });
    expect(ed.msgs).toEqual(['사번 · 이미 있는 사번이에요']);
  });
});
