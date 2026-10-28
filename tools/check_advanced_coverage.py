"""Check advanced notebook source identity, cell mapping and duplicate scope offline."""
from pathlib import Path
import csv
import ast
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]


def check(root=ROOT):
    advanced=json.loads((root/'config/advanced_labs.json').read_text(encoding='utf-8'))
    datasets=json.loads((root/'config/datasets.json').read_text(encoding='utf-8'))
    implemented=json.loads((root/'config/implemented_labs.json').read_text(encoding='utf-8'))
    experiments={e['lab_id']:e for e in json.loads((root/'config/experiments.json').read_text(encoding='utf-8'))}
    with (root/'docs/source-map.csv').open(encoding='utf-8-sig',newline='') as stream:
        sources={r['source_id']:r for r in csv.DictReader(stream)}
    expected={f'M{i:02d}' for i in range(1,30)}|{f'F{i:02d}' for i in range(2,17)}
    if set(advanced)!=expected or expected-set(implemented):raise AssertionError('Advanced source coverage incomplete')
    total=0
    for lab,spec in advanced.items():
        source=sources[experiments[lab]['source_id']]
        notebook=datasets[spec['notebook']]
        if source['source_sha256']!=notebook['sha256'] or source['source_file']!=notebook['path']:
            raise AssertionError(f'Notebook identity differs: {lab}')
        summary=json.loads((root/f'docs/results/{lab}/summary.json').read_text(encoding='utf-8'))
        cells=[i for section in spec['sections'] for i in section['cells']]
        coverage=summary['notebook_coverage']
        if len(set(cells))!=len(cells) or len(cells)!=coverage['nonempty_code_cells'] or len(cells)!=coverage['mapped_code_cells']:
            raise AssertionError(f'Cell mapping differs: {lab}')
        if spec['notebook'] not in summary['source_files'] or any(k not in summary['source_files'] for k in spec['inputs']):
            raise AssertionError(f'Not every registered source was read: {lab}')
        for path,proof in summary.get('publication_line_endings',{}).items():
            published=(root/path).read_bytes()
            executed=published.replace(b'\n',b'\r\n')
            if b'\r' in published or proof['operation']!='CRLF_to_LF_only':raise AssertionError('Unexpected source transport normalization')
            if hashlib.sha256(executed).hexdigest()!=proof['executed_sha256'] or hashlib.sha256(published).hexdigest()!=proof['published_sha256']:
                raise AssertionError('Execution/publication byte proof differs')
            if proof['published_sha256']!=summary['implementation_sha256'][path]:raise AssertionError('Normalized code manifest differs')
            if path.endswith('.py') and ast.dump(ast.parse(executed.decode('utf-8')))!=ast.dump(ast.parse(published.decode('utf-8'))):raise AssertionError('Normalized Python AST differs')
            if path.endswith('.json') and json.loads(executed)!=json.loads(published):raise AssertionError('Normalized JSON value differs')
        total+=len(cells)
    if 'F01' in implemented or experiments['F01']['status']!='待补资料':raise AssertionError('Missing F01 input must not count as verified')
    if not (root/experiments['F01']['target_script']).is_file():raise AssertionError('Pending F01 Python entry missing')
    duplicate=json.loads((root/'docs/results/F04/summary.json').read_text(encoding='utf-8'))
    if duplicate['duplicate_of']!='F05':raise AssertionError('Vintage duplicate must be explicit')
    if (root/'docs/results/F04/metrics.csv').read_bytes()!=(root/'docs/results/F05/metrics.csv').read_bytes():
        raise AssertionError('Shared Vintage implementation produced different duplicate outputs')
    print(f'PASS: 44 advanced source entries, {total} code cells mapped, F04/F05 duplicate explicit, F01 remains pending.')


if __name__=='__main__':check()
