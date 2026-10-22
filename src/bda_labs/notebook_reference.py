"""Read cached notebook text and document coverage without executing source cells."""
import json
import re

import numpy as np


def read_notebook(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def cached_text(notebook, cell_number):
    parts = []
    for output in notebook['cells'][cell_number - 1].get('outputs', []):
        value = output.get('data', {}).get('text/plain', output.get('text', []))
        parts.append(value if isinstance(value, str) else ''.join(value))
    return '\n'.join(parts)


def cached_series(notebook, cell_number):
    return dict(re.findall(r'^\s*(\S+)\s+([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\s*$',
                           cached_text(notebook, cell_number), flags=re.MULTILINE))


def compare_displayed(actual, reference):
    """Compare to printed precision, allowing only representation roundoff beyond it."""
    expected = float(reference)
    mantissa, *exponent = reference.lower().split('e')
    decimals = len(mantissa.partition('.')[2])
    unit = 10. ** ((int(exponent[0]) if exponent else 0) - decimals)
    tolerance = max(unit / 2 + 1e-14, 64 * np.finfo(float).eps * abs(expected))
    difference = abs(float(actual) - expected)
    if not np.isfinite(actual) or difference > tolerance:
        raise AssertionError(f'Cached output differs: actual={actual}, reference={reference}')
    return {'actual': float(actual), 'reference_text': reference,
            'absolute_tolerance': tolerance, 'absolute_difference': difference,
            'roundoff_relative_bound': 64 * np.finfo(float).eps}


def write_coverage(notebook, sections, path):
    """Require every nonempty code cell to have an explicit implementation mapping."""
    code_cells = {i for i, c in enumerate(notebook['cells'], 1)
                  if c['cell_type'] == 'code' and ''.join(c.get('source', [])).strip()}
    mapped = {}
    lines = ['# Notebook迁移对照', '', '仅记录教学意图和实现去向，不执行或整段复制教材代码。', '',
             '| 原单元格 | 教学内容 | Python实现与调整 |', '|---|---|---|']
    for numbers, topic, implementation in sections:
        for i in numbers:
            if i in mapped:
                raise AssertionError(f'Notebook cell {i} mapped twice')
            mapped[i] = topic
        lines.append(f"| {', '.join(map(str, numbers))} | {topic} | {implementation} |")
    if set(mapped) != code_cells:
        raise AssertionError(f'Coverage differs: missing={code_cells-set(mapped)}, extra={set(mapped)-code_cells}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return {'nonempty_code_cells': len(code_cells), 'mapped_code_cells': len(mapped),
            'source_cells_total': len(notebook['cells'])}
