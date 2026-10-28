"""Offline Vintage reconstruction and A/B credit-risk modeling."""
import csv
import io
import json
import re
import sqlite3

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from threadpoolctl import threadpool_limits

from bda_labs.common import context
from bda_labs.advanced_common import specification, read_csv, complete, bars
from bda_labs.advanced_regression import classification_metrics


def read_mysql_dump(path, table):
    """Parse only literal INSERT tuples; never execute SQL from a supplied dump."""
    text=path.read_text(encoding='utf-8-sig')
    create=re.search(r'CREATE TABLE `'+re.escape(table)+r'`\s*\((.*?)\) ENGINE',text,re.S)
    if not create:raise ValueError('Missing expected CREATE TABLE schema')
    columns=re.findall(r'^\s*`([^`]+)`',create[1],re.M)
    pattern=r"INSERT INTO `"+re.escape(table)+r"`(?:\s*\([^;]*?\))?\s+VALUES\s*\((.*?)\);"
    values=[]
    for match in re.finditer(pattern,text,re.S|re.I):
        parsed=next(csv.reader(io.StringIO(match[1]),quotechar="'",escapechar='\\',skipinitialspace=True))
        if len(parsed)!=len(columns):raise ValueError('Unsupported dump tuple length')
        values.append([None if x=='NULL' else x for x in parsed])
    if not values or len(values)!=len(re.findall(r'INSERT INTO `'+re.escape(table)+'`',text)):
        raise ValueError('Unparsed or missing INSERT rows')
    return pd.DataFrame(values,columns=columns)


def vintage(ctx,keys):
    customers=read_mysql_dump(ctx.source(keys[0]),'customer_detail')
    repayments=read_mysql_dump(ctx.source(keys[1]),'repayment_sum_month')
    customers['合同期限']=pd.to_numeric(customers['合同期限']);customers['合同金额']=pd.to_numeric(customers['合同金额'])
    for c in ['分期数','当前最大逾期天数','剩余本金']:repayments[c]=pd.to_numeric(repayments[c])
    customers['放款月']=customers['放款日期'].str[:7]
    p=repayments['放款月'].str.split('-',expand=True).astype(int)
    q=repayments['观测月'].str.split('-',expand=True).astype(int)
    delta=q[0]-p[0]
    # Preserve the source SQL's limited 0/1 calendar-year branch. Also retain a
    # general calendar-month delta for explicit diagnostics beyond that scope.
    repayments['mob']=np.where(delta==0,q[1]-p[1],np.where(delta==1,12+q[1]-p[1],0))
    unrestricted=12*delta+q[1]-p[1]
    cohorts=customers[(customers['合同期限']==6)&customers['放款日期'].between('2017-11-01','2018-04-30')]
    if customers['合同ID'].duplicated().any():raise ValueError('Duplicate contract identifiers')
    if repayments.duplicated(['合同ID','观测月']).any():raise ValueError('Duplicate contract/month observations')
    denominator=cohorts.groupby('放款月')['合同金额'].sum()
    repayment=repayments[repayments['分期数']==6]
    # Source joins aggregates by term+cohort, not individual contract. Retain that
    # query scope rather than quietly restricting it to the customer IDs above.
    records=[];rates=[]
    latest=pd.Period(repayments['观测月'].max(),freq='M')
    with sqlite3.connect(':memory:') as connection:
        customers.to_sql('customer_detail',connection,index=False)
        repayments.to_sql('repayment_sum_month',connection,index=False)
        for month,amount in denominator.items():
            row={'section':'Vintage','item':month,'loan_amount_10000':round(float(amount/10000),2)}
            values=[]
            for mob in range(1,7):
                subset=repayment[(repayment['放款月']==month)&(repayment['mob']==mob)&(repayment['当前最大逾期天数']>0)]
                bad=float(subset['剩余本金'].sum())
                sql=connection.execute('SELECT COALESCE(SUM(CASE WHEN mob=? AND 当前最大逾期天数>0 THEN 剩余本金 ELSE 0 END),0) FROM repayment_sum_month WHERE 分期数=6 AND 放款月=?',(mob,month)).fetchone()[0]
                if not np.isclose(sql,bad,atol=1e-6):raise AssertionError('Vintage pandas/SQLite numerator differs')
                rate=bad/amount if amount>0 else np.nan
                maturity=latest.ordinal-pd.Period(month,freq='M').ordinal>=mob
                observed=bool(((repayment['放款月']==month)&(repayment['mob']==mob)).any())
                row[f'mob_{mob}_source_rate']=round(float(rate),4) if np.isfinite(rate) else None
                row[f'mob_{mob}_observed']=observed
                row[f'mob_{mob}_mature_rate']=round(float(rate),4) if maturity and observed and np.isfinite(rate) else None
                values.append(float(rate) if maturity and observed else np.nan)
            records.append(row);rates.append(values)
    from bda_labs.common import plotting
    plt=plotting();fig,ax=plt.subplots(figsize=(8,5))
    for row,values in zip(records,rates):ax.plot(range(1,7),values,marker='o',label=row['item'])
    ax.set(title='Vintage：仅展示已有观测的成熟账龄',xlabel='MOB',ylabel='delinquent remaining principal / origination')
    ax.legend();fig.tight_layout();fig.savefig(ctx.output/'figure.png',dpi=150);plt.close(fig)
    return records,{'customer_rows':len(customers),'repayment_rows':len(repayments),'cohorts':len(denominator),
                    'pandas_sqlite_aggregate_checked':True,'source_year_branch_differences':int((unrestricted!=repayments['mob']).sum()),
                    'duplicate_of':'F05' if ctx.output.name=='F04' else None}


