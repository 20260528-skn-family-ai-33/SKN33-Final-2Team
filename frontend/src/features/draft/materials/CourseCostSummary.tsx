import './courseCostSummary.css';
import type { Choices } from '../result/skillOrder';

type Course = { id: string; title: string; cost: number | null; why: string; knowledge: string };
export function CourseCostSummary({ skills, choices, order }: { skills: { name: string; courses: Course[] }[]; choices: Choices; order: string[] }) {
  const selected = new Map<string, Course>();
  for (const name of order) {
    const choice = choices[name];
    if (!choice || choice.enabled === false || !choice.course) continue;
    const course = skills.find(skill => skill.name === name)?.courses.find(item => item.id === choice.course);
    if (course) selected.set(course.id, course);
  }
  const courses = [...selected.values()];
  const known = (course: Course) => typeof course.cost === 'number' && Number.isFinite(course.cost) && course.cost >= 0;
  const total = courses.reduce((sum, course) => sum + (known(course) ? course.cost! : 0), 0);
  const unknown = courses.filter(course => !known(course)).length;
  return <aside className="course-cost-summary" aria-label="선택 강좌 예상 비용">
    <h3>예상 비용</h3>
    {courses.length ? <ol>{courses.map(course => <li key={course.id}><b title={course.title}>{course.title}</b>{(course.knowledge || course.why) && <p title={course.knowledge || course.why}>{course.knowledge || course.why}</p>}<span>{known(course) ? `${course.cost!.toLocaleString()}원` : '가격 미확인'}</span></li>)}</ol> : <p className="muted">선택한 강좌가 없어요.</p>}
    <div className="course-cost-total" aria-live="polite"><span>총</span><b>{total.toLocaleString()}원{unknown ? ' + 미확인' : ''}</b></div>
    {unknown > 0 && <p className="muted">가격 미확인 {unknown}개는 합계에서 제외</p>}
    <p className="course-cost-note muted">선택 강좌 기준 · 도서 제외</p>
  </aside>;
}
