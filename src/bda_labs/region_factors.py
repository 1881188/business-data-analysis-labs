"""S07: reproduce principal-component extraction and varimax directions, not ML factor analysis."""
import numpy as np
import pandas as pd
from .common import context, finish, plotting, save_table
from .notebook_reference import read_notebook, cached_text, write_coverage
from .statistical_reference import numpy_tokens, indexed_table_tokens, check_array
from .dimension_reduction import standardized_pca, principal_rotation

FEATURES = [f'X{i}' for i in range(1,10)]
NAMES = ['GDP','人均GDP','工业增加值','第三产业增加值','固定资产投资','基本建设投资','社会消费品零售总额','海关出口总额','地方财政收入']


def main(argv=None):
    ctx = context('S07',argv)
    nb = read_notebook(ctx.source('notebook_factors'))
    raw = pd.read_csv(ctx.source('factor_regions'),encoding='gbk')
    if raw.AREA.isna().any() or raw.AREA.duplicated().any():
        raise ValueError('Expected distinct named regions')
    z,scaler,model,weights,scores,rotation,gradient = principal_rotation(raw[FEATURES])
    _,_,full,_ = standardized_pca(raw[FEATURES],9)
    checks = {'standardized_matrix':check_array(z,numpy_tokens(cached_text(nb,9))),
        'full_eigenvalues_and_ratios':check_array(np.r_[full.explained_variance_,full.explained_variance_ratio_],numpy_tokens(cached_text(nb,14))),
        'two_retained_eigenvalues':check_array(model.explained_variance_,numpy_tokens(cached_text(nb,17))),
        'rotated_unit_directions':check_array(weights,indexed_table_tokens(cached_text(nb,27),9,2)),
        'twenty_region_scores':check_array(scores,indexed_table_tokens(cached_text(nb,34),10,2))}
    variance = pd.DataFrame({'component':range(1,10),'sample_eigenvalue':full.explained_variance_,
        'explained_ratio':full.explained_variance_ratio_,'cumulative_ratio':np.cumsum(full.explained_variance_ratio_)})
    coefficients = pd.DataFrame(weights,columns=['Gross_direction','Avg_direction'])
    coefficients.insert(0,'variable',NAMES)
    coefficients.insert(0,'feature',FEATURES)
    region_scores = pd.DataFrame({'region':raw.AREA,'Gross':scores[:,0],'Avg':scores[:,1]})
    correlations = pd.DataFrame(np.corrcoef(z.T,scores.T)[:9,9:],columns=['Gross_correlation','Avg_correlation'])
    correlations.insert(0,'feature',FEATURES)
    save_table(variance,ctx.output/'regional_explained_variance.csv')
    save_table(coefficients,ctx.output/'rotated_directions.csv')
    save_table(region_scores,ctx.output/'region_scores.csv')
    save_table(correlations,ctx.output/'feature_score_correlations.csv')
    save_table(pd.DataFrame(rotation,columns=['Gross','Avg']).rename_axis('original_component').reset_index(),ctx.output/'rotation_matrix.csv')
    coverage = write_coverage(nb,[([4,5,6],'数据读取与变量字典','GBK读取，显式选择X1-X9，保留地区名称'),
        ([8,9],'中心标准化','StandardScaler；90个标准化值按源缓存显示精度核对'),
        ([11,13,14,16,17],'PCA与成分个数','完整SVD核对9个特征值、9个比例和保留2个特征值'),
        ([22,23,25,27],'主成分提取与varimax旋转','用现有statsmodels旋转单位特征向量，保留fa_kit原方法语义'),
        ([29,30,31,32,33,34],'得分矩阵计算','Z乘旋转方向矩阵，18个权重与20个得分核对；重复显示不重复计数'),
        ([35,36],'命名和地区关联','按同一行序将Gross/Avg与AREA关联，不把变量名当作客观排名'),
        ([37,38],'中文图形','明确区域层级和原数据单位/年度缺失，保存无界面PNG')],ctx.output/'notebook-map.md')
    plt = plotting()
    fig,axes = plt.subplots(1,2,figsize=(13,5.5),layout='constrained')
    axes[0].bar(variance.component,variance.explained_ratio*100,color=['#087f8c','#d67b28']+['#bdcbd4']*7)
    axes[0].plot(variance.component,variance.cumulative_ratio*100,'o-',color='#5b5fa6',label='累计解释比例')
    axes[0].set(title='地区经济指标的主成分解释比例',xlabel='主成分序号',ylabel='标准化总变异（%）',xticks=range(1,10),ylim=(0,105))
    axes[0].legend(frameon=False)
    axes[1].scatter(scores[:,0],scores[:,1],s=55,color='#087f8c')
    axes[1].axhline(0,color='#bdcbd4',linestyle='--')
    axes[1].axvline(0,color='#bdcbd4',linestyle='--')
    for r in region_scores.itertuples():axes[1].annotate(r.region,(r.Gross,r.Avg),xytext=(5,6),textcoords='offset points',fontsize=10)
    axes[1].margins(.16)
    axes[1].set(title='10个地区的旋转主成分得分',xlabel='Gross（规模方向）',ylabel='Avg（人均GDP方向）')
    fig.savefig(ctx.output/'regional_factors.png',dpi=150)
    plt.close(fig)
    retained = float(model.explained_variance_ratio_.sum())
    score_covariance = np.cov(scores,rowvar=False)
    score_correlation = float(np.corrcoef(scores,rowvar=False)[0,1])
    report = f"""# S07 地区经济数据的主成分旋转

## 结果

10个地区、9个指标。前两个主成分累计保留{retained:.4%}的标准化总变异，样本特征值为{model.explained_variance_[0]:.6f}和{model.explained_variance_[1]:.6f}。按教材选取两维，再做varimax正交旋转。

![解释比例与地区得分](regional_factors.png)

旋转方向Gross的8个规模相关变量权重大多为正，Avg的X2（人均GDP）权重最大。名称是对本样本方向的解释，不是已经验证的潜在因果因子，也没有把不同方向合成为客观综合排名。来源含省、直辖市等地区，不能统称10座城市；原材料没有明确年度和单位，不能写成当前经济表现。

## 原方法与Python实现

源Notebook虽称“因子分析”，实际调用fa_kit默认的协方差特征分解、保留两列**单位范数特征向量**并旋转，再以Z×方向矩阵作为得分。本实现用完整SVD和现有statsmodels.rotate_factors重建这一流程，没有改换为最大似然共同因子模型，也没有将特征向量乘以特征值平方根后再旋转。

方向系数与“变量和得分的相关系数”不同，分别保存在rotated_directions.csv与feature_score_correlations.csv。旋转矩阵正交、保留子空间投影相同、总保留方差不变和varimax梯度收敛均独立检查。**方向正交不等于得分不相关**：旋转后两列得分相关为{score_correlation:.6f}，因为原两主成分的方差不相等。没有白化这两列得分。

PCA以ddof=0标准化、n−1协方差计算，本例9个样本特征值之和为10而非9。教材的“累计解释超过85%、最后保留特征值高于0.8”在本例支持两维，但不应机械推广为通用选维规则。10个样本相对9个变量很少，本结果仅是教学描述。

## 核对范围和来源

148项缓存值按显示精度核对：90个标准化值、9个特征值、9个解释比例、再次显示的2个保留特征值、18个旋转方向和全部20个地区得分。原Notebook另有重复显示，这里没有重复计数。每项差值和容差记录在summary.json，全部24个非空代码单元见[迁移对照](notebook-map.md)。

方法语义核对依据[fa_kit提取源码](https://github.com/bmcmenamin/fa_kit/blob/master/fa_kit/extraction.py)、[旋转源码](https://github.com/bmcmenamin/fa_kit/blob/master/fa_kit/rotation.py)和[数据预处理源码](https://github.com/bmcmenamin/fa_kit/blob/master/fa_kit/factor_analysis.py)。实际旋转调用[statsmodels官方接口](https://www.statsmodels.org/stable/generated/statsmodels.multivariate.factor_rotation.rotate_factors.html)，不捆绑或执行fa_kit源文件。
"""
    finish(ctx,{'lab_id':'S07','status':'reference_verified','source_rows':len(raw),'features':FEATURES,
        'extraction':'principal_component_eigenvectors_then_varimax','retained_variance_ratio':retained,
        'rotation_gradient_norm':gradient,'score_sample_covariance':score_covariance.tolist(),
        'score_correlation':score_correlation,'reference_checks':checks,'notebook_coverage':coverage},report)


if __name__ == '__main__':main()