def behavioral_features(balance,labels):
    if labels['Account_ID'].duplicated().any():raise ValueError('Account label/limit must be unique')
    if balance.duplicated(['Account_ID','Period']).any():raise ValueError('Duplicate account-period balance')
    joined=balance.merge(labels[['Account_ID','Cust_ID','Credit_Limit']],on=['Account_ID','Cust_ID'],how='left',validate='many_to_one')
    if joined['Credit_Limit'].isna().any():raise ValueError('Unmatched balance account')
    if (balance['Period']<1).any() or not np.equal(balance['Period'],np.floor(balance['Period'])).all():raise ValueError('Observation periods must be positive integers')
    output={}
    for length in [3,6,12]:
        frame=joined[joined['Period'].isin(range(13-length,13))].copy()
        cust='Cust_ID';account=['Cust_ID','Account_ID'];groups=frame.groupby(cust)
        payment=frame['Payment']/frame['Balance'].where(frame['Balance']>0)
        frame['Pay_Ratio']=payment
        frame['Pay_Flag']=~((frame['Payment']==0)&(frame['Balance']>0))
        features={}
        for base in ['Pay_Ratio','Pay_Flag']:
            for aggregation,suffix in [('mean','AVG'),('max','MAX'),('min','MIN')]:
                if base=='Pay_Ratio':features[f'Pay_Ratio_{suffix}_AMT']=frame.groupby(cust)[base].agg(aggregation)
                features[f'{base}_{suffix}_ACC']=frame.groupby(account)[base].mean().groupby(cust).agg(aggregation)
        features['Pay_Ratio_Count']=frame.groupby(cust)['Pay_Flag'].mean()
        for i in [1,2,3]:
            col=f'Delq{i}'
            features[col+'_Count']=frame.groupby(cust)[col].sum()
            features[col+'_Percent']=frame.groupby(cust)[col].mean()
            features[col+'_Count_ACC']=frame.groupby(account)[col].max().groupby(cust).sum()
        features['Delq_Status']=pd.Series(np.select([features['Delq3_Percent']>0,features['Delq2_Percent']>0,features['Delq1_Percent']>0],[3,2,1],default=0),index=features['Delq1_Percent'].index)
        frame['Balance']=frame['Balance'].clip(lower=0)
        frame['BillUseRate']=frame['Balance']/frame['Credit_Limit'].where(frame['Credit_Limit']>0)
        frame['SpendUseRate']=frame['Spend']/frame['Credit_Limit'].where(frame['Credit_Limit']>0)
        for base in ['BillUseRate','SpendUseRate']:
            account_means=frame.groupby(account)[base].mean()
            for aggregation,suffix in [('mean','AVG'),('max','MAX'),('min','MIN')]:
                features[base+'_'+suffix]=frame.groupby(cust)[base].agg(aggregation)
                features[base+'_'+suffix+'_ACC']=account_means.groupby(cust).agg(aggregation)
            features['NumAcc_High'+base]=(account_means>.75).groupby(cust).sum()
            features['NumAcc_Low'+base]=(account_means<.5).groupby(cust).sum()
            last=frame[frame['Period']==12].set_index(account)[base]
            trend=last/account_means.where(account_means!=0)
            for aggregation,suffix in [('max','MAX'),('mean','AVG')]:features[base+'_Trend_'+suffix+'_ACC']=trend.groupby(cust).agg(aggregation)
        for base in ['BillUseRate','SpendUseRate','Balance','Spend']:
            agg=frame.groupby(account)[base].agg(['mean','std'])
            cv=(agg['std']/agg['mean'].where(agg['mean']!=0)).fillna(0)
            for aggregation,suffix in [('mean','AVG'),('max','MAX'),('min','MIN')]:features[base+'_CV_'+suffix+'_ACC']=cv.groupby(cust).agg(aggregation)
        output.update({f'{name}_L{length}M':series for name,series in features.items()})
    labelgroups=labels.groupby('Cust_ID')
    output['NumAcc']=labelgroups['Account_ID'].count()
    for aggregation,suffix in [('sum','SUM'),('max','MAX'),('min','MIN')]:output['CreditLimit_'+suffix]=labelgroups['Credit_Limit'].agg(aggregation)
    output['Target']=labelgroups['label'].max()
    result=pd.DataFrame(output).replace([np.inf,-np.inf],np.nan)
    if not result.columns.is_unique:raise AssertionError('Repeated feature names')
    return result


