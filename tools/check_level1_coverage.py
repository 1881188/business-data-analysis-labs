"""Enforce the declared 22-unit milestone without counting plugin demos as labs."""
from pathlib import Path
import csv,json


def check(root):
    specs=json.loads((root/'config/implemented_labs.json').read_text(encoding='utf-8'))
    expected={f'B{i:02}' for i in range(1,23)}
    if not expected<=set(specs):raise AssertionError('Level-one migration units are incomplete')
    with (root/'docs/source-map.csv').open(encoding='utf-8-sig',newline='') as stream:all_rows=list(csv.DictReader(stream))
    rows=[r for r in all_rows if r['book'].startswith('1《')]
    excel=[r for r in rows if r['source_file'].endswith('.xlsx')]
    cases=[r for r in rows if r['source_file'].endswith('.pbix') and '图表安装文件' not in r['source_file']]
    if len(rows)!=401 or len(excel)!=62 or len(cases)!=11:raise AssertionError('Source inventory changed; review milestone scope')
    for row in excel+cases:
        if row['lab_id'] not in expected or row['target_script']!=specs[row['lab_id']]['entry'] or row['status'] not in ['reference_verified','execution_verified']:
            raise AssertionError('Missing level-one workbook/PBIX destination: '+row['source_file'])
    for lab in expected:
        summary=json.loads((root/'docs/results'/lab/'summary.json').read_text(encoding='utf-8'))
        if summary['status'] not in ['reference_verified','execution_verified']:raise AssertionError('Unverified level-one lab')
    print('PASS: level-one 22/22 declared units; 62 workbooks and 11 case PBIX destinations; 401 materials retained.')


if __name__=='__main__':check(Path(__file__).resolve().parents[1])
