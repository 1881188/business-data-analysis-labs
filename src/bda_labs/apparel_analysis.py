"""Apparel star model, weighted measures, monthly targets and observed cohorts.

Course-specific numerical results remain local because the supplied guide restricts
redistribution. Published figures are explicitly generated from synthetic inputs.
"""
import argparse
import json
import sys
import zipfile
from xml.etree import ElementTree as ET
import numpy as np
import pandas as pd
from .common import context, finish, plotting, save_table, write_json
from .tabular_tools import many_to_one, unique_key, money_minor
from .workbook_reference import coverage_table, read_cached_book
from .pbix_audit import visual_audit

SCHEMAS={
 '零售单':{'订单id':'order_id','订单编号':'order_number','订单日期id':'date_id','订单日期':'date','店铺id':'store_id','会员id':'member_id','员工id':'employee_id','数量':'quantity','零售金额':'list_amount','成交金额':'paid_amount'},
 '零售单明细':{'订单明细id':'detail_id','订单id':'order_id','商品id':'sku_id','数量':'quantity','折扣率':'saved_discount','标准价':'unit_list','零售金额':'list_amount','成交金额':'paid_amount'},
 '属性表':{'属性id':'attribute_id','属性名称':'attribute'},
 '颜色表':{'颜色id':'color_id','颜色编号':'color_code','颜色名称':'color'},
 '尺码表':{'尺码id':'size_id','尺码编号':'size_code','尺码名称':'size'},
 '员工表':{'员工id':'employee_id','员工工号':'employee_number','员工姓名':'employee','店铺id':'registered_store_id'},
 'SKU表':{'SKUid':'sku_id','款号id':'style_id','颜色id':'color_id','尺码id':'size_id'},
 '款号表':{'款号id':'style_id','品牌id':'brand_id','年份id':'season_year_id','季节id':'season_id','大类id':'category_id','成本':'unit_cost'},
 '店铺表':{'店铺id':'store_id','店铺名称':'store','商圈':'district','店铺面积':'area','品牌id':'store_brand_id'},
 'vip表':{'VIPid':'member_id'},
 '员工月目标表':{'年月':'year_month','员工id':'employee_id','基础目标':'base','挑战目标':'challenge','攀高目标':'high'},
 '店铺月目标表':{'年月':'year_month','店铺id':'store_id','基础目标':'base','挑战目标':'challenge','攀高目标':'high','连带率目标':'attachment_target'}
}


def positive_quantity(values):
    x=pd.to_numeric(values,errors='raise')
    if x.isna().any() or not np.isfinite(x).all() or (x<=0).any() or x.mod(1).ne(0).any():
        raise ValueError('The reviewed non-refund source requires positive integral quantities')
    return x.astype('int64')


def optional_dimension(frame,dimension,key,label):
    unique_key(dimension,key)
    out=frame.merge(dimension,on=key,how='left',validate='many_to_one')
    out[label+'_unfilled']=out[key].isna()
    out[label+'_unmatched']=out[key].notna() & out[label].isna()
    out[label]=out[label].fillna(pd.Series(np.where(out[key].isna(),'未填写','维表缺失'),index=out.index))
    return out


def reconcile_orders(header,detail):
    columns=['quantity','list_cents','paid_cents']
    totals=detail.groupby('order_id',as_index=False)[columns].sum()
    merged=header[['order_id',*columns]].merge(totals,on='order_id',how='outer',validate='one_to_one',suffixes=('_header','_detail'),indicator=True)
    if merged._merge.ne('both').any():raise ValueError('Header and detail order sets differ')
    for name in columns:
        if merged[name+'_header'].ne(merged[name+'_detail']).any():raise ValueError(f'Order-level {name} does not reconcile')
    return len(merged)*len(columns)


