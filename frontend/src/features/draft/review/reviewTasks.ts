/** Per-tab review reuse. Pending work survives navigation; failures are never cached. */
export class ReviewTasks {
  private flights = new Map<string, {scope: string; operation: string; work: Promise<unknown>}>();
  private values = new Map<string, {value: unknown; expires: number}>();
  constructor(private limit = 24, private ttl = 10 * 60_000, private now = () => Date.now()) {}
  run<T>(scope: string, operation: string, load: () => Promise<T>, fresh = false): Promise<T> {
    const key = JSON.stringify([scope, operation]);
    const pending = this.flights.get(key);
    if (pending) return pending.work.then(value => structuredClone(value) as T);
    const cached = this.values.get(key);
    if (!fresh && cached && cached.expires > this.now()) {
      this.values.delete(key); this.values.set(key, cached);
      return Promise.resolve(structuredClone(cached.value) as T);
    }
    this.values.delete(key);
    const work = Promise.resolve().then(load).then(value => {
      if (this.flights.get(key)?.work === work) {
        this.values.set(key, {value: structuredClone(value), expires: this.now() + this.ttl});
        while (this.values.size > this.limit) this.values.delete(this.values.keys().next().value!);
      }
      return value;
    }).finally(() => { if (this.flights.get(key)?.work === work) this.flights.delete(key); });
    this.flights.set(key, {scope, operation, work});
    return work.then(value => structuredClone(value));
  }
  remember<T>(scope: string, operation: string, value: T): void {
    this.values.set(JSON.stringify([scope, operation]), {value: structuredClone(value), expires: this.now() + this.ttl});
    while (this.values.size > this.limit) this.values.delete(this.values.keys().next().value!);
  }
  recall<T>(scope: string, operation: string): T | undefined {
    const key = JSON.stringify([scope, operation]), row = this.values.get(key);
    if (!row || row.expires <= this.now()) { this.values.delete(key); return; }
    return structuredClone(row.value) as T;
  }
  async waitForChanges(scope: string): Promise<void> {
    await Promise.allSettled([...this.flights.values()].filter(row => row.scope === scope && row.operation.startsWith('regenerate:')).map(row => row.work));
  }
  forget(scope: string): void {
    for (const key of this.values.keys()) if ((JSON.parse(key) as string[])[0] === scope) this.values.delete(key);
  }
  clear(): void { this.values.clear(); this.flights.clear(); }
}
export const reviewTasks = new ReviewTasks();
