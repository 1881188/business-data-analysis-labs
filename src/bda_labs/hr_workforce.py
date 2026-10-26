"""Reconstruct workforce stocks and flows from employment dates, without TODAY()."""
import argparse
import json
import re
import sys
import zipfile
import numpy as np
import pandas as pd
from .common import context, finish, plotting, save_table
from .tabular_tools import unique_key
from .workbook_reference import read_cached_book, coverage_table
from .pbix_audit import visual_audit

AGE_LABELS=['25岁以下','25—34岁','35—44岁','45—54岁','55岁及以上']


def day(value):
    result=pd.Timestamp(value)
    if pd.isna(result) or result.tzinfo is not None or result!=result.normalize():raise ValueError('Expected a date without time or timezone')
    return result


def prepare(raw):
    columns={'员工工号':'employee_id','姓名':'name','性别':'gender','部门':'department','职称':'title','职级':'grade',
             '出生日期':'birth','入职日期':'hired','离职日期':'left','员工状态':'source_status','文化程度':'education'}
    f=raw[list(columns)].rename(columns=columns).copy()
    for col in ['employee_id','name','department']:
        f[col]=f[col].astype('string').str.strip()
        if f[col].isna().any() or f[col].eq('').any():raise ValueError('Missing workforce identity or department')
    unique_key(f,'employee_id')
    for col in ['birth','hired','left']:
        values=f[col].replace(r'^\s*$',pd.NA,regex=True)
        f[col]=pd.to_datetime(values,errors='raise')
        if f[col].dt.tz is not None or f[col].dropna().ne(f[col].dropna().dt.normalize()).any():raise ValueError('Employment fields must be calendar dates')
    if f[['birth','hired']].isna().any().any():raise ValueError('Birth and hire dates are required')
    if f.birth.gt(f.hired).any() or (f.left.notna()&f.left.lt(f.hired)).any():raise ValueError('Impossible birth/hire/exit ordering')
    f['status_date_mismatch']=(f.source_status.eq('在职')&f.left.notna()) | (f.source_status.eq('离职')&f.left.isna()) | ~f.source_status.isin(['在职','离职'])
    return f


def age_years(birth,as_of):
    end=day(as_of)
    if birth.isna().any() or birth.gt(end).any():raise ValueError('Age requires observed birth dates on or before cutoff')
    before_anniversary=(end.month<birth.dt.month) | ((end.month==birth.dt.month)&(end.day<birth.dt.day))
    return (end.year-birth.dt.year-before_anniversary.astype(int)).astype('int64')


def analyze(frame,start,end):
    start,end=day(start),day(end)
    if start>end:raise ValueError('Start date follows end date')
    f=frame.copy()
    opening=f.hired.lt(start)&(f.left.isna()|f.left.ge(start))
    hires=f.hired.between(start,end)
    exits=f.left.between(start,end)
    closing=f.hired.le(end)&(f.left.isna()|f.left.gt(end))
    touched=opening|hires
    if int(opening.sum()+hires.sum()-exits.sum())!=int(closing.sum()):raise AssertionError('Workforce stock/flow equation failed')
    # Employment interval [hired, left): the exit date is excluded from day-end headcount.
    first=f.hired.clip(lower=start)
    last=f.left.fillna(end+pd.Timedelta(days=1)).clip(upper=end+pd.Timedelta(days=1))
    person_days=(last-first).dt.days.clip(lower=0)
    period_days=(end-start).days+1
    average=float(person_days.sum()/period_days)
    f['opening']=opening;f['hired_in_period']=hires;f['left_in_period']=exits;f['closing']=closing;f['touched']=touched
    f['person_days']=person_days
    f['age_at_cutoff']=age_years(f.birth,end)
    f['age_band']=pd.cut(f.age_at_cutoff,[0,25,35,45,55,np.inf],labels=AGE_LABELS,right=False)
    stop=f.left.fillna(end+pd.Timedelta(days=1)).clip(upper=end+pd.Timedelta(days=1))
    f['service_days_asof']=(stop-f.hired).dt.days.where(f.hired.le(end)).astype('Int64')
    m={'source_employee_records':len(f),'opening':int(opening.sum()),'hires':int(hires.sum()),'exits':int(exits.sum()),
       'closing':int(closing.sum()),'touched':int(touched.sum()),'person_days':int(person_days.sum()),'period_days':period_days,
       'average_daily_headcount':average,'period_exits_per_average_headcount':int(exits.sum())/average if average else None}
    return f,m


def monthly(frame,start,end):
    start,end=day(start),day(end);rows=[]
    for month in pd.period_range(start,end,freq='M'):
        left=max(start,month.start_time);right=min(end,month.end_time.normalize())
        _,m=analyze(frame,left,right)
        rows.append({'month':str(month),'start':left.date().isoformat(),'end':right.date().isoformat(),
                     'complete_calendar_month':left==month.start_time and right==month.end_time.normalize(),**m})
    result=pd.DataFrame(rows)
    if len(result)>1 and not np.array_equal(result.opening.iloc[1:].to_numpy(),result.closing.iloc[:-1].to_numpy()):raise AssertionError('Monthly stock continuity failed')
    return result


