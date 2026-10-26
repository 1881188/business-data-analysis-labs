"""Income trend drill-down: observed coverage, prior-period denominators and bridges."""
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table,compare_numeric
from .case_workbooks import money_cents,calendar_period,ratio,check_cell,chart_audit
from .tabular_tools import unique_key
from .workbook_reference import read_cached_book,coverage_table


def prepare(raw):
    f=raw[['订单年份','订单月份','销售省份','销售额']].rename(columns={'销售省份':'province'}).copy()
    f['period']=calendar_period(f['订单年份'],f['订单月份'])
    f['province']=f.province.astype('string').str.strip()
    if f.province.isna().any() or f.province.eq('').any():raise ValueError('Missing province')
    f['amount_cents']=money_cents(f['销售额'],allow_negative=False)
    unique_key(f,['period','province'])
    return f[['period','province','amount_cents']].sort_values(['period','province']).reset_index(drop=True)


def totals(frame):
    if frame.empty:raise ValueError('Income analysis needs observed periods')
    index=pd.period_range(frame.period.min(),frame.period.max(),freq='M')
    g=frame.groupby('period').agg(amount_cents=('amount_cents','sum'),province_records=('province','size')).reindex(index)
    g.index.name='period';g['amount']=g.amount_cents/100
    g['mom_base']=g.amount.shift(1);g['yoy_base']=g.amount.shift(12)
    g['mom_growth']=ratio(g.amount-g.mom_base,g.mom_base)
    g['yoy_growth']=ratio(g.amount-g.yoy_base,g.yoy_base)
    annual=frame.assign(year=frame.period.dt.year).groupby('year').agg(amount_cents=('amount_cents','sum'),months_observed=('period','nunique'))
    annual=annual.reindex(range(frame.period.dt.year.min(),frame.period.dt.year.max()+1));annual['amount']=annual.amount_cents/100
    annual['calendar_months_present']=annual.months_observed.eq(12)
    annual['prior_year_amount']=annual.amount.shift(1);annual['annual_growth']=ratio(annual.amount-annual.prior_year_amount,annual.prior_year_amount)
    return g.reset_index(),annual.reset_index()


def province_bridge(frame,current,prior):
    current,prior=pd.Period(current,freq='M'),pd.Period(prior,freq='M')
    def side(period,name):
        return frame.loc[frame.period.eq(period),['province','amount_cents']].set_index('province').rename(columns={'amount_cents':name})
    result=side(prior,'prior_cents').join(side(current,'current_cents'),how='outer')
    result['prior_observed']=result.prior_cents.notna();result['current_observed']=result.current_cents.notna()
    result['prior_amount']=result.prior_cents/100;result['current_amount']=result.current_cents/100
    result['yoy_growth']=ratio(result.current_amount-result.prior_amount,result.prior_amount)
    result['textbook_current_denominator']=ratio(result.current_amount-result.prior_amount,result.current_amount)
    # Zero only represents an absent term in an observed-record sum, never an imputed sales observation.
    both_periods_observed=result.prior_observed.any() and result.current_observed.any()
    result['observed_sum_delta']=(result.current_cents.fillna(0)-result.prior_cents.fillna(0))/100 if both_periods_observed else np.nan
    prior_sum=result.prior_cents.sum(min_count=1)/100;current_sum=result.current_cents.sum(min_count=1)/100
    result['contribution_to_observed_growth_pp']=ratio(result.observed_sum_delta,prior_sum)*100
    if both_periods_observed:compare_numeric([result.observed_sum_delta.sum()],[current_sum-prior_sum],'Province observed-sum bridge')
    return result.reset_index()


