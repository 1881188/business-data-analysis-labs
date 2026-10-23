"""S12: reproducible, descriptive bank-channel segmentation and a surrogate tree."""
import importlib.metadata
import numpy as np
import pandas as pd
from statsmodels.multivariate.factor_rotation import rotate_factors
from sklearn.preprocessing import QuantileTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score,silhouette_score,accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier,plot_tree,export_text
from threadpoolctl import threadpool_limits
from .dimension_reduction import standardized_pca
from .common import context,finish,plotting,save_table
from .notebook_reference import read_notebook,cached_text,cached_series,write_coverage
from .statistical_reference import check_array,numpy_tokens,indexed_table_tokens,check_printed

CHANNELS=['CNT_TBM','CNT_ATM','CNT_POS','CNT_CSC']
FACTORS=['ATM_POS','TBM','CSC']
SEED=20261023


def channel_features(raw):
    if raw.ID.isna().any() or raw.ID.duplicated().any():raise ValueError('Expected one unique nonmissing customer ID per row')
    x=raw[CHANNELS].copy()
    values=x.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values<0).any() or (values%1!=0).any():raise ValueError('Channel counts must be finite nonnegative integers')
    if not np.array_equal(x.sum(axis=1).to_numpy(),raw.CNT_TOT.to_numpy()):raise ValueError('CNT_TOT differs from the four-channel sum')
    return x


def rotate_channels(x):
    z,scaler,pc,_=standardized_pca(x,3)
    basis=pc.components_.T
    weights,rotation=rotate_factors(basis,'varimax',tol=1e-10,max_tries=10000)
    # Semantic order is defined from feature names, independent of cached values.
    order=[int(np.argmax(abs(weights[1:3]).sum(axis=0))),int(np.argmax(abs(weights[0]))),int(np.argmax(abs(weights[3])))]
    if len(set(order))!=3:raise ValueError('The retained directions do not have distinct ATM/POS, TBM and CSC interpretations')
    weights,rotation=weights[:,order],rotation[:,order]
    signs=np.where(weights[np.argmax(abs(weights),axis=0),np.arange(3)]<0,-1,1)
    weights*=signs;rotation*=signs
    if not np.allclose(weights.T@weights,np.eye(3),atol=1e-10,rtol=0):raise AssertionError('Nonorthogonal rotated directions')
    if not np.allclose(weights@weights.T,basis@basis.T,atol=1e-10,rtol=0):raise AssertionError('Retained subspace changed')
    return z,scaler,pc,weights,z@weights


def cluster(values,seed=SEED):
    values=np.asarray(values,dtype=float)
    if values.ndim!=2 or values.shape[1]!=3 or len(values)<3 or not np.isfinite(values).all():raise ValueError('Expected finite three-dimensional scores')
    if len(np.unique(values,axis=0))<3:raise ValueError('At least three distinct score vectors are required')
    with threadpool_limits(limits=1):
        model=KMeans(n_clusters=3,n_init=10,random_state=seed,max_iter=300,algorithm='lloyd').fit(values)
    # Labels are arbitrary; canonical ordering is by ATM_POS, then TBM, then CSC center.
    order=np.lexsort(model.cluster_centers_.T[::-1]);mapping=np.empty(3,dtype=int);mapping[order]=np.arange(3)
    return mapping[model.labels_],model.cluster_centers_[order],float(model.inertia_),int(model.n_iter_)


def cluster_quality(values,labels,inertia,iterations,branch):
    indices=np.random.default_rng(SEED).choice(len(values),min(2000,len(values)),replace=False)
    sampled=labels[indices];groups=len(np.unique(sampled))
    with threadpool_limits(limits=1):
        silhouette=float(silhouette_score(values[indices],sampled)) if 1<groups<len(indices) else None
    return {'branch':branch,'inertia_own_geometry_only':inertia,'iterations':iterations,'sampled_silhouette':silhouette,
            'uniform_sample_n':len(indices),'sampled_groups':groups,'smallest_cluster':int(np.bincount(labels).min())}


