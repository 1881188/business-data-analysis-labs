"""Inspect report metadata; queryRef labels can outlive aggregation changes."""
import json
import zipfile
import pandas as pd
from .workbook_reference import pbix_visuals

AGGREGATIONS = {0: 'Sum', 1: 'Avg', 2: 'Count', 3: 'Min', 4: 'Max',
                5: 'CountNonNull', 6: 'Median', 7: 'StandardDeviation', 8: 'Variance'}
AGGREGATION_SOURCE = 'https://github.com/microsoft/skills-for-fabric/blob/main/skills/powerbi-report-cli/references/authoring/expressions.md'


def visual_audit(path, destinations):
    """Map every container including text and slicers; never decode the binary model."""
    rows = pbix_visuals(path)
    with zipfile.ZipFile(path) as archive:
        layout = json.loads(archive.read('Report/Layout').decode('utf-16le'))
    containers = [(p, v) for p in layout['sections'] for v in p.get('visualContainers', [])]
    if len(rows) != len(destinations):
        raise ValueError('Every Power BI visual requires an explicit migration destination')
    for row, (page, container), destination in zip(rows, containers, destinations):
        visual = json.loads(container.get('config', '{}')).get('singleVisual', {})
        title = visual.get('vcObjects', {}).get('title', [])
        row['title_literal'] = '; '.join(str(t.get('properties', {}).get('text', {})) for t in title)
        row['aggregations'] = json.dumps([
            {**a, 'function': AGGREGATIONS.get(a['function_code'], 'unknown')}
            for a in row['aggregations']], ensure_ascii=False)
        row['filters'] = json.dumps({'report': layout.get('filters'), 'page': page.get('filters'),
                                     'visual': container.get('filters')}, ensure_ascii=False)
        row['order_by'] = json.dumps(visual.get('prototypeQuery', {}).get('OrderBy', []), ensure_ascii=False)
        row['source'] = path.name
        row['python_destination'] = destination
    return pd.DataFrame(rows)