def woe_model(ctx,frame,target,acard):
    import toad
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    X=frame.drop(columns=target);y=frame[target].astype(int)
    seed=1223 if acard else 1234
    a,b=train_test_split(np.arange(len(frame)),test_size=.33,stratify=y,random_state=seed)
    train=X.iloc[a].copy();test=X.iloc[b].copy();yt=y.iloc[a];yv=y.iloc[b]
    records=[{'section':'training_profile','item':col,'dtype':str(train[col].dtype),
              'missing':int(train[col].isna().sum()),'unique':int(train[col].nunique())} for col in train]
    retained=toad.selection.drop_empty(train,threshold=.9)
    retained=toad.selection.drop_var(retained,threshold=0)
    if acard:
        retained=toad.selection.drop_iv(retained,yt,threshold=.02)
        # Preserve the explicitly taught Age manual bin override.
        if 'Age' not in retained:retained=retained.assign(Age=train['Age'])
    combiner=toad.transform.Combiner()
    combiner.fit(retained,yt,method='dt',n_bins=5,min_samples=.05)
    if acard:combiner.update({'Age':[36.5,51.5,57.5]})
    woe=toad.transform.WOETransformer()
    trainbins=combiner.transform(retained);testbins=combiner.transform(test[retained.columns])
    for col in trainbins:
        table=pd.DataFrame({'bin':trainbins[col],'bad':yt}).groupby('bin',dropna=False)['bad'].agg(['size','mean'])
        records += [{'section':'train_bin_'+col,'item':str(i),'customers':int(r['size']),'bad_rate':float(r['mean'])} for i,r in table.iterrows()]
    trainwoe=woe.fit_transform(trainbins,yt);testwoe=woe.transform(testbins)
    selected=toad.selection.drop_corr(trainwoe,yt,threshold=.7 if acard else .6)
    selected=toad.selection.stepwise(selected,yt,direction='both',criterion='aic')
    if not len(selected.columns):raise RuntimeError('AIC removed every WOE feature')
    testselected=testwoe[selected.columns]
    model=LogisticRegression(max_iter=3000).fit(selected,yt)
    for name,features,labels in [('train',selected,yt),('test',testselected,yv)]:
        records.append({'section':'WOE_logistic','item':name,**classification_metrics(labels,model.predict_proba(features)[:,1])})
    for col,coef in zip(selected,model.coef_[0]):records.append({'section':'coefficient','item':col,'value':float(coef)})
    for col,value in toad.metrics.PSI(selected,testselected).items():
        records.append({'section':'PSI','item':col,'value':float(value)})
    if len(selected.columns)>1:
        matrix=np.column_stack([np.ones(len(selected)),selected.to_numpy()])
        for i,col in enumerate(selected):records.append({'section':'VIF','item':col,'value':float(variance_inflation_factor(matrix,i+1))})
    details={'train_rows':len(a),'test_rows':len(b),'input_features':len(X.columns),
             'WOE_features_before_selection':len(trainwoe.columns),'selected_features':list(selected),
             'split_seed':seed,'toad_version':toad.__version__}
    if acard:
        card=toad.ScoreCard(combiner=combiner,transer=woe,base_score=600,base_odds=35,pdo=50)
        card.fit(selected,yt)
        scores=card.predict(test[selected.columns])
        factor=50/np.log(2);manual=600-factor*np.log(35)-factor*card.model.decision_function(testselected)
        if not np.allclose(scores,manual,atol=1e-7):raise AssertionError('Scorecard raw/WOE/log-odds conversion differs')
        details['score_conversion_checked']=True
        details['score_distribution']={'min':float(scores.min()),'max':float(scores.max()),'mean':float(scores.mean())}
        bucket=pd.qcut(pd.Series(scores,index=yv.index),10,duplicates='drop')
        table=pd.DataFrame({'bucket':bucket,'bad':yv}).groupby('bucket',observed=True)['bad'].agg(['size','mean'])
        records += [{'section':'test_score_bucket','item':str(i),'customers':int(r['size']),'bad_rate':float(r['mean'])} for i,r in table.iterrows()]
        # Export method-level bin scores locally; no personal applicant rows.
        card.export(to_frame=True).to_csv(ctx.output/'scorecard_private.csv',index=False)
    bars(ctx,['train','test'],[r['AUC'] for r in records if r['section']=='WOE_logistic'],'信用风险：WOE 逻辑回归 AUC','AUC')
    return records,details


