"""Check source syntax, local Markdown links and published result provenance, without private data."""
from pathlib import Path
import ast,csv,json,re,sys
from urllib.parse import unquote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from bda_labs.common import ROOT,sha256
from build_docs import PUBLIC


def main():
    specs=json.loads((ROOT/'config/implemented_labs.json').read_text(encoding='utf-8'))
    experiments={r['lab_id']:r for r in json.loads((ROOT/'config/experiments.json').read_text(encoding='utf-8'))}
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
    for lab in PUBLIC:
        summary=json.loads((ROOT/f"docs/results/{lab}/summary.json").read_text(encoding="utf-8"))
        if lab in {'B11','B12'} and any(value is not None for value in summary.get('selection',{}).values()):
            raise AssertionError(f'Published {lab} report must use the default full-data selection')
        if lab=='B13':
            if summary.get('real_case_metrics_published') is not False or {'metrics','diagnostics'} & set(summary):
                raise AssertionError('Restricted B13 results must remain local')
            if any(name not in {'report.md','summary.json','workbook-map.md'} and not name.startswith('synthetic_') for name in PUBLIC[lab]):
                raise AssertionError('Unexpected real-case B13 publication artifact')
        expected_state='参考核对通过' if summary['status']=='reference_verified' else '运行通过'
        if experiments[lab]['status']!=expected_state or experiments[lab]['target_script']!=specs[lab]['entry']:
            raise AssertionError(f'Experiment registry does not match the published result: {lab}')
        coverage=summary.get('notebook_coverage')
        if coverage and coverage['nonempty_code_cells']!=coverage['mapped_code_cells']:
            raise AssertionError(f'Incomplete Notebook coverage: {lab}')
        workbook_coverage=summary.get('workbook_coverage')
        if workbook_coverage and workbook_coverage['source_sheets']!=workbook_coverage['mapped_sheets']:
            raise AssertionError(f'Incomplete worksheet coverage: {lab}')
        if 'source_formula_cells' in summary and summary['source_formula_cells']!=summary['formula_cells_covered']:
            raise AssertionError(f'Incomplete saved-formula coverage: {lab}')
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
    print(f'PASS: Python syntax, local links, {len(PUBLIC)} result provenance records, 572 source mappings and publication allowlist.')


if __name__=='__main__':main()
