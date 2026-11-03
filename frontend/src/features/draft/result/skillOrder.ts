export type SkillChoice = { course: string | null; books: string[]; enabled?: boolean };
export type Choices = Record<string, SkillChoice>;
export function displayOrder(order: string[], choices: Choices): string[] {
  return [...order.filter(name => choices[name]?.enabled !== false), ...order.filter(name => choices[name]?.enabled === false)];
}
export function moveSkill(order: string[], source: string, target: string, choices: Choices): string[] {
  if (source === target || !order.includes(source) || !order.includes(target) || choices[source]?.enabled === false || choices[target]?.enabled === false) return order;
  const active = order.filter(name => choices[name]?.enabled !== false);
  const from = active.indexOf(source), to = active.indexOf(target);
  active.splice(from, 1); active.splice(to, 0, source);
  return [...active, ...order.filter(name => choices[name]?.enabled === false)];
}

export type DurationEstimate = { method?: string; weeks: number | null; basis: string; course: string | null; books: string[] };
export function currentWeeks(choice: SkillChoice, estimate?: DurationEstimate): number | null {
  if (!estimate || estimate.course !== choice.course || JSON.stringify([...estimate.books].sort()) !== JSON.stringify([...choice.books].sort())) return null;
  return typeof estimate.weeks === 'number' && Number.isInteger(estimate.weeks) && estimate.weeks >= 0 ? estimate.weeks : null;
}
export function totalWeeks(order: string[], choices: Choices, estimates: Record<string,DurationEstimate>): number | null {
  const active=order.filter(name=>choices[name]?.enabled!==false);
  if (!active.length) return order.length ? 0 : null;
  const weeks=active.map(name=>choices[name] ? currentWeeks(choices[name],estimates[name]) : null);
  return weeks.some(value=>value===null) ? null : weeks.reduce<number>((sum,value)=>sum+(value??0),0);
}