def main(lab,argv=None):
    ctx=context(lab,argv);spec=specification(lab)
    with threadpool_limits(limits=1):
        if lab in {'F04','F05'}:
            rows,details=vintage(ctx,spec['inputs'])
            notes='从教材 SQL 备份仅解析字面量行，不连接 MySQL、不执行备份语句。按原查询的期限、放款日期和分组范围重建 MOB；以 SQLite 独立聚合核对 pandas 分子。原 SQL 未成熟账龄的 0 另保留 source_rate，展示曲线只使用已有观测的成熟账龄，避免把未观察当零风险。F04 是 F05 的相同代码检查点，只共享实现，不计作新的业务案例。'
        else:
            if lab=='F06':
                frame=read_csv(ctx,spec['inputs'][0]).set_index('ID')
                frame=frame.loc[~frame.index.duplicated(),~frame.columns.duplicated()]
                cats=['GENDER','FLAG_OWN_CAR','HOUSING_TYPE','FLAG_OWN_REALTY','EDULEVEL','MARRIAGE']
                for col in frame:
                    frame[col]=frame[col].astype(str) if col in cats else pd.to_numeric(frame[col],errors='raise')
                frame['DAYS_EMPLOYED']=frame['DAYS_EMPLOYED'].where(frame['DAYS_EMPLOYED']>=0)
                frame=frame.replace([np.inf,-np.inf],np.nan)
                for c in cats:frame[c]=frame[c].replace(['nan','','special','missing'],'missing')
                rows,details=woe_model(ctx,frame,'TARGET',True)
                vintage_rows,vintage_details=vintage_tables(ctx,spec['inputs'][1:])
                rows+=vintage_rows;details['Vintage']=vintage_details
                # vintage_tables does not replace the main scorecard chart.
                notes='保留缺失/零方差/IV 筛选、决策树分箱、Age 人工切点、WOE、相关筛选、双向 AIC、VIF、PSI 与 600/35/50 评分卡。仅在训练集学习分箱、WOE及筛选。修复源代码把 WOE 数据再次当原始数据评分的风险，用原始输入评分并独立核对 log-odds 转分。末尾数据库列表属环境演示，替换为本地备份表清单；Vintage 查询见同批 F05 的完整离线实现。'
            else:
                balance=read_csv(ctx,spec['inputs'][0]);labels=read_csv(ctx,spec['inputs'][1])
                frame=behavioral_features(balance,labels)
                frame=frame.fillna(-9999)
                rows,details=woe_model(ctx,frame,'Target',False)
                details.update({'balance_rows':len(balance),'accounts':len(labels),'customer_rows':len(frame),'observation_windows':[3,6,12],
                                'post_observation_rows_excluded':int((balance['Period']>12).sum())})
                notes='保留还款、逾期、额度使用、趋势/波动、账户汇总及 3/6/12 月窗口。严格取截至 Period=12 的窗口；提供文件中的第13期不进入任何特征。修复源循环累加导致重复特征和窗口后缀多次追加，以及 Spend_CV 错用 Balance_CV；账户额度关联按客户+账户校验 many-to-one，避免连接放大。额度为零按缺失处理。标签文件未给表现窗口日期，因此这里只验证给定标签下教学留出，不能声称通过真实业务的时间外验证。'
    complete(ctx,lab,rows,details,notes=notes)


def vintage_tables(ctx,keys):
    # Keep A-card's own figure; reuse the fully checked Vintage computation.
    figure=ctx.output/'figure.png';saved=figure.read_bytes()
    rows,details=vintage(ctx,keys)
    figure.write_bytes(saved)
    return rows,details
