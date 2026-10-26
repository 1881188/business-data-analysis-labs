"""Monthly application changes: additive contributions, never causal attribution."""
import re,zipfile
from xml.etree import ElementTree as ET
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table,compare_numeric
from .case_workbooks import ratio,check_cell
from .closure_tools import chart_caches
from .tabular_tools import unique_key
from .workbook_reference import read_cached_book,coverage_table


def prepare(raw):
    f=raw[['申请书编号（主键）','申请日期','申请渠道']].rename(columns={'申请书编号（主键）':'application_id','申请日期':'date','申请渠道':'channel'}).copy()
    for col in ['application_id','channel']:
        f[col]=f[col].astype('string').str.strip()
        if f[col].isna().any() or f[col].eq('').any():raise ValueError('Missing application key/channel')
    unique_key(f,'application_id');f['date']=pd.to_datetime(f.date,errors='raise')
    if f.date.isna().any() or f.date.dt.tz is not None or f.date.ne(f.date.dt.normalize()).any():raise ValueError('Expected observed calendar dates')
    f['period']=f.date.dt.to_period('M')
    return f


def analyze(frame,prior='2021-04',current='2021-05'):
    if frame.empty:raise ValueError('Application case requires observed records')
    prior,current=pd.Period(prior,freq='M'),pd.Period(current,freq='M')
    if current!=prior+1:raise ValueError('Require consecutive comparison months')
    grid=pd.period_range(frame.period.min(),frame.period.max(),freq='M')
    table=pd.crosstab(frame.period,frame.channel).reindex(grid)
    # An observed month's absent channel is a zero count; an entirely absent month remains unknown.
    monthly=table.sum(axis=1,min_count=1).rename('applications').to_frame();monthly.index.name='period'
    monthly['previous']=monthly.applications.shift(1);monthly['mom_growth']=ratio(monthly.applications-monthly.previous,monthly.previous)
    a=table.loc[prior] if prior in table.index else pd.Series(np.nan,index=table.columns)
    b=table.loc[current] if current in table.index else pd.Series(np.nan,index=table.columns)
    change=pd.DataFrame({'channel':table.columns,'prior':a.to_numpy(),'current':b.to_numpy()})
    change['delta']=change.current-change.prior;total_delta=b.sum(min_count=1)-a.sum(min_count=1);base=a.sum(min_count=1)
    change['channel_growth']=ratio(change.delta,change.prior)
    change['growth_contribution_pp']=ratio(change.delta,base)*100
    change['signed_share_of_net_change']=ratio(change.delta,total_delta)
    change['change_over_absolute_net_change']=ratio(change.delta,abs(total_delta))
    if not pd.isna(total_delta):compare_numeric([change.delta.sum()],[total_delta],'Channel delta conservation')
    shares=table.div(monthly.applications,axis=0);shares.index.name='period'
    return monthly.reset_index(),table.rename_axis('period').reset_index(),shares.reset_index(),change


