"""Fold-safe fraud classifiers, insurance boosters, explanations and search methods."""
import importlib.metadata
import json
import os

import numpy as np
import pandas as pd
from scipy.stats import uniform, randint
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, AdaBoostClassifier, IsolationForest, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, adjusted_rand_score
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, train_test_split, cross_val_score, StratifiedKFold
from sklearn.naive_bayes import MultinomialNB
from sklearn.neighbors import KNeighborsClassifier, LocalOutlierFactor
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier, export_text
from threadpoolctl import threadpool_limits

from bda_labs.common import context
from bda_labs.advanced_common import read_csv, specification, complete, bars
from bda_labs.advanced_regression import classification_metrics, self_roundtrip


def preprocessing(frame,scale=False):
    cats=frame.select_dtypes(include='object').columns.tolist()
    nums=[c for c in frame if c not in cats]
    cat=make_pipeline(SimpleImputer(strategy='most_frequent'),OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=-1))
    num=make_pipeline(SimpleImputer(strategy='mean'),StandardScaler()) if scale else SimpleImputer(strategy='mean')
    return ColumnTransformer([('categorical',cat,cats),('numerical',num,nums)],verbose_feature_names_out=False)


def evaluate(name,model,train,test,ytrain,ytest,records):
    last_auc=None
    for split,X,y in [('train',train,ytrain),('test',test,ytest)]:
        probability=model.predict_proba(X)[:,1]
        result=classification_metrics(y,probability)
        records.append({'section':name,'item':split,**result})
        last_auc=result['AUC']
        for threshold in np.linspace(0,1,21):
            point=classification_metrics(y,probability,float(threshold))
            records.append({'section':name+'_curve_'+split,'item':round(float(threshold),2),
                            'TPR':point['recall'],'FPR':1-point['specificity'],
                            'precision':point['precision'],'recall':point['recall']})
    return last_auc