def build_model(book):
    if set(book)!=set(SCHEMAS):raise ValueError('Unexpected or missing source sheets')
    tables={}
    for name,columns in SCHEMAS.items():
        if set(columns)-set(book[name]):raise ValueError(f'Missing columns in {name}')
        tables[name]=book[name][list(columns)].rename(columns=columns).copy()
    h=tables['零售单'];d=tables['零售单明细'];stores=tables['店铺表'];attrs=tables['属性表'];sku=tables['SKU表'];styles=tables['款号表']
    for name,f in tables.items():
        key=['year_month','employee_id'] if name=='员工月目标表' else ['year_month','store_id'] if name=='店铺月目标表' else f.columns[0]
        unique_key(f,key)
    for f in [h,d]:
        f['quantity']=positive_quantity(f.quantity)
        for source,target in [('list_amount','list_cents'),('paid_amount','paid_cents')]:
            f[target]=money_minor(f[source])
            if (f[target]<0).any():raise ValueError('Refund accounting is not specified by this source version')
    h['date']=pd.to_datetime(h.date,errors='raise')
    if h.date.isna().any() or h.date_id.astype(str).ne(h.date.dt.strftime('%Y%m%d')).any():raise ValueError('Date key and date disagree')
    h['month']=h.date.dt.strftime('%Y-%m')
    h['basket_type']=np.where(h.quantity.eq(1),'1件',np.where(h.quantity.eq(2),'2件',np.where(h.quantity.eq(3),'3件','4件及以上')))
    if stores.area.isna().any() or not np.isfinite(stores.area).all() or stores.area.le(0).any():raise ValueError('Store area must be finite and positive')
    h=many_to_one(h,stores,on='store_id')
    h=optional_dimension(h,tables['员工表'],'employee_id','employee')
    h['member_unmatched']=h.member_id.notna() & ~h.member_id.isin(tables['vip表'].member_id)
    # A member ID is the documented membership indicator; no blank-ID pseudo-member.
    checks=reconcile_orders(h,d)
    for key,label in [('brand_id','brand'),('category_id','category'),('season_year_id','season_year'),('season_id','season')]:
        lookup=attrs.rename(columns={'attribute_id':key,'attribute':label})
        styles=many_to_one(styles,lookup,on=key)
    sku=many_to_one(sku,styles,on='style_id')
    sku=many_to_one(sku,tables['颜色表'][['color_id','color']],on='color_id')
    sku=many_to_one(sku,tables['尺码表'][['size_id','size']],on='size_id')
    d=many_to_one(d,sku,on='sku_id')
    columns=['order_id','order_number','date','month','store_id','store','area','member_id','employee_id','employee','employee_unfilled','employee_unmatched','registered_store_id','basket_type']
    f=many_to_one(d,h[columns],on='order_id')
    f['discount']=f.paid_cents/f.list_cents.replace(0,np.nan)
    f['unit_list_cents']=money_minor(f.unit_list)
    f['price_quantity_difference']=f.list_cents-f.unit_list_cents*f.quantity
    for name,key in [('员工月目标表','employee_id'),('店铺月目标表','store_id')]:
        t=tables[name]
        t['month']=pd.to_datetime(t.year_month.astype(str),format='%Y%m',errors='raise').dt.strftime('%Y-%m')
        if (~t[key].isin(tables['员工表'].employee_id if key=='employee_id' else stores.store_id)).any():raise ValueError('Target key is absent from its dimension')
        for col in ['base','challenge','high']:
            t[col+'_cents']=money_minor(t[col])
            if t[col+'_cents'].lt(0).any():raise ValueError('Negative monthly target')
    diagnostics={'order_reconciliation_values':checks,'header_rows':len(h),'detail_rows':len(f),
        'employee_unfilled_orders':int(h.employee_unfilled.sum()),'employee_unmatched_orders':int(h.employee_unmatched.sum()),
        'member_unmatched_orders':int(h.member_unmatched.sum()),'discount_above_one_rows':int(f.discount.gt(1).sum()),
        'saved_discount_differences':int((f.discount-f.saved_discount).abs().gt(1e-12).sum()),
        'unit_price_quantity_differences':int(f.price_quantity_difference.ne(0).sum()),
        'employee_registered_store_differences':int((h.employee_id.notna() & h.registered_store_id.ne(h.store_id)).sum())}
    return h,f,tables,diagnostics


def ratio(a,b):return float(a/b) if b else None


def measures(f,scope_stores):
    paid=int(f.paid_cents.sum())/100;listed=int(f.list_cents.sum())/100;orders=int(f.order_id.nunique());quantity=int(f.quantity.sum())
    members=f[f.member_id.notna()];n=int(members.member_id.nunique());member_sales=int(members.paid_cents.sum())/100
    unique_key(scope_stores,'store_id');area=float(scope_stores.area.sum())
    return {'paid':paid,'listed':listed,'discount':ratio(paid,listed),'members':n,'member_sales':member_sales,
            'member_average':ratio(member_sales,n),'orders':orders,'order_average':ratio(paid,orders),
            'quantity':quantity,'unit_average':ratio(paid,quantity),'attachment':ratio(quantity,orders),
            'sales_per_area':ratio(paid,area)}


