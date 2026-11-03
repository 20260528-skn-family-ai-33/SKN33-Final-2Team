import { expect, it, vi } from 'vitest';
import { ReviewTasks } from './reviewTasks';
function deferred<T>() { let resolve!: (value: T) => void; const work=new Promise<T>(done=>{resolve=done;}); return {work,resolve}; }
it('다른 선택으로 이동 후 복귀해도 진행 중 같은 작업은 한 번만 실행한다', async () => {
  const cache=new ReviewTasks(), a=deferred<{id:string}>(), b=deferred<{id:string}>();
  const loadA=vi.fn(()=>a.work), loadB=vi.fn(()=>b.work);
  const first=cache.run('A','initial',loadA), other=cache.run('B','initial',loadB), back=cache.run('A','initial',loadA);
  await Promise.resolve(); expect(loadA).toHaveBeenCalledOnce(); expect(loadB).toHaveBeenCalledOnce();
  b.resolve({id:'B'}); expect(await other).toEqual({id:'B'});
  a.resolve({id:'A'}); expect(await first).toEqual({id:'A'}); expect(await back).toEqual({id:'A'});
});
it('완료 결과와 제외한 산출물 선택을 복사해서 재사용한다', async () => {
  const cache=new ReviewTasks(), load=vi.fn().mockResolvedValue({selected:['one','two']});
  const value=await cache.run<{selected:string[]}>('A','initial',load); value.selected.pop();
  expect(await cache.run('A','initial',load)).toEqual({selected:['one','two']}); expect(load).toHaveBeenCalledOnce();
  cache.remember('A','picks',{selected:['two']});
  const picks=cache.recall<{selected:string[]}>('A','picks')!; picks.selected.pop();
  expect(cache.recall('A','picks')).toEqual({selected:['two']}); expect(cache.recall('B','picks')).toBeUndefined();
});
it('실패는 캐시하지 않아 명시적으로 다시 시도할 수 있다', async () => {
  const cache=new ReviewTasks(), load=vi.fn().mockRejectedValueOnce(Error('failed')).mockResolvedValue('ok');
  await expect(cache.run('A','initial',load)).rejects.toThrow('failed');
  expect(await cache.run('A','initial',load)).toBe('ok'); expect(load).toHaveBeenCalledTimes(2);
});
it('재제안은 진행 중 중복을 합치지만 완료 후 새 클릭에는 새 작업을 만든다', async () => {
  const cache=new ReviewTasks(), pending=deferred<string>(), load=vi.fn(()=>pending.work);
  const a=cache.run('A','regenerate:SQL',load,true), b=cache.run('A','regenerate:SQL',load,true);
  pending.resolve('v1'); await Promise.all([a,b]); expect(load).toHaveBeenCalledOnce();
  await cache.run('A','regenerate:SQL',load,true); expect(load).toHaveBeenCalledTimes(2);
});
it('복귀 시 같은 선택의 재제안을 기다리되 다른 선택은 기다리지 않는다', async () => {
  const cache=new ReviewTasks(), pending=deferred<string>();
  const work=cache.run('A','regenerate:SQL',()=>pending.work,true);
  let ready=false; const same=cache.waitForChanges('A').then(()=>{ready=true;});
  await cache.waitForChanges('B'); expect(ready).toBe(false);
  pending.resolve('done'); await Promise.all([work,same]); expect(ready).toBe(true);
});
it('만료와 용량 제한을 적용하되 진행 중인 작업은 만료로 중복 생성하지 않는다', async () => {
  let now=0; const cache=new ReviewTasks(2,10,()=>now), load=vi.fn().mockResolvedValue('ok');
  await cache.run('A','initial',load); now=11; await cache.run('A','initial',load); expect(load).toHaveBeenCalledTimes(2);
  await cache.run('B','initial',load); await cache.run('C','initial',load); await cache.run('A','initial',load); expect(load).toHaveBeenCalledTimes(5);
  const pending=deferred<string>(), once=vi.fn(()=>pending.work), a=cache.run('P','initial',once); now=100;
  const b=cache.run('P','initial',once); pending.resolve('p'); await Promise.all([a,b]); expect(once).toHaveBeenCalledOnce();
});
it('로그아웃 등 캐시 정리 뒤 이전 작업이 완료돼도 결과를 다시 보관하지 않는다', async () => {
  const cache=new ReviewTasks(), pending=deferred<string>(); const old=cache.run('A','initial',()=>pending.work);
  cache.clear(); pending.resolve('old'); await old;
  const load=vi.fn().mockResolvedValue('new'); expect(await cache.run('A','initial',load)).toBe('new'); expect(load).toHaveBeenCalledOnce();
});
