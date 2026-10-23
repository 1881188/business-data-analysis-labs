"""S10: observed-response regression, with a separately audited legacy imputation branch."""
import re
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold
from statsmodels.stats.outliers_influence import variance_inflation_factor
from .anova_expenses import fit_estimable,legacy_reference_check
from .common import context,finish,plotting,save_table
from .notebook_reference import read_notebook,cached_text,write_coverage
from .statistical_reference import check_printed

NUMERIC=['gender','Age','Income','Ownrent','Selfempl','dist_home_val','dist_avg_income']
NAMES=['raw_full','raw_reduced','log_reduced','log_age_squared','log_age_interaction']
EDUCATION=['中学','大学','小学及以下','研究生']


def prepare(raw,legacy=False):
    if raw.id.isna().any() or raw.id.duplicated().any():raise ValueError('Expected distinct nonmissing record IDs')
    frame=raw.drop(columns=['id','Acc','edad2']).drop_duplicates().copy()
    audit={'source_rows':len(raw),'duplicate_feature_rows':len(raw)-len(frame),'missing_response':int(frame.avg_exp.isna().sum()),
           'missing_education':int(frame.edu_class.isna().sum()),'invalid_age':int((~frame.Age.between(1,120)).sum())}
    if legacy:
        frame['avg_exp']=frame.avg_exp.fillna(frame.avg_exp.mean())
        # Preserve the textbook first-seen coding, including a missing-category dummy.
        frame['edu_class']=pd.factorize(frame.edu_class,sort=False,use_na_sentinel=False)[0]
        valid_age=frame.Age.between(1,120)
        frame['Age']=frame.Age.astype(float).where(valid_age,frame.loc[valid_age,'Age'].mean())
        frame=pd.concat([frame,pd.get_dummies(frame.edu_class,prefix='edu',drop_first=True,dtype=bool)],axis=1)
    else:
        # Age limits are an explicit teaching plausibility rule, not a learned population rule.
        frame=frame.loc[frame.avg_exp.notna() & frame.Age.between(1,120) & frame.edu_class.notna()].copy()
        if not set(frame.edu_class).issubset(EDUCATION):raise ValueError('Unknown education category')
    if not set(frame.gender).issubset({'Male','Female'}):raise ValueError('Unknown gender label')
    frame['gender']=frame.gender.map({'Male':1,'Female':0})
    if frame.empty or not np.isfinite(frame[['avg_exp',*NUMERIC]].to_numpy(dtype=float)).all() or frame.avg_exp.le(0).any():
        raise ValueError('Positive observed expense and finite features are required')
    frame['ln_avg_exp']=np.log(frame.avg_exp)
    frame['Age_sq']=frame.Age**2
    frame['Age_gender']=frame.Age*frame.gender
    audit['retained_rows']=len(frame);audit['excluded_rows']=len(raw)-len(frame)
    return frame,audit


def formulas(legacy=False):
    education='edu_1+edu_2+edu_3+edu_4' if legacy else 'C(edu_class)'
    reduced='gender+Age+Income+Ownrent+Selfempl+dist_home_val+'+education
    return ['avg_exp~'+reduced+'+dist_avg_income','avg_exp~'+reduced,
            'ln_avg_exp~'+reduced,'ln_avg_exp~'+reduced+'+Age_sq',
            'ln_avg_exp~'+reduced+'+Age_sq+Age_gender']


def prediction_pipeline(numeric):
    return make_pipeline(ColumnTransformer([
        ('numeric',StandardScaler(),numeric),
        ('education',OneHotEncoder(categories=[EDUCATION],drop='first',handle_unknown='error',sparse_output=False),['edu_class'])]),LinearRegression())


def cross_validate(frame):
    """Same five held-out folds for every variant; all fitted transforms stay inside training."""
    y=frame.avg_exp.to_numpy();predictions={name:np.empty(len(frame)) for name in ['training_mean',*NAMES]}
    folds=np.empty(len(frame),dtype=int);smearing=[];category_support=[]
    for fold,(train,test) in enumerate(KFold(5,shuffle=True,random_state=20261023).split(frame),1):
        a,b=frame.iloc[train],frame.iloc[test];folds[test]=fold
        category_support.append({'fold':fold,'validation_records_in_education_absent_from_training':int((~b.edu_class.isin(a.edu_class.unique())).sum())})
        predictions['training_mean'][test]=a.avg_exp.mean()
        for i,name in enumerate(NAMES):
            numeric=NUMERIC.copy() if i==0 else NUMERIC[:-1].copy()
            if i>=3:numeric+=['Age_sq']
            if i>=4:numeric+=['Age_gender']
            model=prediction_pipeline(numeric)
            target=a.avg_exp.to_numpy() if i<2 else a.ln_avg_exp.to_numpy()
            model.fit(a,target);value=model.predict(b)
            if i>=2:
                factor=float(np.exp(target-model.predict(a)).mean())
                value=np.exp(value)*factor
                smearing.append({'fold':fold,'model':name,'training_smearing':factor})
            if not np.isfinite(value).all():raise AssertionError('Nonfinite held-out prediction')
            predictions[name][test]=value
    records=[]
    for name,pred in predictions.items():
        records.append({'model':name,'n':len(y),'folds':5,'mae_yuan':float(abs(y-pred).mean()),
                        'rmse_yuan':float(np.sqrt(np.mean((y-pred)**2))),
                        'oof_r_squared':float(1-np.sum((y-pred)**2)/np.sum((y-y.mean())**2)),
                        'negative_predictions':int((pred<0).sum())})
    private=pd.DataFrame({'source_index':frame.index,'fold':folds,'observed':y,**predictions})
    return pd.DataFrame(records),private,smearing,category_support


