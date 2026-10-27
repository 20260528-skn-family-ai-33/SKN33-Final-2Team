"""Build an evidence-checked finite review input from saved course research; no network."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.database.ingestion.course_supplement import validate_rows, canonical_url
from src.database.ingestion.ai_catalog_filter import AICatalogFilter
from src.shared.catalog_scope import scoped_matches
from src.shared.skill_matching import SkillMatcher


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def public_title_matches(title, page_text):
    normalized=' '.join(str(title or '').split())
    return bool(normalized) and normalized in ' '.join(str(page_text or '').split())


def prepare_files(input_path, output_path, *, only_ids=None):
    source = input_path.parent
    rows = read(input_path)
    if only_ids:
        requested=set(only_ids)
        rows=[row for row in rows if row['fields']['course_id'] in requested]
        if {row['fields']['course_id'] for row in rows}!=requested:
            raise ValueError('선택한 강좌 ID가 후보에 없습니다.')
    baseline = read(source/'baseline.json')
    pages = {r['course_id']: r for r in read(source/'kmooc_page_checks.json')}
    audit_path = source/'before_skill_corrections/skill_mapping_audit.json'
    if not audit_path.exists():audit_path = source/'skill_mapping_audit.json'
    audit = {r['course_id']: r for r in read(audit_path)['courses']}
    matcher = SkillMatcher(baseline['skills'])
    gate = AICatalogFilter(baseline['skills'], client=object())  # Payload sizing only; cannot call an API.
    verified, prepared, held, seen = {}, [], [], list(baseline['courses'])
    for original in rows:
        row = deepcopy(original)
        rid, provider = row['fields']['course_id'], row['source']
        evidence = []
        if row.get('html_path'):
            evidence.append(dict(path=row['html_path'], sha256=row['html_sha256']))
        if row['raw'].get('html_path'):
            evidence.append(dict(path=row['raw']['html_path'], sha256=row['raw']['html_sha256']))
        evidence.extend(row.get('api_proofs') or row['raw'].get('api_proofs') or [])
        evidence.extend((row.get('curriculum_enrichment') or {}).get('source_proofs') or [])
        if provider == 'API_KMOOC':
            page = pages[rid]
            evidence.append(dict(path=page['html_path'], sha256=page['html_sha256']))
        for proof in evidence:
            key = proof['path'], proof['sha256']
            if key in verified:continue
            path = (ROOT/proof['path']).resolve()
            if (not path.is_relative_to((ROOT/'data/import_sources').resolve())
                    or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != proof['sha256']):
                raise ValueError('원문 해시/경로 검사 실패: ' + rid)
            verified[key] = True
        if provider in ('WEB_STEP', 'API_KMOOC'):
            if provider == 'WEB_STEP':
                titles = row['lesson_titles']
                page = row
            else:
                page = pages[rid]
                titles = [l['title']+' '+l.get('description','') for l in page.get('lessons',[])]
                if not titles:
                    body = row['fields']['syllabus_summary']
                    if '주차별 학습 내용\n' in body:
                        titles = body.split('주차별 학습 내용\n',1)[1].split('기존 공개 소개·설명',1)[0].strip().splitlines()
            row['raw']['public_detail'] = dict(course_id=rid, title=row['fields']['title'],
                url=row['fields']['url'], fetched_at=page['fetched_at'], html_path=page['html_path'],
                html_sha256=page['html_sha256'], curriculum_titles=titles)
            if provider == 'API_KMOOC':
                for key in ('audit_action_present','enroll_action_present','public_page_title_matches'):
                    row['raw']['public_detail'][key] = page[key]
                row['raw']['public_detail']['public_page_title_matches']=public_title_matches(
                    row['fields']['title'],page.get('page_text'))
                row['raw']['public_detail']['title_match_basis']='whitespace_normalized_public_page_text'
        if row.get('source_duration'):
            row['raw']['source_duration'] = row['source_duration']
        matches = scoped_matches(matcher, row['fields'])
        # Candidate skills are a review scope, not an AI acceptance. Actual admission can only remove them.
        base = set(row['research_skill_ids'])
        instructional = set(audit[rid]['specific_instructional_skill_ids'])
        removed_by_content_review = set(row.get('proposed_skill_ids') or []) - base
        row['reviewed_skill_ids'] = sorted(set(matches) - removed_by_content_review)
        row['preparation'] = dict(removed_unmatched_proposals=sorted(base-set(matches)),
            additional_review_candidates=sorted(set(row['reviewed_skill_ids'])-base),
            final_semantic_review='pending', source_proofs=evidence)
        if not row['reviewed_skill_ids']:
            held.append(dict(course_id=rid, title=row['fields']['title'], reason='no_supported_curriculum_skill'))
            continue
        try:
            checked = validate_rows([row], baseline['skills'], seen)[0]
            payload = json.dumps(gate.payload('courses', checked), ensure_ascii=False, sort_keys=True)
            if len(payload) > 64000:
                raise ValueError('AI 심사 입력 길이 한도 초과')
        except ValueError as exc:
            held.append(dict(course_id=rid, title=row['fields']['title'], reason=str(exc)))
            continue
        prepared.append(row)
        seen.append(row['fields'])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(prepared, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    report = dict(input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
        output_sha256=hashlib.sha256(output_path.read_bytes()).hexdigest(),
        input_candidates=len(rows), prepared_candidates=len(prepared), held_candidates=len(held),
        by_source=dict(Counter(r['source'] for r in prepared)), held=held,
        verified_source_files=len(verified),
        proposed_skill_links=sum(len(r['reviewed_skill_ids']) for r in prepared),
        extra_skill_proposals=sum(len(r['preparation']['additional_review_candidates']) for r in prepared),
        removed_nonmatching_proposals=sum(len(r['preparation']['removed_unmatched_proposals']) for r in prepared),
        paid_api_calls=0,database_changes=False, final_semantic_review='pending')
    report_path = output_path.with_name('preparation_manifest.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only-ids',nargs='+',help='기존 승인 범위 안의 별도 소규모 입력만 준비')
    args = parser.parse_args()
    prepare_files(args.input, args.output, only_ids=args.only_ids)
