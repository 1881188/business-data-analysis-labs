"""S06: explain standardized, whitened PCA of four telecom usage variables."""
import re
import numpy as np
import pandas as pd
from .common import context, finish, plotting, save_table
from .notebook_reference import read_notebook, cached_text, write_coverage
from .statistical_reference import numpy_tokens, check_array
from .dimension_reduction import standardized_pca

FEATURES = ['cnt_call','cnt_msg','cnt_wei','cnt_web']


def main(argv=None):
    ctx = context('S06',argv)
    nb = read_notebook(ctx.source('notebook_pca'))
    raw = pd.read_csv(ctx.source('pca_telecom'))
    if raw.ID.isna().any() or raw.ID.duplicated().any():
        raise ValueError('Each telecom row must identify one distinct customer')
    data = raw[FEATURES]
    if data.lt(0).any().any():
        raise ValueError('Usage counts must be nonnegative')
    z,scaler,model,scores = standardized_pca(data,2,whiten=True)
    _,_,full,_ = standardized_pca(data,4)
    covariance = np.cov(scores,rowvar=False,ddof=1)
    if not np.allclose(scores.mean(axis=0),0,rtol=0,atol=1e-12) or not np.allclose(covariance,np.eye(2),rtol=0,atol=1e-12):
        raise AssertionError('Whitened scores must have sample covariance equal to identity')
    checks = {'variance_ratios':check_array(model.explained_variance_ratio_,numpy_tokens(cached_text(nb,6))),
              'component_directions':check_array(model.components_,numpy_tokens(cached_text(nb,7)))}
    text = cached_text(nb,8)
    if '...' not in text or len(scores) < 7:
        raise ValueError('Expected source display with the first/last three rows')
    positions = [0,1,2,len(scores)-3,len(scores)-2,len(scores)-1]
    checks['displayed_score_rows'] = check_array(scores[positions],numpy_tokens(text,allow_ellipsis=True))
    corr = data.corr()
    reference = {}
    for line in cached_text(nb,5).splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[0] in FEATURES and all(re.fullmatch(r'[-+]?\d+\.\d+',s) for s in parts[1:]):
            reference[parts[0]] = parts[1:]
    if set(reference) != set(FEATURES):
        raise ValueError('Expected complete cached feature-correlation table')
    pairs = [(i,j) for i in range(4) for j in range(i+1,4)]
    checks['six_unique_correlations'] = check_array([corr.iloc[i,j] for i,j in pairs],
                                                  [reference[FEATURES[i]][j] for i,j in pairs])
    coverage = write_coverage(nb,[([3,4],'导入与读取客户使用量','ID唯一检查，显式选择4个计数特征，不将ID入模'),
        ([5],'相关矩阵','六个不同相关系数核对，解释共线性'),
        ([6],'标准化与两主成分PCA','StandardScaler的ddof=0标准化，完整SVD，保持whiten=True'),
        ([7],'主成分方向','最大绝对权重为正的符号约定，保留PC方向和白化系数的区别'),
        ([8],'主成分投影','保存本地全部600行，只核对源缓存前后三行12个值')],ctx.output/'notebook-map.md')
    variance = pd.DataFrame({'component':['PC1','PC2','PC3','PC4'], 'sample_eigenvalue':full.explained_variance_,
                            'explained_ratio':full.explained_variance_ratio_, 'cumulative_ratio':np.cumsum(full.explained_variance_ratio_)})
    directions = pd.DataFrame(model.components_.T,index=FEATURES,columns=['PC1_direction','PC2_direction'])
    directions['PC1_whitened_coefficient'] = model.components_[0]/np.sqrt(model.explained_variance_[0])
    directions['PC2_whitened_coefficient'] = model.components_[1]/np.sqrt(model.explained_variance_[1])
    save_table(variance,ctx.output/'explained_variance.csv')
    save_table(directions.rename_axis('feature').reset_index(),ctx.output/'component_directions.csv')
    save_table(pd.DataFrame({'feature':FEATURES,'mean':scaler.mean_,'population_std':scaler.scale_}),ctx.output/'scaling.csv')
    save_table(raw[['ID']].assign(PC1=scores[:,0],PC2=scores[:,1]),ctx.output/'customer_scores_private.csv')
    plt = plotting()
    fig,axes = plt.subplots(1,2,figsize=(12,5),layout='constrained')
    axes[0].bar(variance.component,variance.explained_ratio*100,color=['#087f8c','#d67b28','#93a7b5','#c6d1d9'])
    axes[0].plot(variance.component,variance.cumulative_ratio*100,'o-',color='#5b5fa6',label='累计解释比例')
    axes[0].set(title='四个主成分的方差解释',ylabel='占标准化数据总变异（%）',ylim=(0,105))
    axes[0].legend(frameon=False)
    im = axes[1].imshow(model.components_,vmin=-1,vmax=1,cmap='RdBu_r',aspect='auto')
    axes[1].set(xticks=range(4),xticklabels=FEATURES,yticks=[0,1],yticklabels=['PC1','PC2'],title='主成分单位方向（白化之前）')
    for i in range(2):
        for j in range(4):axes[1].text(j,i,f'{model.components_[i,j]:.3f}',ha='center',va='center',color='white' if abs(model.components_[i,j])>.65 else '#172c37')
    fig.colorbar(im,ax=axes[1],label='方向权重')
    fig.savefig(ctx.output/'telecom_pca.png',dpi=150)
    plt.close(fig)
    total = float(model.explained_variance_ratio_.sum())
    report = f"""# S06 电信使用量主成分分析

## 结果与解释

{len(raw)}名不同客户，4个计数特征cnt_call、cnt_msg、cnt_wei、cnt_web。PC1解释{model.explained_variance_ratio_[0]:.4%}，PC2解释{model.explained_variance_ratio_[1]:.4%}，合计保留{total:.4%}的标准化总变异。PC1主要由消息/微信/网页使用方向构成，PC2主要是通话方向；业务名称依据原字段名作教学解释，不代表已完成聚类或客户画像验证。

![PCA解释比例和方向](telecom_pca.png)

## 代码内涵

先对每列减均值，再除以总体标准差（ddof=0），防止计数尺度支配PCA。PCA使用样本协方差（n−1分母），因此四个样本特征值之和为4×600/599，而不是恰好4。固定完整SVD避免不同自动求解器带来不必要差异。

教材设置whiten=True。本实现保持该设置，得分等于标准化投影除以对应样本特征值平方根，两列得分的样本协方差检查为单位矩阵。components_是单位方向，不能直接当成白化后完整得分系数；两种系数均在component_directions.csv分开列出。主成分整体正负号不影响解释比例，本实现约定最大绝对方向权重为正。

## 核对与限制

28项缓存数值按显示精度核对：2个解释比例、8个方向权重、6个不重复相关系数，以及源输出前后三行的12个白化得分。原缓存中间594行被省略，不能声称1200个得分全部对过参考。独立检查覆盖全部得分的均值、样本协方差和有限性，ID未入模，客户得分仅保存在本地。

这是对本样本的描述性降维，没有训练测试评估或分群标签。用于预测流水线时应仅在训练分区拟合标准化和PCA。全部6个非空代码单元见[迁移对照](notebook-map.md)。[scikit-learn官方PCA文档](https://scikit-learn.org/1.6/modules/generated/sklearn.decomposition.PCA.html)说明白化及解释方差口径。
"""
    finish(ctx,{'lab_id':'S06','status':'reference_verified','source_rows':len(raw),'features':FEATURES,
        'retained_variance_ratio':total,'whiten':True,'score_sample_covariance':covariance.tolist(),
        'reference_checks':checks,'notebook_coverage':coverage},report)


if __name__ == '__main__':main()
