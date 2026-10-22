"""S09: separate presentation margins from valid contingency-test observations."""
import re
import numpy as np
import pandas as pd
from scipy import stats
from .common import context, finish, plotting, save_table
from .notebook_reference import read_notebook, cached_text, write_coverage
from .statistical_reference import check_array, numpy_tokens, check_printed


def analyze_table(observed):
    if isinstance(observed,pd.DataFrame) and ('All' in observed.index or 'All' in observed.columns):
        raise ValueError('Presentation margins must not be passed to an independence test')
    values = np.asarray(observed,dtype=float)
    if values.ndim != 2 or min(values.shape) < 2 or not np.isfinite(values).all():
        raise ValueError('A finite two-way contingency table with at least two categories per axis is required')
    if (values < 0).any() or (values % 1 != 0).any() or (values.sum(axis=0) == 0).any() or (values.sum(axis=1) == 0).any():
        raise ValueError('Use nonnegative integer frequencies with nonempty row and column margins')
    pearson = stats.chi2_contingency(values,correction=False)
    n = int(values.sum())
    results = {'n':n,'pearson_chi2':float(pearson.statistic),'pearson_p':float(pearson.pvalue),
               'dof':int(pearson.dof),'minimum_expected':float(pearson.expected_freq.min()),
               'cramers_v':float(np.sqrt(pearson.statistic/(n*min(np.array(values.shape)-1))))}
    if values.shape == (2,2):
        yates = stats.chi2_contingency(values,correction=True)
        fisher = stats.fisher_exact(values.astype('int64'),alternative='two-sided')
        results.update(yates_chi2=float(yates.statistic),yates_p=float(yates.pvalue),
                       fisher_odds_ratio=float(fisher.statistic),fisher_two_sided_p=float(fisher.pvalue))
    return results,pearson.expected_freq


def categorical_reference(text,labels):
    rows = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] in labels and all(re.fullmatch(r'\d+(?:\.\d+)?',v) for v in parts[1:]):
            rows[parts[0]] = parts[1:]
    if set(rows) != set(labels):
        raise ValueError('Expected complete cached contingency table')
    return [v for label in labels for v in rows[label]]


