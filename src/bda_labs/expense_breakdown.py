"""Two independent expense snapshots with explicit reconciliation residuals."""
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table,compare_numeric
from .case_workbooks import money_cents,calendar_period,ratio,check_cell,chart_audit
from .tabular_tools import unique_key
from .workbook_reference import read_cached_book,coverage_table

SHEETS={'raw':['总费用数据','财务三大期间费用数据','管理费用数据'],
        'complete':['总费用数据-原始数据','财务三大期间费用-原始数据','管理费用-原始数据']}


def prepare(raw,has_category=True):
    count=4 if has_category else 3
    f=raw.iloc[:,:count].dropna(how='all').copy()
    f.columns=['year','month','category','amount'] if has_category else ['year','month','amount']
    f['period']=calendar_period(f.year,f.month)
    if not has_category:f['category']='总费用'
    f['category']=f.category.astype('string').str.strip()
    if f.category.isna().any() or f.category.eq('').any():raise ValueError('Missing expense category')
    f['amount_cents']=money_cents(f.amount)
    unique_key(f,['period','category'])
    return f[['period','category','amount_cents']].sort_values(['period','category']).reset_index(drop=True)


def changes(frame,prior,current):
    prior,current=pd.Period(prior,freq='M'),pd.Period(current,freq='M')
    if current!=prior+1:raise ValueError('Month-on-month comparison requires consecutive calendar months')
    def side(p,name):return frame.loc[frame.period.eq(p),['category','amount_cents']].set_index('category').rename(columns={'amount_cents':name})
    f=side(prior,'prior_cents').join(side(current,'current_cents'),how='outer')
    f['prior_amount']=f.prior_cents/100;f['current_amount']=f.current_cents/100
    f['delta']=(f.current_cents-f.prior_cents)/100
    f['growth']=ratio(f.delta,f.prior_amount)
    return f.reset_index()


def reconcile(total,period,details):
    reported=total.groupby('period').amount_cents.sum(min_count=1)
    observed=period.groupby('period').amount_cents.sum(min_count=1)
    admin=period.loc[period.category.eq('管理费用')].set_index('period').amount_cents
    detail=details.groupby('period').amount_cents.sum(min_count=1)
    r=pd.concat([reported.rename('reported_total_cents'),observed.rename('observed_period_cents'),
                 admin.rename('admin_parent_cents'),detail.rename('observed_admin_detail_cents')],axis=1).sort_index()
    r['total_residual_cents']=r.reported_total_cents-r.observed_period_cents
    r['admin_residual_cents']=r.admin_parent_cents-r.observed_admin_detail_cents
    for col in list(r):r[col.removesuffix('_cents')]=r[col]/100
    return r.reset_index()


def analyze(total,period,details,prior='2020-06',current='2020-07'):
    r=reconcile(total,period,details).set_index('period')
    before,after=r.loc[pd.Period(prior)],r.loc[pd.Period(current)]
    categories=changes(period,prior,current);admin=changes(details,prior,current)
    total_delta=(after.reported_total_cents-before.reported_total_cents)/100
    period_delta=(after.observed_period_cents-before.observed_period_cents)/100
    admin_delta=(after.admin_parent_cents-before.admin_parent_cents)/100
    for table,base,now,delta in [(categories,before.reported_total,after.reported_total,total_delta),
                                 (admin,before.admin_parent,after.admin_parent,admin_delta)]:
        table['prior_share_of_parent']=ratio(table.prior_amount,base)
        table['current_share_of_parent']=ratio(table.current_amount,now)
        table['contribution_to_parent_growth_pp']=ratio(table.delta,base)*100
        table['signed_share_of_parent_change']=ratio(table.delta,delta)
    residual_delta=(after.total_residual_cents-before.total_residual_cents)/100
    admin_residual_delta=(after.admin_residual_cents-before.admin_residual_cents)/100
    # Compare independent level totals; never alter a source to force a zero residual.
    compare_numeric([period_delta+residual_delta],[total_delta],'Expense total bridge')
    detail_delta=(after.observed_admin_detail_cents-before.observed_admin_detail_cents)/100
    compare_numeric([detail_delta+admin_residual_delta],[admin_delta],'Administration bridge')
    metrics={'reported_prior':before.reported_total,'reported_current':after.reported_total,'reported_delta':total_delta,
             'reported_growth':ratio(total_delta,before.reported_total).item(),'observed_period_delta':period_delta,
             'total_residual_prior':before.total_residual,'total_residual_current':after.total_residual,'total_residual_delta':residual_delta,
             'admin_delta':admin_delta,'admin_residual_delta':admin_residual_delta}
    return r.reset_index(),categories,admin,metrics


