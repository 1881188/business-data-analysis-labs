"""Excel correlation and linear trend migrated to explicit numerical calculations."""
import re
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
from scipy import stats

from .common import context, finish, plotting, save_table, compare_numeric
from .notebook_reference import compare_displayed


def calculate(raw):
    frame = raw[['x', 'y']].apply(pd.to_numeric, errors='raise').copy()
    if len(frame) < 3 or not np.isfinite(frame.to_numpy()).all():
        raise ValueError('At least three complete finite x/y pairs are required')
    if (frame.nunique() < 2).any():
        raise ValueError('Correlation requires variation in both variables')
    fit = stats.linregress(frame.x, frame.y)
    return frame, {'n': len(frame), 'pearson': float(fit.rvalue),
                   'spearman': float(stats.spearmanr(frame.x, frame.y).statistic),
                   'kendall': float(stats.kendalltau(frame.x, frame.y).statistic),
                   'slope': float(fit.slope), 'intercept': float(fit.intercept),
                   'r_squared': float(fit.rvalue ** 2)}


def main(argv=None):
    ctx = context('B09', argv)
    raw = pd.read_excel(ctx.source('correlation_raw'), sheet_name='原始数据')
    frame, result = calculate(raw)
    reference = ctx.source('correlation_reference')
    expected = pd.read_excel(reference, sheet_name='原始数据')
    input_check = compare_numeric(frame, expected[['x', 'y']], 'Reference x/y input')
    with zipfile.ZipFile(reference) as archive:
        chart = ET.fromstring(archive.read('xl/charts/chart1.xml'))
        labels = ' '.join(e.text for e in chart.iter() if e.tag.endswith('}t') and e.text)
    match = re.search(r'y\s*=\s*(\d+(?:\.\d+)?)x\s*\+\s*(\d+(?:\.\d+)?).*R²\s*=\s*(\d+(?:\.\d+)?)', labels)
    if match is None:
        raise ValueError('Expected rounded trend label is missing from the reference chart')
    checks = {key: compare_displayed(result[key], value)
              for key, value in zip(['slope', 'intercept', 'r_squared'], match.groups())}
    fitted = result['intercept'] + result['slope'] * frame.x
    save_table(pd.DataFrame([result]), ctx.output / 'metrics.csv')
    save_table(frame.assign(fitted=fitted, residual=frame.y - fitted), ctx.output / 'fitted_rows.csv')
    plt = plotting()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    axes[0].scatter(frame.x, frame.y, color='#087f8c', alpha=.8)
    order = np.argsort(frame.x.to_numpy())
    axes[0].plot(frame.x.iloc[order], fitted.iloc[order], color='#d67b28',
                 label=f"y = {result['slope']:.4f}x + {result['intercept']:.3f}\nR² = {result['r_squared']:.4f}")
    axes[0].set(title='相关关系与样本内线性拟合', xlabel='x（教材未注明单位）', ylabel='y（教材未注明单位）')
    axes[0].legend(frameon=False)
    axes[1].scatter(frame.x, frame.y - fitted, color='#087f8c', alpha=.8)
    axes[1].axhline(0, color='#96a6af', linestyle='--')
    axes[1].set(title='残差检查', xlabel='x', ylabel='实际 y − 拟合 y')
    fig.savefig(ctx.output / 'correlation_fit.png', dpi=150)
    plt.close(fig)
    report = f"""# B09 相关分析与线性趋势

## 结果

教材给出{len(frame)}对x/y观测，没有行业、采样时间或单位字典。Pearson相关系数为{result['pearson']:.6f}，Spearman为{result['spearman']:.6f}，Kendall为{result['kendall']:.6f}。

线性拟合为 **y = {result['slope']:.6f}x + {result['intercept']:.6f}**，样本内R²为{result['r_squared']:.6f}。这说明本样本中存在较强正相关，不能解释为x变化导致y变化，也不能把样本内R²当作预测集表现。

![相关关系和残差](correlation_fit.png)

## 从Excel迁移

Excel散点图的线性趋势对应scipy.stats.linregress。相关系数描述共同变化，斜率描述x每增加一单位时拟合y的变化，截距是x=0的拟合值。只有在适用范围内解释截距才有意义。另计算两种秩相关以说明线性关联与单调关联的区别。

原始与参考表的全部{frame.size}个输入数值一致。参考图仅显示四舍五入后的斜率、截距与R²，因此只按各自显示精度核对这3项，不能宣称有完整精度的参考系数。Pearson和两种秩相关没有单独参考答案。metrics.csv保留本实现完整精度，行级拟合值仅留本地。

缺失、非有限值和常量变量会明确报错，避免自动删行改变样本范围。这里没有划分训练测试集，也没有进行因果识别或样本外预测。
"""
    finish(ctx, {'lab_id': 'B09', 'status': 'reference_verified', 'metrics': result,
                 'reference_checks': {'input_values': input_check, 'rounded_chart_metrics': checks}}, report)


if __name__ == '__main__':
    main()
