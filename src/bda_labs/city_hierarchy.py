"""S13: Ward clustering of two retained regional score directions; source files are read-only."""
import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist
from scipy.cluster.hierarchy import linkage,dendrogram,cut_tree,is_valid_linkage,cophenet
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import adjusted_rand_score
from .dimension_reduction import principal_rotation,standardized_pca
from .common import context,finish,plotting,save_table,compare_numeric
from .notebook_reference import read_notebook,cached_text,write_coverage
from .statistical_reference import check_array,numpy_tokens


def ward_scores(scores):
    values=np.asarray(scores,dtype=float)
    if values.ndim!=2 or values.shape[1]!=2 or len(values)<3 or not np.isfinite(values).all():raise ValueError('Ward input must be finite observations with two score columns')
    distances=pdist(values,metric='euclidean')
    z=linkage(distances,method='ward')
    is_valid_linkage(z,throw=True)
    if np.any(np.diff(z[:,2])<-1e-12) or int(z[-1,3])!=len(values):raise AssertionError('Invalid monotone Ward hierarchy')
    return distances,z


def main(argv=None):
    ctx=context('S13',argv);nb=read_notebook(ctx.source('notebook_hierarchy'))
    raw=pd.read_csv(ctx.source('hierarchy_cities'),encoding='gbk');reference=pd.read_csv(ctx.source('hierarchy_reference'))
    features=[f'X{i}' for i in range(1,10)]
    if raw.AREA.isna().any() or raw.AREA.duplicated().any():raise ValueError('Distinct region labels are required')
    if raw.AREA.tolist()!=reference.AREA.tolist():raise ValueError('Reference region order differs')
    compare_numeric(raw[features],reference[features],'reference raw features',tolerance=0)
    z,_,pc,weights,scores,rotation,gradient=principal_rotation(raw[features])
    # Rotation preserves Euclidean distances in the retained subspace, including across numerical optima.
    _,_,pc3,_=standardized_pca(raw[features],3)
    reference_scores=reference[['Gross','Avg']].to_numpy()
    score_comparison=compare_numeric(scores,reference_scores,'provided two-score reference',tolerance=1e-6)
    distances,tree=ward_scores(scores);reference_distances,reference_tree=ward_scores(reference_scores)
    tree_comparison=compare_numeric(tree,reference_tree,'Ward tree numeric invariance',tolerance=1e-10)
    if not np.allclose(distances,pdist(z@pc.components_.T),atol=1e-10,rtol=0):raise AssertionError('Rotation changed retained-space distances')
    cached=[line for line in cached_text(nb,10).splitlines() if '[' in line]
    # Cached weight digits may differ at ~1e-8 between fa_kit and statsmodels stopping rules.
    weight_tokens=numpy_tokens(cached_text(nb,21));cached_weights=np.asarray(weight_tokens,dtype=float).reshape(9,2)
    weights_comparison=compare_numeric(weights,cached_weights,'legacy rotation directions',tolerance=3e-8)
    checks={'eigenvalues':check_array(pc3.explained_variance_,numpy_tokens(cached[0])),
            'variance_fractions':check_array(pc3.explained_variance_ratio_,numpy_tokens(cached[1])),
            'all_nine_ward_merges':check_array(tree,numpy_tokens(cached_text(nb,33)))}
    cached_tree=np.asarray(numpy_tokens(cached_text(nb,33)),dtype=float).reshape(-1,4)
    if not np.array_equal(tree[:,[0,1,3]],cached_tree[:,[0,1,3]]):raise AssertionError('Cached merge node IDs/member counts differ')
    cluster3=cut_tree(tree,n_clusters=3).ravel();cluster4=cut_tree(tree,n_clusters=4).ravel()
    standardized=StandardScaler().fit_transform(scores);_,standardized_tree=ward_scores(standardized)
    sensitivity=[]
    for k in [2,3,4]:
        a=cut_tree(tree,n_clusters=k).ravel();b=cut_tree(standardized_tree,n_clusters=k).ravel()
        if not np.array_equal(a,cut_tree(reference_tree,n_clusters=k).ravel()):raise AssertionError('Reference partition differs')
        sensitivity.append({'illustrative_clusters':k,'ari_with_score_standardization':float(adjusted_rand_score(a,b))})
    city=pd.DataFrame({'AREA':raw.AREA,'Gross':scores[:,0],'Avg':scores[:,1],'illustrative_k3':cluster3,'illustrative_k4':cluster4})
    save_table(city,ctx.output/'city_clusters.csv')
    # The source notebook overwrites fa_cities_10.csv. This migration writes only to the output directory.
    save_table(raw.join(pd.DataFrame(scores,index=raw.index,columns=['Gross','Avg'])),ctx.output/'local_derived_cities.csv')
    save_table(pd.DataFrame(tree,columns=['left_node','right_node','ward_height','members']).assign(merge_node=np.arange(len(raw),2*len(raw)-1)),ctx.output/'ward_linkage.csv')
    save_table(pd.DataFrame(weights,index=features,columns=['Gross','Avg']).rename_axis('feature').reset_index(),ctx.output/'city_directions.csv')
    save_table(pd.DataFrame({'component':[1,2,3],'eigenvalue':pc3.explained_variance_,'variance_fraction':pc3.explained_variance_ratio_}),ctx.output/'city_variance.csv')
    save_table(pd.DataFrame(sensitivity),ctx.output/'scale_sensitivity.csv')
    coverage=write_coverage(nb,[
        ([1,2,3,6,7],'读取、相关、标准化','核对本章地区标签和提供的参考表；不套用第7章同名文件的地区顺序，标准化ddof=0'),
        ([8,9,10,11,12],'主成分个数判断','保存3个特征值和精确方差比例；0.8+0.12只作舍入演示，实际选2维保留92.3279%'),
        ([15,16,17,18,19,20,21],'主成分提取与旋转','使用已有statsmodels库旋转单位方向；报告缓存8位权重的数值算法容差'),
        ([23,24,25,27],'得分合并与导出重读','重算得分并核对提供CSV；派生明细仅写本地outputs，绝不覆盖源fa_cities_10.csv'),
        ([28,29],'带地区标签的散点','按本章AREA标注二维得分，坐标不解释为有明确单位的绩效量'),
        ([31,32,33,34],'欧氏压缩距离和Ward树','pdist二维观察向量后linkage，核对全部9次合并；附加k=3/4示例切树及再标准化敏感性')],ctx.output/'notebook-map.md')
    plt=plotting();fig,ax=plt.subplots(figsize=(12,6),layout='constrained')
    dendrogram(tree,labels=raw.AREA.to_list(),ax=ax,color_threshold=0,above_threshold_color='#247d86')
    ax.set(title='10地区：两维主成分旋转得分的Ward树',ylabel='Ward合并高度（未对得分再次标准化）',xlabel='本章原始地区标签')
    fig.savefig(ctx.output/'city_dendrogram.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    axes[0].scatter(scores[:,0],scores[:,1],c=cluster3,cmap='Set2',s=80,edgecolors='#172c37')
    for i,name in enumerate(raw.AREA):axes[0].annotate(name,scores[i],xytext=(5,5),textcoords='offset points',fontsize=10)
    axes[0].set(title='原得分与示例k=3切树',xlabel='Gross（合成方向）',ylabel='Avg（合成方向）');axes[0].margins(.16)
    axes[1].bar(['Gross','Avg'],np.var(scores,axis=0,ddof=1),color=['#247d86','#d67b28'])
    axes[1].set(title='得分方差不同：距离权重需解释',ylabel='样本方差')
    fig.savefig(ctx.output/'city_scores.png',dpi=150);plt.close(fig)
    cophenetic=float(cophenet(tree,distances)[0])
    report=f'''# S13 地区层次聚类

本章cities_10.csv包含10个地区、9项指标。地区标签逐行以本章文件为准：第7章同名数据的辽宁与福建标签位置不同，不能沿用前一实验的地区得分表。源表与本章提供的fa_cities_10.csv已核对AREA及9项原始数值。

## 实现与参考核对

九项指标先按ddof=0标准化，保留前两主成分{pc.explained_variance_ratio_.sum():.6%}变异，旋转单位方向得到Gross、Avg。重算得分与提供CSV在绝对加相对容差1e-6内一致。原缓存权重打印8位，fa_kit与statsmodels的停止规则使末位有微小差别；18项权重单独采用3e-8绝对加相对容差，最大绝对差{weights_comparison['maximum_absolute_difference']:.3g}，没有宣称全部打印末位一致。

另有42项按原打印精度核对：3个特征值、3个方差占比、全部9次Ward合并的36个值。正交旋转保持两维保留子空间的所有欧氏距离，因而上述权重末位差别不会改变本例树；本次树与提供CSV所建树在1e-10绝对加相对容差内一致，k=2/3/4分区相同。源Notebook的写文件步骤改为outputs内的派生文件，教材原文件始终只读。

![Ward树](city_dendrogram.png)

ward_scores先pdist得到45个欧氏压缩距离，再linkage(method='ward')。树的每行是左右节点、合并高度、成员数；高度按Ward簇内平方误差准则更新，不能直接当作两城市原始距离。最后节点成员数10、节点引用合法、合并高度单调均经过检查。接口含义见[SciPy官方说明](https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.linkage.html)。

## 解释与敏感性

![示例分区及得分尺度](city_scores.png)

教材只画树，没有给定最优群数。本实现附加k=3和k=4只为教学演示；分组编号没有高低等级含义。保持源流程，不对Gross、Avg再次标准化；它们方差不同，在原得分距离中贡献也不同。scale_sensitivity.csv记录再标准化后k=2/3/4分区ARI，显示距离定义对结论的影响，不能据此证明哪种距离更正确。

树的cophenetic相关为{cophenetic:.6f}，只描述本样本树对成对距离的拟合。10地区样本、未明确年度与单位的X1至X9不能支持当前地区绩效排名或总体推广。公共输出仅含派生地区得分、树和聚合统计，不重新发布原始9项指标。[代码迁移](notebook-map.md)覆盖全部非空代码单元。
'''
    finish(ctx,{'lab_id':'S13','status':'execution_verified','regions':len(raw),'retained_variance':float(pc.explained_variance_ratio_.sum()),
                'reference_checks':checks,'printed_values_compared':42,'weight_comparison_with_algorithm_tolerance':weights_comparison,
                'provided_score_comparison':score_comparison,'provided_tree_comparison':tree_comparison,
                'cophenetic_correlation':cophenetic,'rotation_gradient':gradient,'scale_sensitivity':sensitivity,'notebook_coverage':coverage},report)


if __name__=='__main__':main()