def reference_checks(frame,monthly,annual,sheet):
    rows=[]
    for row in range(5,9):check_cell(rows,sheet,f'B{row}',annual.set_index('year').loc[sheet.get(f'A{row}'),'amount'],'annual')
    check_cell(rows,sheet,'B9',annual.amount.sum(),'annual total')
    current=monthly.set_index('period')
    for row in range(21,33):check_cell(rows,sheet,f'B{row}',current.loc[pd.Period(year=2020,month=sheet.get(f'A{row}'),freq='M'),'amount'],'2020 month')
    check_cell(rows,sheet,'B33',current.loc['2020-01':'2020-12','amount'].sum(),'2020 total')
    def block(start,end,province=None):
        data=frame if province is None else frame.loc[frame.province.eq(province)]
        for row in range(start,end+1):
            month=sheet.get(f'A{row}');pair=[]
            for col,year in [('B',2019),('C',2020)]:
                values=data.loc[data.period.eq(pd.Period(year=year,month=month,freq='M')),'amount_cents']
                amount=values.sum()/100 if len(values) else np.nan;pair.append(amount)
                check_cell(rows,sheet,f'{col}{row}',amount,'monthly pivot')
            check_cell(rows,sheet,f'D{row}',np.nansum(pair),'monthly two-year total')
            check_cell(rows,sheet,f'E{row}',ratio(pair[1]-pair[0],pair[1]).item(),'saved denominator',f'=(C{row}-B{row})/C{row}')
        for col,year in [('B',2019),('C',2020)]:check_cell(rows,sheet,f'{col}{end+1}',data.loc[data.period.dt.year.eq(year),'amount_cents'].sum()/100,'pivot annual total')
        check_cell(rows,sheet,f'D{end+1}',data.loc[data.period.dt.year.isin([2019,2020]),'amount_cents'].sum()/100,'pivot combined total')
    block(44,55);block(106,117,'四川')
    bridge=province_bridge(frame,'2020-11','2019-11').set_index('province')
    for row in range(66,96):
        item=bridge.loc[sheet.get(f'A{row}')]
        for col,value in [('B',item.prior_amount),('C',item.current_amount)]:check_cell(rows,sheet,f'{col}{row}',value,'November province pivot')
        check_cell(rows,sheet,f'D{row}',np.nansum([item.prior_amount,item.current_amount]),'November two-year total')
        if f'E{row}' in sheet.formulas:
            # Excel treats a blank referenced numerator as zero; retain that compatibility only here.
            b=0 if pd.isna(item.prior_amount) else item.prior_amount;c=item.current_amount
            check_cell(rows,sheet,f'E{row}',ratio(c-b,c).item(),'saved denominator with Excel blank',f'=(C{row}-B{row})/C{row}')
        else:check_cell(rows,sheet,f'E{row}',0,'manual zero for absent current record')
    for col,value in [('B',bridge.prior_amount.sum()),('C',bridge.current_amount.sum()),('D',bridge.prior_amount.sum()+bridge.current_amount.sum())]:check_cell(rows,sheet,f'{col}96',value,'November total')
    if set(sheet.formulas)!={r['cell'] for r in rows if r['formula']}:raise AssertionError('Unmapped source formula')
    return pd.DataFrame(rows)


