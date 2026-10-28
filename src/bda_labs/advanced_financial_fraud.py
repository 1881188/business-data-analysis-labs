"""Income inconsistency, historical contact graphs and application-fraud models."""
import numpy as np
import pandas as pd
import networkx as nx
from scipy.stats import norm
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV, GroupShuffleSplit, StratifiedGroupKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from threadpoolctl import threadpool_limits

from bda_labs.common import context
from bda_labs.advanced_common import specification,read_csv,complete,bars
from bda_labs.advanced_regression import classification_metrics


class IncomeFeatures(TransformerMixin,BaseEstimator):
    def fit(self,X,y=None):
        self.scaler_=StandardScaler().fit(X[['age','income']])
        self.encoder_=OneHotEncoder(handle_unknown='ignore',sparse_output=False).fit(X[['gender','city_level','edu']])
        predictors=np.column_stack([X['age'],self.encoder_.transform(X[['gender','city_level','edu']])])
        self.regression_=LinearRegression().fit(predictors,X['income'])
        residual=X['income'].to_numpy()-self.regression_.predict(predictors)
        self.residual_scaler_=StandardScaler().fit(residual[:,None])
        return self

    def transform(self,X):
        result=X.drop(columns=[c for c in ['userid','flag'] if c in X]).copy()
        z=self.scaler_.transform(X[['age','income']])
        result['age_st']=z[:,0];result['age_st_abs']=abs(z[:,0])
        result['income_st']=z[:,1];result['income_st_abs']=abs(z[:,1])
        predictors=np.column_stack([X['age'],self.encoder_.transform(X[['gender','city_level','edu']])])
        residual=X['income'].to_numpy()-self.regression_.predict(predictors)
        standardized=self.residual_scaler_.transform(residual[:,None]).ravel()
        result['income_resid']=residual;result['income__resid_st']=standardized;result['income__resid_st_abs']=abs(standardized)
        return result


def historical_network_features(events):
    """Contact graph and disclosed bad status as of each application date.

    Current applicant's own outcome is excluded. Same-day rejection is visible,
    other bad outcomes must have been disclosed strictly before the application.
    """
    required=['userid','connid','in_date','flag','flag_date']
    if events[['userid','connid','in_date']].isna().any().any():raise ValueError('Missing graph key/date')
    graph=nx.Graph();contacts=set();rows=[]
    status=events.sort_values('in_date').drop_duplicates('userid',keep='last').set_index('userid')[['flag','flag_date']].to_dict('index')
    for date,day in events.sort_values('in_date').groupby('in_date',sort=True):
        graph.add_edges_from(day[['userid','connid']].itertuples(index=False,name=None))
        comp={};known_bad={}
        for i,nodes in enumerate(nx.connected_components(graph)):
            bad=set()
            for node in nodes:
                info=status.get(node,{})
                flag=info.get('flag');when=info.get('flag_date',np.nan)
                if flag in {1,-1,-2} and (when<date or (when==date and flag==-1)):bad.add(node)
                comp[node]=(i,len(nodes))
            known_bad[i]=bad
        for user in day['userid'].drop_duplicates():
            i,size=comp[user];neighbours=list(graph[user])
            rows.append({'userid':user,'date':date,'net_size':size,'degree':graph.degree(user),
                         'average_neighbor_degree':float(np.mean([graph.degree(n) for n in neighbours])) if neighbours else 0.,
                         'percentage':len(known_bad[i]-{user})/size,'is_AC':int(user in contacts)})
        contacts.update(day['connid'])
    return pd.DataFrame(rows).sort_values('date').drop_duplicates('userid',keep='last')