def main(argv=None):
    ctx = context('S09',argv)
    nb = read_notebook(ctx.source('notebook_contingency'))
    raw = pd.read_csv(ctx.source('contingency_accepts'))
    if raw.application_id.isna().any() or raw.application_id.duplicated().any():
        raise ValueError('Expected one distinct application per row')
    valid = raw[['bankruptcy_ind','bad_ind']].dropna().copy()
    if set(valid.bankruptcy_ind) != {'N','Y'} or set(valid.bad_ind) != {0,1}:
        raise ValueError('Unexpected bankruptcy/bad categories')
    observed = pd.crosstab(valid.bankruptcy_ind,valid.bad_ind).reindex(index=['N','Y'],columns=[0,1])
    results,expected = analyze_table(observed)
    margins = pd.crosstab(valid.bankruptcy_ind,valid.bad_ind,margins=True).reindex(index=['N','Y','All'],columns=[0,1,'All'])
    percentages = margins.div(margins['All'],axis=0)
    # Deliberately retain the wrong original calculation only as a labelled diagnostic.
    legacy = stats.chi2_contingency(margins)
    source_test = cached_text(nb,3)
    checks = {'nine_display_counts':check_array(margins,categorical_reference(cached_text(nb,1),['N','Y','All'])),
              'nine_display_proportions':check_array(percentages,categorical_reference(cached_text(nb,2),['N','Y','All'])),
              'legacy_expected_including_margins':check_array(legacy.expected_freq,numpy_tokens(source_test.split('expected_freq =',1)[1])),
              'legacy_statistics':{key:check_printed(value,re.search(pattern,source_test).group(1))
                  for key,value,pattern in [('chi2',legacy.statistic,r'chisq\s*=\s*([\d.]+)'),
                      ('pvalue',legacy.pvalue,r'p-value\s*=\s*([\d.]+)'),('dof',legacy.dof,r'dof\s*=\s*(\d+)')]}}
    excluded = len(raw)-len(valid)
    rates = pd.DataFrame({'bankruptcy_ind':observed.index,'records':observed.sum(axis=1).to_numpy(),
                         'bad_records':observed[1].to_numpy(),'bad_fraction':observed[1].div(observed.sum(axis=1)).to_numpy()})
    save_table(margins.rename_axis('bankruptcy_ind').reset_index(),ctx.output/'display_counts.csv')
    save_table(percentages.rename_axis('bankruptcy_ind').reset_index(),ctx.output/'display_row_proportions.csv')
    save_table(pd.DataFrame(expected,index=observed.index,columns=['expected_good','expected_bad']).rename_axis('bankruptcy_ind').reset_index(),ctx.output/'expected_counts_without_margins.csv')
    save_table(rates,ctx.output/'sample_bad_fractions.csv')
    tests = pd.DataFrame([
        {'analysis':'Pearson_without_margins','statistic_kind':'chi_squared','statistic':results['pearson_chi2'],'dof':results['dof'],'pvalue':results['pearson_p']},
        {'analysis':'Yates_without_margins','statistic_kind':'chi_squared','statistic':results['yates_chi2'],'dof':results['dof'],'pvalue':results['yates_p']},
        {'analysis':'Fisher_two_sided','statistic_kind':'odds_ratio','statistic':results['fisher_odds_ratio'],'dof':pd.NA,'pvalue':results['fisher_two_sided_p']},
        {'analysis':'INVALID_legacy_with_margins','statistic_kind':'chi_squared','statistic':legacy.statistic,'dof':legacy.dof,'pvalue':legacy.pvalue}])
    save_table(tests,ctx.output/'test_comparison.csv')
    coverage = write_coverage(nb,[([1],'列联频数和合计','展示表保留All，检验仅用无合计的2×2表，单独报告217条缺失'),
        ([2],'行比例','分母是各破产标志组人数；样本坏账比例不当作总体坏账率'),
        ([3],'卡方独立性检验','保留错误旧结果用于诊断；主分析排除合计，明确Pearson/Yates/Fisher差别')],ctx.output/'notebook-map.md')
    plt = plotting()
    fig,axes = plt.subplots(1,2,figsize=(11,5),layout='constrained')
    bad = rates.bad_fraction.to_numpy()*100
    axes[0].bar(['N','Y'],100-bad,color='#bdcbd4',label='bad_ind=0')
    axes[0].bar(['N','Y'],bad,bottom=100-bad,color='#d67b28',label='bad_ind=1')
    for i,r in enumerate(rates.itertuples()):axes[0].text(i,50,f'n={r.records:,}\n样本坏账 {r.bad_fraction:.2%}',ha='center',va='center')
    axes[0].set(title='未加权完整样本的组内比例',xlabel='bankruptcy_ind',ylabel='组内比例（%）',ylim=(0,106))
    axes[0].legend(frameon=False,loc='lower left')
    residuals = (observed.to_numpy()-expected)/np.sqrt(expected)
    limit = max(1.,float(abs(residuals).max()))
    im = axes[1].imshow(residuals,cmap='RdBu_r',vmin=-limit,vmax=limit)
    axes[1].set(title=f"Pearson残差（不含合计，df={results['dof']}）",xticks=[0,1],xticklabels=['bad=0','bad=1'],yticks=[0,1],yticklabels=['N','Y'],ylabel='bankruptcy_ind')
    for i in range(2):
        for j in range(2):axes[1].text(j,i,f'{residuals[i,j]:.3f}',ha='center',va='center',color='white' if abs(residuals[i,j])>.7*limit else '#172c37')
    fig.colorbar(im,ax=axes[1],label='(观察−期望)/√期望')
    fig.savefig(ctx.output/'contingency_diagnostics.png',dpi=150)
    plt.close(fig)
    report = f"""# S09 列联表与独立性检验

## 样本与正确检验

原表{len(raw):,}条不同申请，bankruptcy_ind缺失{excluded}条。主分析采用{len(valid):,}条完整记录，没有把缺失值填成N。N组样本坏账比例{rates.iloc[0].bad_fraction:.4%}，Y组{rates.iloc[1].bad_fraction:.4%}；这不是因果差异。

去除All合计行列后：未作连续性校正的Pearson χ²={results['pearson_chi2']:.6f}，df={results['dof']}，p={results['pearson_p']:.6f}；Yates校正p={results['yates_p']:.6f}；双侧Fisher p={results['fisher_two_sided_p']:.6f}。Cramér's V={results['cramers_v']:.6f}，最小期望频数{results['minimum_expected']:.3f}。

![样本比例和Pearson残差](contingency_diagnostics.png)

## 原代码问题与核对

教材把含All合计的3×3展示表传给chi2_contingency，产生df={legacy.dof}、p={legacy.pvalue:.6f}。合计不是独立观测类别，这个自由度和p值不适用。在本表中错误流程的未校正χ²恰与正确2×2 Pearson相同，但自由度改变，所以p值不同；不能因统计量相同就认为实现正确。

只在独立诊断分支重建错误旧流程：9个展示频数、9个行比例、9个旧期望频数和χ²/p/df共30项按缓存显示精度核对。主流程已经修正，状态记为运行通过，未把旧p值当正确答案。test_comparison.csv用INVALID前缀明确标记旧行。

## 解释边界

若事先用α=0.05，三种正确检验均未拒绝独立性假设，不能据此断言两者完全无关系或两组风险等同。各检验回答的是样本分类关联，单变量结果也不是可部署的风控模型。

weight字段含1和4.75，教材未给出抽样权重定义。本实验遵循原例使用未加权样本计数，不把加权伪频数送入普通Pearson检验，不把样本坏账比例推广为总体概率。缺失记录的排除也可能影响代表性。公式、自由度及Yates行为参见[SciPy官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2_contingency.html)。全部3个非空代码单元见[迁移对照](notebook-map.md)。
"""
    finish(ctx,{'lab_id':'S09','status':'execution_verified','source_rows':len(raw),'complete_rows':len(valid),
        'excluded_missing_bankruptcy':excluded,'primary_unweighted':results,
        'invalid_legacy_diagnostic':{'chi2':float(legacy.statistic),'pvalue':float(legacy.pvalue),'dof':int(legacy.dof)},
        'reference_checks_diagnostic_only':checks,'notebook_coverage':coverage},report)


if __name__ == '__main__':main()