def main(argv=None):
    ctx=context('B16',argv)
    original=ctx.source('income_raw');reference=ctx.source('income_reference')
    books={'income_raw':read_cached_book(original),'income_reference':read_cached_book(reference)}
    frame=prepare(pd.read_excel(original,sheet_name='原始数据'))
    full=prepare(pd.read_excel(reference,sheet_name='原始数据'))
    pd.testing.assert_frame_equal(frame,full)
    monthly,annual=totals(frame);sheet=books['income_reference']['准备区']
    checks=reference_checks(frame,monthly,annual,sheet)
    bridge=province_bridge(frame,'2020-11','2019-11')
    sichuan,unused=totals(frame.loc[frame.province.eq('四川')])
    # 2020 country and Sichuan saved formulas use the current-period denominator.
    for data in [monthly,sichuan]:data['textbook_current_denominator']=ratio(data.amount-data.yoy_base,data.amount)
    expected=[[sheet.get(f'B{r}') for r in range(5,9)],[sheet.get(f'B{r}') for r in range(21,33)],
              [sheet.get(f'E{r}') for r in range(44,56)],[sheet.get(f'E{r}') for r in range(66,96)],[sheet.get(f'E{r}') for r in range(106,118)]]
    destinations=['income_dashboard:年度已观察金额（不把总计当一年）','income_dashboard:2020月度金额（不把总计当一月）',
                  'income_dashboard:标准同比与原式分开','province_bridge:类别/数值长度错配修正；按省键关联','income_drilldown:四川标准同比与原式分开']
    charts,chart_points=chart_audit(reference,destinations*2,expected*2)
    coverage=coverage_table(books,{
        ('income_raw','原始数据'):'唯一年月省份金额输入，缺记录不自动当0',
        ('income_reference','业务需求'):'绘图文本框：平台收入趋势→年度、月份、11月省份、四川月度下钻',
        ('income_reference','原始数据'):'与独立原始输入逐行同键核对，金额不重复计入',
        ('income_reference','准备区'):'全部汇总及52个公式缓存核对；原式分母错误单独标记',
        ('income_reference','报表界面'):'10幅图（含准备区的重复图）全部登记，缓存值核对'},ctx.output/'workbook-map.md')
    for name,data in [('monthly_trends',monthly),('annual_trends',annual),('november_province_bridge',bridge),('sichuan_monthly',sichuan),('reference_checks',checks),('chart_map',charts)]:save_table(data,ctx.output/(name+'.csv'))
    current=monthly[monthly.period.dt.year.eq(2020)];sc=sichuan[sichuan.period.dt.year.eq(2020)]
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(14,10),layout='constrained');fig.suptitle('收入趋势分析 · 已提供销售记录',fontsize=16)
    ax[0,0].bar(annual.year.astype(str),annual.amount/10000,color='#087f8c');ax[0,0].set(title='年度金额持续增长',ylabel='金额（万源单位）')
    ax[0,1].plot(current.period.dt.month,current.amount/10000,marker='o');ax[0,1].set(title='2020年月度金额',xlabel='月份',ylabel='金额（万源单位）');ax[0,1].set_xticks(range(1,13))
    ax[1,0].plot(current.period.dt.month,current.yoy_growth*100,marker='o',label='标准同比：以上年同月为分母');ax[1,0].plot(current.period.dt.month,current.textbook_current_denominator*100,marker='x',label='教材原式：以当月为分母');ax[1,0].axhline(0,color='gray',lw=.8);ax[1,0].set(title='同比口径对照',xlabel='月份',ylabel='变化（%）');ax[1,0].legend(fontsize=8)
    ax[1,1].bar(current.period.dt.month,current.province_records,color='#087f8c');ax[1,1].set(title='每月已提供省份记录数',xlabel='月份',ylabel='省份数',ylim=(0,32))
    fig.savefig(ctx.output/'income_dashboard.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(15,7),layout='constrained')
    ranked=bridge.sort_values('observed_sum_delta');selected=pd.concat([ranked.head(6),ranked.tail(6)])
    ax[0].barh(selected.province,selected.observed_sum_delta/10000,color=np.where(selected.observed_sum_delta<0,'#d95f45','#087f8c'));ax[0].axvline(0,color='gray',lw=.8);ax[0].set(title='11月观察金额增减：六项减少与六项增加',xlabel='2020减2019（万源单位）')
    ax[1].plot(sc.period.dt.month,sc.yoy_growth*100,marker='o',label='标准同比');ax[1].plot(sc.period.dt.month,sc.textbook_current_denominator*100,marker='x',label='教材原式');ax[1].axhline(0,color='gray',lw=.8);ax[1].set(title='四川2020年月度变化',xlabel='月份',ylabel='变化（%）');ax[1].legend(fontsize=9)
    fig.savefig(ctx.output/'income_drilldown.png',dpi=150);plt.close(fig)
    nov=current[current.period.eq(pd.Period('2020-11'))].iloc[0]
    grid_missing=len(pd.period_range(frame.period.min(),frame.period.max(),freq='M'))*frame.province.nunique()-len(frame)
    report=f'''# B16 收入趋势分析

## 业务问题与结论

线上超市平台2017—2020年销售趋势，从年度→2020月度→11月省份→四川月度逐层定位。输入为{len(frame)}条唯一年月省份记录，两份工作簿的原始区域逐行一致。源金额单位未注明，图按“源单位/万源单位”展示。

年度金额分别为{', '.join(f"{r.year}年 {r.amount:,.0f}" for r in annual.itertuples())}。2020年已观察合计比2019年增长{annual.loc[annual.year.eq(2020),'annual_growth'].iloc[0]:.4%}；年度未显示增长放缓，11月局部下降需单独解释。11月从{nov.yoy_base:,.0f}降至{nov.amount:,.0f}，标准同比{nov.yoy_growth:.4%}，金额减少{nov.yoy_base-nov.amount:,.0f}。

![收入趋势](income_dashboard.png)

## 原式错误与缺失记录

标准同比=(当期−上年同期)/上年同期；教材52个保存公式为(当期−上年同期)/当期。代码逐式确认并复算缓存，兼容列明确命名textbook_current_denominator，不当作标准同比。四川11月标准同比约−89.15%，教材原式约−821.69%，差异来自分母。

以已出现的31个省份×48个月构造覆盖网格，共1488个组合，其中只提供1187条，未提供{grid_missing}个组合；未提供不等于真实零销售。总额表示已提供记录的合计，province_records公开覆盖数。缺少整月保持未知，不能用上一条记录代替上一自然月/上一年。个别省份缺一侧时，标准同比未知，保留observed标记。原准备区把2020年11月没有宁夏、青海记录时的增长率手填为0，本实现仅在参考核对表保留这两个常量，不带入主指标。贵州、西藏自治区、新疆的原式还利用Excel空白引用当0，与主分析的缺记录规则分开。

## 下钻与解释边界

november_province_bridge.csv按省份外连接，金额桥为“当期已观察合计−上期已观察合计”。仅为对观察合计分解，缺一侧的项在求和桥中用0表示没有求和项，原金额列仍未知，不宣称停业/新开省份。贡献百分点以11月上年已观察总额为分母，和等于整体同比；不能平均各省同比。

![收入下钻](income_drilldown.png)

图选金额下降和增长各六项，完整省份表在CSV。四川是教材指定下钻例，不宣称它是金额下降最大省份。省份金额变化只定位现象，缺少订单数、客户、品类或价格数据，不能推断具体经营原因。

## 教材覆盖与验证

5张来源工作表均有去向（业务需求/看板页主要是绘图文本和图表）。{int(checks.numeric_compared.sum())}个数字缓存及缺失位置逐项核对，全部52个公式有映射；10幅图的{chart_points}个数值缓存核对。年度和月度源引用虽然覆盖总计行，其保存图缓存实际未纳入总计，Python同样只画真实期间。两份11月省份图的类别29项、数值30项，缺重庆标签，Python按省份键修正。

状态为指定范围参考核对通过：核对保存快照及原式，主指标修正分母，未声称重建Excel透视表交互。教材原文件只读且不随仓库分发。

```powershell
python run_labs.py --lab B16
```
'''
    finish(ctx,{'lab_id':'B16','status':'reference_verified','records':len(frame),'provinces':int(frame.province.nunique()),
                'months':len(monthly),'missing_province_month_combinations':grid_missing,'source_input_equality':True,
                'numeric_reference_checks':int(checks.numeric_compared.sum()),'formula_checks':len(sheet.formulas),
                'source_formula_cells':len(sheet.formulas),'formula_cells_covered':len(sheet.formulas),
                'chart_numeric_checks':chart_points,'charts':len(charts),'chart_length_mismatches':int((~charts.category_value_length_equal).sum()),
                'november_2020':{'prior_amount':nov.yoy_base,'amount':nov.amount,'yoy_growth':nov.yoy_growth},'workbook_coverage':coverage},report)


if __name__=='__main__':main()
