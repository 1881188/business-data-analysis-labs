"""Telecom cleaning, representations, projection and feature-selection demonstrations."""
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.feature_selection import VarianceThreshold, chi2, f_classif, f_regression, RFE, SelectKBest, SelectFromModel
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, MinMaxScaler, Normalizer, OneHotEncoder
from threadpoolctl import threadpool_limits

from bda_labs.common import context
from bda_labs.advanced_common import read_csv, specification, complete, bars


def main(lab='M28',argv=None):
    ctx=context(lab,argv);raw=read_csv(ctx,specification(lab)['inputs'][0])
    data=raw[raw['traffic']<5000].copy()
    records=[{'section':'missing','item':col,'value':int(n)} for col,n in data.isna().sum().items()]
    records.append({'section':'state_recode','item':'2_or_4_to_missing','value':int(data['state'].replace([2,4],np.nan).isna().sum())})
    records.append({'section':'missing','item':'state_or_IMEI_available','value':len(data.dropna(thresh=1,subset=['state','IMEI']))})
    all_zero=data.fillna(0)
    mode=data['state'].mode().iloc[0]
    data['state']=data['state'].fillna(mode);data['IMEI']=data['IMEI'].fillna(0)
    imputed=SimpleImputer(strategy='most_frequent').fit_transform(raw[['state','IMEI']])
    if not np.isfinite(imputed).all() or all_zero.isna().any().any():raise AssertionError('Missing value demonstration failed')
    lower=data['expenditure'].mean()-3*data['expenditure'].std();upper=data['expenditure'].mean()+3*data['expenditure'].std()
    clipped=data['expenditure'].clip(lower,upper)
    if (clipped<=-1).any() or (data[['call','traffic']]<=-1).any().any():raise ValueError('log1p domain error')
    data['log_expd']=np.log1p(clipped);data['log_call']=np.log1p(data['call']);data['log_traffic']=np.log1p(data['traffic'])
    data['has_IMEI']=(data['IMEI']>0).astype(int)
    cut_indicator=pd.cut(data['IMEI'],[-np.inf,0,np.inf],labels=False)
    if not np.array_equal(cut_indicator,data['has_IMEI']):raise AssertionError('Binarization and cut differ')
    data['duration']=(pd.Timestamp('2015-01-01')-pd.to_datetime(data['join_time'])).dt.days/30
    for name,bins in [('equal_width',pd.cut(data['duration'],5)),('equal_depth',pd.qcut(data['duration'],14,duplicates='drop')),
                      ('business',pd.cut(data['duration'],[-np.inf,5,12,36,np.inf]))]:
        grouped=data.groupby(bins,observed=False)['churn'].agg(['count','mean','sum'])
        records += [{'section':name,'item':str(i),'count':int(r['count']),'churn_rate':r['mean'],'churn_count':int(r['sum'])} for i,r in grouped.iterrows()]
    encoded=OneHotEncoder(sparse_output=False).fit_transform(data[['state']])
    dummies=pd.get_dummies(data['state'])
    if encoded.shape!=dummies.shape or not np.array_equal(encoded,dummies.to_numpy()):raise AssertionError('One-hot implementations differ')
    consumption=data[['log_expd','log_call','log_traffic']]
    scaled=StandardScaler().fit_transform(consumption)
    ranged=MinMaxScaler().fit_transform(consumption);normalized=Normalizer().transform(scaled)
    if not np.allclose(np.linalg.norm(normalized,axis=1),1,atol=1e-10):raise AssertionError('Row normalization failed')
    data['unit_price']=data['expenditure']/(data['traffic']+1)
    data['TAC']=data['IMEI'].map(lambda x:str(x)[:6])
    with threadpool_limits(limits=1):
        pca=PCA(n_components=2,whiten=True,svd_solver='full').fit(scaled);scores=pca.transform(scaled)
        if not np.allclose(np.cov(scores,rowvar=False),np.eye(2),atol=1e-10):raise AssertionError('PCA whitening covariance differs')
        synthetic=np.array([[-1,0,1],[1,2,3]])
        projected=pca.transform(synthetic)
        lda=LinearDiscriminantAnalysis().fit(scaled,data['churn'])
        lda_scores=lda.transform(scaled);lda.transform(synthetic)
        records += [{'section':'PCA','item':i+1,'variance':v,'ratio':r} for i,(v,r) in enumerate(zip(pca.explained_variance_,pca.explained_variance_ratio_))]
        records.append({'section':'LDA','item':'in_sample_accuracy','value':lda.score(scaled,data['churn'])})
        for i,value in enumerate(lda.coef_[0]):records.append({'section':'LDA_coefficient','item':consumption.columns[i],'value':value})
        vc=data[['vip','has_IMEI']];variance=VarianceThreshold(.09).fit(vc)
        records += [{'section':'variance','item':c,'value':v,'selected':bool(k)} for c,v,k in zip(vc,variance.variances_,variance.get_support())]
        categorical=data[['vip','state','has_IMEI']]
        continuous=pd.DataFrame(scaled,index=data.index,columns=['s_expd','s_call','s_traffic']).assign(duration=data['duration'])
        for name,func,frame,target in [('chi2',chi2,categorical,data['churn']),('ANOVA',f_classif,continuous,data['churn']),
                                       ('regression_F',f_regression,continuous,continuous['s_expd'])]:
            selector=SelectKBest(func,k=2).fit(frame,target)
            records += [{'section':name,'item':c,'score':float(s),'pvalue':float(p),'selected':bool(k)}
                        for c,s,p,k in zip(frame,selector.scores_,selector.pvalues_,selector.get_support())]
        rfe=RFE(LogisticRegression(max_iter=2000),n_features_to_select=2).fit(continuous,data['churn'])
        forest=RandomForestClassifier(random_state=42,n_jobs=1).fit(continuous,data['churn'])
        gbdt=SelectFromModel(GradientBoostingClassifier(random_state=42),threshold='mean').fit(continuous,data['churn'])
        records += [{'section':'wrapper_embedded','item':c,'RFE_selected':bool(r),'RF_importance':float(v),'GBDT_selected':bool(g)}
                    for c,r,v,g in zip(continuous,rfe.support_,forest.feature_importances_,gbdt.get_support())]
    bars(ctx,list(continuous.columns),forest.feature_importances_,'电信特征工程：训练内随机森林重要性','importance')
    complete(ctx,lab,records,{'input_rows':len(raw),'retained_rows':len(data),'traffic_outliers_removed':len(raw)-len(data),
                            'expenditure_cap':[float(lower),float(upper)],'PCA_whitening_checked':True,
                            'one_hot_identity_checked':True,'evaluation_scope':'descriptive_in_sample'},
             notes='这是预处理与特征选择方法演示，沿用源样本内拟合口径；LDA 准确率不是泛化估计。回归 F 示例把 s_expd 同时放在输入和目标中，仅演示 API，不能当预测方案。等频分箱遇重复边界明确合并。时间截止按教材 2015-01-01 固定；TAC 是字符串前六位教学示例，不发布终端标识。')
