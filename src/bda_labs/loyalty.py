"""B06: exact textbook segmentation plus an explicit 13-week boundary sensitivity check."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table,compare_numeric
from .rfm import money_cents

AS_OF=pd.Timestamp('2021-01-01')


def quantile_score(values,lower,upper):
    return np.where(values<lower,1,np.where(values>upper,3,2))


def calculate(raw,as_of=AS_OF,recent_inclusive=False):
    df=raw[['订单编号','会员编号','消费日期','消费金额']].copy()
    if df.isna().any().any():raise ValueError('Missing loyalty input fields')
    df['消费日期']=pd.to_datetime(df['消费日期'],errors='raise').dt.normalize()
    if not df['消费日期'].between(as_of-pd.DateOffset(years=1),as_of,inclusive='left').all():
        raise ValueError('Expected the previous calendar-year observation window')
    if df.groupby('订单编号')['会员编号'].nunique().gt(1).any():raise ValueError('An order belongs to multiple members')
    if df.groupby('订单编号')['消费日期'].nunique().gt(1).any():raise ValueError('An order spans multiple dates; clarify receipt timing first')
    df['cents']=money_cents(df['消费金额'])
    cut=as_of-pd.Timedelta(weeks=13)
    recent=df['消费日期'].ge(cut) if recent_inclusive else df['消费日期'].gt(cut)
    g=df.groupby('会员编号').agg(last_purchase=('消费日期','max'),frequency=('订单编号','nunique'),monetary_cents=('cents','sum'))
    g['recent_orders']=df.loc[recent].groupby('会员编号')['订单编号'].nunique().reindex(g.index,fill_value=0)
    g['older_orders']=df.loc[~recent].groupby('会员编号')['订单编号'].nunique().reindex(g.index,fill_value=0)
    potential=g.older_orders.eq(0)&g.recent_orders.eq(1)
    at_risk=g.last_purchase.lt(cut)
    regular=~potential&~at_risk
    if (potential&at_risk).any():raise AssertionError('Special groups must be disjoint')
    if not regular.any():raise ValueError('No members remain for quantile scoring')
    f_low,f_high=g.loc[regular,'frequency'].quantile([.25,.75]).tolist()
    m_low,m_high=g.loc[regular,'monetary_cents'].quantile([.25,.75]).tolist()
    g['f_score']=pd.Series(pd.NA,index=g.index,dtype='Int64')
    g['m_score']=pd.Series(pd.NA,index=g.index,dtype='Int64')
    g.loc[regular,'f_score']=quantile_score(g.loc[regular,'frequency'],f_low,f_high)
    g.loc[regular,'m_score']=quantile_score(g.loc[regular,'monetary_cents'],m_low,m_high)
    g['total_score']=g.f_score+g.m_score
    g['segment']=pd.Series(index=g.index,dtype='string')
    g.loc[potential,'segment']='潜在用户'
    g.loc[at_risk,'segment']='易流失用户'
    g.loc[regular,'segment']=g.loc[regular,'total_score'].map({2:'低价值用户',3:'低价值用户',4:'普通用户',5:'进阶用户',6:'忠诚用户'})
    if g.segment.isna().any():raise AssertionError('Unclassified customer')
    return g.rename_axis('customer_id').reset_index(),{'cutoff':str(cut.date()),'recent_inclusive':recent_inclusive,
        'f_q25':f_low,'f_q75':f_high,'m_q25_cents':m_low,'m_q75_cents':m_high,
        'scored_members':int(regular.sum())}


def main(argv=None):
    ctx=context('B06',argv)
    raw=pd.read_excel(ctx.source('loyalty_raw'),sheet_name='销售流水表',usecols='A:E',dtype={'会员编号':'string','订单编号':'string'})
    customers,thresholds=calculate(raw)
    ref_path=ctx.source('loyalty_reference')
    main_ref=pd.read_excel(ref_path,sheet_name='参考答案',skiprows=8,usecols='A:G').rename(columns={
        '会员编号':'customer_id','消费次数':'frequency','消费额':'monetary','F评分':'f_score','M评分':'m_score','总分':'total_score','用户类别':'segment'})
    special_ref=pd.read_excel(ref_path,sheet_name='潜在&易流失用户',usecols='A:B').rename(columns={'会员编号':'customer_id','用户类别':'segment'})
    labels=pd.concat([main_ref[['customer_id','segment']],special_ref],ignore_index=True)
    if labels.customer_id.duplicated().any():raise AssertionError('Duplicate members in reference partition')
    joined=customers.merge(labels,on='customer_id',how='outer',suffixes=('_python','_excel'),indicator=True,validate='one_to_one')
    bad=joined.loc[~joined['_merge'].eq('both')|joined.segment_python.ne(joined.segment_excel)]
    save_table(bad,ctx.output/'reference_differences.csv')
    if not bad.empty:raise AssertionError('Loyalty customer labels differ from the reference')
    scored=customers.set_index('customer_id').reindex(main_ref.customer_id)
    checks={'all_customer_labels':{'members_compared':len(labels),'mismatches':0},
        'regular_customer_values':compare_numeric(scored[['frequency','monetary_cents','f_score','m_score','total_score']].astype(float),
            np.column_stack([main_ref.frequency,money_cents(main_ref.monetary),main_ref.f_score,main_ref.m_score,main_ref.total_score]),'Loyalty scores',tolerance=0)}
    # The source formula uses > cutoff for recent orders but < cutoff for at-risk status.
    # A consistent inclusive [cutoff, as_of) window is a separate sensitivity experiment.
    alternative,alt_thresholds=calculate(raw,recent_inclusive=True)
    sensitivity=customers[['customer_id','segment']].merge(alternative[['customer_id','segment']],on='customer_id',suffixes=('_textbook','_inclusive'),validate='one_to_one')
    sensitivity=sensitivity.loc[sensitivity.segment_textbook.ne(sensitivity.segment_inclusive)]
    save_table(sensitivity,ctx.output/'boundary_sensitivity.csv')
    save_table(customers,ctx.output/'customers.csv')
    grouped=customers.groupby('segment').agg(customers=('customer_id','size'),receipts=('frequency','sum'),monetary_cents=('monetary_cents','sum')).sort_values('customers',ascending=False)
    grouped['customer_share']=grouped.customers/len(customers)
    grouped['revenue_share']=grouped.monetary_cents/grouped.monetary_cents.sum()
    if int(grouped.monetary_cents.sum())!=int(money_cents(raw['消费金额']).sum()):raise AssertionError('Loyalty amount conservation failed')
    save_table(grouped.reset_index(),ctx.output/'segments.csv')
    plt=plotting()
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    order=grouped.iloc[::-1]
    axes[0].barh(order.index,order.customers,color='#6b8ba4')
    axes[0].set(title='客户分层人数',xlabel='客户数（人）')
    axes[1].barh(order.index,order.revenue_share*100,color='#087f8c')
    axes[1].set(title='销售额贡献',xlabel='年度销售额占比（%）')
    for y,value in enumerate(order.customers):axes[0].text(value+2,y,str(value),va='center',fontsize=9)
    fig.suptitle('用户忠诚度：先识别潜在与易流失，再对其余用户评分',fontsize=15,color='#17364d')
    fig.savefig(ctx.output/'loyalty_segments.png',dpi=150)
    plt.close(fig)
    summary={'lab_id':'B06','status':'reference_verified','as_of':str(AS_OF.date()),'source_rows':len(raw),
        'customers':len(customers),'receipts':int(customers.frequency.sum()),'sales_cents':int(grouped.monetary_cents.sum()),
        'thresholds':thresholds,'reference_checks':checks,'boundary_customer_label_changes':len(sensitivity),
        'inclusive_window_thresholds':alt_thresholds,'segments':grouped.reset_index().to_dict('records')}
    report=f"""# B06 用户忠诚度模型

