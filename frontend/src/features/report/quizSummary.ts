type Evidence={skill:string;concept?:string;pre:string;post:string};
export function quizSummary(evidence:Evidence[]){
 const rows:Record<string,{label:string;pre:number;post:number;count:number}>={};
 for(const q of evidence){
  const key=JSON.stringify([q.skill,q.concept||'']);
  const row=rows[key] ||= {label:q.concept?`${q.skill} · ${q.concept}`:`${q.skill} · 스킬 단위`,pre:0,post:0,count:0};
  row.pre+=Number(q.pre==='정답');row.post+=Number(q.post==='정답');row.count++;
 }
 return Object.values(rows);
}
