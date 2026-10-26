"""Retail sales measures with one filter context and exact minor-unit arithmetic."""
import argparse
from decimal import Decimal, InvalidOperation
import json
import sys
import numpy as np
import pandas as pd
from .common import context, finish, plotting, save_table
from .workbook_reference import read_cached_book, coverage_table
from .pbix_audit import visual_audit, AGGREGATION_SOURCE

COLUMNS = {'订单号':'order_id','订单时间':'ordered_at','实际支付':'payment',
           '城市':'city','数量':'quantity','商品名称':'product','商品类别':'category'}


def to_cents(value):
    try: amount=Decimal(str(value))*100
    except InvalidOperation as exc: raise ValueError('Invalid payment') from exc
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError('Payments must be finite and have no fractional cents')
    if amount < 0: raise ValueError('This non-refund dataset requires nonnegative payments')
    return int(amount)


def prepare(raw):
    if set(COLUMNS)-set(raw.columns):raise ValueError('Missing retail source columns')
    frame=raw[list(COLUMNS)].rename(columns=COLUMNS).copy()
    if frame.isna().any().any():raise ValueError('Missing retail values require an explicit source review')
    for name in ['order_id','city','product','category']:
        frame[name]=frame[name].astype(str).str.strip()
        if frame[name].eq('').any():raise ValueError(f'Blank {name}')
    if frame.duplicated().any():raise ValueError('Exact duplicate detail rows require review, not silent deletion')
    frame['ordered_at']=pd.to_datetime(frame.ordered_at,errors='raise')
    if frame.ordered_at.isna().any():raise ValueError('Missing order time')
    frame['cents']=frame.payment.map(to_cents)
    frame['quantity']=pd.to_numeric(frame.quantity,errors='raise')
    if not np.isfinite(frame.quantity).all() or (frame.quantity<=0).any() or frame.quantity.mod(1).ne(0).any():
        raise ValueError('Quantity must be a positive integer')
    frame['quantity']=frame.quantity.astype('int64')
    for column in ['ordered_at','city']:
        if frame.groupby('order_id')[column].nunique().gt(1).any():
            raise ValueError(f'Conflicting {column} for the same order')
    frame['date']=frame.ordered_at.dt.strftime('%Y-%m-%d')
    return frame


def date_boundary(value):
    if value is None:return None
    try:
        stamp=pd.Timestamp(value)
    except (ValueError,TypeError) as exc:raise ValueError('Date must use YYYY-MM-DD') from exc
    if stamp.tzinfo is not None or stamp!=stamp.normalize() or str(value)!=stamp.strftime('%Y-%m-%d'):
        raise ValueError('Date must use YYYY-MM-DD')
    return stamp


def select(frame,start=None,end=None,city=None,category=None):
    first,last=date_boundary(start),date_boundary(end)
    if first is not None and last is not None and first>last:raise ValueError('Start date follows end date')
    mask=pd.Series(True,index=frame.index)
    if first is not None:mask &= frame.ordered_at.ge(first)
    if last is not None:mask &= frame.ordered_at.lt(last+pd.Timedelta(days=1))
    if city is not None:mask &= frame.city.eq(city)
    if category is not None:mask &= frame.category.eq(category)
    return frame.loc[mask].copy()


def metrics(frame):
    count=int(frame.order_id.nunique());cents=int(frame.cents.sum())
    return {'rows':len(frame),'order_count':count,'nonnull_order_id_count':int(frame.order_id.count()),
            'payment_cents':cents,'payment':cents/100,'quantity':int(frame.quantity.sum()),
            'payment_per_order':cents/100/count if count else None,
            'zero_payment_rows':int(frame.cents.eq(0).sum())}


def aggregate(frame,keys):
    data=frame.groupby(keys,dropna=False,as_index=False).agg(
        payment_cents=('cents','sum'),quantity=('quantity','sum'),order_count=('order_id','nunique'),
        detail_rows=('order_id','size'))
    data['payment']=data.payment_cents/100
    data['payment_per_order']=data.payment/data.order_count
    return data


def write_html(cube,path):
    # Each source order is one row: day/city/category groups are disjoint order sets.
    # Customer/order IDs, timestamps, product names and individual rows are omitted.
    payload=json.dumps(cube[['date','city','category','payment_cents','quantity','order_count']].to_dict('records'),ensure_ascii=False).replace('<','\\u003c')
    template='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>B11 零售销售看板</title><style>
