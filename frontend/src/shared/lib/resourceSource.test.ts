import { expect,it } from 'vitest';
import { resourceSource } from './resourceSource';
it('shows platform as well as institution in course lists', () => {
  const base={id:'fixture',title:'Fixture',kind:'강좌'};
  expect(resourceSource({...base,provider:'안양대학교',platform:'KOCW'})).toBe('KOCW · 안양대학교');
  expect(resourceSource({...base,provider:'현대씨앤알㈜',platform:'STEP'})).toBe('STEP · 현대씨앤알㈜');
  expect(resourceSource({...base,provider:'선문대학교',platform:'K-MOOC'})).toBe('K-MOOC · 선문대학교');
  expect(resourceSource({...base,provider:'인프런 / Jason',platform:'Inflearn'})).toBe('인프런 / Jason');
});
