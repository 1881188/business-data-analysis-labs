"""S08: compare the textbook zero-fill branch with observed-expense ANOVA."""
import re
import numpy as np
import pandas as pd
from scipy import stats
from scipy.linalg import null_space
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm
from .common import context, finish, plotting, save_table
from .notebook_reference import read_notebook, cached_text, write_coverage
from .statistical_reference import check_printed


def prepare_expenses(raw,blank_policy='exclude'):
    if blank_policy not in ('exclude','textbook_zero'):
        raise ValueError('Unknown blank-expense policy')
    frame = raw[['avg_exp','edu_class','gender']].copy(deep=True)
    text = frame.avg_exp.astype('string').str.strip()
    blank = text.eq('').fillna(False)
    text = text.mask(blank,'0' if blank_policy == 'textbook_zero' else pd.NA)
    frame['avg_exp'] = pd.to_numeric(text,errors='raise').astype(float)
    frame = frame.dropna(subset=['avg_exp','edu_class','gender']).copy()
    if frame.empty or not np.isfinite(frame.avg_exp).all() or frame.avg_exp.lt(0).any():
        raise ValueError('Observed expense must be nonnegative and finite')
    for name in ['edu_class','gender']:frame[name] = frame[name].astype(str)
    return frame, {'source_rows':len(raw),'blank_expenses':int(blank.sum()),'retained_rows':len(frame),
                   'excluded_rows':len(raw)-len(frame),'blank_policy':blank_policy}


def fit_estimable(formula,frame):
    model = ols(formula,data=frame)
    rank = np.linalg.matrix_rank(model.exog)
    if rank != model.exog.shape[1] or len(model.endog) <= rank:
        raise ValueError('Model coefficients require full rank and positive residual degrees of freedom')
    return model.fit()


def fit_observed_models(frame):
    if frame.edu_class.nunique() < 2 or frame.gender.nunique() < 2:
        raise ValueError('Both factors must have at least two observed levels')
    one = fit_estimable('avg_exp ~ C(edu_class)',frame)
    additive = fit_estimable('avg_exp ~ C(edu_class) + C(gender)',frame)
    cell_codes = pd.MultiIndex.from_frame(frame[['edu_class','gender']]).factorize(sort=True)[0].astype(str)
    cells = fit_estimable('avg_exp ~ C(cell)',frame.assign(cell=cell_codes))
    # Diagnose the unobserved combination before fitting/interpreting a full interaction parameterization.
    interaction_design = ols('avg_exp ~ C(edu_class)*C(gender)',data=frame).exog
    rank = int(np.linalg.matrix_rank(interaction_design))
    projection = cells.model.exog@np.linalg.lstsq(cells.model.exog,additive.model.exog,rcond=None)[0]
    if not np.allclose(projection,additive.model.exog,atol=1e-12,rtol=0):
        raise AssertionError('Additive and observed-cell models are not nested')
    comparison = anova_lm(additive,cells)
    independent = stats.f_oneway(*(g.avg_exp.to_numpy() for _,g in frame.groupby('edu_class')))
    if not np.isclose(one.fvalue,independent.statistic,rtol=1e-11,atol=1e-11):
        raise AssertionError('One-way ANOVA differs from independent scipy calculation')
    return {'one_way':one,'additive':additive,'observed_cells':cells},comparison,{
        'full_interaction_columns':int(interaction_design.shape[1]),'full_interaction_rank':rank,
        'unestimable_dimensions':int(interaction_design.shape[1]-rank)}


