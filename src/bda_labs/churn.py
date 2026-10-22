"""S11: interpretable telecom churn models with a held-out test set and corrected metrics."""
from __future__ import annotations

import warnings
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
    precision_score, recall_score, f1_score, roc_auc_score, roc_curve)
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor

from .common import context, finish, plotting, save_table, write_json

FORMULA = "churn ~ duration + AGE + incomeCode + peakMinDiff + call_10086 + C(edu_class) + C(feton) + C(posTrend) + C(negTrend) + C(curPlan) + C(avgplan) + C(gender)"
CONTINUOUS = ["duration", "AGE", "incomeCode", "nrProm", "peakMinAv", "peakMinDiff", "call_10086"]
CATEGORICAL = ["posTrend", "prom", "edu_class", "feton", "curPlan", "avgplan", "gender", "negTrend", "planChange", "posPlanChange", "negPlanChange"]
MODEL_NUMERIC=["duration","AGE","incomeCode","peakMinDiff","call_10086"]
MODEL_CATEGORICAL=["edu_class","feton","posTrend","negTrend","curPlan","avgplan","gender"]


def fit_regularized(frame):
    """Same predictors, with an explicitly different L2 estimator; preprocessing fits here only."""
    transform=ColumnTransformer([
        ("numeric",StandardScaler(),MODEL_NUMERIC),
        ("categorical",OneHotEncoder(drop="first",handle_unknown="error",sparse_output=False),MODEL_CATEGORICAL)])
    pipe=Pipeline([("prepare",transform),("model",LogisticRegression(C=1.,solver="lbfgs",max_iter=3000,tol=1e-8))])
    pipe.fit(frame,frame.churn.astype(int))
    model=pipe.named_steps["model"]
    if np.max(model.n_iter_)>=model.max_iter:raise RuntimeError("Regularized logistic regression did not converge")
    return pipe


def fit_logit(formula, frame):
    model = smf.logit(formula, data=frame).fit(disp=False, maxiter=300)
    if not model.mle_retvals.get("converged",False): raise RuntimeError(f"Logit did not converge: {formula}")
    if not np.isfinite(model.params).all(): raise RuntimeError("Non-finite model coefficients")
    if int(model.nobs)!=len(frame): raise ValueError("Formula silently dropped rows; inspect missing/invalid values")
    return model


def forward_aic(frame: pd.DataFrame):
    """Training-only deterministic forward selection; categorical model remains textbook-specified."""
    selected,remaining,trace=[],sorted(CONTINUOUS),[]
    current=fit_logit("churn ~ 1",frame).aic
    while remaining:
        candidates=[]
        for feature in remaining:
            model=fit_logit("churn ~ "+" + ".join(selected+[feature]),frame)
            candidates.append((float(model.aic),feature))
        aic,feature=min(candidates)
        if aic >= current-1e-8: break
        selected.append(feature)
        remaining.remove(feature)
        trace.append({"step":len(selected),"feature_added":feature,"aic":aic,"previous_aic":float(current)})
        current=aic
    return selected,trace


def choose_threshold(y,probability):
    """Use validation probabilities only. Return finite Youden cutoff, with an explicit tie rule."""
    fpr,tpr,thresholds=roc_curve(y,probability,drop_intermediate=False)
    valid=np.isfinite(thresholds)&(thresholds>=0)&(thresholds<=1)
    fpr,tpr,thresholds=fpr[valid],tpr[valid],thresholds[valid]
    if not len(thresholds): raise ValueError("No finite validation threshold")
    scores=tpr-fpr
    ties=np.flatnonzero(np.isclose(scores,scores.max(),atol=1e-12,rtol=0))
    idx=min(ties,key=lambda j:abs(thresholds[j]-.5))
    return float(thresholds[idx]),float(scores[idx])