def fraud_models(ctx,lab,data):
    from xgboost import XGBClassifier
    from lightgbm import LGBMClassifier
    X=data.iloc[:,:4].copy();y=data['flag']
    a,b=train_test_split(np.arange(len(X)),test_size=.4,random_state=1234)
    train=X.iloc[a];test=X.iloc[b];yt=y.iloc[a];yv=y.iloc[b]
    records=[];aucs={};notes=[];params={}
    if lab=='M12':
        models=[
            ('decision_tree',DecisionTreeClassifier(random_state=42),{'criterion':['entropy','gini'],'max_depth':[2,3,4,5],
                'min_samples_split':[2,6,10],'min_samples_leaf':[2,6,10],'class_weight':[{0:1,1:1},{0:1,1:2},{0:1,1:3}]},'roc_auc'),
            ('random_forest',RandomForestClassifier(n_estimators=13,max_depth=8,random_state=42,n_jobs=1),
                {'max_features':[.5,.6,.7],'min_samples_split':[2,3,4]},'f1'),
            ('AdaBoost',AdaBoostClassifier(random_state=42),{'n_estimators':[15,20,25],'learning_rate':[.5,1,1.5]},'recall'),
            ('XGBoost',XGBClassifier(random_state=42,n_jobs=1,eval_metric='auc'),
                {'n_estimators':[50,100,150],'reg_lambda':[.01,.41,.81],'max_depth':[2,3,5],'learning_rate':[.5,1]},'recall'),
            ('LightGBM',LGBMClassifier(random_state=42,n_jobs=1,verbosity=-1,subsample=.5,subsample_freq=1,colsample_bytree=.5),
                {'num_leaves':randint(5,50),'max_depth':randint(2,5),'learning_rate':[.04,.08],
                 'n_estimators':randint(30,100),'min_child_samples':[10,20],'reg_alpha':uniform(1,5),
                 'reg_lambda':uniform(1,5),'cat_smooth':uniform(3,10)},'recall')]
        for name,model,grid,scoring in models:
            search=(RandomizedSearchCV(model,grid,scoring=scoring,cv=4,n_iter=24,random_state=12345,n_jobs=1,error_score='raise')
                    if name=='LightGBM' else GridSearchCV(model,grid,scoring=scoring,cv=4,n_jobs=1,error_score='raise'))
            search.fit(train,yt);params[name]=search.best_params_
            aucs[name]=evaluate(name,search,train,test,yt,yv,records)
            records.append({'section':'search','item':name,'CV_score':search.best_score_, 'objective':scoring,
                            'candidates':len(search.cv_results_['params']),'parameters':str(search.best_params_)})
            if name=='decision_tree':
                self_roundtrip(ctx,search.best_estimator_,test)
                # Rule extraction is based on this run's tree, not the stale
                # hard-coded if/then leaf counts in the source notebook.
                notes.append('```text\n'+export_text(search.best_estimator_,feature_names=list(X),max_depth=3)+'\n```')
            if hasattr(search.best_estimator_,'feature_importances_'):
                records += [{'section':name+'_importance','item':c,'value':float(v)} for c,v in zip(X,search.best_estimator_.feature_importances_)]
            if name=='LightGBM':self_roundtrip(ctx,search.best_estimator_,test)
        fit,val=train_test_split(a,test_size=.2,stratify=y.iloc[a],random_state=42)
        early=XGBClassifier(n_estimators=100,max_depth=3,learning_rate=.1,eval_metric='auc',early_stopping_rounds=3,random_state=42,n_jobs=1)
        early.fit(X.iloc[fit],y.iloc[fit],eval_set=[(X.iloc[val],y.iloc[val])],verbose=False)
        aucs['XGB_early_stop']=evaluate('XGB_early_stop',early,train,test,yt,yv,records)
        notes.append('保留五类分类器、四折搜索与训练内早停。默认树网格 min_samples 取 2/6/10、XGB reg_lambda 取 .01/.41/.81；LightGBM 随机搜索由 300 缩为 24 个候选，实际候选数随表发布，不声称跑完原耗时网格。早停不观察测试集。')
    else:
        models=[('KNN',make_pipeline(StandardScaler(),KNeighborsClassifier()),{'kneighborsclassifier__n_neighbors':list(range(1,19,2))}),
                ('MultinomialNB',MultinomialNB(),None),
                ('SVC',make_pipeline(StandardScaler(),SVC(probability=True,random_state=42)),
                 {'svc__kernel':['linear','rbf'],'svc__C':[.01,.31,.61,.91],'svc__gamma':[.01,.31,.61,.91]}),
                ('MLP',make_pipeline(StandardScaler(),MLPClassifier(max_iter=1000,random_state=42)),
                 {'mlpclassifier__hidden_layer_sizes':[(10,),(15,),(5,5)],'mlpclassifier__activation':['logistic','relu'],
                  'mlpclassifier__alpha':uniform(.01,10)})]
        for name,model,grid in models:
            if grid is None:search=model
            elif name=='MLP':search=RandomizedSearchCV(model,grid,n_iter=20,cv=4,scoring='roc_auc',random_state=42,n_jobs=1,error_score='raise')
            else:search=GridSearchCV(model,grid,cv=4,scoring='roc_auc',n_jobs=1,error_score='raise')
            search.fit(train,yt);aucs[name]=evaluate(name,search,train,test,yt,yv,records)
            if grid is not None:records.append({'section':'search','item':name,'CV_AUC':search.best_score_,'parameters':str(search.best_params_)})
        notes.append('保留 KNN、多项式朴素贝叶斯、线性/RBF SVC 和 MLP。所有缩放放入搜索 Pipeline，每折只拟合折内训练样本；朴素贝叶斯按教材使用原非负特征。SVC 的 C/gamma 网格各取 .01/.31/.61/.91；MLP 保留 20 次随机搜索。')
    bars(ctx,list(aucs),list(aucs.values()),'申请反欺诈：同一留出集 AUC','AUC')
    return records,{'train_rows':len(a),'test_rows':len(b),'split_seed':1234},'\n\n'.join(notes)


def insurance_data(ctx,lab):
    spec=specification(lab);raw=read_csv(ctx,spec['inputs'][0])
    if lab!='M27':raw=raw.dropna().reset_index(drop=True)
    y=raw.pop('resp_flag');a,b=train_test_split(np.arange(len(raw)),test_size=.3,stratify=y,random_state=42)
    return raw,y,a,b