def legacy_reference_check(model,text):
    metrics = [('nobs',model.nobs,r'No\. Observations:\s*(\d+)'),
               ('df_model',model.df_model,r'Df Model:\s*(\d+)'),
               ('df_resid',model.df_resid,r'Df Residuals:\s*(\d+)'),
               ('r_squared',model.rsquared,r'R-squared:\s*([\d.eE+-]+)'),
               ('f_statistic',model.fvalue,r'F-statistic:\s*([\d.eE+-]+)'),
               ('f_pvalue',model.f_pvalue,r'Prob \(F-statistic\):\s*([\d.eE+-]+)')]
    checks = {}
    for key,value,pattern in metrics:
        token = re.search(pattern,text).group(1)
        if key in ('nobs','df_model','df_resid') and value != int(token):
            raise AssertionError('Cached OLS observation/degree count differs')
        checks[key] = check_printed(value,token)
    coefficients = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 7 and parts[0] in model.params.index:
            coefficients[parts[0]] = check_printed(model.params[parts[0]],parts[1])
    if set(coefficients) != set(model.params.index):
        raise ValueError('Expected every cached coefficient in the OLS summary')
    return {'metrics':checks,'coefficients':coefficients,'values_compared':len(checks)+len(coefficients)}


def robust_observed_interaction(additive,cells):
    mapping = np.linalg.lstsq(cells.model.exog,additive.model.exog,rcond=None)[0]
    constraints = null_space(mapping.T).T
    if len(constraints) == 0:
        raise ValueError('There are no observable interaction contrasts')
    result = cells.get_robustcov_results(cov_type='HC3').f_test(constraints)
    return {'df_numerator':int(result.df_num),'df_denominator':int(result.df_denom),
            'f_statistic':float(np.asarray(result.fvalue).squeeze()),'pvalue':float(result.pvalue)}


def model_record(name,model):
    return {'model':name,'nobs':int(model.nobs),'rank':int(np.linalg.matrix_rank(model.model.exog)),
            'design_columns':int(model.model.exog.shape[1]),'df_model':int(model.df_model),
            'df_resid':int(model.df_resid),'r_squared':float(model.rsquared),
            'f_statistic':float(model.fvalue),'f_pvalue':float(model.f_pvalue),'residual_sum_squares':float(model.ssr)}


