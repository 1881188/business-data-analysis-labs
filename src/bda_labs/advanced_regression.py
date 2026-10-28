"""Customer expenditure OLS/regularization and response/marketing logistic models."""
import json

import joblib
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import OLSInfluence, variance_inflation_factor
from sklearn.feature_selection import RFECV
from sklearn.linear_model import Ridge, Lasso, ElasticNet, LogisticRegression
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn import metrics
from threadpoolctl import threadpool_limits

from bda_labs.common import context
from bda_labs.advanced_common import read_csv, specification, complete, bars


def classification_metrics(y, probability, threshold=.5):
    y=np.asarray(y);probability=np.asarray(probability)
    if set(np.unique(y))!={0,1}:raise ValueError('Binary labels 0/1 required for evaluation')
    if not np.isfinite(probability).all() or (probability<0).any() or (probability>1).any():
        raise ValueError('Invalid binary probability')
    pred=(probability>=threshold).astype(int)
    tn,fp,fn,tp=metrics.confusion_matrix(y,pred,labels=[0,1]).ravel()
    fpr,tpr,_=metrics.roc_curve(y,probability)
    return {'AUC':float(metrics.roc_auc_score(y,probability)), 'AP':float(metrics.average_precision_score(y,probability)),
            'KS':float(max(tpr-fpr)), 'precision':float(metrics.precision_score(y,pred,zero_division=0)),
            'recall':float(metrics.recall_score(y,pred,zero_division=0)),
            'specificity':float(tn/(tn+fp)), 'F1':float(metrics.f1_score(y,pred,zero_division=0)),
            'accuracy':float(metrics.accuracy_score(y,pred)), 'TN':int(tn),'FP':int(fp),'FN':int(fn),'TP':int(tp)}


def self_roundtrip(ctx, model, X):
    path=ctx.output/'model_private.joblib'
    before=model.predict(X)
    joblib.dump(model,path)
    restored=joblib.load(path)  # Only our just-written model, never supplied pickles.
    if not np.allclose(before,restored.predict(X),atol=1e-12):
        raise AssertionError('Self-created model round trip failed')


def forward_aic(frame, response, columns):
    selected=[];remaining=sorted(columns);score=smf.ols(response+' ~ 1',frame).fit().aic
    while remaining:
        choices=[(smf.ols(response+' ~ '+' + '.join(selected+[c]),frame).fit().aic,c) for c in remaining]
        best,candidate=min(choices)
        if best>=score-1e-10:break
        selected.append(candidate);remaining.remove(candidate);score=best
    return smf.ols(response+' ~ '+(' + '.join(selected) or '1'),frame).fit()