def booster_examples(ctx,lab):
    import xgboost as xgb
    import lightgbm as lgb
    raw,y,a,b=insurance_data(ctx,lab)
    records=[];aucs={}
    catcols=raw.select_dtypes(include='object').columns.tolist()
    pre=preprocessing(raw);pre.fit(raw.iloc[a])
    names=list(pre.get_feature_names_out())
    train=pd.DataFrame(pre.transform(raw.iloc[a]),columns=names);test=pd.DataFrame(pre.transform(raw.iloc[b]),columns=names)
    yt=y.iloc[a].to_numpy();yv=y.iloc[b].to_numpy()
    fit,val=train_test_split(np.arange(len(train)),test_size=.3,stratify=yt,random_state=42)
    # Early-stopping preprocessing is fitted only to its internal training part.
    inner_pre=preprocessing(raw).fit(raw.iloc[a[fit]])
    inner_train=pd.DataFrame(inner_pre.transform(raw.iloc[a[fit]]),columns=names)
    inner_val=pd.DataFrame(inner_pre.transform(raw.iloc[a[val]]),columns=names)
    if lab=='M14':
        sklearn_model=xgb.XGBClassifier(random_state=42,n_jobs=1).fit(train,yt)
        aucs['sklearn']=evaluate('sklearn',sklearn_model,train,test,yt,yv,records)
        dtrain=xgb.DMatrix(train,label=yt);dtest=xgb.DMatrix(test)
        params={'objective':'binary:logistic','eval_metric':'auc','seed':42,'nthread':1}
        variants=[('native_default',{},10),('native_parameters',{'max_depth':5,'eta':.4},15),
                  ('monotone',{'max_depth':5,'eta':.4,'tree_method':'exact',
                    'monotone_constraints':tuple([0,1,-1]+[0]*(len(names)-3))},10),
                  ('interaction',{'max_depth':5,'eta':.4,'interaction_constraints':[[0,2],[1,3,4],[5,6]]},10),
                  ('parallel_forest',{'colsample_bynode':.8,'eta':1.,'num_parallel_tree':100,'subsample':.8},1)]
        for name,extra,rounds in variants:
            if 'interaction_constraints' in extra:
                extra={**extra,'interaction_constraints':[[names[i] for i in group] for group in extra['interaction_constraints']]}
            model=xgb.train({**params,**extra},dtrain,num_boost_round=rounds)
            result=classification_metrics(yv,model.predict(dtest));records.append({'section':name,'item':'test',**result});aucs[name]=result['AUC']
        early=xgb.train({**params,'max_depth':5,'eta':.4},xgb.DMatrix(inner_train,label=yt[fit]),num_boost_round=15,
                        evals=[(xgb.DMatrix(inner_val,label=yt[val]),'validation')],early_stopping_rounds=3,verbose_eval=False)
        inner_test=pd.DataFrame(inner_pre.transform(raw.iloc[b]),columns=names)
        p=early.predict(xgb.DMatrix(inner_test),iteration_range=(0,early.best_iteration+1))
        result=classification_metrics(yv,p);records.append({'section':'early_stop','item':'test',**result});aucs['early_stop']=result['AUC']
        details={'best_iteration':int(early.best_iteration),'xgboost_version':xgb.__version__}
        notes='原生接口显式指定 binary:logistic，修正源代码空参数默认回归目标被当分类概率的问题。保留 sklearn/原生 API、参数、早停、单调/交互约束和单轮并行森林。约束是教学演示，不代表已确认的业务因果方向；单调向量按实际列数构造。'
    else:
        hist=HistGradientBoostingClassifier(random_state=42).fit(train,yt);aucs['HistGB']=evaluate('HistGB',hist,train,test,yt,yv,records)
        sklearn_model=lgb.LGBMClassifier(random_state=42,n_jobs=1,verbosity=-1).fit(train,yt)
        aucs['sklearn']=evaluate('sklearn',sklearn_model,train,test,yt,yv,records)
        params={'objective':'binary','metric':'auc','seed':42,'num_threads':1,'verbosity':-1,'deterministic':True,'force_col_wise':True}
        dataset=lgb.Dataset(train,label=yt,free_raw_data=False)
        model=lgb.train(params,dataset,num_boost_round=100)
        pred=model.predict(test);result=classification_metrics(yv,pred);records.append({'section':'native','item':'test',**result});aucs['native']=result['AUC']
        binary=ctx.output/'train_private.bin'
        if binary.exists():binary.unlink()
        previous_directory=os.getcwd()
        try:
            os.chdir(ctx.output)
            dataset.save_binary(binary.name)
            restored=lgb.train(params,lgb.Dataset(binary.name),num_boost_round=100)
        finally:os.chdir(previous_directory)
        if not np.allclose(pred,restored.predict(test),atol=1e-12):raise AssertionError('LightGBM binary round trip differs')
        inner=lgb.Dataset(inner_train,label=yt[fit],categorical_feature=[c for c in ['GEND','AART'] if c in names],free_raw_data=False)
        valid=lgb.Dataset(inner_val,label=yt[val],reference=inner)
        early=lgb.train({**params,'num_leaves':31},inner,num_boost_round=200,valid_sets=[valid],callbacks=[lgb.early_stopping(5,verbose=False)])
        inner_test=pd.DataFrame(inner_pre.transform(raw.iloc[b]),columns=names)
        result=classification_metrics(yv,early.predict(inner_test));records.append({'section':'early_stop','item':'test',**result});aucs['early_stop']=result['AUC']
        modelpath=ctx.output/'lightgbm_private.txt'
        try:
            os.chdir(ctx.output)
            early.save_model(modelpath.name)
            restored_model=lgb.Booster(model_file=modelpath.name)
        finally:os.chdir(previous_directory)
        if not np.allclose(early.predict(inner_test),restored_model.predict(inner_test)):raise AssertionError('LightGBM save/load differs')
        # New datasets avoid inheriting categorical metadata for a numeric
        # monotone demo (constraints on categorical features are invalid).
        monotone=[1,0,-1]+[0]*(len(names)-3)
        for name,extra in [('monotone',{'monotone_constraints':monotone,'monotone_constraints_method':'advanced'}),
                           ('interaction',{'interaction_constraints':[[1,3,4],[5,6]]})]:
            model=lgb.train({**params,**extra},lgb.Dataset(train,label=yt),num_boost_round=100)
            result=classification_metrics(yv,model.predict(test));records.append({'section':name,'item':'test',**result});aucs[name]=result['AUC']
        records += [{'section':'split_importance','item':c,'value':int(v)} for c,v in zip(names,early.feature_importance())]
        details={'best_iteration':int(early.best_iteration),'lightgbm_version':lgb.__version__,'binary_roundtrip_checked':True}
        notes='保留 HistGradientBoosting、sklearn/原生 LightGBM、二进制数据集回读、类别声明、早停、模型文本回读及单调/交互约束。原生目标显式 binary；类别特征与单调数值演示采用各自数据集。预处理只拟合对应训练段。'
    bars(ctx,list(aucs),list(aucs.values()),'保险响应：提升树方法留出 AUC','AUC')
    details.update({'train_rows':len(a),'test_rows':len(b),'encoded_features':names,'categorical_features':catcols})
    return records,details,notes