def grouped(f,stores,keys):
    rows=[]
    for key,g in f.groupby(keys,dropna=False,sort=True):
        key=key if isinstance(key,tuple) else (key,)
        scope=stores[stores.store_id.isin(g.store_id.unique())] if 'store_id' in keys else stores
        rows.append({**dict(zip(keys,key)),**measures(g,scope)})
    return pd.DataFrame(rows,columns=[*keys,*measures(f.iloc[:0],stores)])


def weekly_comparison(f,stores,day):
    day=pd.Timestamp(day).normalize()
    first,last=f.date.min(),f.date.max()
    empty={key:None for key in measures(f.iloc[:0],stores)}
    values=[measures(f[f.date.dt.normalize().eq(d)],stores) if first<=d<=last else empty
            for d in [day,day-pd.Timedelta(days=7)]]
    relative={'paid','listed','member_average','order_average','unit_average'}
    rows=[]
    for name in ['paid','listed','discount','members','member_average','orders','order_average','quantity','unit_average','attachment']:
        current,previous=values[0][name],values[1][name]
        if current is None or previous is None:change=None
        elif name in relative:change=ratio(current-previous,previous)
        else:change=current-previous
        rows.append({'metric':name,'current':current,'previous_week_same_day':previous,'change':change,
                     'change_kind':'relative' if name in relative else 'percentage_point_fraction' if name=='discount' else 'absolute'})
    return pd.DataFrame(rows)


def target_completion(header,targets,key):
    # Monthly target is joined once to monthly actual, never to transaction rows.
    actual=header.groupby(['month',key],dropna=False,as_index=False).agg(paid_cents=('paid_cents','sum'),orders=('order_id','nunique'))
    unique_key(targets,['month',key])
    result=actual.merge(targets,on=['month',key],how='outer',validate='one_to_one',indicator=True)
    result['target_present']=result._merge.ne('left_only')
    result['has_sales']=result._merge.ne('right_only')
    first,last=header.date.min(),header.date.max()
    periods=pd.to_datetime(result.month+'-01')
    inside=periods.between(first.to_period('M').start_time,last.to_period('M').start_time) if pd.notna(first) else pd.Series(False,index=result.index)
    result['within_input_window']=inside
    result['window_covers_calendar_month']=periods.ge(first) & (periods+pd.offsets.MonthEnd(0)).le(last)
    for col in ['paid_cents','orders']:result.loc[inside,col]=result.loc[inside,col].fillna(0)
    for col in ['base','challenge','high']:
        result[col+'_completion']=result.paid_cents/result[col+'_cents'].replace(0,np.nan)
    return result.drop(columns='_merge')


def observed_cohorts(header):
    members=header[header.member_id.notna()][['member_id','date']].copy()
    if members.empty:return pd.DataFrame(columns=['cohort','age_month','cohort_members','repeat_members','repeat_rate','observed','complete_calendar_month'])
    members['period']=members.date.dt.to_period('M')
    members=members.drop_duplicates(['member_id','period'])
    first=members.groupby('member_id').period.min().rename('cohort')
    members=members.join(first,on='member_id');sizes=first.value_counts()
    observed=members.groupby(['cohort','period']).member_id.nunique()
    cutoff=header.date.max();last=cutoff.to_period('M');first_period=first.min()
    rows=[]
    for cohort,size in sizes.sort_index().items():
        for age in range(last.ordinal-first_period.ordinal+1):
            period=cohort+age;available=period<=last
            count=int(observed.get((cohort,period),0)) if available else None
            rows.append({'cohort':str(cohort),'age_month':age,'cohort_members':int(size),
                         'repeat_members':count,'repeat_rate':count/size if available else None,
                         'observed':available,'complete_calendar_month':bool(available and period.start_time>=header.date.min().normalize() and period.end_time.normalize()<=cutoff.normalize())})
    return pd.DataFrame(rows)