def evaluate(y,probability,threshold):
    y=np.asarray(y,dtype=int)
    probability=np.asarray(probability,dtype=float)
    if not np.isfinite(probability).all() or ((probability<0)|(probability>1)).any():
        raise ValueError("Predicted probabilities must be finite and in [0, 1]")
    pred=(probability>=threshold).astype(int)
    tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return {"threshold":float(threshold),"rows":len(y),"positive_rate":float(y.mean()),
        "tn":int(tn),"fp":int(fp),"fn":int(fn),"tp":int(tp),
        "accuracy":float((pred==y).mean()),"precision":float(precision_score(y,pred,zero_division=0)),
        "recall":float(recall_score(y,pred,zero_division=0)),"specificity":float(tn/(tn+fp)),
        "f1":float(f1_score(y,pred,zero_division=0)),"roc_auc":float(roc_auc_score(y,probability)),
        "average_precision":float(average_precision_score(y,probability)),"brier":float(brier_score_loss(y,probability))}


def main(argv=None):
    ctx=context("S11",argv)
    data=pd.read_csv(ctx.source("telecom_churn"))
    if data.isna().any().any(): raise ValueError("Missing data require an explicit training-only preprocessing policy")
    if data.subscriberID.duplicated().any(): raise ValueError("Subscriber IDs must be unique before row splitting")
    if set(data.churn.unique())!={0,1}: raise ValueError("Expected churn labels 0/1")
    # Outer split exactly follows the source notebook. The outer test is never used for selection.
    train=data.sample(frac=.7,random_state=666).copy()
    test=data.loc[~data.index.isin(train.index)].copy()
    inner,validation=train_test_split(train,test_size=.2,random_state=2026,stratify=train.churn)
    if set(train.subscriberID)&set(test.subscriberID): raise AssertionError("Train/test customer overlap")
    if set(inner.index)&set(validation.index): raise AssertionError("Training/validation overlap")
    single=fit_logit("churn ~ duration",train)
    # Retain the original continuous-variable selection exercise with corrected null-model initialization.
    selected,trace=forward_aic(train[["churn"]+CONTINUOUS])
    save_table(pd.DataFrame(trace),ctx.output/"forward_aic.csv")
    screening=[]
    for feature in CATEGORICAL:
        tab=pd.crosstab(train[feature],train.churn)
        chi2,p,dof,expected=chi2_contingency(tab)
        screening.append({"feature":feature,"chi2":chi2,"p_value":p,"dof":dof,
                          "minimum_expected_count":float(expected.min()),"training_rows":len(train)})
    save_table(pd.DataFrame(screening),ctx.output/"categorical_screening.csv")
    with warnings.catch_warnings(record=True) as captured:
        textbook=smf.logit(FORMULA,train).fit(disp=False,maxiter=300)
    textbook_diagnostic={"formula":FORMULA,"converged":bool(textbook.mle_retvals.get("converged",False)),
        "design_shape":list(textbook.model.exog.shape),"design_rank":int(np.linalg.matrix_rank(textbook.model.exog)),
        "maximum_absolute_coefficient":float(np.abs(textbook.params).max()),
        "warning_types":[type(w.message).__name__ for w in captured],"use_for_decision":False}
    write_json(ctx.output/"textbook_fit_diagnostic.json",textbook_diagnostic)
    validation_model=fit_regularized(inner)
    cutoff,youden=choose_threshold(validation.churn,validation_model.predict_proba(validation)[:,1])
    multi=fit_regularized(train)
    uni_prob=single.predict(test)
    multi_prob=multi.predict_proba(test)[:,1]
    rows=[]
    for name,prob,t in [("duration_textbook_0.3",uni_prob,.3),("multivariate_l2_0.5",multi_prob,.5),
                        ("multivariate_l2_validation_cutoff",multi_prob,cutoff)]:
        rows.append({"model":name,**evaluate(test.churn,prob,t)})
    metrics=pd.DataFrame(rows)
    save_table(metrics,ctx.output/"metrics.csv")
    # Sensitivity sweep is validation-only, not an outer-test optimization exercise.
    val_prob=validation_model.predict_proba(validation)[:,1]
    sweep=pd.DataFrame([evaluate(validation.churn,val_prob,t) for t in np.arange(.1,1,.1)])
    save_table(sweep,ctx.output/"validation_threshold_sweep.csv")
    names=multi.named_steps["prepare"].get_feature_names_out()
    weights=multi.named_steps["model"].coef_[0]
    coef=pd.DataFrame({"term":names,"coefficient":weights,"odds_ratio":np.exp(weights),
        "scale":["per_training_standard_deviation" if name.startswith("numeric__") else "relative_to_dropped_category" for name in names]})
    coef=pd.concat([pd.DataFrame({"term":["intercept"],"coefficient":multi.named_steps["model"].intercept_,
        "odds_ratio":np.exp(multi.named_steps["model"].intercept_),"scale":["intercept"]}),coef],ignore_index=True)
    save_table(coef,ctx.output/"coefficients.csv")
    # VIF diagnostic is a training-data exercise; never a reason to reuse the test set.
    exog=train[CONTINUOUS].assign(intercept=1.)
    vif=[]
    for j,name in enumerate(CONTINUOUS):
        value=float(variance_inflation_factor(exog.to_numpy(),j))
        vif.append({"feature":name,"vif":value})
    save_table(pd.DataFrame(vif),ctx.output/"vif.csv")
    private=pd.DataFrame({"subscriber_id":test.subscriberID,"actual":test.churn,"probability":multi_prob,
                          "prediction":(multi_prob>=cutoff).astype(int)})
    save_table(private,ctx.output/"test_predictions.csv")
    save_table(pd.DataFrame({"source_index":data.index,"subscriber_id":data.subscriberID,
        "split":["test" if idx in test.index else "validation" if idx in validation.index else "inner_train" for idx in data.index]}),ctx.output/"split_membership.csv")
    chosen=rows[-1]
    cm=np.array([[chosen["tn"],chosen["fp"]],[chosen["fn"],chosen["tp"]]])
    plt=plotting()
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout="constrained")
    for name,prob,color in [("仅在网时长",uni_prob,"#6b8ba4"),("L2正则多元模型",multi_prob,"#087f8c")]:
        fpr,tpr,_=roc_curve(test.churn,prob)
        axes[0].plot(fpr,tpr,color=color,label=f"{name}（AUC={roc_auc_score(test.churn,prob):.3f}）")
    axes[0].plot([0,1],[0,1],linestyle="--",color="#aaa")
    axes[0].set(title="独立测试集ROC",xlabel="假阳性率",ylabel="真正率（召回率）")
    axes[0].legend(loc="lower right",fontsize=9)
    axes[1].imshow(cm,cmap="Blues")
    for (i,j),value in np.ndenumerate(cm):
        axes[1].text(j,i,str(value),ha="center",va="center",fontsize=19,
                     color="white" if value>cm.max()/2 else "#17364d")
    axes[1].set(xticks=[0,1],yticks=[0,1],xticklabels=["预测留存","预测流失"],yticklabels=["实际留存","实际流失"],
                title=f"多元模型混淆矩阵（验证阈值={cutoff:.3f}）")
    fig.suptitle("电信客户流失：区分排序能力与阈值决策",fontsize=17,color="#17364d")
    fig.savefig(ctx.output/"churn_evaluation.png",dpi=150)
    plt.close(fig)
    summary={"lab_id":"S11","status":"run_verified","source_rows":len(data),"train_rows":len(train),"test_rows":len(test),
        "inner_train_rows":len(inner),"validation_rows":len(validation),"outer_random_state":666,"inner_random_state":2026,
        "threshold_source":"training_partition_validation_only", "validation_youden":youden,
        "multivariate_formula":FORMULA,"continuous_aic_selected":selected,"metrics":rows,
        "coefficient_count":len(coef),"primary_models_converged":True,"subscriber_overlap":0,
        "primary_model":"StandardScaler + one-hot + L2 logistic regression; C=1.0 fixed without test tuning",
        "textbook_unpenalized_diagnostic":textbook_diagnostic,
        "reference_note":"Outer split and duration-only source model retained. Unpenalized multivariate reproduction failed convergence; L2, metrics and threshold selection explicitly changed."}
    table="\n".join(f"| {r['model']} | {r['threshold']:.4f} | {r['roc_auc']:.4f} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} |" for r in rows)
    report=f"""# S11 电信客户流失逻辑回归

## 业务问题与数据

估计客户流失概率，解释在网时长、使用行为与客户属性的统计关系。数据{len(data):,}名不同客户、20列，churn=1为流失。subscriberID仅作分区和追溯，不进入模型。

沿用教材random_state=666的70%抽样：训练{len(train):,}人、独立测试{len(test):,}人。训练部分再分为拟合{len(inner):,}人和验证{len(validation):,}人，用验证集Youden指数选择阈值{cutoff:.6f}，再用完整训练部分重新拟合多元模型。测试集不参与变量筛选或阈值选择。

教材未正则多元Logit在当前环境中没有收敛，极端系数绝对值达到{textbook_diagnostic['maximum_absolute_coefficient']:.2f}。保留失败诊断，主模型采用相同预测变量、训练内标准化、独热编码和L2正则逻辑回归，C固定为1.0。该结果不冒充与教材未正则模型数值一致。

## 独立测试结果

| 模型 | 阈值 | ROC AUC | 精确率 | 召回率 | F1 |
|---|---:|---:|---:|---:|---:|
{table}

![模型评价](churn_evaluation.png)

验证阈值下，多元模型识别流失客户{chosen['tp']}人，漏判{chosen['fn']}人，误报{chosen['fp']}人。阈值可以改变召回与误报的平衡，AUC不随所选分类阈值改变。Youden指数没有直接编码营销成本和挽留收益，不能称为商业利润最优阈值。

## 从Notebook到脚本的修正

1. 保留单变量duration、教材多元公式的收敛诊断、训练集前向AIC练习、分类列联检验、概率预测、阈值分析、ROC和VIF诊断。多元主模型采用上述明确说明的L2调整。
2. 原Notebook阈值循环中的precision/recall等名称与实际分母不一致。这里按正类churn=1统一：precision=TP/(TP+FP)，recall=TP/(TP+FN)，specificity=TN/(TN+FP)。
3. 原Notebook在测试集上挑“最优阈值”。这里把选择过程移到训练部分内的验证集，阈值灵敏度表也只使用该验证集。
4. 前向AIC使用仅截距模型初始化，候选顺序固定；分类检验仅用训练数据，未按测试结果改变预测变量。它是另一个教学诊断，不冒充多元模型的自动来源。
5. 裸表达式和show改为明确的CSV、JSON、图和报告。取消原代码中基于位置歧义的Series索引写法。

## 解释与限制

逻辑回归为logit(p)=β0+Σβx。正则模型数值变量按训练标准差缩放，exp(β)解释为增加一个训练标准差对应的优势比；分类变量相对被删除的基准水平解释。正则系数不附加未经计算的经典p值或置信区间。这里是样本观察关联，不是干预的因果效应。随机划分只证明同分布历史样本上的表现，尚未验证未来月份或其他运营商。

本实验检查了主模型收敛、客户分区不重叠和概率有效性；未正则教材多元公式的收敛失败单独记录，未逐项核对原Notebook缓存数值。重新拟合可能改变验证时的概率尺度，阈值也需要在新业务样本上重新验证。类别集合只在对应训练分区学习，遇到未知测试类别明确报错。

本地另有coefficients.csv、forward_aic.csv、categorical_screening.csv、vif.csv、validation_threshold_sweep.csv，以及不纳入公开仓库的客户级预测与分区表。
"""
    finish(ctx,summary,report)


if __name__=="__main__": main()