def bayesian_search(X,y,make_model,groups,seed=42):
    """Bounded GP expected-improvement search over normalized hyperparameters."""
    rng=np.random.default_rng(seed);points=[];scores=[];parameters=[]
    def decode(point):
        return {'n_estimators':int(round(10+point[0]*110)),'learning_rate':.05+point[1]*.15,
                'max_depth':int(round(1+point[2]*2)),'min_split_gain':point[3]*10,
                'min_child_weight':point[4]*10,'subsample':.5+point[5]*.5,
                'colsample_bytree':.5+point[6]*.5,'reg_lambda':point[7]}
    for step in range(15):
        if step<5:point=rng.random(8)
        else:
            gp=GaussianProcessRegressor(kernel=Matern(nu=2.5),alpha=1e-6,normalize_y=True,random_state=seed,n_restarts_optimizer=0).fit(np.asarray(points),scores)
            candidates=rng.random((512,8));mean,std=gp.predict(candidates,return_std=True)
            improvement=mean-max(scores)-.001;z=improvement/np.maximum(std,1e-12)
            expected=improvement*norm.cdf(z)+std*norm.pdf(z)
            point=candidates[int(np.argmax(expected))]
        params=decode(point)
        model=make_model(params)
        cv=StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=42)
        score=float(cross_val_score(model,X,y,groups=groups,cv=cv,scoring='roc_auc',n_jobs=1,error_score='raise').mean())
        points.append(point);scores.append(score);parameters.append(params)
    best=int(np.argmax(scores));model=make_model(parameters[best]).fit(X,y)
    return model,[{'section':'GP_Bayesian_search','item':i,'CV_AUC':s,'parameters':str(p)} for i,(s,p) in enumerate(zip(scores,parameters))]