def demo_sources():
    """Wholly invented records, kept separate from every course-specific value."""
    orders=[(1,'2024-01-05',1,101,11,2,300,240),(2,'2024-01-12',2,102,12,1,100,80),
            (3,'2024-02-05',1,101,11,1,200,150),(4,'2024-02-20',1,103,None,1,100,90),
            (5,'2024-03-06',2,102,12,1,100,100),(6,'2024-03-20',1,101,11,1,100,75)]
    h=pd.DataFrame(orders,columns=['order_id','date','store_id','member_id','employee_id','quantity','list_amount','paid_amount'])
    h['date']=pd.to_datetime(h.date);h['order_number']=['DEMO'+str(i) for i in h.order_id];h['date_id']=h.date.dt.strftime('%Y%m%d').astype(int)
    d=pd.DataFrame([(1,1,1,1,.9,100,100,90),(2,1,2,1,.75,200,200,150),(3,2,1,1,.8,100,100,80),
                    (4,3,2,1,.75,200,200,150),(5,4,1,1,.9,100,100,90),(6,5,1,1,1.,100,100,100),(7,6,1,1,.75,100,100,75)],
                   columns=list(SCHEMAS['零售单明细'].values()))
    values={'零售单':h,'零售单明细':d,
        '属性表':pd.DataFrame([(1,'演示品牌'),(2,'演示上衣'),(3,'演示年'),(4,'演示季'),(5,'演示外套')],columns=['attribute_id','attribute']),
        '颜色表':pd.DataFrame([(1,'C','演示色')],columns=['color_id','color_code','color']),
        '尺码表':pd.DataFrame([(1,'M','演示码')],columns=['size_id','size_code','size']),
        '员工表':pd.DataFrame([(11,'E1','示例员工甲',1),(12,'E2','示例员工乙',2)],columns=list(SCHEMAS['员工表'].values())),
        'SKU表':pd.DataFrame([(1,1,1,1),(2,2,1,1)],columns=list(SCHEMAS['SKU表'].values())),
        '款号表':pd.DataFrame([(1,1,3,4,2,10),(2,1,3,4,5,20)],columns=list(SCHEMAS['款号表'].values())),
        '店铺表':pd.DataFrame([(1,'示例店甲','示例商圈',100,1),(2,'示例店乙','示例商圈',200,1)],columns=list(SCHEMAS['店铺表'].values())),
        'vip表':pd.DataFrame({'member_id':[101,102,103]}),
        '员工月目标表':pd.DataFrame([(202401,11,100,200,300)],columns=list(SCHEMAS['员工月目标表'].values())),
        '店铺月目标表':pd.DataFrame([(202401,1,500,700,900,1.5),(202402,1,400,600,800,1.5),(202403,2,300,400,500,1.5)],columns=list(SCHEMAS['店铺月目标表'].values()))}
    return {name:f.rename(columns={v:k for k,v in SCHEMAS[name].items()}) for name,f in values.items()}


