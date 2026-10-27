"""5차 목업 DB 준비: 팀원 전체 백업 복원 → 보조 스키마(app_ext) → 보충 자료.

  python tools/setup_db.py            # 빈 Docker DB면 복원부터(백업 기본 위치 team_db/), 아니면 보충만 (여러 번 실행해도 같은 결과)
  python tools/setup_db.py --supplement-only   # 팀원이 운영하는 DB(복사본)에 붙을 때: 복원 없이 보조 스키마·보충만 · 그 DB 팀 표에 데이터를 쓴다

보충 자료 (2026-10-21 사용자 결정 · 2026-10-27 팀 최신 DB 기준으로 정리):
  - 관리자 전용 계정 1개(아이디 .env GP5_ADMIN_LOGIN · 비밀번호 GP5_DEMO_PASSWORD)
  - 직원·부서·보유 스킬·자격·학력은 팀 DB(#22 최신 백업)의 것을 그대로 쓴다. 예전 직원 가데이터 엑셀(2.9.0)은 쓰지 않는다
  - 사번이 있는 팀 시험 직원의 비밀번호를 이 로컬 사본에서만 시연 비밀번호로 바꾼다. 사번이 없는 계정(REAL_USER)은
    로그인할 수 없고 팀 DB 의 사번 필수 제약 때문에 고칠 수도 없어 건드리지 않는다
    (--keep-team-passwords 면 그대로 · --supplement-only 는 남의 DB라 늘 그대로 · 2026-10-23 사용자 결정)
  - 학습 자료 보조 값(형식·시간·단계·비용)을 규칙으로 채우고 '추정'으로 표시, 자격증 분야 묶음
  - 규정 묶음(적용 직원 구분·국외근무 전용·짧은 키)
  - 목표 후보 첫 생성(가데이터 규칙 · 본인 입력이 없으면 기본 후보)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.auth import hash_password, verify_password  # noqa: E402
from app.config import S, env  # noqa: E402

# 복원 대상 컨테이너 = '{compose 이름}-db-1'. 고정값이면 다른 compose 프로젝트의 DB에 복원할 수 있어 설정으로 뺐다(2026-10-26)
COMPOSE_PROJECT = env('COMPOSE_PROJECT_NAME', 'gp5')
# 팀 DB 백업 기본 위치(.env TEAM_DB_DUMP 가 비면): 팀원이 받은 파일을 이 폴더 team_db/ 에 넣기만 하면 되게(2026-10-23 사용자 결정)
DUMP_DEFAULT = 'team_db/growpath_latest.dump'


def say(msg: str) -> None:
    print('  ' + msg, flush=True)


# ── 1. 복원 ──
def db_is_empty() -> bool:
    return db.val("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'") == 0


def dump_path() -> Path:
    p = Path(env('TEAM_DB_DUMP', DUMP_DEFAULT))
    return p if p.is_absolute() else (ROOT / p).resolve()


def restore(dump: Path) -> None:
    if not dump.is_file():
        others = sorted(x.name for x in (ROOT / 'team_db').glob('*.dump'))
        raise SystemExit('\n'.join([
            f'팀 DB 백업 파일이 없어요: {dump}',
            f'  · 팀 DB 담당 팀원에게 백업 파일({dump.name})을 받아 위 위치에 넣고 다시 실행하세요. 기본 위치는 이 폴더의 team_db/ 예요.',
            '  · 다른 곳에 두었다면 .env 의 TEAM_DB_DUMP 에 그 위치를 적으세요.',
            *([f"  · team_db/ 에 있는 다른 백업: {', '.join(others)} — 이 파일을 쓰려면 TEAM_DB_DUMP 를 그 이름으로 고치세요(판이 다르면 시연 자료가 안 맞을 수 있어요)."] if others else []),
        ]))
    user, name = env('GP5_DB_USER', 'growpath'), env('GP5_DB_NAME', 'growpath')
    container = f'{COMPOSE_PROJECT}-db-1'
    say(f'팀원 백업 복원: {dump.name} → {container}')
    subprocess.run(['docker', 'cp', str(dump), f'{container}:/tmp/team.dump'], check=True)
    subprocess.run(['docker', 'exec', container, 'pg_restore', '-U', user, '-d', name, '--no-owner', '--no-privileges', '--exit-on-error', '/tmp/team.dump'], check=True)
    subprocess.run(['docker', 'exec', container, 'rm', '-f', '/tmp/team.dump'], check=True)


def apply_app_ext() -> None:
    sql = (ROOT / 'db/02_app_ext.sql').read_text(encoding='utf-8')
    # 매개변수 없이 보내야 SQL 안의 '%'(LIKE)를 자리표시자로 읽지 않는다
    raw = db.engine.raw_connection()
    try:
        raw.cursor().execute(sql)
        raw.commit()
    finally:
        raw.close()
    say('보조 스키마 app_ext 적용')


# ── 2. 계정 ──
def admin_account() -> None:
    with db.tx() as t:
        if not t.one('SELECT 1 FROM app_ext.admin_accounts WHERE login_id = :l', l=S.admin_login):
            t.run('INSERT INTO app_ext.admin_accounts(login_id, name, password_hash) VALUES(:l, :n, :h)', l=S.admin_login, n='시스템 관리자(시연)', h=hash_password(S.demo_password))
            say(f'관리자 계정 만듦: {S.admin_login}')


def team_passwords() -> None:
    n = 0
    with db.tx() as t:
        # 사번 없는 행은 로그인할 수 없고, 팀 DB 의 사번 필수 제약(NOT VALID)이 그런 행의 어떤 수정도 막는다
        for e in t.all("SELECT employee_id, password_hash FROM public.employees WHERE coalesce(btrim(employee_number), '') <> ''"):
            if not verify_password(e['password_hash'], S.demo_password):
                t.run('UPDATE public.employees SET password_hash = :h WHERE employee_id = :i', h=hash_password(S.demo_password), i=e['employee_id'])
                n += 1
    say(f'팀 시험 직원 비밀번호(로컬 사본만 · 사번 있는 계정): {n}명 바꿈')


# ── 3. 학습 자료 보조 값 ──
DIFF_STAGE = {'BEGINNER': 1, 'INTERMEDIATE': 2, 'ADVANCED': 3}
AI_SKILLS = {'RAG & 생성형 AI 에이전트', '자연어 처리(NLP) & LLM 기초', '머신러닝 지도/비지도 학습', 'MLOps & 모델 서빙', 'ETL & 데이터 파이프라인',
             '탐색적 데이터 분석(EDA) & 전처리', '데이터 웨어하우스 & OLAP', '딥러닝 신경망 아키텍처', 'PyTorch/TensorFlow 딥러닝 구현', '컴퓨터 비전(CV) 모델링'}
CLOUD_SKILLS = {'클라우드 컴퓨팅 아키텍처 (AWS/Azure)', '클라우드 IAM & 네트워크 보안', '네트워크 보안 & 침입 탐지', '시스템 & OS 보안 강화',
                '데이터 거버넌스 & 보안 규정 준수', '웹 애플리케이션 취약점 진단', 'TCP/IP 네트워크 프로토콜'}


def resources() -> None:
    with db.tx() as t:
        n = 0
        for c in t.all('SELECT course_id, platform, cost, duration_weeks, difficulty FROM public.courses'):
            kmooc = (c['platform'] or '') == 'K-MOOC'
            hours = (c['duration_weeks'] * 2 if c['duration_weeks'] else 10) if kmooc else 1
            est = ['format', 'hours', 'stage'] + ([] if c['cost'] is not None else [])
            n += t.run("""INSERT INTO app_ext.resource_meta(resource_key, resource_type, course_id, format, hours, stage, cost_won, estimated_fields, is_real)
                          VALUES(:k, 'course', :cid, :f, :h, :s, :c, :e, true) ON CONFLICT (resource_key) DO NOTHING""",
                       k=c['course_id'], cid=c['course_id'], f='영상' if kmooc else '문서', h=hours, s=DIFF_STAGE.get(c['difficulty'] or '', 2),
                       c=int(c['cost']) if c['cost'] is not None else None, e=db.J(est))
        for b in t.all('SELECT isbn FROM public.books'):
            n += t.run("""INSERT INTO app_ext.resource_meta(resource_key, resource_type, isbn, format, hours, stage, estimated_fields, is_real)
                          VALUES(:k, 'book', :i, '문서', 10, 2, :e, true) ON CONFLICT (resource_key) DO NOTHING""", k=f"book_{b['isbn']}", i=b['isbn'], e=db.J(['format', 'hours', 'stage']))
        # 자격증 분야: 시행 기관 + 스킬(마이크로소프트는 스킬로 나눔)
        groups = [('kdata', '데이터·SQL (한국데이터산업진흥원)', '한국데이터산업진흥원', 'https://www.dataq.or.kr/www/sub/introduction.do', 1),
                  ('ms-ai', 'Microsoft · AI·데이터', 'Microsoft', 'https://learn.microsoft.com/credentials/', 2),
                  ('ms-cloud', 'Microsoft · 클라우드·보안', 'Microsoft', 'https://learn.microsoft.com/credentials/', 3),
                  ('ms-dev', 'Microsoft · 개발·운영', 'Microsoft', 'https://learn.microsoft.com/credentials/', 4),
                  ('ms-etc', 'Microsoft · 업무 앱·기타', 'Microsoft', 'https://learn.microsoft.com/credentials/', 5)]
        for g in groups:
            t.run("""INSERT INTO app_ext.cert_groups(group_key, label, issuer, url, display_order) VALUES(:k, :l, :i, :u, :o)
                     ON CONFLICT (group_key) DO UPDATE SET label = EXCLUDED.label, issuer = EXCLUDED.issuer, url = EXCLUDED.url, display_order = EXCLUDED.display_order""",
                  k=g[0], l=g[1], i=g[2], u=g[3], o=g[4])
        skills = {}
        for r in t.all('SELECT cs.cert_id, s.name FROM public.certification_skills cs JOIN public.skill_tags s USING (skill_id)'):
            skills.setdefault(r['cert_id'], set()).add(r['name'])
        for x in t.all('SELECT cert_id, title, provider FROM public.certifications ORDER BY cert_id'):
            sk = skills.get(x['cert_id'], set())
            if (x['provider'] or '') == '한국데이터산업진흥원':
                grp = 'kdata'
            elif (x['provider'] or '').startswith('Microsoft'):
                grp = 'ms-ai' if sk & AI_SKILLS else 'ms-cloud' if sk & CLOUD_SKILLS else 'ms-dev' if sk else 'ms-etc'
            else:
                key = 'org-' + re.sub(r'\W+', '-', x['provider'] or '기타').strip('-').lower()
                t.run('INSERT INTO app_ext.cert_groups(group_key, label, issuer, display_order) VALUES(:k, :l, :i, 9) ON CONFLICT DO NOTHING', k=key, l=x['provider'] or '기타', i=x['provider'])
                grp = key
            n += t.run("""INSERT INTO app_ext.resource_meta(resource_key, resource_type, cert_id, format, hours, stage, estimated_fields, is_real, cert_code, cert_group, cert_short)
                          VALUES(:k, 'cert', :c, '시험', 30, 4, :e, true, :code, :g, :short) ON CONFLICT (resource_key) DO NOTHING""",
                       k=f"cert_{x['cert_id']}", c=x['cert_id'], e=db.J(['hours']), code=str(x['cert_id']), g=grp, short=x['title'])
    say(f'학습 자료 보조 값(추정) 새로 넣음: {n}건')


# ── 4. 규정 묶음 ──
GENERAL = ['인재개발규정', '취업규칙', '유연근무제 운영기준', '근무및부업관리규정', '여비규정', '인사규정', '인사규정시행세칙', '연봉규정', '연봉규정시행세칙',
           '복지후생규정', '복지후생규정시행세칙', '직제규정', '직제규정 시행세칙', '위임전결규정', '인사규정 채용 세칙', '내부임용시험시행지침']
OVERSEAS = ['국외근무직원복무규정', '국외근무직원연봉및복지후생규정']
OTHER = {'실무직': ['실무직 관리규정', '실무직 관리기준', '실무직 보수기준'], '운영직': ['운영직관리세칙'], '전문직': ['전문직관리세칙'], '특정직': ['특정직관리세칙'],
         '청원경찰': ['청원경찰관리규정'], '기간제근로자': ['기간제근로자 관리규정', '기간제근로자 관리기준'], '특수직': ['특수직 보수기준']}
# 4차 조항 id 앞머리와 같은 짧은 키(화면 주소·기록에 씀)
SHORT = {'인재개발규정': 'dev', '취업규칙': 'emp', '유연근무제 운영기준': 'flex', '근무및부업관리규정': 'side', '여비규정': 'trip', '인사규정': 'hr',
         '인사규정시행세칙': 'hrd', '연봉규정': 'pay', '연봉규정시행세칙': 'payd', '복지후생규정': 'wel', '복지후생규정시행세칙': 'weld', '직제규정': 'org',
         '직제규정 시행세칙': 'orgd', '위임전결규정': 'dele', '국외근무직원복무규정': 'osw', '국외근무직원연봉및복지후생규정': 'ospay', '실무직 관리규정': 'prac',
         '실무직 관리기준': 'pracs', '실무직 보수기준': 'pracp', '인사규정 채용 세칙': 'hire', '내부임용시험시행지침': 'exam'}


def regulations() -> None:
    group_of = {n: '일반직' for n in GENERAL + OVERSEAS}
    for g, names in OTHER.items():
        for n in names:
            group_of[n] = g
    with db.tx() as t:
        n = 0
        for r in t.all('SELECT regulation_id, name FROM regulations.regulations ORDER BY name'):
            name = r['name']
            if t.one('SELECT 1 FROM app_ext.regulation_meta WHERE regulation_id = :i', i=r['regulation_id']):
                continue
            key = SHORT.get(name) or 'reg-' + r['regulation_id'][:8]
            t.run("""INSERT INTO app_ext.regulation_meta(regulation_id, short_key, employee_group, overseas_only, org) VALUES(:i, :k, :g, :o, '한국수자원공사')""",
                  i=r['regulation_id'], k=key, g=group_of.get(name, '미분류'), o=name in OVERSEAS)
            n += 1
    say(f'규정 묶음 정보 새로 넣음: {n}건')


def goals() -> None:
    try:
        from app.services import goals as G
    except ImportError as e:  # 서버 코드가 아직 없을 때(처음 개발 중)는 건너뛴다
        say(f'목표 후보 첫 생성 건너뜀: {e}')
        return
    n = G.seed_all()
    say(f'목표 후보 첫 생성(가데이터 규칙·기본 후보): {n}명')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--supplement-only', action='store_true')
    ap.add_argument('--keep-team-passwords', action='store_true')
    args = ap.parse_args()
    print('GrowPath 5차 DB 준비')
    if not args.supplement_only:
        if db_is_empty():
            restore(dump_path())
        else:
            say('DB에 이미 표가 있어 복원은 건너뜀')
    apply_app_ext()
    # 시연 비밀번호는 저장소 밖에서 정한다(팀 database/RESTORE.md · 2026-10-26). 없으면 계정 단계만 건너뛴다
    if not S.demo_password:
        say('GP5_DEMO_PASSWORD 가 비어 있어 관리자 계정·팀 테스트 비밀번호 단계를 건너뜀(.env 에 넣고 다시 실행)')
    else:
        admin_account()
        if args.supplement_only:
            say('팀 테스트 직원 비밀번호: 그대로 둠(--supplement-only · 팀원이 운영하는 DB)')
        elif not args.keep_team_passwords:
            team_passwords()
    resources()
    regulations()
    goals()
    print('완료')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
