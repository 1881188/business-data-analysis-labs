"""Order/detail star model with explicit province and category filter context."""
import argparse
import json
import sqlite3
import sys
import zipfile
import numpy as np
import pandas as pd
from .common import context, finish, plotting, save_table
from .tabular_tools import many_to_one, unique_key, money_minor
from .pbix_audit import visual_audit


def build_model(orders, details, products, categories, employees):
    h=orders.rename(columns={'OrderID':'order_id','EmployeeID':'employee_id','ShipProvince':'province','OrderDate':'date'}).copy()
    d=details.rename(columns={'订单ID':'order_id','产口ID':'product_id','销售金额':'sales','销售成本':'cost'}).copy()
    p=products.rename(columns={'ProductID':'product_id','ProductName':'product','CategoryID':'category_id'}).copy()
    c=categories.rename(columns={'CategoryID':'category_id','CategoryName':'category'}).copy()
    e=employees.rename(columns={'EmployeeID':'employee_id','FullName':'employee'}).copy()
    unique_key(h,'order_id');unique_key(p,'product_id');unique_key(c,'category_id');unique_key(e,'employee_id')
    if h[['date','province','employee_id']].isna().any().any():raise ValueError('Missing order header fields')
    h['date']=pd.to_datetime(h.date,errors='raise')
    if h.date.isna().any():raise ValueError('Missing date')
    d['sales_cents']=money_minor(d.sales);d['cost_cents']=money_minor(d.cost)
    if (d[['sales_cents','cost_cents']]<0).any().any():raise ValueError('Refund semantics are not specified by this source')
    if (~h.order_id.isin(d.order_id)).any():raise ValueError('Header without detail requires source review')
    p=many_to_one(p,c[['category_id','category']],on='category_id')
    h=h.merge(e[['employee_id','employee']],on='employee_id',how='left',validate='many_to_one')
    h['employee_missing']=h.employee.isna();h['employee']=h.employee.fillna('雇员维表缺失')
    f=many_to_one(d,h,on='order_id');f=many_to_one(f,p[['product_id','product','category_id','category']],on='product_id')
    f['profit_cents']=f.sales_cents-f.cost_cents;f['month']=f.date.dt.strftime('%Y-%m')
    if len(f)!=len(d) or f.sales_cents.sum()!=d.sales_cents.sum():raise AssertionError('Model changed the detail grain')
    return h,f


def select(frame,year=None,month=None,province=None,category=None):
    if month is not None and not 1<=month<=12:raise ValueError('Month must be 1 through 12')
    mask=pd.Series(True,index=frame.index)
    if year is not None:mask &= frame.date.dt.year.eq(year)
    if month is not None:mask &= frame.date.dt.month.eq(month)
    if province is not None:mask &= frame.province.eq(province)
    if category is not None:mask &= frame.category.eq(category)
    return frame.loc[mask].copy()


def measures(frame):
    sales=int(frame.sales_cents.sum());cost=int(frame.cost_cents.sum())
    return {'sales_cents':sales,'cost_cents':cost,'profit_cents':sales-cost,
            'sales':sales/100,'cost':cost/100,'profit':(sales-cost)/100,
            'orders':int(frame.order_id.nunique()),'detail_rows':len(frame),
            'margin':(sales-cost)/sales if sales else None}


def group(frame,keys):
    out=frame.groupby(keys,dropna=False,as_index=False).agg(sales_cents=('sales_cents','sum'),cost_cents=('cost_cents','sum'),orders=('order_id','nunique'))
    out['profit_cents']=out.sales_cents-out.cost_cents
    for name in ['sales','cost','profit']:out[name]=out[name+'_cents']/100
    out['margin']=out.profit_cents/out.sales_cents.replace(0,np.nan)
    return out


def sqlite_check(frame,actual):
    with sqlite3.connect(':memory:') as conn:
        frame[['order_id','sales_cents','cost_cents']].to_sql('detail',conn,index=False)
        row=conn.execute('SELECT COALESCE(SUM(sales_cents),0), COALESCE(SUM(cost_cents),0), COUNT(DISTINCT order_id) FROM detail').fetchone()
    expected=(actual['sales_cents'],actual['cost_cents'],actual['orders'])
    if row!=expected:raise AssertionError('SQLite total differs')
    return 3