def snapshot_differences(raw,complete):
    rows=[]
    for level,left,right in zip(['total','period','admin'],raw,complete):
        merged=left.merge(right,on=['period','category'],how='outer',suffixes=('_raw','_complete'),validate='one_to_one')
        merged['level']=level;merged['raw_amount']=merged.amount_cents_raw/100;merged['complete_amount']=merged.amount_cents_complete/100
        merged['complete_minus_raw']=(merged.amount_cents_complete-merged.amount_cents_raw)/100
        merged['same_observed_amount']=merged.amount_cents_raw.eq(merged.amount_cents_complete)
        rows.append(merged)
    return pd.concat(rows,ignore_index=True)


def reference_checks(sheet,total,categories,admin):
    rows=[]
    for row,month in [(5,6),(6,7)]:check_cell(rows,sheet,f'C{row}',total.set_index('period').loc[pd.Period(year=2020,month=month,freq='M'),'amount_cents']/100,'reported total')
    def block(table,start,end,rate=False):
        indexed=table.set_index('category')
        for row in range(start,end+1):
            data=indexed.loc[sheet.get(f'A{row}').strip()]
            for col,value in [('B',data.prior_amount),('C',data.current_amount),('D',data.prior_amount+data.current_amount)]:check_cell(rows,sheet,f'{col}{row}',value,'saved pivot')
            formula=f'=(C{row}-B{row})/B{row}' if rate else f'=C{row}-B{row}'
            check_cell(rows,sheet,f'E{row}',data.growth if rate else data.delta,'saved change formula',formula)
        for col,value in [('B',table.prior_amount.sum()),('C',table.current_amount.sum()),('D',table.prior_amount.sum()+table.current_amount.sum())]:check_cell(rows,sheet,f'{col}{end+1}',value,'saved pivot total')
    block(categories,19,21);block(admin,31,38,True)
    if set(sheet.formulas)!={r['cell'] for r in rows if r['formula']}:raise AssertionError('Unmapped source formula')
    return pd.DataFrame(rows)


