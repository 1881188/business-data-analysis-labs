"""Check source syntax, local Markdown links and published result provenance, without private data."""
from pathlib import Path
import ast,csv,json,re,sys
from urllib.parse import unquote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bda_labs.common import ROOT,sha256
from build_docs import PUBLIC


def main():
    for folder in [ROOT/"src",ROOT/"labs",ROOT/"tools",ROOT/"tests"]:
        for path in folder.rglob("*.py"):ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
    ast.parse((ROOT/"run_labs.py").read_text(encoding="utf-8"))
    docs=[ROOT/"README.md",*list((ROOT/"docs").rglob("*.md")),*list((ROOT/"labs").rglob("README.md")),ROOT/"data/README.md"]
    for path in docs:
        text=path.read_text(encoding="utf-8")
        if text.count('```')%2:raise AssertionError(f"Unclosed code fence: {path}")
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if re.match(r'^(https?://|#|mailto:)',target):continue
            target=unquote(target.strip('<>').split('#')[0])
            if target and not (path.parent/target).exists():raise AssertionError(f"Broken local link {path}: {target}")
    for lab in ['B05','S01','S11']:
        summary=json.loads((ROOT/f"docs/results/{lab}/summary.json").read_text(encoding="utf-8"))
        for path,digest in summary['implementation_sha256'].items():
            if sha256(ROOT/path)!=digest:raise AssertionError(f"Stale results: {lab} / {path}")
        expected={f'{lab}/{name}' for name in PUBLIC[lab]}
        actual={p.relative_to(ROOT/'docs/results').as_posix() for p in (ROOT/f'docs/results/{lab}').rglob('*') if p.is_file()}
        if expected!=actual:raise AssertionError(f'Publication file set differs from the allowlist: {lab}')
        registry=json.loads((ROOT/'config/datasets.json').read_text(encoding='utf-8'))
        for key,source in summary['source_files'].items():
            if registry[key]!=source:raise AssertionError(f'Dataset manifest changed since {lab} ran: {key}')
    with (ROOT/'docs/source-map.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    if len(rows)!=572:raise AssertionError('Incomplete material map')
    if len([r for r in rows if r['source_file'].endswith('.ipynb')])!=58:raise AssertionError('Incomplete Notebook map')
    forbidden={'customers.csv','test_predictions.csv','split_membership.csv','write.csv'}
    for path in (ROOT/'docs/results').rglob('*'):
        if path.name in forbidden:raise AssertionError(f'Private or intermediate output in publication: {path}')
    print('PASS: Python syntax, local links, 3 result provenance records, 572 source mappings and publication allowlist.')


if __name__=='__main__':main()