def explanation(ctx):
    import xgboost as xgb
    import lightgbm as lgb
    from bda_labs.advanced_explanation import marginal_response
    from sklearn.datasets import load_iris
    import statsmodels.api as sm
    raw,y,a,b=insurance_data(ctx,'M16');pre=preprocessing(raw).fit(raw.iloc[a]);names=list(pre.get_feature_names_out())
    train=pd.DataFrame(pre.transform(raw.iloc[a]),columns=names);test=pd.DataFrame(pre.transform(raw.iloc[b]),columns=names)
    yt=y.iloc[a].to_numpy();yv=y.iloc[b].to_numpy();records=[]
    # Constant/collinear columns are removed before an unpenalized Logit.
    standardized=StandardScaler().fit_transform(train)
    from scipy.linalg import qr
    _,r,pivot=qr(standardized,mode='economic',pivoting=True)
    rank=np.linalg.matrix_rank(r);selected=sorted(pivot[:rank])
    logit=sm.Logit(yt,sm.add_constant(standardized[:,selected])).fit(disp=False,maxiter=200)
    if not logit.mle_retvals.get('converged',True):raise RuntimeError('Explanation Logit did not converge')
    records += [{'section':'logit_coefficient','item':names[j],'value':float(c)} for j,c in zip(selected,logit.params[1:])]
    tree=DecisionTreeClassifier(random_state=42).fit(train,yt)
    forest=RandomForestClassifier(oob_score=True,random_state=42,n_jobs=1).fit(train,yt)
    small=RandomForestClassifier(n_estimators=5,random_state=42,n_jobs=1).fit(train,yt)
    model=xgb.train({'objective':'binary:logistic','seed':42,'nthread':1},xgb.DMatrix(train,label=yt),num_boost_round=10)
    light=lgb.train({'objective':'binary','num_threads':1,'verbosity':-1,'seed':42},lgb.Dataset(train,label=yt),num_boost_round=100)
    for name,values in [('tree',tree.feature_importances_),('forest',forest.feature_importances_),
                        ('XGB_weight',[model.get_score(importance_type='weight').get(c,0) for c in names]),('LGB_split',light.feature_importance())]:
        records += [{'section':name+'_importance','item':c,'value':float(v)} for c,v in zip(names,values)]
    sample=test.iloc[:min(1000,len(test))]
    contributions=model.predict(xgb.DMatrix(sample),pred_contribs=True)
    margin=model.predict(xgb.DMatrix(sample),output_margin=True)
    if not np.allclose(contributions.sum(axis=1),margin,atol=1e-5):raise AssertionError('TreeSHAP additivity failed')
    mean_abs=np.abs(contributions[:,:-1]).mean(axis=0)
    records += [{'section':'TreeSHAP_mean_absolute','item':c,'value':float(v)} for c,v in zip(names,mean_abs)]
    for col in ['GEND','BANK','age','meda']:
        if col not in names:raise ValueError('Missing source PDP feature '+col)
        background=train.sample(min(1000,len(train)),random_state=42)
        unique=np.sort(background[col].unique())
        grid=unique if len(unique)<=20 else np.linspace(*background[col].quantile([.05,.95]).to_numpy(),20)
        response=marginal_response(forest,background,col,grid)
        records += [{'section':'PDP_'+col,'item':float(g),'value':float(p)} for g,p in zip(grid,response)]
    example=test.iloc[[0]]
    lengths=[int(tree.decision_path(example).sum())]
    lengths += [int(t.decision_path(example.to_numpy()).sum()) for t in small.estimators_]
    records += [{'section':'decision_path','item':i,'value':n} for i,n in enumerate(lengths)]
    top=np.argsort(tree.feature_importances_)[-5:];simple=DecisionTreeClassifier(max_depth=5,random_state=42).fit(train.iloc[:,top],yt)
    rules=export_text(simple,feature_names=[names[i] for i in top])
    iris=load_iris();iris_tree=DecisionTreeClassifier(random_state=42).fit(iris.data,iris.target)
    records.append({'section':'iris_example','item':'tree_nodes','value':int(iris_tree.tree_.node_count)})
    # Reconstruct the source's random counterfactual search without dice_ml,
    # which would pull incompatible pandas dependencies. Respect empirical
    # categorical domains and numeric ranges; report no personal row values.
    rng=np.random.default_rng(42);candidates=train.sample(2000,replace=True,random_state=42).reset_index(drop=True)
    original=example.to_numpy()[0];target=1-int(tree.predict(example)[0])
    vary=rng.random(candidates.shape)<.25
    proposals=pd.DataFrame(np.where(vary,candidates.to_numpy(),original),columns=names)
    opposite=tree.predict(proposals)==target;feasible=proposals.loc[opposite]
    count=min(4,len(feasible))
    if count==0:raise RuntimeError('Random counterfactual search found no class flip')
    records.append({'section':'counterfactual','item':'random_search','found':count,'candidates':len(candidates)})
    order=np.argsort(mean_abs)[-10:][::-1]
    bars(ctx,[names[i] for i in order],mean_abs[order],'保险响应：TreeSHAP 平均绝对贡献','raw log-odds contribution')
    return records,{'train_rows':len(a),'test_rows':len(b),'TreeSHAP_additivity_checked':True,
                    'counterfactuals_found':count,'PDP_features':['GEND','BANK','age','meda'],
                    'forest_oob_accuracy':float(forest.oob_score_)}, (
                    '用 XGBoost 内置精确 TreeSHAP 替代额外 shap 包，核验贡献和等于模型 raw margin；只发布聚合贡献与偏依赖，不公开单个客户路径/蜂群点。'
                    '固定 sklearn 版本在双取值二分类偏依赖网格有形状兼容问题，按替换单特征再平均正类概率的定义显式重建。偏依赖组合可能偏离相关变量的真实联合分布，不作因果解释。'
                    '随机反事实采用训练集经验取值重组与模型翻转检验，重建 dice 随机搜索的教学意图；未加入现实可行动约束，不能作为客户改进建议。'
                    '\n\n简化树规则：\n\n```text\n'+rules+'\n```')