def main(argv=None):
    ctx = context('S08',argv)
    nb = read_notebook(ctx.source('notebook_anova'))
    raw = pd.read_csv(ctx.source('anova_creditcard'))
    if raw.id.isna().any() or raw.id.duplicated().any():
        raise ValueError('Expected distinct customer rows')
    primary,audit = prepare_expenses(raw)
    legacy,legacy_audit = prepare_expenses(raw,'textbook_zero')
    models,comparison,rank_audit = fit_observed_models(primary)
    robust_interaction = robust_observed_interaction(models['additive'],models['observed_cells'])
    interaction = comparison.iloc[1]
    interaction_info = {'df_difference':int(interaction.df_diff),'f_statistic':float(interaction.F),
                        'pvalue':float(interaction['Pr(>F)'])}
    if not np.isfinite(list(interaction_info.values())).all():
        raise AssertionError('Observed-cell interaction test is not defined')
    legacy_models = {'TEXTBOOK_ZERO_additive':fit_estimable('avg_exp ~ C(edu_class)+C(gender)',legacy),
                     'TEXTBOOK_ZERO_interaction':fit_estimable('avg_exp ~ C(edu_class)*C(gender)',legacy)}
    reference = {name:legacy_reference_check(model,cached_text(nb,cell))
                 for (name,model),cell in zip(legacy_models.items(),[5,8])}
    one_table = anova_lm(models['one_way'],typ=2)
    additive_table = anova_lm(models['additive'],typ=2)
    robust_table = anova_lm(models['additive'],typ=2,robust='hc3')
    anova_tables = []
    for name,table in [('one_way_type_II',one_table),('additive_type_II',additive_table),('additive_type_II_HC3',robust_table)]:
        item = table.rename_axis('term').reset_index()
        if name.endswith('HC3'):item = item.drop(columns='sum_sq')
        item.insert(0,'analysis',name)
        anova_tables.append(item)
    save_table(pd.concat(anova_tables,ignore_index=True),ctx.output/'anova_tables.csv')
    save_table(pd.DataFrame([
        {'analysis':'classical_nested_F','df_numerator':interaction_info['df_difference'],
         'df_denominator':int(models['observed_cells'].df_resid),'F':interaction_info['f_statistic'],'pvalue':interaction_info['pvalue']},
        {'analysis':'HC3_Wald_F','df_numerator':robust_interaction['df_numerator'],
         'df_denominator':robust_interaction['df_denominator'],'F':robust_interaction['f_statistic'],'pvalue':robust_interaction['pvalue']}]),ctx.output/'observed_cell_interaction_test.csv')
    all_models = {**models,**legacy_models}
    records = [model_record(name,model) for name,model in all_models.items()]
    save_table(pd.DataFrame(records),ctx.output/'model_comparison.csv')
    coefficient_rows = []
    for name,model in all_models.items():
        for term,value in model.params.items():
            coefficient_rows.append({'model':name,'term':term,'coefficient':value,'standard_error':model.bse[term],
                                     't_statistic':model.tvalues[term],'pvalue':model.pvalues[term]})
    save_table(pd.DataFrame(coefficient_rows),ctx.output/'model_coefficients.csv')
    combinations = pd.MultiIndex.from_product([sorted(legacy.edu_class.unique()),sorted(legacy.gender.unique())],names=['edu_class','gender'])
    groups = []
    for name,frame in [('observed_primary',primary),('TEXTBOOK_ZERO_compatibility',legacy)]:
        table = frame.groupby(['edu_class','gender']).avg_exp.agg(['count','mean','std']).reindex(combinations)
        table['count'] = table['count'].fillna(0).astype(int)
        table = table.reset_index()
        table.insert(0,'sample_policy',name)
        groups.append(table)
    group_table = pd.concat(groups,ignore_index=True)
    save_table(group_table,ctx.output/'group_statistics.csv')
    blank = raw.avg_exp.astype('string').str.strip().eq('').fillna(False)
    blank_cross = pd.crosstab(raw.Acc,blank).reindex(columns=[False,True],fill_value=0)
    blank_cross.columns=['observed_expense','blank_expense']
    save_table(blank_cross.rename_axis('Acc_code').reset_index(),ctx.output/'blank_expense_by_Acc.csv')
    lev = stats.levene(*(g.avg_exp.to_numpy() for _,g in primary.groupby(['edu_class','gender'])),center='median')
    coverage = write_coverage(nb,[([2],'OLS/方差分析导入','statsmodels公式接口和anova_lm，新增真正单因素模型'),
        ([3,4],'样本和空白处理','主流程将空白当缺失；单独兼容分支保留教材空白填0以核对'),
        ([5],'原所谓单因素模型','原式其实是教育+性别加性模型，兼容结果核对，主分析输出Type II及HC3'),
        ([7,8],'多因素和交互','简化重复公式，诊断缺失单元格导致的不可估计系数；用观察单元均值模型做可识别的嵌套检验')],ctx.output/'notebook-map.md')
    plt = plotting()
    fig,axes = plt.subplots(1,2,figsize=(12,5),sharey=True,layout='constrained')
    for ax,table,title in zip(axes,[groups[1],groups[0]],['教材兼容：空白填0（100条）','主分析：只保留已观察消费额（70条）']):
        for gender,color in [('0','#087f8c'),('1','#d67b28')]:
            subset = table[table.gender==gender].set_index('edu_class').reindex(sorted(legacy.edu_class.unique()))
            x = np.arange(len(subset))
            ax.plot(x,subset['mean'],'o-',color=color,label=f'gender={gender}')
            for i,row in enumerate(subset.itertuples()):
                other = table[(table.edu_class==row.Index)&(table.gender!=gender)]['mean'].iloc[0]
                above = pd.isna(other) or row.mean >= other
                offset = (36,7) if row.mean==0 else (4,8 if above else -18)
                if row.count:ax.annotate(f'n={row.count}',(i,row.mean),xytext=offset,textcoords='offset points',fontsize=9)
            ax.set(xticks=x,xticklabels=subset.index)
        ax.set(title=title,xlabel='edu_class代码',ylabel='avg_exp组均值（原字段单位）')
        ax.legend(frameon=False)
    fig.savefig(ctx.output/'expense_anova.png',dpi=150)
    plt.close(fig)
    edu_p = float(additive_table.loc['C(edu_class)','PR(>F)'])
    gender_p = float(additive_table.loc['C(gender)','PR(>F)'])
    report = f"""# S08 消费额方差分析与样本口径

## 原始问题与主分析

100条客户记录中，30条avg_exp为空白字符串；这30条全部属于Acc=0。空白表示没有可用消费额，不能凭代码自动视作真实0。主分析保留{len(primary)}条已观察消费额，未观察记录不补0；兼容分支按教材填0，仅用于重现原结果。

![两种样本口径下的组均值](expense_anova.png)

教材标题“单因素”下的公式实际同时包含教育和性别。本实现新增真正的教育单因素模型，再给出教育+性别加性模型。主分析加性模型Type II教育项p={edu_p:.6g}、性别项p={gender_p:.6g}，另提供HC3异方差稳健检验。它们反映观察样本中的条件关联，不代表教育或性别的因果效应。

## 空单元格与可识别交互

主样本中edu_class=0、gender=1组合没有记录。标准完整交互设计有{rank_audit['full_interaction_columns']}列、秩{rank_audit['full_interaction_rank']}，存在{rank_audit['unestimable_dimensions']}个不可识别维度，不能照搬100条兼容样本的8个系数或3自由度交互解释。

因此用实际观察到的7个教育×性别单元拟合满秩单元均值模型，与加性模型做嵌套比较：可检验增量自由度{interaction_info['df_difference']}，F={interaction_info['f_statistic']:.6f}、p={interaction_info['pvalue']:.6f}。这是观察单元上的加性拟合不足检验，不能补出缺失组合的均值。单因素F与scipy.f_oneway独立核对。

## 假设与核对

最小观察单元仅2条记录。基于单元的中位数Levene检验p={lev.pvalue:.6g}，在α=0.05下提示方差不齐。对同一组可识别交互对比另计算HC3稳健Wald F={robust_interaction['f_statistic']:.6f}、p={robust_interaction['pvalue']:.6f}（分子/分母自由度{robust_interaction['df_numerator']}/{robust_interaction['df_denominator']}）。经典交互F依赖等方差假设，不能单凭其接近0.05的p值宣称存在稳定交互；稳健检验在小组样本下也需谨慎解释。

经典Type II表、HC3表及观察单元交互检验分开输出，所检验的假设不同。HC3行只输出df/F/p，平方和留空，避免将稳健检验派生的数值误当作可加的总变异分解。模型残差平方和单独记录于model_comparison.csv。没有把同一数据上的多个p值当作多份独立证据。

兼容分支的两个OLS模型共25项原缓存值核对：13个系数，以及每个模型的样本数、模型/残差自由度、R²、总体F与总体p。只按原打印精度对账。主流程改变了响应缺失处理，因此实验状态记为运行通过，不宣称修正后的70条分析有同一参考答案。教材重复的A+B+A*B公式简化成A*B，设计矩阵含义不变。

原表没有完整单位、采样与Acc定义字典。本报告保留代码含义，不能将70条选择后的消费样本推广到所有申请客户。原记录不改写，公开文件为模型/分组汇总。[statsmodels官方文档](https://www.statsmodels.org/stable/generated/statsmodels.stats.anova.anova_lm.html)说明Type II和HC3的检验口径。全部6个非空代码单元见[迁移对照](notebook-map.md)。
"""
    finish(ctx,{'lab_id':'S08','status':'execution_verified','source_rows':len(raw),'primary_sample_audit':audit,
        'textbook_compatibility_audit':legacy_audit,'model_metrics':records,'interaction_rank_audit':rank_audit,
        'observed_cell_interaction_test':interaction_info,'observed_cell_interaction_HC3':robust_interaction,'levene_median_pvalue':float(lev.pvalue),
        'reference_checks_compatibility_only':reference,'notebook_coverage':coverage},report)


if __name__ == '__main__':main()
