"""Build a verifiable local delivery ZIP without accounts, dummy workforce or model weights."""
import argparse
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_PARTS = {'.git','.idea','.vscode','.cache','__pycache__','.pytest_cache',
              '.integration_backups','local_db','logs','checkpoints','사내DB_가데이터','node_modules'}
TEXT_SUFFIXES={'.py','.ps1','.cmd','.md','.txt','.yaml','.yml','.toml','.json','.jsonl','.csv','.sql','.html','.js','.gs'}
SECRET_KEYS=re.compile(r'^(?:password|passwd|hf_token|openai_api_key|runpod_jupyter_token|database_url|access_token|refresh_token|api_key)$',re.I)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def allowed(path):
    rel=path.relative_to(ROOT);parts=rel.parts
    if any(p in SKIP_PARTS or p.startswith('.venv') for p in parts):return False
    if not parts or parts[0]!='fine_tunning':return False
    if path.name.startswith('.env') or path.name in ('secrets.toml','worker_credentials.json','local_connection.json','connection_settings.json'):return False
    if len(parts)==2:return path.name in ('README.md','requirements.txt','requirements-runpod.txt','requirements-kernel-b200.txt','check_qwen35_local.ps1','import_manifest.json')
    if parts[1]=='docs':return path.suffix in {'.md','.html','.docx','.pdf'}
    if parts[1]=='metadata':return path.suffix=='.json'
    if parts[1]=='scripts':return path.suffix=='.py'
    if parts[1]=='configs':return path.suffix in {'.yaml','.yml','.json'} and not path.name.startswith(('local_recipe_','control_'))
    if parts[1]=='data':return len(parts)>=4 and (parts[2] in ('production','eval') or parts[2:4]==('revision_1500','assembled')) and path.suffix in TEXT_SUFFIXES
    if parts[1] in ('reports','outputs'):return path.suffix in {'.json','.jsonl','.md','.log'} and path.name not in ('gpu.lock','candidate_versions.lock')
    return False

def check_credentials(value,where=''):
    if isinstance(value,dict):
        for key,item in value.items():
            if SECRET_KEYS.fullmatch(key) and isinstance(item,str) and item.strip():
                if item not in ('fixture-token','test','example','change-me') and not item.startswith(('${','YOUR_','<')):
                    raise ValueError('Credential-like nonempty field in '+where+': '+key)
            check_credentials(item,where)
    elif isinstance(value,list):
        for item in value:check_credentials(item,where)

def pack(output, factory_only=True):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Output exists; choose a new file name')
    scan_root=ROOT/'fine_tunning'
    files=sorted(p for p in scan_root.rglob('*') if p.is_file() and allowed(p))
    required=['fine_tunning/README.md','fine_tunning/scripts/qwen35_b200_runner.py',
       'fine_tunning/data/production/expanded_3000/all.jsonl',
       'fine_tunning/data/production/expanded_3000/release_manifest.json',
       'fine_tunning/data/revision_1500/assembled/all.jsonl']
    if factory_only:
        required=[x for x in required if x.startswith('fine_tunning/')]+['fine_tunning/docs/RECOMMEND.md','fine_tunning/metadata/final_model.json','fine_tunning/metadata/codex_reviews.json']
    names={p.relative_to(ROOT).as_posix() for p in files}
    if set(required)-names:raise ValueError('Missing required files: '+str(set(required)-names))
    manifest={'format_version':1,'folder':'fine_tunning','contains_credentials':False,
      'contains_model_weights':False,'contains_dummy_workforce':False,
      'exclusions':['credentials and account dumps','dummy workforce','caches and environments','large model weights','duplicate regulation V18'],
      'historical_paths':'Immutable JSON receipts retain original qwen_factory paths; local folder is fine_tunning.', 'files':{}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.zip',delete=False) as f:staged=Path(f.name)
    try:
        with zipfile.ZipFile(staged,'w',zipfile.ZIP_DEFLATED) as z:
            for p in files:
                name=p.relative_to(ROOT).as_posix();raw=p.read_bytes()
                if p.suffix=='.json':
                    try:check_credentials(json.loads(raw),name)
                    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('Invalid JSON: '+name)
                if re.search(rb'(?:sk-proj-|hf_)[A-Za-z0-9_-]{25,}',raw):raise ValueError('Token-like content: '+name)
                manifest['files'][name]={'sha256':digest(raw),'bytes':len(raw)}
                z.writestr(name,raw)
            z.writestr('delivery_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        with zipfile.ZipFile(staged) as z:
            assert z.testzip() is None
            for name,info in manifest['files'].items():
                if digest(z.read(name))!=info['sha256']:raise ValueError('Archive SHA mismatch: '+name)
        staged.replace(output)
    finally:staged.unlink(missing_ok=True)
    receipt={'path':str(output),'files':len(files),'bytes':output.stat().st_size,'sha256':digest(output.read_bytes()),'zip_crc_and_all_member_sha256':'PASS'}
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--factory-only',action='store_true')
    args=parser.parse_args()
    print(json.dumps(pack(args.output,args.factory_only),ensure_ascii=False))