def main(lab='F08',argv=None):
    from imblearn.pipeline import Pipeline as ResamplingPipeline
    from imblearn.over_sampling import RandomOverSampler,SMOTE,BorderlineSMOTE
    from imblearn.combine import SMOTETomek,SMOTEENN
    from lightgbm import LGBMClassifier
    ctx=context(lab,argv);spec=specification(lab)
    basic=read_csv(ctx,spec['inputs'][0]);events=read_csv(ctx,spec['inputs'][1]);newbasic=read_csv(ctx,spec['inputs'][2])
    records=[];aucs={}
    duplicate_users=int((basic.groupby('userid').size()>1).sum())
    cv=StratifiedGroupKFold(n_splits=4,shuffle=True,random_state=42)
    with threadpool_limits(limits=1):
        y=basic['flag'].astype(int);features=basic[['age','gender','city_level','edu','income']]
        a,b=next(GroupShuffleSplit(n_splits=1,test_size=.3,random_state=12345).split(features,y,basic['userid']))
        if set(basic.iloc[a]['userid'])&set(basic.iloc[b]['userid']):raise AssertionError('Application user crosses holdout')
        pipeline=Pipeline([('features',IncomeFeatures()),('model',GradientBoostingClassifier(random_state=42,n_estimators=80,learning_rate=.2,max_depth=2))])
        search=GridSearchCV(pipeline,{'model__loss':['log_loss','exponential']},cv=cv,scoring='roc_auc',n_jobs=1,error_score='raise').fit(features.iloc[a],y.iloc[a],groups=basic.iloc[a]['userid'])
        for split,idx in [('train',a),('test',b)]:
            result=classification_metrics(y.iloc[idx],search.predict_proba(features.iloc[idx])[:,1]);records.append({'section':'income_anomalies','item':split,**result})
            if split=='test':aucs['income_anomalies']=result['AUC']
        derived=search.best_estimator_.named_steps['features'].transform(features.iloc[a])
        for c in ['age_st','age_st_abs','income_st','income_st_abs','income_resid','income__resid_st','income__resid_st_abs']:
            for label in [0,1]:records.append({'section':'training_distribution','item':c,'class':label,'mean':float(derived.loc[y.iloc[a]==label,c].mean())})
        historical=historical_network_features(events)
        graph=nx.from_pandas_edgelist(events,'userid','connid')
        communities=nx.community.louvain_communities(graph,weight=None,seed=42)
        records += [{'section':'community','item':i,'value':len(g)} for i,g in enumerate(sorted(communities,key=len,reverse=True))]
        # Replace brittle source hard-coded community IDs with a reproducible
        # largest-community illustration and chronological aggregate snapshots.
        for date,group in historical.groupby('date'):
            records.append({'section':'graph_snapshot','item':int(date),'applications':len(group),
                            'mean_net_size':float(group['net_size'].mean()),'prior_contact_conversion':int(group['is_AC'].sum())})
        source_id='id103572'
        records.append({'section':'component_example','item':'source_requested_component_size',
                        'value':len(nx.node_connected_component(graph,source_id)) if source_id in graph else 0})
        # Use raw application fields, never source-wide precomputed residuals.
        rawcols=['userid','flag','age','gender','city_level','edu','income']
        scored=newbasic[rawcols].merge(historical.drop(columns='date'),on='userid',how='left',validate='many_to_one')
        match=float(scored['net_size'].notna().mean())
        y=scored.pop('flag').astype(int);X=scored.drop(columns='userid')
        users=scored['userid']
        a,b=next(GroupShuffleSplit(n_splits=1,test_size=.3,random_state=12345).split(X,y,users))
        if set(users.iloc[a])&set(users.iloc[b]):raise AssertionError('Repeated user crosses holdout')
        Xtrain=X.iloc[a];Xtest=X.iloc[b];yt=y.iloc[a];yv=y.iloc[b]
        pre=[('income',IncomeFeatures()),('impute',SimpleImputer(strategy='constant',fill_value=0))]
        gbdt=Pipeline([*pre,('model',GradientBoostingClassifier(n_estimators=35,random_state=42))])
        grid={'model__loss':['log_loss','exponential'],'model__learning_rate':[.1,.3],
              'model__max_depth':[1,2],'model__min_samples_split':[2,4]}
        search=GridSearchCV(gbdt,grid,scoring='f1',cv=cv,n_jobs=1,error_score='raise').fit(Xtrain,yt,groups=users.iloc[a])
        result=classification_metrics(yv,search.predict_proba(Xtest)[:,1]);records.append({'section':'with_network_GBDT','item':'test',**result});aucs['network_GBDT']=result['AUC']
        samplers={'random_over':RandomOverSampler(sampling_strategy=.2,random_state=0),
                  'SMOTE':SMOTE(sampling_strategy=.2,random_state=0),'BorderlineSMOTE':BorderlineSMOTE(sampling_strategy=.2,random_state=0),
                  'SMOTETomek':SMOTETomek(sampling_strategy=.2,random_state=0),'SMOTEENN':SMOTEENN(sampling_strategy=.2,random_state=0)}
        # Source demonstrations resample engineered numeric features. They are
        # illustrative; all imputation/scaling uses training only.
        transformer=Pipeline([*pre,('scale',StandardScaler())]).fit(Xtrain,yt)
        transformed=transformer.transform(Xtrain)
        for name,sampler in samplers.items():
            sx,sy=sampler.fit_resample(transformed,yt)
            records.append({'section':'sampling_demonstration','item':name,'rows':len(sx),'bad_rows':int(np.sum(sy==1))})
        def make_model(params):
            return Pipeline([*[(name,clone(obj)) for name,obj in pre],('model',LGBMClassifier(**params,objective='binary',
                            subsample_freq=1,random_state=42,n_jobs=1,verbosity=-1))])
        best,trials=bayesian_search(Xtrain,yt,make_model,users.iloc[a]);records+=trials
        result=classification_metrics(yv,best.predict_proba(Xtest)[:,1]);records.append({'section':'network_LightGBM_GP','item':'test',**result});aucs['network_LGB_GP']=result['AUC']
    bars(ctx,list(aucs),list(aucs.values()),'金融反欺诈：各自留出样本的 AUC','AUC')
    complete(ctx,lab,records,{'initial_applications':len(basic),'network_rows':len(events),'network_nodes':graph.number_of_nodes(),
                            'communities':len(communities),'historical_feature_customers':len(historical),
                            'second_applications':len(newbasic),'network_match_fraction':match,
                            'second_train_rows':len(a),'second_test_rows':len(b),'Bayesian_initial_points':5,'Bayesian_iterations':10,
                            'repeated_user_groups':duplicate_users,'holdout_group_overlap':0,
                            'graph_feature_scope':'last_application_snapshot_in_supplied_event_log_excluding_own_outcome'},
             notes='保留收入残差/标准化绝对偏离、GBDT、连通分量、Louvain、按日关系特征、五种重采样演示和 LightGBM 贝叶斯调参。'
             '特征工程在 CV 折内拟合，重建全量关系日志的按日特征，替代源脚本因 dat 被社区子集覆盖而导出的少量特征。修复联系人集合更新缩进；坏标签仅按披露时间使用且排除申请者自身。原表有重复客户，保留申请行并按客户分组划分留出和CV，防止同人跨分区。'
             'Louvain 社区编号不稳定，因此以规模排序替代硬编码 675/10500。GP+期望改进保留高斯过程贝叶斯搜索原理，默认 5 初始点 + 10 次迭代、三折 AUC，未执行源 50 次迭代。'
             '基础表未给申请日期，因此匹配关系日志中该用户最后申请快照；无法核验多次申请与快照逐次时间对齐，不能声称完成严格线上时点验证。新增申请与历史图的匹配比例单独报告；未匹配按缺失处理，不暗示每个新客都有完整关系图。图表 AUC 来自两组不同申请样本，不能直接作单变量增益实验。节点标识、关系边、个人残差和评分均不公开。')