def pipeline_lab(ctx):
    raw,y,a,b=insurance_data(ctx,'M27');records=[];aucs={}
    prep=preprocessing(raw,scale=True)
    for name,estimator,grid in [('logistic',LogisticRegression(max_iter=3000),{'model__C':np.arange(1,2,.1),'model__class_weight':[None,'balanced'],'pre__numerical__simpleimputer__strategy':['mean','median']}),
                                ('tree',DecisionTreeClassifier(random_state=42),{'model__max_depth':[2,4,6],'model__min_samples_leaf':[10,30]})]:
        pipeline=Pipeline([('pre',clone(prep)),('model',estimator)])
        search=GridSearchCV(pipeline,grid,cv=3,n_jobs=1,scoring='accuracy',error_score='raise').fit(raw.iloc[a],y.iloc[a])
        aucs[name]=evaluate(name,search,raw.iloc[a],raw.iloc[b],y.iloc[a],y.iloc[b],records)
        records.append({'section':'search','item':name,'parameters':str(search.best_params_),'CV_accuracy':search.best_score_})
        new=read_csv(ctx,specification('M27')['inputs'][1])
        probability=search.predict_proba(new)[:,1]
        records.append({'section':'new_users','item':name,'rows':len(new),'mean_probability':float(probability.mean())})
        self_roundtrip(ctx,search,new)
    bars(ctx,list(aucs),list(aucs.values()),'保险 Pipeline：留出集 AUC','AUC')
    return records,{'train_rows':len(a),'test_rows':len(b),'self_created_pipeline_roundtrip':True},'完整 Pipeline 在 CV 折内拟合缺失填补、类别编码和标准化；支持新类别。完成源末尾的树模型调参练习。新用户仅预测不计算无标签评估；只回读本次生成的完整 Pipeline，不读取教材 joblib。'


