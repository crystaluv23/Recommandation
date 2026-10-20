"""Apply only the ten inventoried explicit synthetic issuer metadata bindings."""
import ast
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
inventory=json.loads((HERE/'remaining-old-fixture-diagnosis.json').read_text())
sha=lambda raw:hashlib.sha256(raw).hexdigest()
records=[]
for filename in inventory['minimal_proposal']['files']:
    path=REPO/filename; before=path.read_bytes()
    backup=HERE/('before-named-producer-'+path.name)
    if backup.exists(): assert backup.read_bytes()==before
    else: backup.open('xb').write(before)
    lines=before.decode().splitlines(keepends=True)
    tree=ast.parse(before)
    chosen={r['line'] for r in inventory['producer_inventory'] if r['file']==filename and r['content_producer']=='sec_company_facts_content'}
    insertions=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Call) and n.lineno in chosen:
            content=next(k.value for k in n.keywords if k.arg=='content')
            line=lines[content.lineno-1]
            assert line.lstrip().startswith('content=')
            indent=line[:len(line)-len(line.lstrip())]
            insertions.append((content.lineno-1,indent+'metadata={"cik": "0000000001"},\n'))
    assert len(insertions)==len(chosen)
    for index,line in sorted(insertions,reverse=True):lines.insert(index,line)
    after=''.join(lines).encode()
    # Deleting precisely the inserted binding lines restores every original byte.
    restored_lines=list(lines)
    for offset,(index,line) in reversed(list(enumerate(sorted(insertions)))):
        assert restored_lines[index+offset]==line
        del restored_lines[index+offset]
    assert ''.join(restored_lines).encode()==before
    path.write_bytes(after)
    records.append({'path':str(path),'before_sha256':sha(before),'after_sha256':sha(after),'insertions':len(insertions),'removing_only_inserted_lines_restores_original_bytes':True})
with (HERE/'named-producer-patch-bindings.json').open('x') as f:json.dump({'files':records,'total':sum(r['insertions'] for r in records)},f,indent=2)
print(json.dumps(records))