def run_expenditure(ctx, data, oos):
    train=data[data['avg_exp'].notna()].copy()
    for frame in [train,oos]:
        for column in ['Income','dist_home_val','dist_avg_income']:
            if (frame[column]<=0).any():raise ValueError('Log transform requires positive values')
            frame[column+'_ln']=np.log(frame[column])
        frame['high_avg_ratio']=frame['high_avg']/frame['dist_avg_income']
    models={
        'simple':smf.ols('avg_exp ~ Income',train).fit(),
        'multiple':smf.ols('avg_exp ~ Income + dist_home_val + dist_avg_income',train).fit(),
        'log_response':smf.ols('avg_exp_ln ~ Income',train).fit(),
        'log_both':smf.ols('avg_exp_ln ~ Income_ln',train).fit(),
        'forward_raw':forward_aic(train,'avg_exp',['Income','Age','dist_home_val','dist_avg_income'])}
    residual=models['log_both'].resid
    standardized=(residual-residual.mean())/residual.std()
    cleaned=train[abs(standardized)<=2].copy()
    models['log_cleaned']=smf.ols('avg_exp_ln ~ Income_ln',cleaned).fit()
    models['log_multiple']=smf.ols('avg_exp_ln ~ Age + Income_ln + dist_home_val_ln + dist_avg_income_ln',cleaned).fit()
    models['forward_ratio']=forward_aic(cleaned,'avg_exp_ln',['Age','high_avg_ratio','dist_home_val_ln','dist_avg_income_ln'])
    models['categorical']=smf.ols('avg_exp_ln ~ dist_avg_income_ln + dist_home_val_ln + C(gender) + C(Ownrent) + C(Selfempl) + C(edu_class)',cleaned).fit()
    models['interaction']=smf.ols('avg_exp_ln ~ dist_avg_income_ln + dist_home_val_ln + C(Selfempl) + C(gender) * C(edu_class)',cleaned).fit()
    oos['edu_class']=oos['edu_class'].replace({0:1})
    pred=np.exp(models['interaction'].predict(oos))
    if not np.isfinite(pred).all():raise AssertionError('Nonfinite expenditure forecast')
    rows=[]
    for name,model in models.items():
        rows.append({'section':name,'item':'fit','R2':model.rsquared,'AIC':model.aic,'rows':int(model.nobs)})
        rows += [{'section':name,'item':col,'coefficient':value,'pvalue':model.pvalues[col]} for col,value in model.params.items()]
    influence=OLSInfluence(models['log_both'])
    rows.append({'section':'diagnostics','item':'Cook_max','value':float(influence.cooks_distance[0].max())})
    rows.append({'section':'diagnostics','item':'normality_p','value':float(stats.normaltest(residual).pvalue)})
    for cols,name in [(['Age','Income_ln','dist_home_val_ln','dist_avg_income_ln'],'before_ratio'),
                      (['Age','high_avg_ratio','dist_home_val_ln','dist_avg_income_ln'],'after_ratio')]:
        matrix=sm.add_constant(cleaned[cols]).to_numpy()
        rows += [{'section':'VIF_'+name,'item':col,'value':variance_inflation_factor(matrix,i+1)} for i,col in enumerate(cols)]
    X=cleaned[['Age','Income','dist_home_val','dist_avg_income']];y=cleaned['avg_exp_ln']
    # Preserve teaching coefficient paths. Generalization estimates below use an
    # unfiltered raw holdout, never data selected using its residuals.
    z=StandardScaler().fit_transform(X)
    for family,klass,alphas in [('ridge',Ridge,np.logspace(-2,3,100)),('lasso',Lasso,np.logspace(-3,0,100))]:
        for alpha in alphas:
            model=klass(alpha=alpha,max_iter=10000).fit(z,y)
            rows += [{'section':family+'_path','item':col,'alpha':alpha,'value':value} for col,value in zip(X.columns,model.coef_)]
    a,b=train_test_split(np.arange(len(train)),test_size=.3,random_state=42)
    features=['Age','Income','dist_home_val','dist_avg_income']
    fits={}
    for name,estimator,grid in [('ridge',Ridge(),{'ridge__alpha':np.logspace(-2,3,100)}),
                                ('lasso',Lasso(max_iter=10000),{'lasso__alpha':np.logspace(-3,0,100)}),
                                ('elastic',ElasticNet(max_iter=10000),{'elasticnet__alpha':np.logspace(-3,1,20),'elasticnet__l1_ratio':[.01,.1,.2,.4,.8,.95,.99,1]})]:
        search=GridSearchCV(make_pipeline(StandardScaler(),estimator),grid,cv=4,scoring='neg_mean_squared_error',n_jobs=1)
        search.fit(train.iloc[a][features],train.iloc[a]['avg_exp_ln'])
        forecast=search.predict(train.iloc[b][features])
        mse=float(metrics.mean_squared_error(train.iloc[b]['avg_exp_ln'],forecast));fits[name]=mse
        rows.append({'section':'holdout_log_scale','item':name,'value':mse,'parameters':json.dumps(search.best_params_)})
    # statsmodels L2/L1 regularization examples use a different objective scaling.
    for l1 in [0,1]:
        model=smf.ols('avg_exp ~ Age + Income + dist_home_val + dist_avg_income',cleaned).fit_regularized(alpha=1,L1_wt=l1)
        rows += [{'section':f'sm_regularized_L1_{l1}','item':col,'value':value} for col,value in zip(model.model.exog_names,model.params)]
    bars(ctx,list(fits),list(fits.values()),'正则化模型：独立留出集对数金额 MSE','MSE')
    return rows,{'training_rows':len(train),'descriptive_outliers_removed':int((abs(standardized)>2).sum()),
                 'scoring_rows':len(oos),'oos_predictions_aggregate':{'mean':float(pred.mean()),'min':float(pred.min()),'max':float(pred.max())},
                 'holdout_rows':len(b),'split_seed':42}, ('OLS 诊断、异常值删除及 AIC 选择仅作教材解释性分析；正则模型另在未按残差过滤的样本上留出测试集，预处理在交叉验证折内拟合。'
                 '不同响应尺度的 R² 不用于直接选胜者。exp(对数预测) 是条件中位数尺度的回变换，未做均值偏差校正。edu_class=0→1 保留教材明确的业务概化；不发布个人预测。')