*{box-sizing:border-box}body{margin:0;background:#f2f5f7;color:#203442;font:16px system-ui,"Microsoft YaHei",sans-serif}main{max-width:1160px;margin:auto;padding:32px}h1{font-size:30px;margin:0 0 8px}p{line-height:1.7;color:#526675}.filters,.cards,.tables{display:grid;gap:14px}.filters{grid-template-columns:repeat(4,1fr);margin:24px 0}label{display:grid;gap:8px}input,select{font:inherit;padding:10px;border:1px solid #bbcbd3;border-radius:6px;background:white}.cards{grid-template-columns:repeat(4,1fr)}article,section{padding:20px;background:white;border-radius:10px;box-shadow:0 2px 10px #16324509}article b{display:block;font-size:27px;margin-top:10px}.tables{grid-template-columns:1fr 1fr;margin-top:18px}section{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:9px 5px;border-bottom:1px solid #e4eaee;text-align:right}th:first-child,td:first-child{text-align:left}.bar{display:block;height:5px;background:#087f8c;margin-top:5px}h2{font-size:19px}button{margin-top:14px;padding:8px 16px;font:inherit;cursor:pointer}#scope{min-height:24px}@media(max-width:760px){main{padding:18px}.filters,.cards,.tables{grid-template-columns:1fr 1fr}.tables section{grid-column:1/-1}article b{font-size:22px}}
</style><main><h1>零售销售看板</h1><p>2022年4月教材样本。调整日期、城市和商品类别后，全部指标使用相同筛选范围。支付额按原“实际支付”汇总，货币单位源表未注明。</p>
<div class="filters"><label>开始日期<input id="start" type="date"></label><label>结束日期<input id="end" type="date"></label><label>城市<select id="city"></select></label><label>商品类别<select id="category"></select></label></div><button id="reset">恢复全量</button><p id="scope" role="status"></p>
<div class="cards"><article>实际支付额<b id="payment"></b></article><article>订单数<b id="orders"></b></article><article>销售数量<b id="quantity"></b></article><article>每单平均支付<b id="average"></b></article></div>
<div class="tables"><section><h2>每日销售</h2><div id="daily"></div></section><section><h2>商品类别</h2><div id="categories"></div><h2>城市销售</h2><div id="cities"></div></section></div>
<p>离线页面仅嵌入“日期×城市×类别”聚合数据，没有订单号、客户标识、商品明细或外部依赖。本数据版本每行一个唯一订单，因此分组订单数可相加；Python仍分别核对非空计数与去重计数。无匹配时每单平均支付显示“无数据”。</p>
</main><script>const rows=__DATA__;const $=id=>document.getElementById(id),fmt=(n,d=0)=>n.toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
for(const key of ['city','category']){$(key).innerHTML='<option value="">全部</option>'+[...new Set(rows.map(r=>r[key]))].sort().map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('')}
const dates=rows.map(r=>r.date).sort(),lo=dates[0],hi=dates[dates.length-1];
function reset(){$('start').value=lo;$('end').value=hi;$('city').value='';$('category').value='';render()}
function group(data,key){const map=new Map();for(const r of data){const v=map.get(r[key])||{name:r[key],cents:0,orders:0,quantity:0};v.cents+=r.payment_cents;v.orders+=r.order_count;v.quantity+=r.quantity;map.set(r[key],v)}return [...map.values()]}
function table(data,sort){data.sort(sort);const max=Math.max(1,...data.map(r=>r.cents));return '<table><thead><tr><th>分组</th><th>支付额</th><th>订单数</th><th>数量</th></tr></thead><tbody>'+data.map(r=>`<tr><td>${esc(r.name)}<span class="bar" style="width:${100*r.cents/max}%"></span></td><td>${fmt(r.cents/100,2)}</td><td>${fmt(r.orders)}</td><td>${fmt(r.quantity)}</td></tr>`).join('')+'</tbody></table>'}
function render(){const start=$('start').value,end=$('end').value,invalid=start&&end&&start>end;const data=invalid?[]:rows.filter(r=>(!start||r.date>=start)&&(!end||r.date<=end)&&(!$('city').value||r.city===$('city').value)&&(!$('category').value||r.category===$('category').value));const total=data.reduce((a,r)=>({cents:a.cents+r.payment_cents,orders:a.orders+r.order_count,quantity:a.quantity+r.quantity}),{cents:0,orders:0,quantity:0});$('scope').textContent=invalid?'开始日期不能晚于结束日期':`${start||'不限'} 至 ${end||'不限'}；${$('city').value||'全部城市'}；${$('category').value||'全部类别'}；${total.orders?'当前筛选结果':'无匹配订单'}`;$('payment').textContent=fmt(total.cents/100,2);$('orders').textContent=fmt(total.orders);$('quantity').textContent=fmt(total.quantity);$('average').textContent=total.orders?fmt(total.cents/100/total.orders,2):'无数据';$('daily').innerHTML=table(group(data,'date'),(a,b)=>a.name.localeCompare(b.name));for(const [id,key] of [['categories','category'],['cities','city']])$(id).innerHTML=table(group(data,key),(a,b)=>b.cents-a.cents)}
for(const id of ['start','end','city','category'])$(id).addEventListener('change',render);$('reset').addEventListener('click',reset);reset();</script></html>'''
    path.write_text(template.replace('__DATA__',payload),encoding='utf-8')


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False)
    for name in ['start-date','end-date','city','category']:parser.add_argument('--'+name)
    options,remaining=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    ctx=context('B11',remaining)
    raw_path=ctx.source('retail_orders');raw=pd.read_excel(raw_path,dtype={'订单号':str})
    full=prepare(raw);selected=select(full,options.start_date,options.end_date,options.city,options.category)
    m=metrics(selected)
    if full.order_id.duplicated().any():
        raise ValueError('The offline aggregate dashboard requires the reviewed one-row-per-order source version')
    independent_cents=sum(to_cents(v) for v in raw['实际支付'])
    if int(full.cents.sum())!=independent_cents:raise AssertionError('Source payment reconciliation failed')
    tables={name:aggregate(selected,[key]) for name,key in [('daily','date'),('categories','category'),('cities','city'),('products','product')]}
    controls=[]
    for name,data in tables.items():
        for col,total in [('payment_cents',m['payment_cents']),('quantity',m['quantity']),('order_count',m['order_count'])]:
            actual=int(data[col].sum())
            if actual!=total:raise AssertionError(f'{name}/{col}: aggregation does not reconcile')
            controls.append({'table':name,'measure':col,'expected':total,'actual':actual,'difference':actual-total})
        save_table(data.sort_values('date' if name=='daily' else 'payment_cents',ascending=name=='daily'),ctx.output/f'{name}.csv')
    cube=aggregate(full,['date','city','category']);save_table(cube,ctx.output/'daily_city_category.csv')
    write_html(cube,ctx.output/'dashboard.html')
    save_table(pd.DataFrame([m]),ctx.output/'metrics.csv');save_table(pd.DataFrame(controls),ctx.output/'reconciliation.csv')
    visuals=visual_audit(ctx.source('retail_pbix'),[
        '实际支付额：sum(实际支付)，按整数分汇总','销售数量：sum(数量)，不再次乘支付额','看板标题',
        'categories；products为本地商品下钻表；原标题“各城市支付额”与类别字段不符，按字段修正标题',
        '日期区间：CLI起止日与离线HTML筛选','Function=5非空订单号计数，queryRef的Min名称已过时；另算nunique',
        'cities水平条形图，无坐标资料，不编造经纬度','daily日期趋势；按日期派生年/季/月/日',
        '第2页同步日期切片器：共用同一筛选上下文'])
    save_table(visuals,ctx.output/'pbix_visual_map.csv')
    books={'retail_orders':read_cached_book(raw_path)}
    coverage=coverage_table(books,{('retail_orders',s):'7列订单表→prepare→select→metrics/aggregate→PNG及离线HTML'
                                 for s in books['retail_orders']},ctx.output/'workbook-map.md')
    save_table(selected,ctx.output/'selected_rows.csv')
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(14,10),layout='constrained')
    scope=' / '.join([f'{options.start_date or full.date.min()}—{options.end_date or full.date.max()}',options.city or '全部城市',options.category or '全部类别'])
    fig.suptitle('零售销售看板 · '+scope,fontsize=16)
    ax[0,0].axis('off')
    cards=[('实际支付额',f"{m['payment']:,.2f}"),('订单数',f"{m['order_count']:,}"),('销售数量',f"{m['quantity']:,}"),('每单平均支付',f"{m['payment_per_order']:,.2f}" if m['payment_per_order'] is not None else '无数据')]
    for i,(label,value) in enumerate(cards):
        x=.02+(i%2)*.52;y=.85-(i//2)*.48;ax[0,0].text(x,y,label,transform=ax[0,0].transAxes,color='#526675');ax[0,0].text(x,y-.17,value,transform=ax[0,0].transAxes,fontsize=23,color='#087f8c',weight='bold')
    daily=tables['daily'];ax[0,1].plot(pd.to_datetime(daily.date),daily.payment,color='#087f8c',marker='o',markersize=3);ax[0,1].tick_params(axis='x',rotation=35,labelsize=8);ax[0,1].set(title='每日实际支付额',ylabel='支付额（货币单位未注明）')
    for axis,name,label in [(ax[1,0],'categories','category'),(ax[1,1],'cities','city')]:
        data=tables[name].sort_values('payment');axis.barh(data[label],data.payment,color='#087f8c');axis.tick_params(axis='y',labelsize=9);axis.set(title='商品类别支付额' if label=='category' else '各城市支付额',xlabel='支付额（货币单位未注明）')
    fig.savefig(ctx.output/'retail_dashboard.png',dpi=150);plt.close(fig)
    selection={'start_date':options.start_date,'end_date':options.end_date,'city':options.city,'category':options.category}
    report=f'''# B11 基础零售销售看板

## 范围与结果

配套零售订单表共{len(full)}行、{full.order_id.nunique()}个唯一订单、7个字段，时间为{full.ordered_at.min()}至{full.ordered_at.max()}，包含{full.city.nunique()}个城市、{full.category.nunique()}个商品类别；无缺失、无重复订单号、无完全重复行。当前筛选为`{json.dumps(selection,ensure_ascii=False)}`，选中{m['rows']}行。

| 指标 | 当前结果 | 定义 |
|---|---:|---|
| 实际支付额 | {m['payment']:,.2f} | 逐行实际支付求和，不再乘数量 |
| 订单数 | {m['order_count']:,} | 订单号去重计数 |
| 非空订单号计数 | {m['nonnull_order_id_count']:,} | 与PBIX保存的Function=5配置对应 |
| 销售数量 | {m['quantity']:,} | 数量求和 |
| 每单平均支付 | {str(round(m['payment_per_order'],6)) if m['payment_per_order'] is not None else '无数据'} | 当前支付额/当前唯一订单数 |

金额按整数分计算后展示，不假设未注明的币种。{m['zero_payment_rows']}条零支付记录保留；没有订单状态、退款或成本字段，不能把零支付自动当成取消，也不推断净收入、利润或转化率。

![零售销售看板](retail_dashboard.png)

[打开离线交互看板](dashboard.html)：下载后用浏览器打开。内嵌全量日期×城市×类别聚合数据，筛选日期、城市、类别会同步更新4个指标和3组明细表。GitHub文件预览不会执行HTML。该页面默认全量，独立于本次CLI筛选；本报告及PNG、CSV使用上述CLI范围。

## 迁移与筛选口径

PBIX两页9个视觉容器全部映射在pbix_visual_map.csv。支付额与数量卡片按Sum；订单号卡片queryRef为Min(sheet1.订单号)，实际Function=5为CountNonNull，并非最小订单号。枚举依据[微软表达式说明]({AGGREGATION_SOURCE})。本版本每行一个唯一订单，因此非空计数与去重计数都为6644（全量）。未来多商品明细必须重新审查，不能直接相加分组订单数。

源柱图标题写“各城市支付额”，字段却是商品类别/商品名称，Python按字段命名为商品类别支付额；商品级下钻products.csv仅在本地输出。源地图只有城市名，没有坐标，改用城市排序条形图。源日期层级迁移为显式日期列，可按年、季度、月份再汇总；默认按日展示。二进制DataModel未解码，未宣称参考PBIX显示值已逐项对账。

CLI日期用YYYY-MM-DD，结束日包含全天，以次日00:00为排他上界。所有指标、每日、类别、城市、商品表共用同一筛选。无匹配订单时支付与数量为0，每单平均支付保持未知。原始输入只读，重复明细、空值、非整数数量和超过两位小数的金额都会报错，避免静默改口径。

## 验证边界

{len(controls)}项分组守恒检查全部通过，支付额以整数分精确相等。独立从原始支付列累加核对全量总额；这些是输入及内部计算检查，没有独立参考答案，因此状态为运行通过。工作表去向见[工作表对照](workbook-map.md)。订单明细和商品下钻表不公开。

```powershell
python labs/cda1_business/b11_retail/main.py --start-date 2022-04-01 --end-date 2022-04-07 --city 广州市 --output-root outputs/filtered
```

生成的过滤结果写入单独目录，默认全量公开报告使用无筛选运行结果。离线HTML用相同日期边界与分母；不同商品可分属同一订单时，必须先改变聚合模型，现有脚本会拒绝该数据版本。
'''
    finish(ctx,{'lab_id':'B11','status':'execution_verified','metrics':m,'selection':selection,
                'source_rows':len(full),'source_unique_orders':int(full.order_id.nunique()),
                'full_source_payment_cents':independent_cents,'workbook_coverage':coverage,
                'pbix_visuals':len(visuals),'aggregate_checks':len(controls),'aggregate_cube_rows':len(cube),
                'public_dashboard_grain':'date x city x category; one row per unique order verified before aggregation'},report)


if __name__=='__main__':main()
