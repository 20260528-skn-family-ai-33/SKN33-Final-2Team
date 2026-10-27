"""Refresh the existing interactive ERD form from the live schema; no row content exported."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import re
from pathlib import Path
from psycopg import sql

from .deployment import connect
from .final_schema import snapshot

LABELS=dict(employee_recommended_prompts='직원 추천 질문',employees='직원·로그인 계정',institutions='기관',departments='부서 계층',job_grades='직급',employee_skills='보유 스킬',employee_certifications='보유 자격증',employee_education_records='학력',skill_tags='스킬 태그',jobs='직무',majors='전공',courses='강좌',books='도서',certifications='자격증',projects='프로젝트·계획',diagnostic_rounds='진단 회차',assessment_questions='설문 문항',assessment_responses='설문 응답',roadmaps='선택 로드맵',roadmap_steps='로드맵 단계',roadmap_step_resources='단계별 학습 자료',roadmap_comments='부서장 코멘트',growth_reports='성장 보고서',prompt_versions='운영 프롬프트',learning_resource_embeddings='학습 자료·스킬 벡터',regulations='규정',regulation_versions='규정 버전',regulation_files='규정 출처 파일',regulation_nodes='규정 원문 구조',regulation_scopes='규정 적용 범위',regulation_references='규정 참조',rag_chunks='규정 검색 청크',rag_chunk_sources='청크 원문 출처',rag_chunk_embeddings='규정 청크 벡터',evaluation_result_schemas='평가기준 체계',evaluation_item_definitions='평가기준 항목',evaluation_schema_sources='평가기준 출처',catalog_api_sources='API 원본·매칭 이력',schema_migrations='스키마 적용 이력',course_skills='강좌 스킬',book_skills='도서 스킬',certification_skills='자격증 스킬',job_skills='직무 스킬',major_skills='전공 스킬',agent_generations='과거 에이전트 생성',agent_selections='과거 선택',finetuning_datasets='과거 데이터셋 이력',preference_pairs='과거 선호 쌍',roadmap_requests='과거 요청',test_mock_profiles='테스트 프로필')
LABELS['employee_input_profiles']='직원 입력 확장'
LABELS['documents']='회사 정보·생활안내 문서'
LABELS['chunks']='회사 정보·생활안내 검색 조각·벡터'


def render_html(data: dict, template: str) -> str:
    """Preserve the placeholder form and the previously published HTML API."""
    encoded = json.dumps(data, ensure_ascii=False, default=str).replace('<', chr(92) + 'u003c')
    if '__DATA__' in template:
        if template.count('__DATA__') != 1 or template.count('__GENERATED_AT__') != 1:
            raise ValueError('Use one data and date placeholder in the complete ERD template')
        return template.replace('__DATA__', encoded).replace(
            '__GENERATED_AT__', datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
    match = re.search(r'const\s+D\s*=\s*', template)
    if match is None:
        raise ValueError('ERD template must contain a const D JSON snapshot')
    _, length = json.JSONDecoder().raw_decode(template[match.end():])
    suffix = template[match.end() + length:]
    if not suffix.lstrip().startswith(';'):
        raise ValueError('ERD template JSON snapshot must end with a semicolon')
    return template[:match.end()] + encoded + suffix


def render(conn, template, output):
    """Keep the complete template CSS, routing, drag controls and interactions."""
    data=snapshot(conn)
    for key,spec in data.items():
        spec['label']=LABELS.get(key.split('.')[1],key.split('.')[1])
        # The table names are returned by PostgreSQL schema introspection.
        schema,table=key.split('.')
        spec['rows']=conn.execute(sql.SQL('SELECT count(*) AS n FROM {}.{}').format(
            sql.Identifier(schema),sql.Identifier(table))).fetchone()['n']
    source=template.read_text(encoding='utf-8')
    html = render_html(data, source)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(html,encoding='utf-8')
    return {'file':str(output),'tables':len(data),
            'foreign_keys':sum(len(spec['fks']) for spec in data.values()),
            'form':'existing orthogonal ERD with drag, search, zoom and FK arrows'}


def main():
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template',type=Path,default=root/'docs/erd_template.html')
    parser.add_argument('--output',type=Path,default=root.parent/'docs/07_데이터베이스_저장소_설계/ERD_최종.html')
    args=parser.parse_args()
    with connect('SUPABASE_DB_URL') as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        print(json.dumps(render(conn,args.template,args.output),ensure_ascii=False))


if __name__=='__main__':
    main()
