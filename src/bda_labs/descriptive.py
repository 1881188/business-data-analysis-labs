"""Descriptive statistics, rank correlations and a reproducible shape demonstration."""
from fractions import Fraction
import re
import numpy as np
import pandas as pd

from .common import context, finish, plotting, save_table
from .notebook_reference import read_notebook, cached_text, cached_series, compare_displayed, write_coverage


def describe_price(raw):
    frame = raw[['AREA', 'price']].apply(pd.to_numeric, errors='raise').copy()
    if len(frame) < 2 or not np.isfinite(frame.to_numpy()).all():
        raise ValueError('Complete finite AREA/price values and at least two observations are required')
    if (frame.nunique() < 2).any():
        raise ValueError('Correlation requires nonconstant columns')
    price = frame.price
    metrics = {'count':len(price),'mean':float(price.mean()),'median':float(price.median()),
               'std':float(price.std(ddof=1)), 'q25':float(price.quantile(.25)),
               'q50':float(price.quantile(.5)), 'q75':float(price.quantile(.75)),
               'range':float(price.max()-price.min()), 'variance':float(price.var(ddof=1))}
    correlations = {method:float(frame.corr(method).loc['AREA','price']) for method in ['pearson','spearman','kendall']}
    return frame, metrics, correlations


def main(argv=None):
    ctx = context('S03', argv)
    nb = read_notebook(ctx.source('notebook_descriptive'))
    raw = pd.read_csv(ctx.source('housing_statistics'))
    frame, metrics, correlations = describe_price(raw)
    # Integer price values allow an independent exact-arithmetic check of sample variance.
    if not frame.price.mod(1).eq(0).all():
        raise ValueError('This source-specific exact variance check requires integer prices')
    integers = list(map(int, frame.price))
    n = len(integers)
    exact_variance = float(Fraction(n*sum(v*v for v in integers)-sum(integers)**2,n*(n-1)))
    if not np.isclose(metrics['variance'],exact_variance,rtol=1e-15,atol=0):
        raise AssertionError('Sample variance differs from the independent exact-arithmetic check')
    checks = {}
    for cell, keys in [(3, ['mean','median','std']), (4, ['q25','q50','q75'])]:
        series = cached_series(nb, cell)
        names = keys if cell == 3 else ['0.25','0.50','0.75']
        for key, name in zip(keys, names):
            checks[key] = compare_displayed(metrics[key], series[name])
    for cell, key in [(7,'range'), (8,'variance'), (9,'std')]:
        checks['cell_'+str(cell)] = compare_displayed(metrics[key], cached_text(nb, cell).strip())
    for cell, key in [(15,'pearson'),(16,'spearman'),(17,'kendall')]:
        line = next(line for line in cached_text(nb, cell).splitlines() if re.match(r'^AREA\s+[-+]?\d',line))
        checks[key] = compare_displayed(correlations[key], line.split()[-1])
    normal = pd.Series(np.random.default_rng(20261022).normal(size=1000))
    shape = {'seed':20261022,'n':len(normal),'sample_skew':float(normal.skew()),
             'sample_excess_kurtosis':float(normal.kurtosis())}
    coverage = write_coverage(nb, [([2], '房源数据读取', 'describe_price；检查完整值，保持原始数据不变'),
        ([3,4], '集中趋势与分位数', '均值、中位数、样本标准差及线性插值四分位数'),
        ([5], '房价直方图', '20箱计数并校验记录总量'),
        ([7,8,9], '离散程度', '极差、ddof=1样本方差和标准差'),
        ([11,12,13,14], '正态分布形状演示', '固定种子20261022；偏度和超额峰度不与无种子旧结果强配'),
        ([15,16,17], '三种相关系数', 'Pearson、Spearman和Kendall，逐项核对缓存显示值')], ctx.output/'notebook-map.md')
    save_table(pd.DataFrame([metrics]), ctx.output/'price_statistics.csv')
    save_table(pd.DataFrame([{'method':k,'area_price_correlation':v} for k,v in correlations.items()]),ctx.output/'correlations.csv')
    counts, edges = np.histogram(frame.price, bins=20)
    if counts.sum() != len(frame):
        raise AssertionError('Histogram did not conserve the number of observations')
    save_table(pd.DataFrame({'left':edges[:-1],'right':edges[1:],'count':counts}),ctx.output/'price_histogram.csv')
    plt = plotting()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    axes[0].hist(frame.price, bins=edges, color='#087f8c', edgecolor='white')
    axes[0].axvline(metrics['mean'], color='#d67b28', label=f"均值 {metrics['mean']:,.1f}")
    axes[0].axvline(metrics['median'], color='#5b5fa6', linestyle='--', label=f"中位数 {metrics['median']:,.0f}")
    axes[0].set(title='price分布（20个等宽区间）', xlabel='price（原字段单位）', ylabel='房源记录数')
    axes[0].legend(frameon=False)
    axes[1].bar(['Pearson','Spearman','Kendall'], list(correlations.values()), color=['#087f8c','#d67b28','#5b5fa6'])
    axes[1].axhline(0, color='#96a6af')
    axes[1].set(title='AREA与price的相关系数', ylabel='相关系数', ylim=(-.16,.02))
    fig.savefig(ctx.output/'descriptive_statistics.png', dpi=150)
    plt.close(fig)
    report = f"""# S03 描述性统计与绘图

## 样本结果

原表有{len(raw):,}条房源记录，AREA和price均无缺失。price均值{metrics['mean']:,.6f}，中位数{metrics['median']:,.0f}，25%/75%分位数为{metrics['q25']:,.2f}/{metrics['q75']:,.2f}。样本标准差{metrics['std']:,.6f}，样本方差{metrics['variance']:,.8f}，极差{metrics['range']:,.0f}。

![分布与相关系数](descriptive_statistics.png)

均值高于中位数，说明均值受到较高price记录影响。AREA与price的Pearson为{correlations['pearson']:.6f}，Spearman为{correlations['spearman']:.6f}，Kendall为{correlations['kendall']:.6f}，均为较弱负关联。数据没有明确价格单位、采样框和采集时间，不能据此推断某地当前房价或“面积增大会导致降价”。

## 代码内涵

describe_price集中计算位置、离散程度和相关性。方差和标准差使用pandas默认的ddof=1，分母为n−1；它们不应与总体标准差混用。分位数采用线性插值。20个直方图区间的计数之和等于16,210，没有为图形展示丢弃极端值。

Notebook另生成1000个正态随机数演示偏度与峰度，但没有种子。本实现设种子20261022，偏度为{shape['sample_skew']:.6f}，超额峰度为{shape['sample_excess_kurtosis']:.6f}。正态总体的理论偏度和超额峰度均为0，有限随机样本不会恰好等于0；该随机演示不与旧缓存逐值对账。

## 核对范围

共12项房价统计/相关值在显示舍入与64倍机器精度的浮点容差内核对通过：3项均值/中位数/标准差、3项分位数、极差/方差/再次标准差，以及3种相关。重复标准差按不同源单元分别记录，不当作12个不同指标。旧方差缓存与本次相差{checks['cell_8']['absolute_difference']:.12g}（相对约{checks['cell_8']['absolute_difference']/metrics['variance']:.2g}），并非逐位相同；按整数price用有理数公式(n×Σx²−(Σx)²)/(n×(n−1))独立复算得到{exact_variance:.8f}，与本次方差一致。每项容差、原显示字符串和实际差值见summary.json。逐单元格说明见[迁移对照](notebook-map.md)，共{coverage['mapped_code_cells']}个非空代码单元。
"""
    finish(ctx, {'lab_id':'S03','status':'reference_verified','source_rows':len(raw),'statistics':metrics,
                 'correlations':correlations,'normal_demonstration':shape,'exact_integer_variance':exact_variance,
                 'reference_checks':checks,'notebook_coverage':coverage}, report)


if __name__ == '__main__':
    main()
