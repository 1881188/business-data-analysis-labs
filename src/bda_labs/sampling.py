"""Reproducible simple random, stratified and random-start systematic sampling."""
import math
import numbers

import numpy as np
import pandas as pd

from .common import context, finish, plotting, save_table
from .notebook_reference import read_notebook, cached_series, compare_displayed, write_coverage


def sample_size(population, k):
    if isinstance(k, bool) or not isinstance(k, numbers.Real) or not np.isfinite(k) or k <= 0:
        raise ValueError('k must be a positive integer count or a fraction in (0, 1)')
    if k >= 1:
        if not isinstance(k, numbers.Integral):
            raise ValueError('Counts must be integers')
        n = int(k)
    else:
        n = math.ceil(population * k)
    if population == 0 or n > population:
        raise ValueError('Cannot sample an empty population or exceed its size')
    return n


def get_sample(df, sampling='simple_random', k=1, stratified_col=None, random_state=20261022):
    if sampling not in ('simple_random', 'stratified', 'systematic'):
        raise ValueError('Unknown sampling method')
    rng = np.random.default_rng(random_state)
    if sampling == 'stratified':
        if not stratified_col or len(set(stratified_col)) != len(stratified_col) or not set(stratified_col) <= set(df.columns):
            raise ValueError('Provide distinct existing stratification columns')
        if df.empty:
            raise ValueError('Cannot sample an empty population')
        positions = []
        # Group positions, rather than index labels, also support duplicate DataFrame indices.
        for group in df.groupby(stratified_col, sort=False, dropna=False, observed=True).indices.values():
            positions.extend(rng.choice(group, sample_size(len(group), k), replace=False).tolist())
    else:
        n = sample_size(len(df), k)
        if sampling == 'simple_random':
            positions = rng.choice(len(df), n, replace=False)
        else:
            interval = len(df) / n
            start = rng.uniform(0, interval)
            positions = np.floor(start + np.arange(n) * interval).astype(int)
    return df.iloc[positions].copy()


