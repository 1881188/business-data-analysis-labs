"""Shared output/provenance conventions for the remaining CDA notebooks."""
import json
import importlib.metadata

import numpy as np
import pandas as pd

from bda_labs.common import ROOT, finish, plotting, save_table
from bda_labs.notebook_reference import read_notebook, write_coverage


def specification(lab):
    return json.loads((ROOT / 'config/advanced_labs.json').read_text(encoding='utf-8'))[lab]


def read_csv(ctx, key, **kwargs):
    path = ctx.source(key)
    if 'encoding' in kwargs:
        return pd.read_csv(path, **kwargs)
    try:
        return pd.read_csv(path, encoding='utf-8-sig', **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding='gb18030', **kwargs)


def complete(ctx, lab, records, details, *, notes='', status='execution_verified'):
    spec = specification(lab)
    nb = read_notebook(ctx.source(spec['notebook']))
    sections = [(s['cells'], s['topic'], s['implementation']) for s in spec['sections']]
    coverage = write_coverage(nb, sections, ctx.output / 'notebook-map.md')
    metrics = pd.DataFrame(records)
    save_table(metrics, ctx.output / 'metrics.csv')
    summary = {'lab_id': lab, 'title': spec['title'], 'status': status,
               'notebook_coverage': coverage, **details}
    summary['advanced_runtime']={}
    for name in ['networkx','xgboost','lightgbm','tensorflow','toad','prophet','imbalanced-learn','optuna']:
        try:summary['advanced_runtime'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    report = (f"# {lab} · {spec['title']}\n\n{spec['purpose']}\n\n"
              f"## 实现与调整\n\n{spec['method']}\n\n{notes}\n\n"
              '## 运行结果\n\n完整聚合结果见 [metrics.csv](metrics.csv)，'
              '原单元格去向见 [notebook-map.md](notebook-map.md)。'
              '\n\n![实验结果](figure.png)\n\n'
              '源文件按 SHA-256 校验；不加载教材附带的序列化模型。'
              '本报告的运行通过表示代码可执行并完成内部校验，'
              '不表示与旧 Notebook 的随机结果或未提供的线上结果完全一致。\n')
    finish(ctx, summary, report)


def bars(ctx, labels, values, title, ylabel='value'):
    values = np.asarray(values, dtype=float)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError('A public chart requires finite aggregate values')
    plt = plotting()
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(range(len(values)), values, color='#286a85')
    ax.set_xticks(range(len(values)), labels, rotation=35, ha='right')
    ax.set(title=title, ylabel=ylabel)
    fig.tight_layout()
    fig.savefig(ctx.output / 'figure.png', dpi=150)
    plt.close(fig)