def run_response(ctx,data,oos):
    continuous=['Age','Income','dist_home_val','dist_avg_income','high_avg']
    discrete=['gender','Ownrent','Selfempl','edu_class']
    columns=continuous+discrete
    train=data.sample(frac=.7,random_state=1234).copy();test=data.drop(train.index).copy()
    baseline=smf.logit('Acc ~ Income',train).fit(disp=False)
    rows=[];comparison={}
    p=baseline.predict(test)
    for threshold in np.arange(.1,1,.2):
        rows.append({'section':'single_income_threshold','item':round(float(threshold),2),**classification_metrics(test['Acc'],p,threshold)})
    comparison['Income']=classification_metrics(test['Acc'],p)['AUC']
    selector=RFECV(make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000)),cv=3,scoring='accuracy',
                   importance_getter='named_steps.logisticregression.coef_',n_jobs=1)
    # Selector and scaling are both fitted anew inside each outer tuning fold.
    pipeline=make_pipeline(selector,StandardScaler(),LogisticRegression(max_iter=3000))
    search=GridSearchCV(pipeline,{'logisticregression__C':np.logspace(-4,4,10)},cv=4,scoring='accuracy',n_jobs=1)
    search.fit(train[columns],train['Acc'])
    for name,frame in [('train',train),('test',test)]:
        result=classification_metrics(frame['Acc'],search.predict_proba(frame[columns])[:,1])
        rows.append({'section':'selected_logistic','item':name,**result})
        if name=='test':comparison['RFECV+CV']=result['AUC']
    keep=search.best_estimator_.named_steps['rfecv'].support_
    rows += [{'section':'feature_selection','item':c,'value':bool(k)} for c,k in zip(columns,keep)]
    oos=oos.copy();oos['edu_class']=oos['edu_class'].replace({0:1})
    pred=search.predict_proba(oos[columns])[:,1]
    self_roundtrip(ctx,search,oos[columns])
    bars(ctx,list(comparison),list(comparison.values()),'信用卡响应：留出集 AUC','AUC')
    return rows,{'train_rows':len(train),'test_rows':len(test),'scoring_rows':len(oos),
                 'selected_features':np.array(columns)[keep].tolist(),'C':float(search.best_params_['logisticregression__C']),
                 'new_customer_mean_probability':float(pred.mean()),'self_created_model_roundtrip':True}, (
                 '保留原 sample(frac=0.7, random_state=1234) 划分。RFECV、缩放与正则搜索在训练范围内嵌套；修复原阈值表将 precision/recall/specificity 名称混淆的问题。类别编码按源示例作为数值输入；edu_class 概化赋值生效。只回读本次新训练的私有模型。')


def run_marketing(ctx,data,oos):
    train=data.sample(frac=.7,random_state=1234).copy();test=data.drop(train.index).copy()
    columns=['avg_balance','std_balance','cv_balance','sum_expenditure','sum_income','in_out_ratio']
    # A single train-derived cleaning rule is reused for every partition.
    bounds={c:train[c].fillna(0).quantile([.01,.99]).to_numpy() for c in ['std_balance','cv_balance','sum_expenditure']}
    for frame in [train,test,oos]:
        for col in columns:
            if col in frame:frame[col]=frame[col].fillna(0)
        for col,(lo,hi) in bounds.items():
            if col in frame:frame[col]=frame[col].clip(lo,hi)
    model=smf.logit('y ~ avg_balance + cv_balance + sum_expenditure + C(card)',train).fit(disp=False)
    rows=[{'section':'model','item':c,'coefficient':v,'pvalue':model.pvalues[c]} for c,v in model.params.items()]
    for name,frame in [('train',train),('test',test)]:
        rows.append({'section':'evaluation','item':name,**classification_metrics(frame['y'],model.predict(frame))})
    pred=model.predict(oos)
    if not np.isfinite(pred).all():raise AssertionError('Marketing score is not finite')
    bars(ctx,['train','test'],[r['AUC'] for r in rows if r['section']=='evaluation'],'贷款精准营销：ROC AUC','AUC')
    return rows,{'train_rows':len(train),'test_rows':len(test),'scoring_rows':len(oos),
                 'scoring_mean_probability':float(pred.mean()),'train_only_cap_bounds':{c:v.tolist() for c,v in bounds.items()}}, (
                 '保留教材逻辑回归公式。原脚本对训练与预测数据使用不同列、不同分位数且未执行预测；此版统一使用训练集的盖帽规则，再生成本地预测。新增客群没有标签，只报告评分分布，不伪造 AUC。')


def main(lab,argv=None):
    ctx=context(lab,argv);spec=specification(lab)
    data=read_csv(ctx,spec['inputs'][0],skipinitialspace=True)
    oos=read_csv(ctx,spec['inputs'][1],skipinitialspace=True)
    with threadpool_limits(limits=1):
        rows,details,notes={'M01':run_expenditure,'M02':run_response,'F02':run_marketing}[lab](ctx,data,oos)
    complete(ctx,lab,rows,details,notes=notes)
