"""Parse printed numerical reference arrays without evaluating notebook source code."""
import re
import numpy as np

NUMBER = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'


def numpy_tokens(text, allow_ellipsis=False):
    start, end = text.find('['), text.rfind(']')
    if start < 0 or end < start:
        raise ValueError('No printed array was found')
    body = text[start:end+1]
    if '...' in body and not allow_ellipsis:
        raise ValueError('Truncated arrays cannot be treated as complete references')
    cleaned = body.replace('...', '')
    tokens = re.sub(r'[,\[\]]',' ',cleaned).split()
    if not tokens or not all(re.fullmatch(NUMBER,token) for token in tokens):
        raise ValueError('Unexpected content in printed numeric array')
    return tokens


def check_printed(actual,reference):
    expected = float(reference)
    mantissa,*exponent = reference.lower().split('e')
    decimals = len(mantissa.partition('.')[2])
    unit = 10.**((int(exponent[0]) if exponent else 0)-decimals)
    tolerance = max(unit/2,64*np.finfo(float).eps*abs(expected))
    difference = abs(float(actual)-expected)
    if not np.isfinite(actual) or difference > tolerance:
        raise AssertionError(f'Printed reference differs: actual={actual}, reference={reference}')
    return {'actual':float(actual),'reference_text':reference,'absolute_tolerance':tolerance,
            'absolute_difference':difference,'roundoff_relative_bound':64*np.finfo(float).eps}


def indexed_table_tokens(text, rows, columns):
    tokens = []
    found = []
    for line in text.splitlines():
        match = re.match(r'^\s*(\d+)\s+(.+)$', line)
        if match and len(match.group(2).split()) == columns:
            values = match.group(2).split()
            if all(re.fullmatch(NUMBER, v) for v in values):
                found.append(int(match.group(1)))
                tokens.extend(values)
    if found != list(range(rows)):
        raise ValueError('Printed table row labels or shape differ from the expected reference')
    return tokens


def check_array(actual, tokens):
    values = np.asarray(actual, dtype=float).ravel()
    if len(values) != len(tokens):
        raise AssertionError('Reference array size differs')
    checks = [check_printed(a, b) for a,b in zip(values,tokens)]
    return {'values_compared':len(checks),'mismatches':0,
            'maximum_absolute_difference':max((c['absolute_difference'] for c in checks),default=0.),
            'maximum_absolute_tolerance':max((c['absolute_tolerance'] for c in checks),default=0.),
            'precision_checks':checks}