## 结果

2020年共{len(raw):,}条商品明细，{int(customers.frequency.sum()):,}笔订单，{len(customers):,}名会员，金额{grouped.monetary_cents.sum()/100:,.2f}元。分析时点2021-01-01。潜在与易流失会员先单独识别，其余{thresholds['scored_members']}人按年度消费次数、年度消费金额评分。

![忠诚度分层](loyalty_segments.png)

## 规则与参考核对

F按不同订单编号计数，M按商品明细金额求和。潜在用户在最近13周之前无消费、最近13周只有一笔订单；易流失用户最后消费日在边界之前。排除这两类后，F的25%/75%分位数为{thresholds['f_q25']:g}/{thresholds['f_q75']:g}，M为{thresholds['m_q25_cents']/100:g}/{thresholds['m_q75_cents']/100:g}元。

低于下分位数计1分，高于上分位数计3分，等于边界计2分。F+M总分6/5/4/2至3分别对应忠诚/进阶/普通/低价值用户。不是把最近13周的消费金额当成年金额。

全部{len(labels)}名会员的类别与参考一致；其余{len(main_ref)}名可评分会员的F、M、两项分数和总分逐项一致。客户级对照仅留本地，公开目录只有聚合表。

## 13周边界的原始差异

边界为{thresholds['cutoff']}。原Excel用“消费日期>边界”判断近期，却用“最后消费日期<边界”判断易流失，两处对等于边界的处理不对称。为保证可核对，主结果忠实保留这两条公式。

另计算一致的[边界日,分析日)近期窗口作敏感性检查，产生{len(sensitivity)}名会员标签变化。这个结果单独记录，不悄悄替换教材结果；用于实际业务前应先确认窗口定义。

## 业务解释

标签描述本观察期的行为结构，不能直接当作客户终身价值或真实流失标签。对易流失用户的召回、潜在用户的培育都应另做效果验证；缺少利润与营销成本时不直接断言投入回报。
"""
    finish(ctx,summary,report)


if __name__=='__main__':main()