def main(argv=None):
    ctx=context('B20',argv);raw=ctx.source('applications_raw');reference=ctx.source('applications_reference');report_source=ctx.source('applications_report')
    books={'applications_raw':read_cached_book(raw),'applications_reference':read_cached_book(reference)}
    frame=prepare(pd.read_excel(raw,sheet_name='贷款申请表'))
    formulas=[]
    for name in ['贷款申请表','贷款申请表 (2)']:
        duplicate=prepare(pd.read_excel(reference,sheet_name=name));pd.testing.assert_frame_equal(frame,duplicate)
        sheet=books['applications_reference'][name]
        if len(sheet.formulas)!=len(frame):raise AssertionError('Incomplete month formulas')
        for row,date in enumerate(frame.date,2):
            expected=f'=YEAR(B{row})&"年"&MONTH(B{row})&"月"'
            if sheet.formulas.get(f'D{row}')!=expected or sheet.get(f'D{row}')!=f'{date.year}年{date.month}月':raise AssertionError('Month formula/cache differs')
        formulas.append({'sheet':name,'formula_cells':len(sheet.formulas),'cache_matches':len(frame)})
    monthly,counts,shares,changes=analyze(frame);sheet=books['applications_reference']['业务描述'];checks=[]
    m=monthly.set_index('period');c=counts.set_index('period');s=shares.set_index('period');g=changes.set_index('channel')
    for row in range(16,23):
        period=pd.Period(year=int(re.search(r'^(\d+)年',sheet.get(f'B{row}'))[1]),month=int(re.search(r'年(\d+)月',sheet.get(f'B{row}'))[1]),freq='M')
        check_cell(checks,sheet,f'C{row}',m.loc[period,'applications'],'monthly count')
        if row>16:check_cell(checks,sheet,f'D{row}',m.loc[period,'mom_growth'],'monthly growth')
        for col,channel in [('I','理财经理（柜台）'),('J','手机银行'),('K','自助机')]:check_cell(checks,sheet,f'{col}{row+1}',c.loc[period,channel],'channel monthly')
        check_cell(checks,sheet,f'L{row+1}',m.loc[period,'applications'],'monthly pivot total')
        for col,channel in [('C','理财经理（柜台）'),('D','手机银行'),('E','自助机')]:check_cell(checks,sheet,f'{col}{row+35}',s.loc[period,channel],'monthly share')
        check_cell(checks,sheet,f'F{row+35}',1,'monthly share total')
    check_cell(checks,sheet,'C23',len(frame),'total')
    for col,channel in [('I','理财经理（柜台）'),('J','手机银行'),('K','自助机')]:check_cell(checks,sheet,f'{col}24',c[channel].sum(),'channel total')
    check_cell(checks,sheet,'L24',len(frame),'grand total')
    for row,period in [(44,'2021-04'),(45,'2021-05')]:
        check_cell(checks,sheet,f'B{row}',m.loc[pd.Period(period),'applications'],'bridge total')
        for col,channel in [('C','自助机'),('D','理财经理（柜台）'),('E','手机银行')]:check_cell(checks,sheet,f'{col}{row}',c.loc[pd.Period(period),channel],'bridge count')
    check_cell(checks,sheet,'B46',g.delta.sum(),'net change');check_cell(checks,sheet,'B47',1,'saved contribution total')
    for col,channel in [('C','自助机'),('D','理财经理（柜台）'),('E','手机银行')]:
        check_cell(checks,sheet,f'{col}46',g.loc[channel,'delta'],'channel delta')
        check_cell(checks,sheet,f'{col}47',g.loc[channel,'change_over_absolute_net_change'],'mixed-sign saved convention')
    if sheet.formulas!={'D47':'=-58.974358974359%'}:raise AssertionError('Review changed source formula')
    formulas.append({'sheet':'业务描述','formula_cells':1,'cache_matches':1})
    for col,channel in [('C','理财经理（柜台）'),('D','手机银行'),('E','自助机')]:
        check_cell(checks,sheet,f'{col}58',g.loc[channel,'signed_share_of_net_change'],'signed net contribution')
        check_cell(checks,sheet,f'{col}59',(c[channel].sum()+g.loc[channel,'delta'])/(len(frame)+g.delta.sum()),'saved total includes difference row')
    check_cell(checks,sheet,'F58',1,'signed net sum');check_cell(checks,sheet,'F59',1,'saved average share sum')
    caches=chart_caches(reference,books['applications_reference'],['月度数量和环比双图','按月渠道构成，不重复总计'])
    checks=pd.DataFrame(checks);formula_table=pd.DataFrame(formulas)
    for name,data in [('monthly_applications',monthly),('monthly_channel_counts',counts),('monthly_channel_shares',shares),('channel_change',changes),('reference_checks',checks),('formula_audit',formula_table),('chart_map',caches)]:save_table(data,ctx.output/(name+'.csv'))
    save_table(frame,ctx.output/'applications_private.csv')
    with zipfile.ZipFile(report_source) as z:source_text=''.join(a.text or '' for a in ET.fromstring(z.read('word/document.xml')).iter() if a.tag.split('}')[-1]=='t')
    if not all(word in source_text for word in ['230','14.5%','58.97%','48.72%','7.69%']):raise AssertionError('Review source report summary')
    coverage=coverage_table(books,{('applications_raw','贷款申请表'):'唯一申请编号→月份与渠道数量，明细仅本地',('applications_reference','业务描述'):'需求、月度趋势、构成、两种贡献符号及非加权总计诊断',
        ('applications_reference','贷款申请表'):'与原始表一致；1597个年月公式核对',('applications_reference','贷款申请表 (2)'):'重复副本核对但不再计量；1597个年月公式核对'},ctx.output/'workbook-map.md')
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(15,10),layout='constrained');x=np.arange(len(monthly))
    ax[0,0].plot(x,monthly.applications,marker='o');ax[0,0].set_xticks(x,monthly.period.astype(str),rotation=25);ax[0,0].set(title='申请量按月变化',ylabel='笔')
    ax[0,1].bar(x,monthly.mom_growth*100,color='#087f8c');ax[0,1].set_xticks(x,monthly.period.astype(str),rotation=25);ax[0,1].axhline(0,color='gray',lw=.8);ax[0,1].set(title='环比不持续单向下降',ylabel='%')
    bottom=np.zeros(len(monthly))
    for channel in c.columns:ax[1,0].bar(x,c[channel],bottom=bottom,label=channel);bottom+=c[channel].to_numpy()
    ax[1,0].set_xticks(x,monthly.period.astype(str),rotation=25);ax[1,0].set_title('各月申请渠道构成');ax[1,0].legend(fontsize=8)
    ax[1,1].barh(changes.channel,changes.delta,color=np.where(changes.delta<0,'#d95f45','#087f8c'));ax[1,1].axvline(0,color='gray',lw=.8);ax[1,1].set(title='2021年5月相对4月：渠道数量增减',xlabel='笔')
    fig.savefig(ctx.output/'channel_attribution.png',dpi=150);plt.close(fig)
    report=f'''# B20 银行申请渠道贡献分解

1597个唯一申请，2020年11月至2021年5月，原始表与两个参考副本逐行一致，只计量一次。5月230笔，4月269笔，减少39笔，环比−14.4981%。柜台−23、手机银行−19、自助机+3，和为−39。

![渠道分解](channel_attribution.png)

标准有符号净变化贡献=各渠道增量/整体增量：柜台58.9744%、手机48.7179%、自助机−7.6923%，合计100%。自助机为抵消下降的正向数量变化，贡献负号并非渠道变差。增长贡献百分点=渠道增量/上月总量，合计为总体环比；不是各渠道环比的平均。

源C47:E47用各渠道增量/净变化绝对值，和为−100%，但B47标100%；C58:E58则使用净变化分母且和为100%。两种约定分别保留，主表明确命名不混用。源C59:E59“总计”符合把差异行−23/−19/+3再加入七个月总数、除以1597−39=1558的结果，不等于真实全期间769/1597、723/1597、105/1597；核查时只作旧表诊断，不把差异行当申请。

原DOCX的230笔、下降14.5%、58.97/48.72/−7.69%与本次按显示精度对应。报告称环比持续下降，但2021年4月较3月的环比从−3.9007%回升至−0.7380%，不是严格单调。5月柜台与手机合计210/230=91.3043%，没有曝光/工时/流量分母，不能据此计算渠道转化或客户经理工作压力变化。

宣传不足、APP路径过深是源报告提出的待验证解释，不能由申请量直接证实。机构协调可按分支机构分组随机试验，APP入口可按用户随机试验，预先确定总申请/转化口径和分母；跨渠道迁移与新增业务需分开。未开展实验，不编造效果。

4张工作表、3195个公式缓存均有去向（逐申请年月核对只汇总公开），{len(checks)}项数字缓存及{int(caches.cached_numeric_points.sum())}个图缓存逐项核查；保留稀疏图点索引，首月无环比不填0。整月无记录与观察月内某渠道0笔分开。无外部完整性证明，不把首末日期自动当完整自然月。

```powershell
python run_labs.py --lab B20
```
'''
    finish(ctx,{'lab_id':'B20','status':'reference_verified','applications':len(frame),'source_duplicates_match':True,'source_formula_cells':int(formula_table.formula_cells.sum()),
        'formula_cells_covered':int(formula_table.cache_matches.sum()),'numeric_reference_checks':len(checks),'chart_numeric_checks':int(caches.cached_numeric_points.sum()),'workbook_coverage':coverage},report)


if __name__=='__main__':main()