def search_lab(ctx):
    from xgboost import XGBClassifier
    from lightgbm import LGBMClassifier
    from sklearn.experimental import enable_halving_search_cv  # noqa:F401
    from sklearn.model_selection import HalvingGridSearchCV
    import optuna
    raw,y,a,b=insurance_data(ctx,'M26');records=[];aucs={}
    pipeline=Pipeline([('pre',preprocessing(raw)),('model',XGBClassifier(random_state=42,n_jobs=1))])
    grid={'model__n_estimators':[100,120,140],'model__max_depth':[3,5],'model__subsample':[.8,.9],'model__colsample_bytree':[.8,.9]}
    searches={'grid':GridSearchCV(pipeline,grid,cv=3,n_jobs=1,scoring='roc_auc',error_score='raise'),
              'halving':HalvingGridSearchCV(pipeline,grid,factor=3,cv=3,n_jobs=1,scoring='roc_auc',random_state=42,error_score='raise'),
              'random':RandomizedSearchCV(pipeline,{'model__n_estimators':randint(100,150),'model__max_depth':randint(3,6),
                       'model__subsample':uniform(.5,.5),'model__colsample_bytree':uniform(.5,.5)},n_iter=12,cv=3,n_jobs=1,
                       scoring='roc_auc',random_state=42,error_score='raise')}
    for name,search in searches.items():
        search.fit(raw.iloc[a],y.iloc[a]);aucs[name]=evaluate(name,search,raw.iloc[a],raw.iloc[b],y.iloc[a],y.iloc[b],records)
        records.append({'section':'search','item':name,'CV_AUC':search.best_score_,'parameters':str(search.best_params_),
                        'candidate_evaluations':len(search.cv_results_['params'])})
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    def objective(trial):
        params={'reg_lambda':trial.suggest_float('reg_lambda',.01,10),'num_leaves':trial.suggest_int('num_leaves',2,256),
                'colsample_bytree':trial.suggest_float('colsample_bytree',.4,1),'subsample':trial.suggest_float('subsample',.4,1)}
        model=Pipeline([('pre',preprocessing(raw)),('model',LGBMClassifier(**params,objective='binary',subsample_freq=1,
                        random_state=42,n_jobs=1,verbosity=-1))])
        return float(cross_val_score(model,raw.iloc[a],y.iloc[a],cv=3,scoring='roc_auc',n_jobs=1,error_score='raise').mean())
    study=optuna.create_study(sampler=optuna.samplers.TPESampler(seed=42),direction='maximize');study.optimize(objective,n_trials=12,n_jobs=1)
    best=Pipeline([('pre',preprocessing(raw)),('model',LGBMClassifier(**study.best_params,objective='binary',subsample_freq=1,random_state=42,n_jobs=1,verbosity=-1))]).fit(raw.iloc[a],y.iloc[a])
    aucs['TPE']=evaluate('TPE',best,raw.iloc[a],raw.iloc[b],y.iloc[a],y.iloc[b],records)
    records += [{'section':'TPE_trials','item':t.number,'CV_AUC':t.value,'parameters':str(t.params)} for t in study.trials]
    bars(ctx,list(aucs),list(aucs.values()),'调参方式：独立测试 AUC','AUC')
    return records,{'train_rows':len(a),'test_rows':len(b),'TPE_trials':12,'random_trials':12,'seed':42},'保留网格、逐次减半、随机和 TPE 搜索。默认减半在与网格相同的 24 组候选上比较，随机/TPE 各 12 次，以控制教学运行成本；不声称完成源 3750 组减半和 100 次 TPE。修复原 TPE 反复用测试集作为优化目标的问题，所有目标来自训练三折 AUC，预处理随折重拟合。'


