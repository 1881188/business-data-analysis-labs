"""Audit the textbook's income-zero rule without imputing or mutating source data."""
import numpy as np
import pandas as pd

from .common import context, finish, plotting, save_table
from .notebook_reference import read_notebook, cached_series, compare_displayed, write_coverage


def clean_income(raw):
    for column in ['AvgIncome','AvgHomeValue']:
        if not pd.api.types.is_numeric_dtype(raw[column]):
            raise ValueError(f'{column} must be numeric')
        observed = raw[column].dropna()
        if not np.isfinite(observed).all() or (observed < 0).any():
            raise ValueError(f'{column} contains unsupported negative or nonfinite values')
    result = raw.copy(deep=True)
    result['AvgIncome_was_zero'] = result.AvgIncome.eq(0)
    result['AvgIncome'] = result.AvgIncome.replace(0, np.nan)
    return result


def main(argv=None):
    ctx = context('S05', argv)
    nb = read_notebook(ctx.source('notebook_preprocessing'))
    raw = pd.read_csv(ctx.source('campaign_preprocessing'))
    if raw.ID.isna().any() or raw.ID.duplicated().any():
        raise ValueError('Expected distinct campaign customer identifiers')
    original = raw.copy(deep=True)
    cleaned = clean_income(raw)
    pd.testing.assert_frame_equal(raw, original)
    pd.testing.assert_frame_equal(cleaned[raw.columns.drop('AvgIncome')], raw.drop(columns='AvgIncome'))
    before_missing = int(raw.AvgIncome.isna().sum())
    zeros = int(raw.AvgIncome.eq(0).sum())
    after_missing = int(cleaned.AvgIncome.isna().sum())
    if len(cleaned) != len(raw) or after_missing != before_missing + zeros:
        raise AssertionError('Income missingness did not reconcile')
    checks = {}
    for cell, frame, column in [(2, raw, 'AvgIncome'), (3, raw, 'AvgHomeValue'), (6, cleaned, 'AvgHomeValue')]:
        actual = frame[column].describe()
        expected = cached_series(nb, cell)
        checks[str(cell)] = {key:compare_displayed(actual[key], value) for key,value in expected.items()}
        if len(expected) != 8:
            raise AssertionError('Expected all eight cached descriptive statistics')
    audit = pd.DataFrame({'field':raw.columns, 'missing_before':raw.isna().sum().to_numpy(),
                          'zeros_before':[(raw[c].eq(0).sum() if pd.api.types.is_numeric_dtype(raw[c]) else pd.NA) for c in raw],
                          'missing_after':cleaned[raw.columns].isna().sum().to_numpy()})
    stats = []
    for stage, frame in [('before',raw),('after',cleaned)]:
        for column in ['AvgIncome','AvgHomeValue']:
            stats.append({'stage':stage,'field':column,**frame[column].describe().to_dict()})
    save_table(audit,ctx.output/'missingness_audit.csv')
    save_table(pd.DataFrame(stats),ctx.output/'describe_comparison.csv')
    save_table(cleaned,ctx.output/'cleaned_campaign_private.csv')
    coverage = write_coverage(nb, [([1], '读取数据与初始直方图', '检查客户ID唯一，按全样本计算初始直方图'),
        ([2,3], '收入和房屋价值描述统计', '八项describe数值逐字段对照缓存'),
        ([4], '收入零值转缺失', 'clean_income使用np.nan，保留零值指示字段，不修改输入'),
        ([5], '清洗后直方图', '显式dropna；前后共用区间以比较分布'),
        ([6], '再次检查房屋价值', '保留原值，未擅自把房屋价值0判定为缺失')], ctx.output/'notebook-map.md')
    plt = plotting()
    fig, axes = plt.subplots(1,2,figsize=(12,5),sharey=True,layout='constrained')
    edges = np.linspace(raw.AvgIncome.min(), raw.AvgIncome.max(), 21)
    histograms = []
    for ax, frame, title in zip(axes,[raw,cleaned],['处理前','收入零值转缺失后']):
        observed = frame.AvgIncome.dropna()
        counts, _ = np.histogram(observed,bins=edges)
        if counts.sum() != len(observed):
            raise AssertionError('Histogram lost observed income records')
        histograms.append(counts.tolist())
        ax.hist(observed,bins=edges,color='#087f8c',edgecolor='white')
        ax.set(title=f'{title}（有效值{len(observed):,}条）',xlabel='AvgIncome（原字段单位）',ylabel='记录数')
        ax.ticklabel_format(axis='x',style='plain')
    fig.savefig(ctx.output/'income_preprocessing.png',dpi=150)
    plt.close(fig)
    report = f"""# S05 数据预处理与缺失审计

## 结果

原始数据有{len(raw):,}名不同客户。教材将AvgIncome=0视作缺失的规则应用后，{zeros:,}个零值转为缺失，收入有效值剩{len(raw)-after_missing:,}条，缺失率为{after_missing/len(raw):.2%}。记录总数不变，不删除客户，不做填补。

![收入处理前后](income_preprocessing.png)

收入字段均值由{raw.AvgIncome.mean():,.6f}变为{cleaned.AvgIncome.mean():,.6f}。均值变化来自零值转为缺失后统计分母改变，不能解释成客户收入上涨。前后直方图使用相同的20个区间及纵轴范围，两个图各自计数之和分别等于{int(raw.AvgIncome.notna().sum())}与{int(cleaned.AvgIncome.notna().sum())}。

## 代码内涵与边界

clean_income返回副本，使用np.nan替换旧写法np.NaN，并保留AvgIncome_was_zero以区分原有缺失与本次规则引入的缺失。此规则来自该教材案例，不能泛化为所有业务里的零收入都无效。没有变量字典支持时，先核对零值含义再用于实际模型。

AvgHomeValue有{int(raw.AvgHomeValue.eq(0).sum())}个零值，原Notebook只提示检查，没有执行替换。本实现保留它们并在missingness_audit.csv列出。ARPU原有{int(raw.ARPU.isna().sum()):,}个缺失，Age有{int(raw.Age.isna().sum()):,}个缺失，也保持不变。没有使用响应标签填补数据或拟合预测模型。

## 核对范围

三个原Notebook单元格的24项描述统计按原输出显示精度核对一致：收入处理前8项、房屋价值处理前8项、房屋价值再次检查8项。最后8项是重复检查，不当作24个不同指标。清洗后收入没有describe参考输出，只有本实现的记录守恒、缺失增量和非收入字段不变检查，不宣称它也有参考统计对照。图形采用统一箱界，未按原图不同箱界逐箱对账。

逐单元格说明见[迁移对照](notebook-map.md)。清洗后的客户明细只留在本地，公开文件是聚合审计和描述统计。
"""
    finish(ctx, {'lab_id':'S05','status':'reference_verified','source_rows':len(raw),'income_zeros_converted':zeros,
        'income_missing_before':before_missing,'income_missing_after':after_missing,'income_mean_before':float(raw.AvgIncome.mean()),
        'income_mean_after':float(cleaned.AvgIncome.mean()),'home_value_zeros_retained':int(raw.AvgHomeValue.eq(0).sum()),
        'histogram_counts':histograms,'reference_checks':checks,'notebook_coverage':coverage}, report)


if __name__ == '__main__':
    main()
