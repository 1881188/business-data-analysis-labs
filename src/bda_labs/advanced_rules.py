"""Exact basket Apriori and ordered itemset sequence mining without legacy packages."""
from collections import Counter
from itertools import combinations
import math

import pandas as pd

from bda_labs.common import context
from bda_labs.advanced_common import read_csv, specification, complete, bars


def frequent_itemsets(baskets, min_support):
    if not 0 < min_support <= 1 or not baskets:
        raise ValueError('Support must be in (0,1] and baskets must be nonempty')
    baskets = [frozenset(b) for b in baskets]
    cutoff = math.ceil(min_support * len(baskets) - 1e-12)
    counts = Counter(x for b in baskets for x in b)
    level = {frozenset([x]) for x, n in counts.items() if n >= cutoff}
    result = {s: sum(s <= b for b in baskets) for s in level}
    k = 2
    while level:
        candidates = {a | b for a in level for b in level if len(a | b) == k}
        candidates = {s for s in candidates if all(frozenset(t) in level for t in combinations(sorted(s), k - 1))}
        found = {s: sum(s <= b for b in baskets) for s in candidates}
        level = {s for s, n in found.items() if n >= cutoff}
        result.update({s: found[s] for s in level})
        k += 1
    return result


def association_rules(itemsets, n):
    rows = []
    for items, count in itemsets.items():
        for size in range(1, len(items)):
            for subset in combinations(sorted(items), size):
                a = frozenset(subset); b = items - a
                support, coverage, consequent = count / n, itemsets[a] / n, itemsets[b] / n
                confidence = support / coverage
                rows.append({'antecedents': ' + '.join(sorted(a)), 'consequents': ' + '.join(sorted(b)),
                             'support': support, 'confidence': confidence, 'lift': confidence / consequent,
                             'coverage': coverage, 'leverage': support - coverage * consequent})
    return sorted(rows, key=lambda r: (-r['support'], r['antecedents'], r['consequents']))


def contains_sequence(events, pattern):
    """Each pattern itemset must occur within one later event (gaps allowed)."""
    j = 0
    for event in events:
        if j < len(pattern) and pattern[j] <= event:
            j += 1
    return j == len(pattern)


def sequence_patterns(sequences, min_count):
    """Exhaustive anti-monotone pattern growth, both same-event and later-event.

    Customer support counts once even when a pattern occurs multiple times.
    There is no arbitrary pattern-length truncation.
    """
    if min_count < 1:
        raise ValueError('min_count must be positive')
    alphabet = sorted({v for seq in sequences for event in seq for v in event})
    stack = [(frozenset([x]),) for x in reversed(alphabet)]
    result = {}
    while stack:
        pattern = stack.pop()
        count = sum(contains_sequence(seq, pattern) for seq in sequences)
        if count < min_count:
            continue
        result[pattern] = count
        # Lexicographic extensions of the final itemset avoid duplicate patterns.
        for x in reversed(alphabet):
            stack.append(pattern + (frozenset([x]),))
            if x > max(pattern[-1]):
                stack.append(pattern[:-1] + (pattern[-1] | {x},))
    return result


def main(lab, argv=None):
    ctx = context(lab, argv)
    data = read_csv(ctx, specification(lab)['inputs'][0])
    if data[['CSR_ID', 'PROD', 'OrderNumber']].isna().any().any():
        raise ValueError('Missing transaction key/product/order')
    baskets = data.groupby('CSR_ID')['PROD'].apply(list).tolist()
    if lab == 'M09':
        sequences = []
        for _, customer in data.groupby('CSR_ID', sort=True):
            # OrderNumber is the source's ordering proxy, not a timestamp.
            sequences.append([frozenset(g['PROD']) for _, g in customer.groupby('OrderNumber', sort=True)])
        levels = [('AprioriAll_support_0.1', math.ceil(.1 * len(sequences) - 1e-12)),
                  ('PrefixSpan_count_100', 100)]
        records = []
        counts = {}
        for name, cutoff in levels:
            found = sequence_patterns(sequences, cutoff)
            counts[name] = len(found)
            for pattern, n in sorted(found.items(), key=lambda x: (-x[1], str(x[0]))):
                records.append({'section': name, 'item': ' → '.join('{' + ','.join(sorted(s)) + '}' for s in pattern),
                                'count': n, 'value': n / len(sequences)})
        bars(ctx, list(counts), list(counts.values()), '银行产品：序列模式数量', 'patterns')
        complete(ctx, lab, records, {'customers': len(sequences), 'pattern_counts': counts},
                 notes='以客户为支持度分母；同一订单为无序项集，订单之间有先后。采用完整模式增长重建两种阈值的结果；不依赖旧教学脚本。OrderNumber 仅是教材顺序代理，不能推断真实时间间隔。')
        return
    support = .02 if lab == 'M08' else .01
    found = frequent_itemsets(baskets, support)
    rules = association_rules(found, len(baskets))
    selected = [r for r in rules if r['confidence'] > .1 and r['lift'] > 1]
    records = [{'section': 'frequent_itemset', 'item': ' + '.join(sorted(items)), 'count': n, 'support': n / len(baskets)}
               for items, n in sorted(found.items(), key=lambda x: (-x[1], str(sorted(x[0]))))]
    records += [{'section': 'rule', **r} for r in rules]
    if lab == 'M11':
        for name, predicate in [('财务通', lambda r: '财务通' in r['antecedents'] or '财务通' in r['consequents']),
                                ('好享贷', lambda r: '好享贷' in r['consequents'])]:
            records += [{'section': name, **r} for r in rules if predicate(r) and r['lift'] >= 1]
    bars(ctx, ['frequent itemsets', 'all rules', 'confidence>0.1 & lift>1'],
         [len(found), len(rules), len(selected)], '银行产品交叉销售：关联规则数量', 'count')
    complete(ctx, lab, records, {'customers': len(baskets), 'transaction_rows': len(data),
                                'min_support': support, 'frequent_itemsets': len(found), 'rules': len(rules),
                                'selected_rules': len(selected)},
             notes='布尔篮子以客户去重，重复购买不重复计数。修正旧 FP-growth 示例以交易行数作分母的问题；原先 mlxtend / Orange 的规则定义由精确 Apriori 重建，支持度、置信度、提升度逐式计算。规则描述共现，不能视为营销的因果效果。')