def main(argv=None):
    ctx=context('S12',argv);nb=read_notebook(ctx.source('notebook_bank_segments'))
    raw=pd.read_csv(ctx.source('bank_profiles'));x=channel_features(raw)
    with threadpool_limits(limits=1):z,scaler,pc,weights,scores=rotate_channels(x)
    transformer=QuantileTransformer(n_quantiles=min(1000,len(x)),subsample=10000,output_distribution='normal',random_state=0)
    transformed=transformer.fit_transform(scores)
    text=cached_text(nb,4).splitlines()
    checks={'three_eigenvalues':check_array(pc.explained_variance_,numpy_tokens(text[0])),
            'three_ratios':check_array(pc.explained_variance_ratio_,numpy_tokens(text[1])),
            'twelve_directions':check_array(weights,indexed_table_tokens(cached_text(nb,8),4,3)),
            'first_five_scores_only':check_array(scores[:5],indexed_table_tokens(cached_text(nb,11),5,3))}
    skew_before=pd.DataFrame(scores,columns=FACTORS).skew();skew_after=pd.DataFrame(transformed,columns=FACTORS).skew()
    for cell,actual,label in [(13,skew_before,'absolute_skew_before'),(21,skew_after,'absolute_skew_after')]:
        checks[label]={name:check_printed(abs(actual[name]),token) for name,token in cached_series(nb,cell).items()}
        if len(checks[label])!=3:raise ValueError('Incomplete skew reference')
    raw_labels,raw_centers,raw_inertia,raw_iterations=cluster(scores)
    labels,centers,inertia,iterations=cluster(transformed)
    alternative,_,_,_=cluster(transformed,SEED+1)
    stability=float(adjusted_rand_score(labels,alternative))
    quality=pd.DataFrame([cluster_quality(scores,raw_labels,raw_inertia,raw_iterations,'untransformed_factors'),
                          cluster_quality(transformed,labels,inertia,iterations,'quantile_normal_factors')])
    profiles=[]
    for branch,groups in [('untransformed_factors',raw_labels),('quantile_normal_factors',labels)]:
        for group in range(3):
            part=x.loc[groups==group]
            row={'branch':branch,'cluster':group,'records':len(part),'sample_fraction':len(part)/len(x)}
            for col in CHANNELS:row[col+'_mean']=float(part[col].mean());row[col+'_median']=float(part[col].median())
            row['total_count_share']=float(part.sum().sum()/x.sum().sum())
            profiles.append(row)
    profiles=pd.DataFrame(profiles)
    train,test=train_test_split(np.arange(len(x)),test_size=.3,stratify=labels,random_state=SEED)
    tree=DecisionTreeClassifier(max_depth=3,min_samples_split=100,min_samples_leaf=100,random_state=12345)
    tree.fit(x.iloc[train],labels[train])
    surrogate={'train_records':len(train),'held_out_records':len(test),'train_fidelity':float(accuracy_score(labels[train],tree.predict(x.iloc[train]))),
               'held_out_fidelity':float(accuracy_score(labels[test],tree.predict(x.iloc[test]))),'features':CHANNELS.copy(),
               'feature_importance':dict(zip(CHANNELS,tree.feature_importances_.tolist()))}
    save_table(pd.DataFrame({'ID':raw.ID,'raw_factor_cluster':raw_labels,'quantile_cluster':labels}),ctx.output/'private_customer_clusters.csv')
    save_table(profiles,ctx.output/'cluster_profiles.csv');save_table(quality,ctx.output/'cluster_quality.csv')
    center_rows=[]
    for branch,array in [('untransformed_factors',raw_centers),('quantile_normal_factors',centers)]:
        for i,row in enumerate(array):center_rows.append({'branch':branch,'cluster':i,**dict(zip(FACTORS,row))})
    save_table(pd.DataFrame(center_rows),ctx.output/'cluster_centers.csv')
    save_table(pd.DataFrame(weights,index=CHANNELS,columns=FACTORS).rename_axis('feature').reset_index(),ctx.output/'bank_directions.csv')
    save_table(pd.DataFrame({'component':np.arange(1,4),'eigenvalue':pc.explained_variance_,'variance_fraction':pc.explained_variance_ratio_}),ctx.output/'bank_variance.csv')
    save_table(pd.DataFrame({'factor':FACTORS,'skew_before':skew_before.values,'skew_after':skew_after.values}),ctx.output/'factor_skewness.csv')
    (ctx.output/'surrogate_rules.txt').write_text(export_text(tree,feature_names=CHANNELS).rstrip()+'\n',encoding='utf-8')
    coverage=write_coverage(nb,[
        ([1,2,3,4],'行为字段、相关、标准化和PCA','仅四个渠道计数参与；ID和派生总数排除；标准化ddof=0，完整SVD取3维'),
        ([5,6,7,8,9,10,11],'主成分提取、varimax和命名','statsmodels旋转单位方向；保持ATM_POS/TBM/CSC语义，核对全部方向和仅显示的前5行得分'),
        ([13,14,15,16],'原因子偏态与Kmeans','固定种子、n_init=10；比较原得分聚类，客户标签仅在本地，聚合画像替代饼图'),
        ([18,19,20,21,22,23,24],'分位数正态转换和第二次聚类','显式1000分位点、10000抽样、random_state=0，核对偏度；源Kmeans未设种子，不逐标签宣称一致'),
        ([25,26],'聚类事后解释','仅四渠道训练深度3的替代树；30%保留样本评价对既定标签的拟合程度，matplotlib导出免Graphviz')],ctx.output/'notebook-map.md')
    plt=plotting();fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained')
    grouped=profiles.loc[profiles.branch=='quantile_normal_factors']
    axes[0].bar(['G0','G1','G2'],grouped.records,color=['#247d86','#d67b28','#79609c'])
    axes[0].set(title='转换后聚类规模',ylabel='样本客户数')
    for i,v in enumerate(grouped.records):axes[0].text(i,v,f'{v:,}',ha='center',va='bottom')
    heat=grouped[[c+'_mean' for c in CHANNELS]].to_numpy()
    im=axes[1].imshow(np.log1p(heat),cmap='YlGnBu',aspect='auto')
    axes[1].set(title='四渠道均值画像',xticks=range(4),xticklabels=['TBM','ATM','POS','CSC'],yticks=range(3),yticklabels=['G0','G1','G2'])
    for i in range(3):
        for j in range(4):axes[1].text(j,i,f'{heat[i,j]:.1f}',ha='center',va='center',color='white' if np.log1p(heat[i,j])>np.log1p(heat).max()*.65 else '#172c37')
    fig.colorbar(im,ax=axes[1],label='颜色=log(1+均值)；格中为次数')
    axes[2].bar(np.arange(3)-.18,abs(skew_before),width=.36,color='#d67b28',label='转换前')
    axes[2].bar(np.arange(3)+.18,abs(skew_after),width=.36,color='#247d86',label='转换后')
    axes[2].set(xticks=range(3),xticklabels=FACTORS,title='绝对偏度变化',ylabel='|偏度|');axes[2].legend(frameon=False)
    fig.savefig(ctx.output/'bank_segments.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(20,8),layout='constrained')
    plot_tree(tree,feature_names=CHANNELS,class_names=['G0','G1','G2'],filled=True,rounded=True,ax=ax,fontsize=9,proportion=True)
    ax.set_title('Descriptive surrogate: four channels only; 70% tree training subset')
    fig.savefig(ctx.output/'segment_tree.png',dpi=140);plt.close(fig)
    report=f'''# S12 银行客户渠道使用分群

10万条唯一客户记录，四个渠道计数非负且无缺失，CNT_TOT逐条等于四项之和。ID仅用于本地记录关联，ID和CNT_TOT均不作为降维、聚类或替代树特征。原教材将它们放入事后解释树；编号可能制造无业务意义的切分，本实现移除。

## 从渠道到分群

四项渠道先标准化，再取3个单位主成分方向，保留{pc.explained_variance_ratio_.sum():.6%}变异，随后做varimax，命名ATM_POS、TBM、CSC。方向正交与子空间不变经过检查。缓存共核对39个值：3个特征值、3个方差占比、12个方向、前5行15个得分、转换前后6个绝对偏度。其余客户得分未有完整教材缓存可对账。

分位数转换显式指定n_quantiles=1000、subsample=10000、random_state=0，复现教材偏度。抽样估计的边际变换改变欧氏距离，不能保证联合正态，也不表示数据质量必然更好。没有用结果倒推参数，10000为本环境sklearn 1.6的默认抽样量，显式固定以免后续版本漂移。见[QuantileTransformer官方说明](https://scikit-learn.org/1.6/modules/generated/sklearn.preprocessing.QuantileTransformer.html)。

两种得分各自用KMeans(k=3,n_init=10,random_state={SEED},max_iter=300)拟合。标签按中心排序固定展示，原始标签数字没有业务等级含义。教材Kmeans没有固定种子，公开缓存只有人数和少量标签，无法核对完整旧分区；本次不强求教材35582/34385/30033的人数或标签顺序。显式n_init依据[KMeans官方接口](https://scikit-learn.org/1.6/modules/generated/sklearn.cluster.KMeans.html)。

![规模与渠道画像](bank_segments.png)

转换后分群规模为{', '.join(str(int(n)) for n in grouped.records)}人。另一固定种子重拟合的ARI={stability:.6f}，只衡量本次初始化稳定性，不证明3群是最佳群数。原得分与转换得分的惯性使用不同几何，不能直接比较大小。轮廓系数采用固定均匀2000人子样本；若抽不到两个群则记为空，并记录实际抽到群数。稀有极端群在抽样评价中可能被遗漏，不能只凭该指标裁决。

## 替代树的边界

树只解释已经由全样本描述性聚类生成的标签。固定分层70%/30%拆分用于树拟合；保留部分的标签拟合一致率{surrogate['held_out_fidelity']:.4%}，不是预测真实业务类别的准确率，也不是未见客户分群效果的独立验证。它只用原始四渠道，深度3，最小叶子100；规则见surrogate_rules.txt。

![四渠道替代树](segment_tree.png)

群像以原渠道次数的均值和中位数解释，不能据此宣称客户价值、盈利或营销增量。客户ID、各行得分和标签留在本地。[全部代码单元迁移](notebook-map.md)覆盖两套聚类及解释树。
'''
    finish(ctx,{'lab_id':'S12','status':'execution_verified','records':len(x),'seed':SEED,'n_init':10,
                'threadpool_limit':1,'threadpoolctl_version':importlib.metadata.version('threadpoolctl'),
                'retained_variance':float(pc.explained_variance_ratio_.sum()),'reference_checks':checks,'reference_values_compared':39,
                'cluster_quality':quality.astype(object).where(quality.notna(),None).to_dict('records'),
                'normal_counts':np.bincount(labels).tolist(),'alternate_seed_ari':stability,'surrogate':surrogate,'notebook_coverage':coverage},report)


if __name__=='__main__':main()