def main(argv=None):
    ctx=context('B17',argv);paths={'raw':ctx.source('expenses_raw'),'complete':ctx.source('expenses_reference')}
    books={f'expenses_{"raw" if version=="raw" else "reference"}':read_cached_book(path) for version,path in paths.items()}
    frames={};results={}
    for version,path in paths.items():
        # Explicit source columns exclude the side pivot in L:N of the raw workbook.
        frames[version]=[prepare(pd.read_excel(path,sheet_name=sheet,usecols='A:C' if i==0 else 'A:D'),i!=0) for i,sheet in enumerate(SHEETS[version])]
        results[version]=analyze(*frames[version])
        for name,data in zip(['reconciliation','period_changes','admin_changes'],results[version][:3]):save_table(data,ctx.output/(version+'_'+name+'.csv'))
    differences=snapshot_differences(frames['raw'],frames['complete']);save_table(differences,ctx.output/'snapshot_differences.csv')
    sheet=books['expenses_reference']['准备区'];checks=reference_checks(sheet,frames['complete'][0],results['complete'][1],results['complete'][2])
    # The raw side pivot is a second presentation of six input records, not extra transactions.
    rawsheet=books['expenses_raw']['财务三大期间费用数据'];current_month=None
    for row in range(12,18):
        current_month=rawsheet.get(f'L{row}',current_month)
        category=rawsheet.get(f'M{row}').strip()
        table=frames['raw'][1];amount=table.loc[table.period.eq(pd.Period(year=2020,month=current_month,freq='M'))&table.category.eq(category),'amount_cents'].item()/100
        rows=[];check_cell(rows,rawsheet,f'N{row}',amount,'raw side pivot');checks=pd.concat([checks,pd.DataFrame(rows)],ignore_index=True)
    rows=[];check_cell(rows,rawsheet,'N18',frames['raw'][1].amount_cents.sum()/100,'raw side pivot total');checks=pd.concat([checks,pd.DataFrame(rows)],ignore_index=True)
    save_table(checks,ctx.output/'reference_checks.csv')
    expected=[[sheet.get(f'E{r}') for r in range(19,22)],[sheet.get(f'E{r}') for r in range(31,39)],[sheet.get('C5'),sheet.get('C6')]]
    charts,chart_points=chart_audit(paths['complete'],['expense_dashboard:期间费用差额及未解释差额','admin_comparison:管理明细增长与金额贡献分列','expense_dashboard:报告总费用']*2,expected*2)
    save_table(charts,ctx.output/'chart_map.csv')
    descriptions={}
    for version,key in [('raw','expenses_raw'),('complete','expenses_reference')]:
        for i,name in enumerate(SHEETS[version]):descriptions[(key,name)]=['报告总费用→独立保留，不以分项合计覆盖','三大期间费用→类别清理、月差额、总额对账；原始版右侧透视只核对不重复计入','管理明细→金额与增长率、与管理父项对账'][i]
    descriptions.update({('expenses_reference','业务需求'):'绘图文本框：定位期间费用增长，先验证分层一致性',('expenses_reference','准备区'):'全部11个公式缓存与汇总复算；不跨版本替换输入',('expenses_reference','报表界面'):'6幅源图含重复页面，图缓存与新图去向登记'})
    coverage=coverage_table(books,descriptions,ctx.output/'workbook-map.md')
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(15,10),layout='constrained');fig.suptitle('期间费用分解 · 两版数据独立保留',fontsize=16)
    for j,version in enumerate(['raw','complete']):
        r,c,a,m=results[version];label='原始版' if version=='raw' else '完整版'
        ax[0,j].plot(r.period.astype(str),r.reported_total/10000,marker='o',label='源报告总额');ax[0,j].plot(r.period.astype(str),r.observed_period/10000,marker='x',label='三项合计');ax[0,j].set(title=label+'：总额与期间费用对账',ylabel='金额（万源单位）');ax[0,j].legend(fontsize=9)
        names=[*c.category,'未解释差额变动'];delta=[*c.delta,m['total_residual_delta']]
        ax[1,j].bar(names,np.asarray(delta)/10000,color=['#087f8c' if v>=0 else '#d95f45' for v in delta]);ax[1,j].axhline(0,color='gray',lw=.8);ax[1,j].tick_params(axis='x',rotation=20);ax[1,j].set(title=label+'：总额增长的加法分解',ylabel='7月减6月（万源单位）')
    fig.savefig(ctx.output/'expense_dashboard.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(2,2,figsize=(15,11),layout='constrained')
    for j,version in enumerate(['raw','complete']):
        a=results[version][2].sort_values('delta');label='原始版' if version=='raw' else '完整版'
        ax[0,j].barh(a.category,a.delta/10000,color=np.where(a.delta<0,'#d95f45','#087f8c'));ax[0,j].axvline(0,color='gray',lw=.8);ax[0,j].set(title=label+'：管理明细金额增减',xlabel='7月减6月（万源单位）')
        ax[1,j].barh(a.category,a.growth*100,color='#087f8c');ax[1,j].axvline(0,color='gray',lw=.8);ax[1,j].set(title=label+'：各项增长率（分母为6月）',xlabel='增长（%）')
    fig.savefig(ctx.output/'admin_comparison.png',dpi=150);plt.close(fig)
    raw=results['raw'][3];complete=results['complete'][3]
    report=f'''# B17 财务期间费用分解

## 业务问题与两版结论

零售企业2020年6、7月期间费用增长定位。这里的“财务费用”在源标题中同时指总费用和三大期间费用之一，Python分别命名“报告总费用”“管理费用”“销售费用”“财务费用”，不混用。源金额单位未注明。

两版报告总额都是{raw['reported_prior']:,.0f}→{raw['reported_current']:,.0f}，增加{raw['reported_delta']:,.0f}，环比{raw['reported_growth']:.4%}；但两版的分项金额不同，不能把原始版当成完整版公式的输入。

| 版本 | 期间三项增量 | 管理费用增量 | 总额未解释差额变动 |
|---|---:|---:|---:|
| 原始版 | {raw['observed_period_delta']:,.0f} | {raw['admin_delta']:,.0f} | {raw['total_residual_delta']:,.0f} |
| 完整版 | {complete['observed_period_delta']:,.0f} | {complete['admin_delta']:,.0f} | {complete['total_residual_delta']:,.0f} |

![费用分解](expense_dashboard.png)

## 分层对账

原始版总额与三项合计一致，管理父项与8项明细也一致。增加78,600中，管理+70,000、销售+8,000、财务+600。管理内部工资福利+30,000、折旧摊销+20,000，其他费用−20,000有抵消；金额变化比只看百分比更适合解释总额增量。

完整版6月三项合计1,564,900，高于报告总额4,900；7月三项合计1,579,250，低于报告总额59,350。未解释差额从−4,900变为59,350，变动64,250；三项增量14,350+64,250=报告总额增量78,600。管理+15,050、财务−1,500、销售+800。管理8项与父项对账一致，咨询费+10,000、培训发展+5,000，其他净增50。完整管理增长15,050不能解释报告总增长78,600的全部。

差额仅命名“未解释差额”，未假设它属于某费用或把源总额改成分项合计。snapshot_differences.csv按期间、类别与层级核对两版输入，不相同的金额有明确记录。缺少进一步台账，不能认定业务原因或擅自修正原数据。

## 分母、缺失与贡献

![管理费用对照](admin_comparison.png)

增长率=(7月−6月)/6月；占比用各版对应父项金额，金额差额可以相加，增长率不能相加或简单平均。contribution_to_parent_growth_pp用父项6月金额为分母；signed_share_of_parent_change用父项总增量为分母，可能为负或超过100%，不当作概率。总费用占比在完整版可能不合计100%，差额继续可见。

缺失金额不填0，零分母保持未知，真实零和负的费用冲回保留。按年月键比较连续两个月，原表总费用的“6月/7月”文本、期间费用名称前导空格和原始管理页“份”表头均显式规范。原始版右侧L:N透视只作核对，不重复加入A:D输入。

## 教材覆盖与验证

共9张工作表均有去向，包括只有绘图对象的业务需求与数据看板页。{int(checks.numeric_compared.sum())}个保存数字缓存逐项核对，完整11个公式全部检查结构并复算；6幅图{chart_points}个数字缓存相符。原始版和完整版分别做两层金额桥检查。参考核对通过仅指保存表格、原式与图缓存，不能消除源总分不一致，也不宣称重建Excel图表交互。

```powershell
python run_labs.py --lab B17
```
'''
    finish(ctx,{'lab_id':'B17','status':'reference_verified','snapshots':{'raw':raw,'complete':complete},
                'differing_input_amounts':int((~differences.same_observed_amount).sum()),'numeric_reference_checks':int(checks.numeric_compared.sum()),
                'formula_checks':len(sheet.formulas),'source_formula_cells':len(sheet.formulas),'formula_cells_covered':len(sheet.formulas),
                'chart_numeric_checks':chart_points,'charts':len(charts),'bridge_checks':4,'workbook_coverage':coverage},report)


if __name__=='__main__':main()