def vif_table(model,name):
    x=model.model.exog;names=model.model.exog_names
    return [{'model':name,'feature':label,'vif':float(variance_inflation_factor(x,i))}
            for i,label in enumerate(names) if label!='Intercept']


def main(argv=None):
    ctx=context('S10',argv);nb=read_notebook(ctx.source('notebook_linear'))
    raw=pd.read_excel(ctx.source('linear_creditcard'),sheet_name='creditcard_exp')
    primary,audit=prepare(raw);legacy,legacy_audit=prepare(raw,True)
    models=[fit_estimable(f,primary) for f in formulas()]
    legacy_models=[fit_estimable(f,legacy) for f in formulas(True)]
    checks={name:legacy_reference_check(model,cached_text(nb,cell))
            for name,model,cell in zip(NAMES,legacy_models,[62,69,76,81,84])}
    source_exog=legacy[NUMERIC+['edu_class']]
    legacy_vif={}
    for label in source_exog:
        result=fit_estimable(label+'~'+'+'.join(c for c in source_exog if c!=label),source_exog)
        token=re.search(r'^'+label+r'\s+([\d.eE+-]+)',cached_text(nb,68),re.M).group(1)
        legacy_vif[label]=check_printed(1/(1-result.rsquared),token)
    cv,private,smearing,category_support=cross_validate(primary)
    save_table(private,ctx.output/'private_oof_predictions.csv')
    save_table(cv,ctx.output/'cross_validation.csv')
    records=[];coefficients=[]
    for branch,group in [('observed',models),('INVALID_imputed_response_legacy',legacy_models)]:
        for name,model in zip(NAMES,group):
            records.append({'branch':branch,'model':name,'response_scale':'yuan' if name.startswith('raw') else 'log_yuan',
                            'nobs':int(model.nobs),'parameters':len(model.params),'r_squared':model.rsquared,
                            'f_statistic':model.fvalue,'f_pvalue':model.f_pvalue,'aic_same_response_only':model.aic})
            for term,value in model.params.items():
                coefficients.append({'branch':branch,'model':name,'term':term,'estimate':value})
    save_table(pd.DataFrame(records),ctx.output/'model_comparison.csv')
    save_table(pd.DataFrame(coefficients),ctx.output/'coefficients.csv')
    vif=pd.DataFrame(vif_table(models[0],'observed_raw_full')+vif_table(models[1],'observed_raw_reduced'))
    save_table(vif,ctx.output/'vif.csv')
    save_table(pd.DataFrame([{'branch':'observed',**audit},{'branch':'INVALID_imputed_response_legacy',**legacy_audit}]),ctx.output/'quality_audit.csv')
    corr=[]
    for method in ['pearson','kendall']:
        table=primary[['avg_exp',*NUMERIC]].corr(method=method)
        for a in table:
            for b in table:
                if a<b:corr.append({'method':method,'feature_a':a,'feature_b':b,'correlation':table.loc[a,b]})
    save_table(pd.DataFrame(corr),ctx.output/'correlations.csv')
    coverage=write_coverage(nb,[
        ([1,3,4,5,6,7,10,11,13,15,16,18,19,20],'读取、删列、重复与缺失','prepare核查ID和缺失；正式分支不填响应，教材填均值仅作兼容诊断'),
        ([22,23,24,25,26,27,28,29,45,46,47],'分类编码','正式分支将教育当分类；兼容分支保留首次出现顺序和缺失哑变量'),
        ([32,33,35,36,37,38,39,41,42,43],'箱线图与999年龄异常','记录年龄1至120规则；该异常也缺失响应，正式样本已排除；兼容分支用有效年龄均值'),
        ([50,51,53,54],'相关与散点','保存Pearson/Kendall连续变量相关，正式诊断展示收入散点和小区收入箱线图'),
        ([57,58,59,60,61,62,63,64,67,68,69],'OLS接口、残差、共线性','独立拟合5模型，核对全部教材系数及统计量；正式VIF用真实分类设计，不用任意教育序码'),
        ([72,74,75,76,78,80,81,83,84],'残差、对数、二次与交互','保留5个变体与QQ图；增加同折OOF评估，对数回变换修正仅从训练残差估计')],ctx.output/'notebook-map.md')
    plt=plotting();fig,axes=plt.subplots(2,2,figsize=(12,9),layout='constrained')
    axes[0,0].scatter(primary.Income,primary.avg_exp,s=28,color='#247d86',alpha=.7)
    axes[0,0].set(title='已观察响应：收入与消费',xlabel='年收入（万元）',ylabel='月均信用卡支出（元）')
    axes[0,1].boxplot(primary.dist_avg_income,vert=False)
    axes[0,1].set(title='当地人均收入：不擅自删除极值',xlabel='dist_avg_income（原表未明示单位）',yticks=[])
    for model,ax in [(models[1],axes[1,0])]:
        ax.scatter(model.fittedvalues,model.resid,s=25,color='#247d86');ax.axhline(0,color='#d67b28')
        ax.set(title='原额简化模型：样本内残差',xlabel='拟合消费额（元）',ylabel='残差（元）')
    stats.probplot(models[4].resid,plot=axes[1,1]);axes[1,1].set(title='对数交互模型：残差QQ图',xlabel='理论正态分位数',ylabel='对数残差')
    fig.savefig(ctx.output/'regression_diagnostics.png',dpi=140);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5),layout='constrained');positions=np.arange(len(cv))
    ax.barh(positions,cv.rmse_yuan,color=['#aabac2']+['#247d86']*5)
    ax.set(yticks=positions,yticklabels=cv.model,title='同一组5折：原始元尺度的探索性比较',xlabel='OOF RMSE（元，越低越好）')
    for i,v in enumerate(cv.rmse_yuan):ax.text(v+3,i,f'{v:.1f}',va='center')
    ax.set_xlim(0,cv.rmse_yuan.max()*1.16)
    fig.savefig(ctx.output/'regression_validation.png',dpi=150);plt.close(fig)
    report=f'''# S10 信用卡消费线性回归

76条记录中6条消费额缺失；正式分析只用{len(primary)}条已观察响应。年龄999与教育缺失发生在同一条响应缺失记录，因此它已随缺失响应排除，没有额外删掉已观察样本。原始资料保持只读。数据字典将avg_exp定义为月均信用卡支出（元），Income为年收入（万元）；当地人均收入单位未明确，不猜测。

## 代码与教材修正

prepare分别建立正式样本与明确标记INVALID的教材兼容分支。后者为复核缓存而用总体均值填6个响应，替换999年龄，保留教育首次出现序码。填补预测目标会制造观测，不能用于正式推断或验证。5个兼容OLS共核对{sum(v['values_compared'] for v in checks.values())}项系数和统计量，另核对8个教材VIF；这不代表修正后的主模型与教材数值相同。

正式模型将教育当分类。共线性诊断使用实际含哑变量的设计矩阵，保留截距参与辅助回归；id、Acc、edad2不入模。Pearson和Kendall只比较实际数值字段，不把教育序码当等距数值。fit_estimable拒绝不可识别设计。

![样本内诊断](regression_diagnostics.png)

## 预测验证与解释

五个候选变体依次为原额全变量、去当地人均收入、对数简化、对数加年龄平方、对数加年龄平方及年龄×性别。相同的固定5折共{len(primary)}个OOF预测；编码和标准化仅在每折训练集拟合。对数模型使用训练残差的mean(exp(residual))作回变换修正，它依赖残差分布可迁移假设，不等于保证预测条件均值无偏。训练均值基线也逐折重算。

![同折验证](regression_validation.png)

所有RMSE/MAE都在元尺度计算；原额和对数模型的样本内R²、AIC不可直接跨响应尺度挑选优胜者。这是70条小样本上的探索性同折比较，没有独立最终测试集；据此挑模型后仍需要新样本验证。所有回归系数是条件关联，不是营销干预因果效应。负预测数单独报告，未为改善分数截断。

教育类别词表按教材字段含义预先固定为中学、大学、小学及以下、研究生，中学为基线。正式样本小学及以下仅2条，同一验证折都未出现在对应训练集中；这两条的该类别增量无法学习，最小二乘按零增量处理，即回退基线。每折训练未覆盖教育类别的验证人数写入摘要，这也是本次小样本验证的局限。

客户记录和OOF预测仅存本地，公开模型系数、聚合诊断和图形。[逐单元格迁移](notebook-map.md)说明全部教学内容去向。
'''
    finish(ctx,{'lab_id':'S10','status':'execution_verified','audit':audit,'legacy_audit':legacy_audit,
                'legacy_reference_checks':checks,'legacy_vif_checks':legacy_vif,'legacy_values_compared':sum(v['values_compared'] for v in checks.values())+8,
                'cross_validation':cv.to_dict('records'),'training_only_smearing':smearing,'fold_category_support':category_support,'notebook_coverage':coverage},report)


if __name__=='__main__':main()