def anomaly_lab(ctx):
    raw=read_csv(ctx,specification('M17')['inputs'][0]);X=raw.loc[:,'V1':'V28'];y=raw['Class']
    # Fixed bounded training size makes the 500-neighbour LOF feasible on laptops.
    # Evaluation retains the chronological final 20% of the supplied dataset.
    train_end=int(.6*len(X));test_start=int(.8*len(X))
    idx=np.random.default_rng(42).choice(train_end,size=min(5000,train_end),replace=False)
    train=X.iloc[np.sort(idx)];validation=X.iloc[train_end:test_start];test=X.iloc[test_start:]
    yval=y.iloc[train_end:test_start];ytest=y.iloc[test_start:];records=[];aucs={}
    for col,value in X.kurtosis().items():records.append({'section':'kurtosis','item':col,'value':float(value)})
    best=None;best_ap=-np.inf
    from sklearn.metrics import average_precision_score
    for n,features in [(80,.5),(100,.6),(120,.7)]:
        model=IsolationForest(n_estimators=n,max_features=features,max_samples=.6,contamination=.02,random_state=42,n_jobs=1).fit(train)
        ap=average_precision_score(yval,-model.score_samples(validation))
        records.append({'section':'label_guided_validation','item':n,'feature_fraction':features,'AP':ap})
        if ap>best_ap:best=model;best_ap=ap
    for name,model in [('IsolationForest',best),('LOF',LocalOutlierFactor(n_neighbors=500,contamination=.02,novelty=True,n_jobs=1).fit(train))]:
        anomaly=-model.score_samples(test);pred=(model.predict(test)==-1).astype(int)
        from sklearn.metrics import confusion_matrix
        tn,fp,fn,tp=confusion_matrix(ytest,pred,labels=[0,1]).ravel()
        auc=float(roc_auc_score(ytest,anomaly));aucs[name]=auc
        records.append({'section':'chronological_holdout','item':name,'AUC':auc,'AP':float(average_precision_score(ytest,anomaly)),
                        'ARI':float(adjusted_rand_score(ytest,pred)),'TN':int(tn),'FP':int(fp),'FN':int(fn),'TP':int(tp)})
    bars(ctx,list(aucs),list(aucs.values()),'异常识别：时间留出集 AUC','AUC')
    return records,{'raw_rows':len(raw),'fit_sample_rows':len(train),'validation_rows':len(validation),'test_rows':len(test),
                    'seed':42,'LOF_neighbors':500,'contamination':.02},'模型拟合不使用标签；孤立森林参数用独立验证段标签选取，故明确称为标签辅助选择。默认从前 60% 时段无标签抽 5000 条拟合，保留 LOF 500 邻居，在后 20% 全量评估；这是可复现教学子样本，不是源全样本运行。修复 novelty=True 的 LOF 在其拟合样本上 predict 的误用。'


def main(lab,argv=None):
    ctx=context(lab,argv)
    with threadpool_limits(limits=1):
        if lab in {'M12','M13'}:result=fraud_models(ctx,lab,read_csv(ctx,specification(lab)['inputs'][0]))
        elif lab in {'M14','M15'}:result=booster_examples(ctx,lab)
        elif lab=='M16':result=explanation(ctx)
        elif lab=='M17':result=anomaly_lab(ctx)
        elif lab=='M26':result=search_lab(ctx)
        else:result=pipeline_lab(ctx)
    records,details,notes=result
    complete(ctx,lab,records,details,notes=notes)