def grouping(snapshot,key):
    result=snapshot.groupby(key,dropna=False,observed=False).agg(
        opening=('opening','sum'),hires=('hired_in_period','sum'),exits=('left_in_period','sum'),
        closing=('closing','sum'),touched=('touched','sum'),person_days=('person_days','sum')).reset_index()
    if not result.opening.add(result.hires).sub(result.exits).eq(result.closing).all():raise AssertionError('Group stock/flow equation failed')
    return result


def saved_start(path):
    with zipfile.ZipFile(path) as z:layout=json.loads(z.read('Report/Layout').decode('utf-16le'))
    dates=set()
    for page in layout['sections']:
        for container in page.get('visualContainers',[]):
            config=json.loads(container.get('config','{}')).get('singleVisual',{})
            if config.get('visualType')=='slicer':
                dates.update(re.findall(r"datetime'(\d{4}-\d{2}-\d{2})T",json.dumps(config,ensure_ascii=False)))
    if len(dates)!=1:raise ValueError('Review the saved date slicer before choosing a default period')
    return day(next(iter(dates)))


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False)
    for name in ['start-date','end-date','department']:parser.add_argument('--'+name)
    options,remaining=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    ctx=context('B14',remaining);source=ctx.source('hr_employees');pbix=ctx.source('hr_pbix')
    all_frame=prepare(pd.read_excel(source,sheet_name='员工信息'))
    start=day(options.start_date) if options.start_date else saved_start(pbix)
    cutoff=max(all_frame.hired.max(),all_frame.left.max())
    end=day(options.end_date) if options.end_date else cutoff
    if end>cutoff:raise ValueError('End date exceeds the available event cutoff; no follow-up history supports extrapolation')
    frame=all_frame if options.department is None else all_frame[all_frame.department.eq(options.department)].copy()
    snapshot,m=analyze(frame,start,end);months=monthly(frame,start,end)
    if int(months.person_days.sum())!=m['person_days']:raise AssertionError('Monthly person-days do not conserve exposure')
    # Independent day-by-day enumeration verifies interval-based exposure and end stock.
    daily=pd.DataFrame([{'date':date.date().isoformat(),'headcount':int((frame.hired.le(date)&(frame.left.isna()|frame.left.gt(date))).sum())}
                        for date in pd.date_range(start,end)])
    if int(daily.headcount.sum())!=m['person_days'] or int(daily.headcount.iloc[-1])!=m['closing']:raise AssertionError('Daily enumeration differs from interval arithmetic')
    save_table(daily,ctx.output/'daily_headcount.csv');save_table(months,ctx.output/'monthly_workforce.csv')
    aggregates={}
    for key in ['department','age_band','gender','education']:
        data=grouping(snapshot,key);aggregates[key]=data;save_table(data,ctx.output/(key+'_workforce.csv'))
        for measure in ['opening','hires','exits','closing','touched','person_days']:
            if int(data[measure].sum())!=m[measure]:raise AssertionError('Demographic grouping lost workforce records')
    save_table(snapshot,ctx.output/'employees_private.csv')
    coverage=coverage_table({'hr_employees':read_cached_book(source)},
                           {('hr_employees','员工信息'):'日期事件→期初/入职/离职/期末、每日暴露、月份连续性与聚合；姓名及员工明细仅本地'},ctx.output/'workbook-map.md')
    destinations=['原创人力看板标题','显式start-date/end-date；默认起点读取保存日期，终点为最后已记录事件',
                  'age_band_workforce：期内曾任职、期内离职、期末在职并列比较','期初/入职/离职/期末及离职环比，当前状态列不替代历史时点',
                  'monthly_workforce：月份补齐，区分存量和流量','employees_private：身份、职级、任期明细只在本地']
    visuals=visual_audit(pbix,destinations);save_table(visuals,ctx.output/'pbix_visual_map.csv')
    last=months.iloc[-1];prior=months.iloc[-2] if len(months)>1 else None
    previous_exits=int(prior.exits) if prior is not None else None
    exit_change=(int(last.exits)-previous_exits)/previous_exits if previous_exits else None
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(14,10),layout='constrained');fig.suptitle(f'人力资源分析 · {start.date()} 至 {end.date()}',fontsize=16)
    ax[0,0].axis('off')
    for i,(label,key) in enumerate([('期初在职','opening'),('期间入职','hires'),('期间离职','exits'),('期末在职','closing')]):
        x=.03+(i%2)*.52;y=.84-(i//2)*.45;ax[0,0].text(x,y,label,transform=ax[0,0].transAxes);ax[0,0].text(x,y-.16,str(m[key]),transform=ax[0,0].transAxes,color='#087f8c',fontsize=27,weight='bold')
    x=np.arange(len(months));ax[0,1].plot(x,months.closing,marker='o',label='期末在职',color='#087f8c');ax[0,1].bar(x-.16,months.hires,width=.3,label='入职',alpha=.5);ax[0,1].bar(x+.16,months.exits,width=.3,label='离职',alpha=.5);ax[0,1].set_xticks(x,months.month,rotation=45);ax[0,1].set(title='月度存量与事件数（末月可能不完整）',ylabel='人数');ax[0,1].legend(fontsize=8)
    ages=aggregates['age_band'];x=np.arange(len(ages))
    for offset,key,label in [(-.25,'touched','期内曾任职'),(0,'exits','期内离职'),(.25,'closing','期末在职')]:ax[1,0].bar(x+offset,ages[key],width=.25,label=label)
    ax[1,0].set_xticks(x,ages.age_band,rotation=25);ax[1,0].set_title('以截止日周岁分组（指标不堆叠）');ax[1,0].legend(fontsize=8)
    departments=aggregates['department'];ax[1,1].barh(departments.department,departments.closing,color='#087f8c');ax[1,1].set(title='各部门期末在职',xlabel='人数')
    fig.savefig(ctx.output/'workforce_dashboard.png',dpi=150);plt.close(fig)
    report=f'''# B14 人力资源分析

## 范围与结果

源履历共{len(all_frame)}名不同工号员工。默认开始日期读取PBIX保存的切片器，截止日期冻结为最后一笔入/离职事件；本次为{start.date()}至{end.date()}，部门筛选为{options.department or '全部'}。事件截止不等于完整经营观察期，末月明确标记，不用运行当天日期外推。

| 指标 | 结果 | 定义 |
|---|---:|---|
| 期初在职 | {m['opening']} | 开始日前入职，且尚未在开始日前离职 |
| 期间入职 | {m['hires']} | 入职日期在闭区间内 |
| 期间离职 | {m['exits']} | 离职日期在闭区间内 |
| 期末在职 | {m['closing']} | 截止日已入职，离职日为空或晚于截止日 |
| 期内曾任职 | {m['touched']} | 期初人员与期间新入职人员的并集 |
| 在职人天 | {m['person_days']} | 每日收盘在职人数累计 |
| 平均每日在职 | {m['average_daily_headcount']:.6f} | 在职人天/区间自然日数 |

![人力看板](workforce_dashboard.png)

## 日期与分母

采用任职区间[入职日,离职日)，离职当天不计日末在职；同日入离职两类事件都计数，日末在职及暴露可为0。期初+入职−离职=期末，在各月和各维度均核查。源“员工状态”只是源快照，不直接用于过去时点。源状态与日期不一致共{int(all_frame.status_date_mismatch.sum())}条，保留诊断，不以状态覆盖事件。

最后一个月离职{int(last.exits)}人，上个已展示月为{previous_exits if previous_exits is not None else '未知'}人；相对变化为{f'{exit_change:.4%}' if exit_change is not None else '未知'}。末月可能只覆盖到某一天，不能当作两个完整月的同比表现。monthly_workforce.csv保留完整月标记。period_exits_per_average_headcount另作明确描述的区间事件/平均存量比，不年化，也不解释成个人离职概率。

年龄使用截止日周岁，按25岁以下、25—34、35—44、45—54、55岁及以上分组；2月29日出生在非闰年到3月1日递增。年龄分组边界是本实现明示约定，原PBIX未公开计算式。任职天数遵循同一日期区间，未来尚未入职者不填0。源部门没有变动历史，只能按提供部门标签分组，不推断历史转岗。

## 迁移和验证

PBIX6个容器均有去向，明细表仅写入本地employees_private.csv。未解码DataModel中的DAX，因此“员工人数”等未提供公式的源度量不冒充已逐值复现。Python分列来源总人数、期内曾任职和事件人数，避免混同存量与流量。

每日逐人枚举与区间人天独立核对，月份期末/下月期初连续，四组维度的六项指标守恒。没有独立参考数值，状态为运行通过。姓名、工号、生日、个人离职/任期数据不公开；公开只有聚合结果和方法。

```powershell
python run_labs.py --lab B14
python labs/cda1_business/b14_hr/main.py --start-date 2022-01-01 --end-date 2022-06-30 --output-root outputs/filtered
```

可选--department。截止日不得超出提供事件边界。筛选运行使用单独输出目录，公开报告只使用默认范围。
'''
    finish(ctx,{'lab_id':'B14','status':'execution_verified','selection':vars(options),
                'analysis_start':str(start.date()),'analysis_end':str(end.date()),'source_event_cutoff':str(cutoff.date()),
                'metrics':m,'last_month_complete':bool(last.complete_calendar_month),'previous_month_exits':previous_exits,
                'last_month_exit_relative_change':exit_change,'status_date_mismatches':int(all_frame.status_date_mismatch.sum()),
                'daily_enumeration_check':True,'monthly_continuity_check':True,'group_conservation_checks':24,
                'workbook_coverage':coverage,'pbix_visuals':len(visuals)},report)


if __name__=='__main__':main()
