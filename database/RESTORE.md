# 외부 DB 자료와 복원

[assets.manifest.json](assets.manifest.json)은 필요한 자료의 파일명·버전·해시를 기록한다. `location`은 아직 미지정이다. 담당자에게 접근 가능한 보관 위치를 받아 해시를 대조한 뒤 사용한다. 실제 비밀 설정이 포함된 전달 ZIP은 배포용으로 쓰지 않는다.

| 자료 | 확인 방법 |
|---|---|
| `growpath_full_20261021.dump` | 45,390,365바이트. 옆의 `growpath_full_20261021.manifest.json`과 SHA-256 비교 |
| `pgvector_pg17_windows_x64` 폴더 | 저장소 `data/exports/pgvector_pg17_windows_x64/manifest.json`의 파일별 해시 비교 |
| 규정 원문 | `assets.manifest.json`의 파일별 해시와 DB 파일 출처의 `storage_key` 확인 |

직원 초기 데이터·테스트 비밀번호는 별도 검토해 전달한다. 이 저장소에는 seed SQL과 공용 기본 비밀번호가 없다.

## Windows 새 환경

Python 3.12 의존성 설치는 [README](README.md)를 따른다. 전달자의 기준은 PostgreSQL 17.11 + pgvector 0.8.2 Windows x64다. 다른 OS/메이저 버전에는 해당 환경의 확장이 필요하다.

아래 `<외부 ... 경로>`는 입수한 실제 경로로 바꾼다. 설치 스크립트는 pgvector 파일·해시를 먼저 검사한다.

```powershell
# 팀 저장소 루트; Miniforge가 필요함
powershell -ExecutionPolicy Bypass -File database/scripts/install_postgres.ps1 -VectorBundle "<외부 pgvector 폴더>"
cd database
python scripts/restore_db.py restore --archive "<외부 백업 폴더>/growpath_full_20261021.dump" --initialize --write-config
```

덤프와 `.manifest.json`을 같은 폴더에 둔다. 가상환경을 활성화하거나 해당 Python 경로로 명령을 실행한다. 관리자 비밀번호는 터미널에서 직접 입력한다. 새 서버는 127.0.0.1:55433에 생성된다. PostgreSQL 실행 경로가 기본 Miniforge 위치와 다르면 `--pg-bin`으로 지정한다.

기존 서버에는 새로운 DB 이름으로 복원한다.

```powershell
python scripts/restore_db.py restore --archive "<외부 백업 폴더>/growpath_full_20261021.dump" --database growpath_review
python scripts/db.py verify
python -m src.database.vectors.resource_vectors status
python -m src.database.vectors.regulation_vectors status
```

기존 DB·설정은 덮어쓰지 않는다. 실패한 새 DB는 자동 삭제하지 않으므로 로그 확인 후 관리자가 정리한다. 검증 전 기존 연결을 전환하지 않는다. 되돌릴 때는 마이그레이션 재작성이나 PostgreSQL 내부 파일 복사 대신 검증된 별도 백업을 새 DB에 복원해 연결을 전환한다.

## 백업과 검증 범위

```powershell
python scripts/restore_db.py backup --output "<외부 백업 폴더>/growpath_full_새날짜.dump"
```

동일 스냅샷의 메타데이터와 해시 manifest를 함께 만든다. `local_db.py backup`은 덤프만 만들므로 manifest 기반 전달에는 위 명령을 쓴다.

전달 백업은 50개 테이블·29,903행·202개 제약조건이다. 전달자의 복원 PASS와 이번 정적 검사는 [DB 대응표](../docs/07_데이터베이스_저장소_설계/README.md)에 구분했다. 새 환경의 실제 복원·트리거·권한·검색은 따로 확인해야 한다. 도서 25건의 벡터 최신성 문제는 백업에 남아 있으므로 복원 성공으로 해결되지는 않는다.