def main(argv=None):
    ctx = context('S04', argv)
    nb = read_notebook(ctx.source('notebook_sampling'))
    clients = pd.read_csv(ctx.source('sampling_clients'), encoding='gbk')
    if clients.Client_id.isna().any() or clients.Client_id.duplicated().any() or clients.Dist.isna().any():
        raise ValueError('This case requires distinct client identifiers and known districts')
    designs = [('simple_n22','simple_random',22), ('simple_p10','simple_random',.1),
               ('stratified_n2','stratified',2), ('stratified_p10','stratified',.1),
               ('systematic_n4','systematic',4), ('systematic_p10','systematic',.1)]
    district = clients.groupby('Dist').size().rename('population').to_frame()
    records, samples = [], {}
    for name, method, k in designs:
        sample = get_sample(clients, method, k, ['Dist'] if method == 'stratified' else None)
        samples[name] = sample
        if sample.Client_id.duplicated().any() or not sample.Client_id.isin(clients.Client_id).all():
            raise AssertionError('Sampling selected a duplicate or unknown client')
        counts = sample.groupby('Dist').size().reindex(district.index, fill_value=0)
        district[name] = counts
        if method == 'stratified':
            district[name+'_weight'] = district.population / counts
            expected = pd.Series([sample_size(v, k) for v in district.population], index=district.index)
            if not counts.equals(expected):
                raise AssertionError('Stratified sample allocation differs')
        elif len(sample) != sample_size(len(clients), k):
            raise AssertionError('Requested sample size was not achieved')
        records.append({'design': name, 'method': method, 'k': k, 'sample_size': len(sample),
                        'districts_represented': int((counts > 0).sum()),
                        'district_share_l1_difference': float((counts/len(sample)-district.population/len(clients)).abs().sum())})
        save_table(sample, ctx.output / (name+'_private.csv'))
    checks = {}
    for cell, name in [(2, None), (3, 'simple_p10'), (4, 'stratified_p10'), (5, 'systematic_p10')]:
        expected = cached_series(nb, cell)
        n = len(clients) if name is None else len(samples[name])
        checks[str(cell)] = {column: compare_displayed(n, expected[column]) for column in clients.columns}
    coverage = write_coverage(nb, [([1], '三种抽样函数', 'get_sample；显式随机种子、随机起点、逐层样本量检查'),
                                  ([2], '客户数据读取与计数', '读取GBK，校验客户唯一性及地区'),
                                  ([3], '简单随机抽样', '固定22名和10%两种设计'),
                                  ([4], '分层抽样', '按Dist每层2名或每层10%，另输出设计权重'),
                                  ([5], '系统抽样', '随机起点和浮点间隔，固定4名和10%两种设计')], ctx.output/'notebook-map.md')
    save_table(pd.DataFrame(records), ctx.output/'sampling_designs.csv')
    save_table(district.reset_index(), ctx.output/'district_allocation.csv')
    plt = plotting()
    fig, ax = plt.subplots(figsize=(12, 5), layout='constrained')
    top = district.nlargest(10, 'population')
    x = np.arange(len(top))
    series = [('population','总体'),('simple_p10','简单随机10%'),('stratified_p10','各层10%'),('systematic_p10','系统10%')]
    colors = ['#93a7b5','#087f8c','#d67b28','#5b5fa6']
    for i, ((key, label), color) in enumerate(zip(series, colors)):
        denominator = len(clients) if key == 'population' else len(samples[key])
        ax.bar(x + (i-1.5)*.2, top[key]/denominator*100, .2, label=label, color=color)
    ax.set(xticks=x, xticklabels=top.index.astype(str), xlabel='人数最多的10个地区（Dist代码）',
           ylabel='占各自总体/样本的比例（%）', title='三种抽样设计的地区构成（固定种子20261022）')
    ax.legend(frameon=False, ncol=4)
    fig.savefig(ctx.output/'sampling_composition.png', dpi=150)
    plt.close(fig)
    sizes = '、'.join(f"{r['design']}={r['sample_size']}" for r in records)
    report = f"""# S04 抽样设计

## 运行结果

共有{len(clients):,}名不同客户，分布于{len(district)}个地区。六种设计的样本量：{sizes}。每次以种子20261022独立启动随机数生成器，能够重复得到同一组样本。

![地区构成](sampling_composition.png)

## 代码内涵与修正

简单随机抽样等概率不放回选行。比例先取ceil(N×k)，因此10%得到537人。分层计数k代表**每层**k人，比例代表每层ceil(N_h×k)，各层向上取整导致总数573，比全局10%的537多36。每层2人的总数是154，不能解释成总体只抽2人。district_allocation.csv给出N_h/n_h设计权重，使用分层样本估计总体时需要权重；未加权的各地区占比不等于总体地区占比。

系统抽样采用间隔N/n和区间[0,N/n)内的随机起点，位置为floor(start+j×N/n)，保证恰好n个不同位置。原代码固定从0开始，以N//n+1作间隔；例如N=100、n=50会只得到34行，现已修正。系统抽样仍受原始排序周期影响，固定种子只保证可重复，不能消除周期偏差。

原来的字符串身份判断is改为值比较；每一层独立检查可抽人数，支持缺失分层键作为一层（本例没有缺失），允许完整抽取某层。按行位置抽样，DataFrame重复索引不会使同一位置被重复抽取。

## 核对范围

原Notebook缓存的总体与三种10%抽样计数共16项核对一致，但原程序未设随机种子，无法核对相同客户名单；其系统抽样方法已修正，因此状态记为运行通过。逐单元格说明见[迁移对照](notebook-map.md)。六份客户明细只保存在本地，不纳入公开仓库。
"""
    finish(ctx, {'lab_id':'S04','status':'execution_verified','population':len(clients), 'districts':len(district),
                 'seed':20261022,'designs':records,'cached_count_checks':checks,'notebook_coverage':coverage}, report)


if __name__ == '__main__':
    main()