def figures(f,stores,cohorts,targets,out,prefix,plt,synthetic=False):
    label='完全合成示例' if synthetic else '本地教材结果'
    m=measures(f,stores);monthly=grouped(f,stores,['month']);by_store=grouped(f,stores,['store_id','store'])
    fig,ax=plt.subplots(2,2,figsize=(14,9),layout='constrained');fig.suptitle('服装零售经营分析 · '+label,fontsize=17)
    ax[0,0].axis('off')
    cards=[('成交金额',m['paid']),('订单数',m['orders']),('客单价',m['order_average']),('连带率',m['attachment'])]
    for i,(name,value) in enumerate(cards):
        x=.02+(i%2)*.52;y=.84-(i//2)*.45;ax[0,0].text(x,y,name,transform=ax[0,0].transAxes);ax[0,0].text(x,y-.16,'未知' if value is None else f'{value:,.0f}' if name=='订单数' else f'{value:,.2f}',transform=ax[0,0].transAxes,fontsize=24,color='#087f8c',weight='bold')
    ax[0,1].plot(monthly.month,monthly.paid,color='#087f8c',marker='o');ax[0,1].tick_params(axis='x',rotation=60,labelsize=8);ax[0,1].set(title='月成交趋势',ylabel='成交金额（源单位未注明）')
    by_store=by_store.sort_values('paid');ax[1,0].barh(by_store.store,by_store.paid,color='#087f8c');ax[1,0].set_title('各店成交金额')
    cats=grouped(f,stores,['category'])[['category','paid']].sort_values('paid')
    many_categories=len(cats)>12
    if many_categories:
        rest=pd.DataFrame([{'category':'其余类别合计','paid':cats.iloc[:-12].paid.sum()}])
        cats=pd.concat([cats.iloc[-12:],rest],ignore_index=True).sort_values('paid')
    ax[1,1].barh(cats.category,cats.paid,color='#087f8c');ax[1,1].tick_params(axis='y',labelsize=9);ax[1,1].set_title('商品大类：前12类与其余合计' if many_categories else '商品大类成交金额')
    fig.savefig(out/(prefix+'dashboard.png'),dpi=150);plt.close(fig)
    q=targets[targets.target_present].copy();fig,ax=plt.subplots(figsize=(12,5),layout='constrained')
    if not q.empty:
        for col in ['base','challenge','high']:
            agg=q.groupby('month')[['paid_cents',col+'_cents']].sum(min_count=1)
            ax.plot(agg.index,agg.paid_cents/agg[col+'_cents'].replace(0,np.nan)*100,marker='o',label={'base':'基础','challenge':'挑战','high':'攀高'}[col])
    ax.axhline(100,color='#879eab',linestyle='--');ax.set(title=label+' · 有目标店铺的月度达成率',ylabel='同范围成交额/整月目标（%）');ax.tick_params(axis='x',rotation=45,labelsize=8);ax.legend()
    fig.savefig(out/(prefix+'targets.png'),dpi=150);plt.close(fig)
    matrix=cohorts.pivot(index='cohort',columns='age_month',values='repeat_rate')
    fig,ax=plt.subplots(figsize=(12,7 if len(matrix)>10 else 4),layout='constrained')
    if not matrix.empty:
        cmap=plt.get_cmap('YlGnBu').copy();cmap.set_bad('#e5e9ed')
        im=ax.imshow(matrix.to_numpy(),vmin=0,vmax=1,cmap=cmap,aspect='auto');fig.colorbar(im,ax=ax,label='当月购买人数/首个观察月人数')
        ax.set_yticks(range(len(matrix)),matrix.index);ax.set_xticks(range(len(matrix.columns)),matrix.columns)
    ax.set(title=label+' · 首次观察购买同期群',xlabel='首次观察月之后第几月\n灰色：未到观察月；窗口边界月可能不完整',ylabel='首次观察购买月')
    fig.savefig(out/(prefix+'cohorts.png'),dpi=150);plt.close(fig)


def workbook_metadata(path):
    # Metadata and formula count only; no contact details or embedded images exported.
    with zipfile.ZipFile(path) as archive:
        metadata=ET.fromstring(archive.read('xl/workbook.xml'))
        names=[e.attrib['name'] for e in metadata.iter() if e.tag.endswith('}sheet')]
        formulas=sum(len(ET.fromstring(archive.read(n)).findall('.//{*}f')) for n in archive.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'))
    return names,formulas


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--as-of',help='YYYY-MM-DD for same-weekday comparisons')
    options,remaining=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    ctx=context('B13',remaining);paths={key:ctx.source(key) for key in ['apparel_raw','apparel_raw_copy','apparel_guide','apparel_dictionary','apparel_pbix','apparel_metrics_image','apparel_store_image']}
    if ctx.sources['apparel_raw']['sha256']!=ctx.sources['apparel_raw_copy']['sha256']:raise ValueError('The duplicate course workbooks no longer match')
    book=pd.read_excel(paths['apparel_raw'],sheet_name=None)
    h,f,tables,diagnostics=build_model(book);stores=tables['店铺表'];m=measures(f,stores)
    for name,keys in [('monthly',['month']),('stores',['store_id','store']),('categories',['category']),('employees',['employee_id','employee']),('basket_types',['basket_type'])]:
        result=grouped(f,stores,keys);save_table(result,ctx.output/(name+'.csv'))
        if not np.isclose(result.paid.sum(),m['paid'],atol=1e-8,rtol=0):raise AssertionError('Grouped sales changed total')
    target=target_completion(h,tables['店铺月目标表'],'store_id');employee_target=target_completion(h,tables['员工月目标表'],'employee_id')
    cohorts=observed_cohorts(h)
    as_of=pd.Timestamp(options.as_of) if options.as_of else h.date.max()
    if pd.isna(as_of) or as_of!=as_of.normalize() or not h.date.min()<=as_of<=h.date.max():raise ValueError('as-of must be an observed-range date')
    comparison=weekly_comparison(f,stores,as_of)
    for name,value in [('store_month_targets',target),('employee_month_targets',employee_target),('cohorts',cohorts),('weekly_comparison',comparison),('prepared_details',f)]:save_table(value,ctx.output/(name+'.csv'))
    write_json(ctx.output/'private_summary.json',{'metrics':m,'diagnostics':diagnostics,'as_of':str(as_of.date())})
    coverage_books={};descriptions={};formula_count=0
    for key in ['apparel_raw','apparel_raw_copy','apparel_guide','apparel_dictionary']:
        names,count=workbook_metadata(paths[key]);coverage_books[key]={name:None for name in names};formula_count+=count
        for name in names:
            descriptions[(key,name)]=('重复原始文件，仅校验哈希及结构；计算只读取主副本' if key=='apparel_raw_copy' else
                '本地源输入→星型模型、指标、目标或同期群；不公开原数据' if key=='apparel_raw' else
                '只读教学说明；按代码中显式指标定义重建，内嵌说明图不复制')
    coverage=coverage_table(coverage_books,descriptions,ctx.output/'workbook-map.md')
    if formula_count:raise ValueError('New workbook formulas require an explicit migration mapping')
    # Retain metadata only locally: measure labels and display settings are course material.
    from .workbook_reference import pbix_visuals
    visuals=pbix_visuals(paths['apparel_pbix']);dest=[]
    for v in visuals:
        kind=v['kind'];fields=v['fields']
        if kind in ['shape','textbox','unknown','pageNavigator']:target_name='新报告版式与导航；不复制装饰'
        elif kind=='slicer':target_name='显式日期、店铺或分组范围；与报告说明对应'
        elif '目标' in fields:target_name='target_completion；目标先按月/主体聚合'
        elif '坪效' in fields:target_name='measures.sales_per_area；面积按店铺维表去重'
        elif kind=='multiRowCard':target_name='measures + weekly_comparison；会员成交总额与人均消费分别计算'
        else:target_name='grouped；按员工/大类/联单类型形成明细与汇总'
        dest.append(target_name)
    save_table(visual_audit(paths['apparel_pbix'],dest),ctx.output/'pbix_visual_map.csv')
    plt=plotting();figures(f,stores,cohorts,target,ctx.output,'local_',plt)
    demo_h,demo_f,demo_tables,_=build_model(demo_sources());demo_stores=demo_tables['店铺表']
    demo_cohorts=observed_cohorts(demo_h);demo_target=target_completion(demo_h,demo_tables['店铺月目标表'],'store_id')
    figures(demo_f,demo_stores,demo_cohorts,demo_target,ctx.output,'synthetic_',plt,synthetic=True)
    save_table(pd.DataFrame([measures(demo_f,demo_stores)]),ctx.output/'synthetic_metrics.csv')
    save_table(demo_cohorts,ctx.output/'synthetic_cohorts.csv');save_table(demo_target,ctx.output/'synthetic_targets.csv')
    metric_names={'paid':'成交金额','listed':'吊牌金额','discount':'折扣率','members':'会员人数','member_sales':'会员成交金额','member_average':'会员人均消费','orders':'订单数','order_average':'客单价','quantity':'件数','unit_average':'件单价','attachment':'连带率','sales_per_area':'坪效'}
    rows=['| 指标 | 结果 |','|---|---:|']
    for key,label_name in metric_names.items():
        value=m[key];text='未知' if value is None else f'{value:.4%}' if key=='discount' else f'{value:,}' if isinstance(value,int) else f'{value:,.4f}'
        rows.append(f'| {label_name} | {text} |')
    (ctx.output/'local_report.md').write_text('# B13 本地真实教材结果\n\n'+ '\n'.join(rows)+'\n\n同星期比较日期：'+str(as_of.date())+'。[周比较明细](weekly_comparison.csv)、[店铺月目标](store_month_targets.csv)、[员工月目标](employee_month_targets.csv)、[同期群](cohorts.csv)。真实案例结果只保存在本地。\n\n诊断：\n\n```json\n'+json.dumps(diagnostics,ensure_ascii=False,indent=2)+'\n```\n\n![本地结果](local_dashboard.png)\n\n![本地目标](local_targets.png)\n\n![本地同期群](local_cohorts.png)\n',encoding='utf-8')
    report='''# B13 服装零售经营分析

本实验已用本地配套数据运行，完成订单/明细星型关联、经营指标、同星期日比较、店铺与员工月目标、首次观察购买同期群。资料中的传播限制适用于原数据及案例内容，因此真实业务结果、原图、逐人信息和原说明文件均留在本地outputs/B13。此公开报告中的图与表完全由代码内的独立合成输入生成，不是教材真实结果，也不作为教材参考答案。

## 模型与计算口径

订单头以order_id唯一，明细以detail_id唯一。先逐订单核对数量、吊牌金额、成交金额，再把店铺、员工及SKU/款号/品牌/大类/年份/季节/颜色/尺码作为多对一维度关联。空会员ID表示非会员，不计成一个“空会员”；空销售人员与维表未匹配分开记录。订单所属店铺来自订单，不被员工当前登记店铺覆盖。会员联系字段不参与模型或输出。

![合成经营示例](synthetic_dashboard.png)

成交金额与吊牌金额按整数分汇总，折扣率为合计成交额/合计吊牌额，不平均逐行折扣。会员人均消费只以非空会员ID涉及的成交金额/去重会员数计算；客单价以总成交额/去重订单数计算；件单价以总成交额/件数；连带率以件数/订单数。数量与明细行数不同。坪效按所选店铺维表面积合计，面积只计一次。无分母时保留未知。

同星期比较对比指定日期与7天前：金额及人均/单均价格用相对变化；人数、单数、件数、连带率用绝对差；折扣率用比例差，显示为百分点。报告“环比”不混用日差、周总额和月变化。源PBIX中的会员成交额卡片字段与截图的人均标签存在差异，因此两项指标分别计算，不由标签猜测DAX。

## 月目标与同期群

月目标只按month×store_id或month×employee_id与相同粒度实际成交关联。目标不连接到订单明细逐行相加。无目标保持未知，目标为0时完成率未知；仅在输入时间窗口内，有目标而没有销售的月份实际为0，窗口外保持未知。边界月是否被输入日期覆盖整月另行标记，不擅自按日分摊目标。三个目标名称遵循源字段，不替换层级。月度目标图只汇总有目标的主体，分子与分母是同一主体范围。

![合成目标示例](synthetic_targets.png)

同期群以文件内首次观察到的会员购买月份为基准，每会员每月只计一次；后续购买人数/该首月人数为同期群月复购比例，第0月是群体基数。会员注册日或累计消费字段不替代首次观察购买日。观察窗口之前的购买历史未知，因此不能称为真实终身首次购买或新客获取。未来月份保持未知，末月是否完整另有标记。

![合成同期群示例](synthetic_cohorts.png)

## 异常、验证与边界

逐订单三项金额/数量守恒、维度唯一键、必需外键和分组金额守恒均在真实数据运行中检查。逐行保存折扣与成交/吊牌比例的差异、折扣大于1、标准价×数量与吊牌额不一致均进入本地诊断，保留原成交事实，不静默裁剪到100%或以维表价格覆盖。成本不在本次经营指标中推断利润。

原始文件的重复副本按SHA-256确认一致，仅计算一次；两份说明和两份原表的工作表都登记在[迁移对照](workbook-map.md)。Power BI容器映射留在本地；装饰、导航与内嵌模型不是额外实验。二进制DataModel未解码，不宣称全部DAX或像素复现。参考截图的同日指标与店铺周范围使用不同筛选，实际核对记录保留本地；公开状态为运行通过。

```powershell
python run_labs.py --lab B13
python labs/cda1_business/b13_apparel/main.py --as-of YYYY-MM-DD --output-root outputs/review
```

as-of仅选择“当日与7天前”的比较日期；月度目标及同期群仍使用完整输入，不用某一天的成交额冒充月度目标完成率。本地local_report.md、private_summary.json及相关CSV包含真实结果，文档构建器只发布明确允许的合成结果与方法报告。
'''
    finish(ctx,{'lab_id':'B13','status':'execution_verified','publication_scope':'original implementation and explicitly synthetic outputs only',
                'real_case_metrics_published':False,'workbook_coverage':coverage,'source_formula_cells':formula_count,'formula_cells_covered':formula_count,
                'source_duplicate_sha256_match':True,'local_validation':'order reconciliation, dimension integrity and grouped amount conservation passed',
                'synthetic_metrics':measures(demo_f,demo_stores)},report)


if __name__=='__main__':main()
