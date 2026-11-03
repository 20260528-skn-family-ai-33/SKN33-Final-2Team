"""Standard-library-only verification of saved model and evaluation sources."""
import hashlib
import json
from pathlib import Path

def load_verified(root):
    project=Path(root).resolve().parent
    docs=Path(root)/'metadata'
    model=json.loads((docs/'final_model.json').read_text(encoding='utf-8'))
    review=json.loads((docs/'codex_reviews.json').read_text(encoding='utf-8'))
    if (model['model_id']!=review['model_id'] or model['revision']!=review['model_revision']
            or model['trained_epochs']!=review['trained_epochs']):
        raise ValueError('모델 식별 정보 불일치')
    rows=review['reviews']
    if len(rows)!=10 or sorted(x['case_index'] for x in rows)!=list(range(10)):
        raise ValueError('평가 10사례 구성 불일치')
    reports={}
    for row in rows:
        path=(project/row['report_path']).resolve()
        path.relative_to(Path(root).resolve()/'reports')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['report_sha256']:
            raise ValueError(f"Case {row['case_index']+1}: 원문 SHA256 불일치")
        report=json.loads(raw)
        old={k:report.get(k) for k in ('model','quantization','messages','generation','test_sha256','case_index','adapter_sha256')}
        for key in ('evaluation_cohort','reference_sha256'):
            if key in report:old[key]=report[key]
        old['answer']=report.get('tuned',{}).get('text')
        signature=hashlib.sha256(json.dumps(old,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if signature!=row['case_signature'] or report['case_index']!=row['case_index']:
            raise ValueError('사례 정체성 불일치')
        reports[row['case_index']]=report
    return model,review,reports