def report_states(path):
    with zipfile.ZipFile(path) as archive:layout=json.loads(archive.read('Report/Layout').decode('utf-16le'))
    rows=[]
    for page in layout['sections']:
        for n,v in enumerate(page.get('visualContainers',[]),1):
            visual=json.loads(v['config']).get('singleVisual',{})
            rows.append({'page':page.get('displayName'),'visual':n,'kind':visual.get('visualType'),
                         'container_filters':v.get('filters','[]'),
                         'slicer_general_state':json.dumps(visual.get('objects',{}).get('general',[]),ensure_ascii=False)})
    return pd.DataFrame(rows)


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False)
    for name in ['year','month']:parser.add_argument('--'+name,type=int)
    for name in ['province','category']:parser.add_argument('--'+name)
    options,remaining=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    ctx=context('B12',remaining)
    inputs={key:pd.read_csv(ctx.source('province_'+key),encoding='gb18030' if key in ['orders','details'] else 'utf-8-sig')
            for key in ['orders','details','products','categories','employees']}
    h,f=build_model(**inputs);selection=vars(options);chosen=select(f,**selection);m=measures(chosen)
    checks=sqlite_check(chosen,m);tables={}
    for name,keys in [('monthly',['month']),('provinces',['province']),('categories',['category_id','category']),('products',['product_id','product','category']),('employees',['employee_id','employee'])]:
        tables[name]=group(chosen,keys)
        for col in ['sales_cents','cost_cents','profit_cents']:
            if int(tables[name][col].sum())!=m[col]:raise AssertionError(f'{name} does not conserve {col}')
            checks+=1
        save_table(tables[name],ctx.output/(name+'.csv'))
    profile=pd.DataFrame([{'table':key,'rows':len(value),'columns':len(value.columns)} for key,value in inputs.items()]);save_table(profile,ctx.output/'table_profile.csv')
    missing=h[h.employee_missing].groupby('employee_id',as_index=False).agg(orders=('order_id','nunique'))
    save_table(missing,ctx.output/'missing_employees.csv');save_table(chosen,ctx.output/'selected_details.csv')
    path=ctx.source('province_pbix')
    visual=visual_audit(path,['measures.sales','measures.profit','当前明细中去重订单数；源头表非空卡片的分类筛选传播方向未解码',
        'year参数；保存切片器选择2020','monthly；源折线另存2020/Q3/August局部筛选，作为单独诊断',
        'categories占比','categories及products下钻表','provinces水平条图替代矩形树图','province参数','category参数','month参数'])
    save_table(visual,ctx.output/'pbix_visual_map.csv');save_table(report_states(path),ctx.output/'pbix_saved_states.csv')
    saved_scope=[]
    for label,year,month in [('saved_year_slicer',2020,None),('saved_line_visual',2020,8)]:
        saved_scope.append({'scope':label,**measures(select(f,year=year,month=month))})
    save_table(pd.DataFrame(saved_scope),ctx.output/'saved_scope_metrics.csv')
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(14,10),layout='constrained')
    fig.suptitle('分省销售分析 · '+('全量' if not any(v is not None for v in selection.values()) else json.dumps(selection,ensure_ascii=False)),fontsize=15)
    ax[0,0].axis('off')
    for i,(label,value) in enumerate([('销售金额',f"{m['sales']:,.2f}"),('利润',f"{m['profit']:,.2f}"),('可见订单数',str(m['orders'])),('利润率',f"{m['margin']:.2%}" if m['margin'] is not None else '无数据')]):
        x=.03+(i%2)*.52;y=.82-(i//2)*.46;ax[0,0].text(x,y,label,transform=ax[0,0].transAxes,color='#526675');ax[0,0].text(x,y-.17,value,transform=ax[0,0].transAxes,color='#087f8c',fontsize=22,weight='bold')
    monthly=tables['monthly'];ax[0,1].plot(monthly.month,monthly.sales,marker='o',color='#087f8c');ax[0,1].tick_params(axis='x',rotation=60,labelsize=8);ax[0,1].set(title='年月销售趋势',ylabel='金额（源表未注明货币单位）')
    for axis,name,label,title in [(ax[1,0],'provinces','province','各省销售金额'),(ax[1,1],'categories','category','商品类别销售金额')]:
        q=tables[name].sort_values('sales');axis.barh(q[label],q.sales,color='#087f8c');axis.tick_params(axis='y',labelsize=9);axis.set(title=title,xlabel='金额（源表未注明货币单位）')
    fig.savefig(ctx.output/'province_dashboard.png',dpi=150);plt.close(fig)
    report=f'''# B12 分省销售分析

从订单头、商品明细、商品、类别和雇员五张CSV表建立星型分析。订单头{len(h)}行、明细{len(f)}行；商品按ProductID连接，两个同名商品不能按名称合并。源明细列“产口ID”显式映射为product_id，未改原文件。

## 当前范围与结果

筛选：`{json.dumps(selection,ensure_ascii=False)}`。所有Python指标及维度表共用当前可见明细；年份与月份用数值字段，趋势保留年月。

| 指标 | 结果 | 定义 |
|---|---:|---|
| 销售金额 | {m['sales']:,.2f} | 明细销售金额合计 |
| 销售成本 | {m['cost']:,.2f} | 明细销售成本合计 |
| 利润 | {m['profit']:,.2f} | 销售金额−销售成本 |
| 可见订单数 | {m['orders']} | 当前明细订单ID去重 |
| 利润率 | {f"{m['margin']:.6%}" if m['margin'] is not None else '无数据'} | 合计利润/合计销售金额 |

![分省销售看板](province_dashboard.png)

金额用整数分，货币单位源表未注明。类别/商品订单数可能交叉，不把各类去重订单数相加当总订单数；各省、月份也分别计算去重订单数。商品层下钻表保留product_id，名称重复不误并。

## 关联与来源问题

订单明细→订单头→雇员及明细→商品→类别均为多对一，禁止维度重复键、关键关联缺失及空主键。雇员维表缺少的员工涉及{int(h.employee_missing.sum())}单，保留订单和金额并标为“雇员维表缺失”，不内连接删单。诊断见missing_employees.csv。订单头按主键验证唯一，不把头表数量按明细行重复计算。

PBIX共11个容器全部映射。保存的年份切片器选择2020，而折线还保存了2020年第三季度August的局部筛选；这两个范围不同。pbix_saved_states.csv保留实际过滤状态，saved_scope_metrics.csv分别重算两个范围。默认Python展示全部输入年份，显式参数可选原范围，不将局部折线伪装成全年趋势。

源订单数卡片用头表OrderID非空计数；分类筛选是否反向传播到头表依赖二进制模型关系，未解码确认。Python明确定义为当前可见商品明细涉及的去重订单，不宣称所有筛选下与原卡片等价。sales/利润计算列在PBIX中没有可读取公式，因此用已提供销售金额、销售成本作透明定义，不假定税费、退款或折扣。源矩形树图迁移为便于比较的省份水平条形图。

## 验证与运行

{checks}项检查通过：SQLite独立汇总金额/成本/去重订单，五组维度表各三项金额守恒。没有独立参考数值，状态为运行通过。原始表、雇员姓名和选中订单明细只留本地。

```powershell
python run_labs.py --lab B12
python labs/cda1_business/b12_province/main.py --year 2020 --month 8 --output-root outputs/filtered
```

支持--year、--month、--province、--category。无匹配时合计为0、利润率未知；筛选结果使用独立输出目录，公开报告只接受无筛选全量运行。
'''
    finish(ctx,{'lab_id':'B12','status':'execution_verified','selection':selection,'metrics':m,
                'source_orders':len(h),'source_details':len(f),'missing_employee_orders':int(h.employee_missing.sum()),
                'checks':checks,'pbix_visuals':len(visual)},report)


if __name__=='__main__':main()
