"""Imbalanced classification with train-only resampling and categorical-aware SMOTE."""
import importlib.metadata

import numpy as np
from sklearn.datasets import make_blobs
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OrdinalEncoder
from threadpoolctl import threadpool_limits

from bda_labs.common import context
from bda_labs.advanced_common import read_csv,specification,complete,bars
from bda_labs.advanced_regression import classification_metrics


def main(lab='M29',argv=None):
    from imblearn.over_sampling import SMOTE,SMOTENC
    from imblearn.under_sampling import RandomUnderSampler,TomekLinks,EditedNearestNeighbours
    from imblearn.combine import SMOTETomek,SMOTEENN
    from xgboost import XGBClassifier
    ctx=context(lab,argv);records=[]
    X,y=make_blobs(n_samples=[1000,100],centers=[[0,0],[2,2]],cluster_std=[1.5,1],random_state=42,shuffle=False)
    samplers={'SMOTE':SMOTE(random_state=42,sampling_strategy=.5),
              'random_under':RandomUnderSampler(random_state=42,sampling_strategy=.3),
              'Tomek':TomekLinks(),'ENN':EditedNearestNeighbours(n_neighbors=20),
              'SMOTETomek':SMOTETomek(random_state=42),'SMOTEENN':SMOTEENN(random_state=42)}
    with threadpool_limits(limits=1):
        for name,sampler in samplers.items():
            newX,newy=sampler.fit_resample(X,y)
            records.append({'section':'synthetic_sampling','item':name,'class0':int((newy==0).sum()),'class1':int((newy==1).sum())})
        raw=read_csv(ctx,specification(lab)['inputs'][0]).drop(columns='ID').dropna()
        target=raw.pop('y');cats=raw.select_dtypes(include='object').columns.tolist()
        a,b=train_test_split(np.arange(len(raw)),test_size=.3,stratify=target,random_state=42)
        train=raw.iloc[a].copy();test=raw.iloc[b].copy();ytrain=target.iloc[a];ytest=target.iloc[b]
        encoder=OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=-1)
        train[cats]=encoder.fit_transform(train[cats]);test[cats]=encoder.transform(test[cats])
        columns=list(train);cat_indices=[columns.index(c) for c in cats]
        variants=[('baseline',None,{}),('SMOTE',SMOTE(random_state=42),{}),
                  ('SMOTENC',SMOTENC(categorical_features=cat_indices,random_state=42),{}),
                  ('weighted',None,{'scale_pos_weight':float((ytrain==0).sum()/(ytrain==1).sum())}),
                  ('max_delta_step',None,{'max_delta_step':.6})]
        aucs=[];labels=[];invalid=0
        for name,sampler,params in variants:
            sx,sy=(train,ytrain) if sampler is None else sampler.fit_resample(train,ytrain)
            if name=='SMOTE':invalid=int(np.any(np.asarray(sx[cats])%1!=0,axis=1).sum())
            if name=='SMOTENC':
                if any(not set(sx[c]).issubset(set(train[c])) for c in cats):raise AssertionError('SMOTENC generated invalid categories')
            model=XGBClassifier(n_estimators=10,objective='binary:logistic',random_state=42,n_jobs=1,**params).fit(sx,sy)
            result=classification_metrics(ytest,model.predict_proba(test)[:,1])
            records.append({'section':'holdout','item':name,'train_rows':len(sx),**result})
            labels.append(name);aucs.append(result['AUC'])
    bars(ctx,labels,aucs,'类别不平衡：同一未重采样留出集 AUC','AUC')
    complete(ctx,lab,records,{'raw_complete_rows':len(raw),'train_rows':len(a),'test_rows':len(b),
                            'categorical_features':cats,'plain_SMOTE_fractional_category_rows':invalid,
                            'SMOTENC_categories_checked':True,
                            'imbalanced_learn_version':importlib.metadata.version('imbalanced-learn'),
                            'xgboost_version':importlib.metadata.version('xgboost')},
             notes='编码仅拟合训练集，重采样仅作用于训练样本。普通 SMOTE 在类别代码间插值的结果保留为反例并统计非法类别行；正式类别感知比较用 SMOTENC。保留六种二维合成采样、实际基线、重采样、类别权重和 max_delta_step；测试集保持原始分布，不用准确率掩盖少数类表现。')
