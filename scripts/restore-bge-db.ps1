param(
  [string]$Archive = 'team_db/growpath_bge_m3_embedding.dump',
  [string]$Manifest = 'team_db/growpath_bge_m3_embedding.manifest.json',
  [string]$Database = 'growpath_bge_m3',
  [switch]$Apply
)
$ErrorActionPreference = 'Stop'
# 이 파일은 BOM 포함 UTF-8 로 둔다. BOM 이 없으면 Windows PowerShell 5.1 이 한글을 시스템 코드페이지로 읽어 안내가 깨진다
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# BOM 있는 인코딩으로 파이프하면 psql 입력 앞에 BOM 이 붙는다. 터미널 없이 실행하면 두 번 붙어 첫 SQL 이 실패한다
$OutputEncoding = New-Object System.Text.UTF8Encoding $false

if ($Database -notmatch '^growpath_bge_m3(?:_[a-z0-9_]+)?$') { throw '복원 대상은 별도 growpath_bge_m3 DB여야 합니다.' }
$info = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$contractPath = Join-Path $PSScriptRoot '../database/src/shared/bge_model.json'
$contract = Get-Content -LiteralPath $contractPath -Raw -Encoding UTF8 | ConvertFrom-Json
$archiveFile = Get-Item -LiteralPath $Archive
if ($archiveFile.Name -ne $info.archive -or $archiveFile.Length -ne $info.bytes -or
    (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $info.sha256) {
  throw '백업 이름·크기·SHA-256이 manifest와 다릅니다.'
}
if ($info.embedding_model -ne $contract.model -or $info.embedding_dimensions -ne $contract.dimensions -or
    $info.model_provenance.revision -ne $contract.model_revision -or
    $info.model_provenance.sha256 -ne $contract.weights_sha256 -or
    $info.model_provenance.pooling -ne $contract.pooling -or $info.model_provenance.normalization -ne $contract.normalization) {
  throw '지원하는 BGE 모델·revision·가중치·pooling·정규화 계약과 다릅니다.'
}
Write-Output "백업 검증 완료: $($info.archive), $($info.bytes) bytes, 대상 $Database"
if (-not $Apply) { Write-Output '미리보기: DB 생성·복원을 수행하지 않았습니다. 실제 적용은 -Apply'; exit 0 }
function Invoke-BgePg([string[]]$SqlArgs) {
  $targetDb = 'postgres'
  $query = ''
  $tuplesOnly = $false
  for ($i = 0; $i -lt $SqlArgs.Length; $i++) {
    if ($SqlArgs[$i] -eq '-d') {
      $targetDb = $SqlArgs[++$i]
    } elseif ($SqlArgs[$i] -eq '-Atc') {
      $tuplesOnly = $true
      $query = $SqlArgs[++$i]
    } elseif ($SqlArgs[$i] -eq '-c') {
      $query = $SqlArgs[++$i]
    }
  }
  $cmd = if ($tuplesOnly) {
    'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -At'
  } else {
    'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1"'
  }
  $result = $query | & docker compose exec -T db sh -c $cmd sh $targetDb
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL 명령이 실패했습니다.' }
  return ($result -join "`n")
}
$exists = Invoke-BgePg -SqlArgs @('-d','postgres','-Atc',"SELECT count(*) FROM pg_database WHERE datname='$Database'")
if ($exists.Trim() -eq '0') {
  Invoke-BgePg -SqlArgs @('-d','postgres','-c',"CREATE DATABASE $Database")
} else {
  $marker = Invoke-BgePg -SqlArgs @('-d',$Database,'-Atc',"SELECT to_regclass('growpath_bge_meta.restore_state')")
  if ($marker -and $marker.Trim() -ne '') {
    $restoredHash = Invoke-BgePg -SqlArgs @('-d',$Database,'-Atc','SELECT archive_sha256 FROM growpath_bge_meta.restore_state LIMIT 1')
    if ($restoredHash.Trim() -eq $info.sha256) { Write-Output '동일 백업이 이미 복원되어 있습니다. DB를 변경하지 않습니다.'; exit 0 }
    throw '기존 복원 DB의 백업 해시가 다릅니다. 덮어쓰지 않습니다.'
  }
  $tables = Invoke-BgePg -SqlArgs @('-d',$Database,'-Atc',"SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_type='BASE TABLE'")
  if ($tables.Trim() -ne '0') { throw '복원 대상에 기존 테이블이 있습니다. 덮어쓰지 않습니다.' }
}
$containerFile = "/tmp/bge-$($info.sha256).dump"
& docker compose cp $archiveFile.FullName "db:$containerFile"
if ($LASTEXITCODE -ne 0) { throw '백업 파일 복사가 실패했습니다.' }
& docker compose exec -T db sh -c 'exec pg_restore -U "$POSTGRES_USER" --single-transaction --exit-on-error --no-owner --no-acl -d "$1" "$2"' sh $Database $containerFile
if ($LASTEXITCODE -ne 0) { throw '복원이 실패했습니다. 원본 DB는 변경하지 않았습니다.' }
$verification = @"
DO `$verify`$ BEGIN
IF (SELECT count(*) FROM public.learning_resource_embeddings WHERE embedding_model='BAAI/bge-m3' AND dimensions=1024 AND vector_dims(embedding)=1024) <> 2984
OR (SELECT count(*) FROM regulations.rag_chunk_embeddings WHERE embedding_model='BAAI/bge-m3' AND dimensions=1024 AND vector_dims(embedding)=1024) <> 1406
OR (SELECT count(*) FROM knowledge.chunks WHERE embedding_model='BAAI/bge-m3' AND dimensions=1024 AND vector_dims(embedding)=1024) <> 442
THEN RAISE EXCEPTION 'BGE vector counts differ from manifest'; END IF;
END `$verify`$;
CREATE TABLE IF NOT EXISTS growpath_bge_meta.restore_state(archive_sha256 text PRIMARY KEY, restored_at timestamptz NOT NULL DEFAULT now());
INSERT INTO growpath_bge_meta.restore_state(archive_sha256) VALUES ('$($info.sha256)') ON CONFLICT (archive_sha256) DO NOTHING;
"@
Invoke-BgePg -SqlArgs @('-d',$Database,'-c',$verification)
& docker compose exec -T db rm -f $containerFile
if ($LASTEXITCODE -ne 0) { throw '복원은 완료됐으나 임시 백업 파일 정리에 실패했습니다.' }
Write-Output "별도 $Database 복원 완료: BGE-M3 1024차원 4832개. 기존 DB는 보존했습니다."
