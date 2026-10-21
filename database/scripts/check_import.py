"""Verify imported source/document hashes and ERD metadata without DB/API access."""
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
DATABASE = ROOT / "database"


def verify() -> dict:
    manifest = json.loads((DATABASE / "import-manifest.json").read_text(encoding="utf-8"))
    errors = []
    for entry in manifest["files"]:
        path = (ROOT / entry["path"]).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            errors.append("Missing or invalid path: " + entry["path"])
            continue
        expected = entry.get("sha256", entry.get("source_sha256"))
        if sha256(path.read_bytes()).hexdigest() != expected:
            errors.append("Hash mismatch: " + entry["path"])
        if "/migrations/" in entry["path"] and expected != entry["source_sha256"]:
            errors.append("Applied migration differs from source: " + entry["path"])
    recorded_hashes = {entry["path"]: entry.get("sha256", entry.get("source_sha256")) for entry in manifest["files"]}
    for artifact in manifest.get("drive_verification", {}).get("files", []):
        if artifact["sha256"] != recorded_hashes.get(artifact["path"]):
            errors.append("Drive comparison no longer matches imported file: " + artifact["path"])
    schema = json.loads((DATABASE / "src/database/catalog.current.json").read_text(encoding="utf-8"))
    html = (ROOT / "docs/07_데이터베이스_저장소_설계/ERD_최종.html").read_text(encoding="utf-8")
    start = re.search(r"const\s+D\s*=\s*", html).end()
    erd = json.JSONDecoder().raw_decode(html[start:])[0]
    snapshot = json.loads((DATABASE / "data/exports/growpath_full_20261021.manifest.json").read_text(encoding="utf-8"))
    if set(erd) != set(schema) or set(erd) != set(snapshot["inventory"]["tables"]):
        errors.append("ERD/schema/backup table sets differ")
    for table, spec in schema.items():
        if table not in erd:
            continue
        if any(erd[table][key] != spec[key] for key in ("columns", "pk", "fks", "constraints")):
            errors.append("ERD metadata differs: " + table)
        if not isinstance(erd[table].get("label"), str) or not erd[table]["label"].strip():
            errors.append("ERD label missing: " + table)
        if erd[table]["rows"] != snapshot["inventory"]["tables"].get(table):
            errors.append("ERD row count differs: " + table)
    if errors:
        raise ValueError("\n".join(errors))
    return {"status": "PASS", "files": len(manifest["files"]), "tables": len(schema),
            "rows": sum(snapshot["inventory"]["tables"].values()),
            "database_connected": False, "embedding_api_called": False}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
