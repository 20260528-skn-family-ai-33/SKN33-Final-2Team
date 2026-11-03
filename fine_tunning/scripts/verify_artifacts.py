"""Read-only verification of delivery sources. No model, network, database or GPU calls."""
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

def verify(root):
    root=Path(root).resolve()
    sys.path.insert(0,str(root/'scripts'))
    from artifact_sources import load_verified
    model,reviews,reports=load_verified(root)
    assert model['trained_epochs']==2 and len(reports)==10
    expected={
      'data/revision_1500/assembled/all.jsonl':'998a9499a14f6c08de0526919567bcf5a9fcf31642f75aa24fca143c51265529',
      'data/production/expanded_3000/all.jsonl':'d80e09e8d0283aa1a0276fcef258135d58de89a702664341b244203fefd4e2f2',
      'data/eval/prompts.app_v2.jsonl':'7c1565e23373411d1adf5ef50c31ac8842ad68b92fb9c3610440ea1cc411cafe'}
    for name,sha in expected.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,name
    original=(root/'data/revision_1500/assembled/all.jsonl').read_text(encoding='utf-8-sig').splitlines()
    expanded=(root/'data/production/expanded_3000/all.jsonl').read_text(encoding='utf-8-sig').splitlines()
    assert len(original)==1500 and len(expanded)==3000
    assert [json.loads(x) for x in expanded[:1500]]==[json.loads(x) for x in original]
    release=json.loads((root/'data/production/expanded_3000/release_manifest.json').read_text(encoding='utf-8'))
    checked=[]
    def walk(value):
        if isinstance(value,dict):
            if 'path' in value and 'sha256' in value:
                p=(root/value['path']).resolve();p.relative_to(root)
                assert hashlib.sha256(p.read_bytes()).hexdigest()==value['sha256'],str(p)
                checked.append(value['path'])
            for v in value.values():walk(v)
        elif isinstance(value,list):
            for v in value:walk(v)
    walk(release)
    broken=[]
    for p in [root/'README.md',*list((root/'docs').glob('*.md'))]:
        for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if link.startswith(('http:','https:','mailto:','#')):continue
            if not (p.parent/link.split('#')[0]).exists():broken.append(str(p)+': '+link)
    assert not broken,broken
    modules=list((root/'scripts').glob('*.py'))
    for p in modules:ast.parse(p.read_text(encoding='utf-8-sig'))
    assert not list((root/'docs').rglob('*.json'))
    assert not (root/'docs/evaluation_reports').exists()
    return {'status':'PASS','final_epochs':2,'V18_source_sha_and_signatures':len(reports),
      'training_rows':[1500,3000],'data_sha_checks':len(expected),'release_artifact_checks':len(checked),
      'python_syntax_files':len(modules),'internal_broken_links':broken,'mean_codex':reviews['mean_overall']}

if __name__=='__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[1]),ensure_ascii=False,indent=2))
