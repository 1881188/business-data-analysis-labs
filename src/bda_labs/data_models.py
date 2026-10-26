"""B01: relational keys, bridge tables, snowflake dimensions and aggregation grain."""
import json,re,sqlite3
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table
from .tabular_tools import unique_key,many_to_one,money_minor
from .workbook_reference import pbix_visuals,read_cached_book


def prepare_mall(tables):
    fact=tables['产品销售数据表'].rename(columns=lambda c:c.strip()).copy()
    original_ids=fact.产品编号.astype(str)
    fact['产品编号']=original_ids.str.upper()
    products=tables['产品信息表'].copy();products['产品编号']=products.产品编号.astype(str).str.upper()
    for table,key in [(products,'产品编号'),(tables['品牌'],'品牌名称'),(tables['类别'],'产品类别'),
                      (tables['商铺城市'],'商铺城市'),(tables['日期表'],'日期')]:unique_key(table,key)
    product=many_to_one(products,tables['品牌'],on='品牌名称')
    product=many_to_one(product,tables['类别'],on='产品类别')
    product=product.rename(columns={'产品名称':'dim_product','品牌名称':'dim_brand','产品类别':'dim_category','销售单价':'dim_price'})
    enriched=many_to_one(fact,product,on='产品编号')
    if any(enriched[a].ne(enriched[b]).any() for a,b in [('产品名称','dim_product'),('品牌名称','dim_brand'),('产品类别','dim_category')]):
        raise ValueError('Redundant fact attributes conflict with the product dimension')
    price_difference=enriched.销售单价.ne(enriched.dim_price)
    enriched=many_to_one(enriched,tables['商铺城市'],on='商铺城市')
    dates=tables['日期表'].rename(columns={'日期':'订单日期'})
    enriched=many_to_one(enriched,dates,on='订单日期')
    quantities=pd.to_numeric(fact.销售数量,errors='raise').to_numpy(dtype=float)
    if not np.isfinite(quantities).all() or (quantities<0).any() or (quantities%1!=0).any():raise ValueError('Expected nonnegative whole-unit quantities')
    amounts=money_minor(fact.销售单价)*quantities.astype(np.int64)
    cached=money_minor(fact.销售额)
    enriched['sales_minor']=amounts
    if len(enriched)!=len(fact) or enriched.sales_minor.sum()!=amounts.sum():raise AssertionError('Dimension join changed the fact grain')
    return enriched,{'rows':len(fact),'normalized_product_keys':int(original_ids.ne(fact.产品编号).sum()),
                     'cached_sales_values_compared':len(fact),'row_business_mismatches':int((amounts!=cached).sum()),'sales_minor':int(amounts.sum()),
                     'source_cached_sales_minor':int(cached.sum()),'cached_minus_recomputed_minor':int((cached-amounts).sum()),
                     'distinct_observed_dates':int(fact.订单日期.nunique()),'calendar_dates':len(dates),
                     'fact_dimension_price_differences':int(price_difference.sum())}


def check_mall_formulas(sheet):
    issues=[];checked=0
    for address,formula in sheet.formulas.items():
        match=re.fullmatch(r'=G(\d+)\*H(\d+)',formula)
        if not address.startswith('I') or match is None:raise ValueError('Unexpected mall formula; no generic formula evaluation is permitted')
        a,b=match.groups();row=address[1:]
        expected=int(sheet.get('G'+a))*int(money_minor([sheet.get('H'+b)])[0])
        if expected!=int(money_minor([sheet.get(address)])[0]):raise AssertionError('Saved cache differs from its actual source formula')
        checked+=1
        if a!=row or b!=row:issues.append({'cell':address,'source_formula':formula,'intended_row_formula':f'=G{row}*H{row}'})
    return pd.DataFrame(issues,columns=['cell','source_formula','intended_row_formula']),{'source_formula_cache_checks':checked,'source_formula_cache_mismatches':0,'wrong_row_references':len(issues)}


def mall_filter(frame,year=None,month=None):
    if month is not None and (isinstance(month,bool) or not isinstance(month,(int,np.integer)) or not 1<=month<=12):raise ValueError('Month must be an integer from 1 to 12')
    result=frame.copy()
    if year is not None:result=result.loc[result.年度.eq(year)]
    if month is not None:result=result.loc[result.月.eq(month)]
    return result


def bank_models(ctx):
    encodings={'accounts':'gbk','clients':'gbk','disp':'gbk','card':'gbk','loans':'utf-8','order':'gbk','district':'utf-8'}
    tables={name:pd.read_csv(ctx.source('bank_'+name),encoding=encoding) for name,encoding in encodings.items()}
    keys={'accounts':'account_id','clients':'client_id','disp':'disp_id','card':'card_id','loans':'loan_id','order':'order_id','district':'A1'}
    profile=[]
    for name,frame in tables.items():
        unique_key(frame,keys[name]);profile.append({'table':name,'records':len(frame),'key':keys[name],'missing_cells':int(frame.isna().sum().sum())})
    a,c,d,card,loans,orders,dist=[tables[name] for name in ['accounts','clients','disp','card','loans','order','district']]
    for left,right,key in [(a,dist.rename(columns={'A1':'district_id'}),'district_id'),(c,dist.rename(columns={'A1':'district_id'}),'district_id'),
                           (d,a[['account_id']],'account_id'),(d,c[['client_id']],'client_id'),(card,d[['disp_id']],'disp_id'),
                           (loans,a[['account_id']],'account_id'),(orders,a[['account_id']],'account_id')]:many_to_one(left,right,on=key)
    owners=d.loc[d.type.eq('所有者'),['account_id','client_id']].copy();unique_key(owners,'account_id')
    if set(owners.account_id)!=set(a.account_id):raise ValueError('Exactly one declared owner is required per account for the owner analysis')
    owner_clients=many_to_one(owners,c[['client_id','sex']],on='client_id')
    loan_owner=many_to_one(loans,owner_clients,on='account_id');loan_owner['year']=pd.to_datetime(loan_owner.date,format='%Y-%m-%d',errors='raise').dt.year
    loan_owner['amount_minor']=money_minor(loan_owner.amount)
    loan_stats=loan_owner.groupby(['year','sex'],as_index=False).agg(loan_records=('loan_id','size'),loan_amount_minor=('amount_minor','sum'))
    loan_stats['loan_amount_source_units']=loan_stats.loan_amount_minor/100
    save_table(loan_stats.drop(columns='loan_amount_minor'),ctx.output/'loan_owner_gender.csv')
    linked=many_to_one(card.rename(columns={'type':'card_type'}),d[['disp_id','client_id','account_id']],on='disp_id')
    linked=many_to_one(linked,c[['client_id','sex']],on='client_id')
    card_stats=linked.groupby(['card_type','sex'],as_index=False).agg(cards=('card_id','size'),distinct_clients=('client_id','nunique'))
    save_table(card_stats,ctx.output/'card_gender_counts.csv')
    trans_by_account=[];seen=set();trans_rows=0;missing=0;positive_by_type={};signed_types=set()
    for chunk in pd.read_csv(ctx.source('bank_trans'),encoding='gbk',dtype={'trans_id':'int64','account_id':'int64','amount':'string'},chunksize=100000,low_memory=False):
        unique_key(chunk,'trans_id');ids=set(chunk.trans_id)
        if seen.intersection(ids):raise ValueError('Duplicate transaction ID across chunks')
        seen.update(ids);many_to_one(chunk[['account_id']],a[['account_id']],on='account_id')
        chunk['amount_minor']=money_minor(chunk.amount,grouped=True)
        if chunk.amount_minor.lt(0).any():raise ValueError('Source transaction amounts are expected to be nonnegative magnitudes')
        trans_rows+=len(chunk);missing+=int(chunk.drop(columns='amount_minor').isna().sum().sum());signed_types.update(chunk.type.unique())
        for typ,value in chunk.groupby('type').amount_minor.sum().items():positive_by_type[typ]=positive_by_type.get(typ,0)+int(value)
        trans_by_account.append(chunk.groupby('account_id',as_index=False).agg(transaction_records=('trans_id','size'),transaction_amount_minor=('amount_minor','sum')))
    transactions=pd.concat(trans_by_account).groupby('account_id',as_index=False).sum()
    profile.append({'table':'trans','records':trans_rows,'key':'trans_id','missing_cells':missing})
    profile=pd.DataFrame(profile);save_table(profile,ctx.output/'bank_table_profile.csv')
    order_amount=money_minor(orders.amount);order_summary=orders.assign(order_amount_minor=order_amount).groupby('account_id',as_index=False).agg(order_records=('order_id','size'),order_amount_minor=('order_amount_minor','sum'))
    loan_summary=loan_owner.groupby('account_id',as_index=False).agg(loan_records=('loan_id','size'),loan_amount_minor=('amount_minor','sum'))
    account_summary=a[['account_id','district_id']].copy()
    # Each child fact is aggregated independently before joining it to the account grain.
    for child in [transactions,order_summary,loan_summary]:account_summary=many_to_one(account_summary,child,on='account_id',require_match=False)
    measure_cols=[col for col in account_summary if col.endswith('_records') or col.endswith('_minor')]
    account_summary[measure_cols]=account_summary[measure_cols].fillna(0).astype('int64')
    district=account_summary.groupby('district_id',as_index=False).agg(accounts=('account_id','size'),**{col:(col,'sum') for col in measure_cols})
    for col in list(district):
        if col.endswith('_minor'):district[col.replace('_minor','_source_units')]=district[col]/100;district=district.drop(columns=col)
    save_table(district,ctx.output/'bank_district_totals.csv');save_table(account_summary,ctx.output/'private_account_summary.csv')
    if account_summary.transaction_records.sum()!=trans_rows or account_summary.order_amount_minor.sum()!=order_amount.sum() or account_summary.loan_amount_minor.sum()!=loan_owner.amount_minor.sum():raise AssertionError('Independent fact totals changed after joining')
    # The fanout can be quantified without creating the large many-to-many transaction × order table.
    naive_rows=int((account_summary.transaction_records.clip(lower=1)*account_summary.order_records.clip(lower=1)).sum())
    naive_amount=int((account_summary.transaction_amount_minor*account_summary.order_records.clip(lower=1)).sum())
    loan_all=loans.merge(d[['account_id','client_id']],on='account_id',validate='one_to_many')
    fanout=pd.DataFrame([
        {'demonstration':'transactions_joined_directly_to_orders','safe_grain':'account','safe_records':len(a),'naive_join_records':naive_rows,
         'original_fact_amount':int(transactions.transaction_amount_minor.sum())/100,'naive_repeated_amount':naive_amount/100},
        {'demonstration':'loans_joined_to_all_account_users','safe_grain':'loan_id','safe_records':len(loans),'naive_join_records':len(loan_all),
         'original_fact_amount':float(loans.amount.sum()),'naive_repeated_amount':float(loan_all.amount.sum())}])
    save_table(fanout,ctx.output/'fanout_diagnostics.csv')
    # A separate SQL implementation verifies both published original Power BI analysis questions.
    with sqlite3.connect(':memory:') as db:
        for label,frame in [('cards',card.rename(columns={'type':'card_type'})),('permissions',d),('clients',c),('loans',loans)]:frame.to_sql(label,db,index=False)
        sql=pd.read_sql_query('SELECT k.card_type,c.sex,COUNT(*) cards,COUNT(DISTINCT c.client_id) distinct_clients FROM cards k JOIN permissions d ON k.disp_id=d.disp_id JOIN clients c ON d.client_id=c.client_id GROUP BY k.card_type,c.sex ORDER BY k.card_type,c.sex',db)
        pd.testing.assert_frame_equal(card_stats.sort_values(['card_type','sex']).reset_index(drop=True),sql,check_dtype=False)
        sql_loan=pd.read_sql_query("SELECT substr(l.date,1,4) year,c.sex,COUNT(*) loan_records,SUM(l.amount) amount FROM loans l JOIN permissions d ON l.account_id=d.account_id AND d.type='所有者' JOIN clients c ON c.client_id=d.client_id GROUP BY substr(l.date,1,4),c.sex ORDER BY year,c.sex",db)
        if not np.allclose(sql_loan.amount,loan_stats.loan_amount_source_units,rtol=0,atol=1e-8):raise AssertionError('SQL loan control differs')
    return {'tables':profile.to_dict('records'),'transactions':trans_rows,'accounts':len(a),'clients':len(c),'cards':len(card),
            'distinct_cardholders':int(linked.client_id.nunique()),'clients_without_card':int((~c.client_id.isin(linked.client_id)).sum()),
            'loan_records':len(loans),'owner_accounts':len(owners),'transaction_types':sorted(signed_types),
            'gross_transaction_amount_by_type_source_units':{key:value/100 for key,value in positive_by_type.items()},
            'safe_account_records':len(account_summary),'fanout':fanout.to_dict('records'),'sql_controls':'card_type_by_sex and loan_year_by_owner_sex passed'},profile,card_stats


def main(argv=None):
    ctx=context('B01',argv)
    for key in ['bank_dictionary','bank_relationship_slides','pbi_basics_slides']:ctx.source(key)
    mall,audit=prepare_mall(pd.read_excel(ctx.source('mall_model'),sheet_name=None))
    formula_issues,formula_audit=check_mall_formulas(read_cached_book(ctx.source('mall_model'))['产品销售数据表'])
    audit.update(formula_audit)
    save_table(formula_issues,ctx.output/'mall_formula_issues.csv')
    differences=mall.loc[mall.销售单价.ne(mall.dim_price)].groupby(['产品编号','销售单价','dim_price'],as_index=False).size().rename(columns={'size':'records','dim_price':'dimension_price'})
    save_table(differences,ctx.output/'mall_price_differences.csv')
    monthly=mall.groupby(['年度','月'],as_index=False).agg(records=('sales_minor','size'),units=('销售数量','sum'),sales_minor=('sales_minor','sum'),mean_row_sales_minor=('sales_minor','mean'))
    monthly['sales_amount']=monthly.sales_minor/100;monthly['mean_record_sales']=monthly.mean_row_sales_minor/100
    save_table(monthly.drop(columns=['sales_minor','mean_row_sales_minor']),ctx.output/'mall_monthly.csv')
    for key,name in [('产品名称','mall_products.csv'),('商铺城市','mall_cities.csv')]:
        table=mall.groupby(key,as_index=False).agg(records=('sales_minor','size'),units=('销售数量','sum'),sales_minor=('sales_minor','sum'))
        table['sales_amount']=table.sales_minor/100;save_table(table.drop(columns='sales_minor'),ctx.output/name)
    save_table(mall,ctx.output/'private_mall_enriched.csv')
    demo=pd.read_excel(ctx.source('sales_model'),sheet_name=None);fact=demo['销售业绩表'].copy();original=float(fact['金额（$M）'].sum())
    for key,label in [('客户ID','客户信息表'),('城市编号','城市信息表'),('产品编号','产品信息表')]:fact=many_to_one(fact,demo[label],on=key)
    if len(fact)!=len(demo['销售业绩表']) or not np.isclose(fact['金额（$M）'].sum(),original,rtol=1e-12,atol=1e-9):raise AssertionError('Sales star join changed amounts')
    for key,name in [('区域名','sales_region_totals.csv'),('产品类型','sales_product_totals.csv')]:
        totals=fact.groupby(key,as_index=False).agg(records=('金额（$M）','size'),amount_source_millions=('金额（$M）','sum'));save_table(totals,ctx.output/name)
    save_table(fact,ctx.output/'private_sales_model_enriched.csv')
    bank,profile,cards=bank_models(ctx)
    visual_rows=[]
    for key in ['mall_pbix','bank_model_pbix']:
        for row in pbix_visuals(ctx.source(key)):
            row['source']=key;row['aggregations']=json.dumps(row['aggregations'],ensure_ascii=False)
            row['migration']='按原配置输出均值及总额序列；不凭Sum引用名判断' if key=='mall_pbix' and row['kind']=='lineChart' else '保留配置记录；不复刻PowerBI自动影响因素算法' if row['kind']=='keyDriversVisual' else '年份/月筛选与groupby聚合或持卡人/贷款所有者关联'
            visual_rows.append(row)
    save_table(pd.DataFrame(visual_rows),ctx.output/'pbix_visual_map.csv')
    schema='''# 模型与粒度

```mermaid
erDiagram
    DISTRICT ||--o{ ACCOUNTS : branch_region
    DISTRICT ||--o{ CLIENTS : home_region
    ACCOUNTS ||--o{ DISP : account_rights
    CLIENTS ||--o{ DISP : client_rights
    DISP ||--o{ CARD : issued_to_permission
    ACCOUNTS ||--o{ TRANS : transactions
    ACCOUNTS ||--o{ ORDERS : payment_orders
    ACCOUNTS ||--o| LOANS : loan_in_this_snapshot
```

主键不缺失且唯一。账户开户地区与客户居住地区是两种角色；不能混为一列。disp是账户与客户之间的权限桥。分析贷款按唯一“所有者”归属，分析卡按disp关联具体持卡客户。跨事实表先按account_id各自聚合，再一对一合并。

商场源表一行是销售记录，没有订单ID，不把日期/城市/商品组合强当主键，也不删除相同内容的记录。产品键按案例统一大写，连接产品→品牌/类别形成雪花维度；城市和日期直接连接事实。每次连接核查行数及销售额守恒。

创建模型示例中本次客户表与销售表的客户ID实际上都是唯一，样本表现为一对一；城市和产品则是一对多。理论模型的基数与这个具体样本的观察基数分别解释。
'''
    (ctx.output/'schema.md').write_text(schema,encoding='utf-8')
    mapping='''# 来源与迁移边界

| 来源 | 对应内容 |
|---|---|
| 第1章数据库介绍课件第2至7页及8个CSV | 8个实体、主外键、disp桥；课件给出的8张表记录数均逐表核查 |
| 关系模型PBIX与用处课件第7页 | 卡类型与持卡人性别、贷款年度与所有者性别；pandas结果用独立SQLite查询核查 |
| 商场6工作表和PBIX两页 | 产品/品牌/类别、城市、日期维度；12960个缓存对应原公式，另查同一行业务公式，区分4个错行引用 |
| 创建数据模型示例4工作表 | 客户、城市和产品维度关联；$M单位单独保留 |
| PowerBI基础课件第30至33页 | 星型、雪花、星座与连接方向；落实为唯一键、覆盖检查及先聚合后关联 |

PBIX只读取Report/Layout配置，未解压或执行其专有DataModel引擎，也未声称界面或自动影响因素算法逐项复现。商场第二页折线配置虽然queryRef仍写Sum，显示名为“销售额 的平均值”，因此输出均值与总额两列供区分。关键影响因素对象把销售单价求和；本实验只记录其配置，不把它当作因果结论。
'''
    (ctx.output/'source-map.md').write_text(mapping,encoding='utf-8')
    expected_counts={'accounts':4500,'clients':5369,'disp':5369,'card':892,'loans':682,'order':6471,'trans':1056320,'district':77}
    if dict(zip(profile.table,profile.records))!=expected_counts:raise AssertionError('Counts differ from the supplied database introduction')
    plt=plotting();fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    axes[0].barh(profile.table,profile.records,color='#247d86');axes[0].set_xscale('log');axes[0].set(title='关系模型：8张源表',xlabel='记录数（对数轴）')
    for i,row in enumerate(profile.itertuples()):axes[0].text(row.records*1.05,i,f'{row.records:,}',va='center',fontsize=9)
    axes[0].set_xlim(20,profile.records.max()*5)
    diagnostic=bank['fanout'][1];axes[1].bar(['按唯一所有者归属','直接连全部权限人'],[diagnostic['safe_records'],diagnostic['naive_join_records']],color=['#247d86','#d67b28'])
    axes[1].set(title='贷款关联人数增加不等于贷款增加',ylabel='关联后行数')
    for i,value in enumerate([diagnostic['safe_records'],diagnostic['naive_join_records']]):axes[1].text(i,value,str(value),ha='center',va='bottom')
    fig.savefig(ctx.output/'model_summary.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for year,group in monthly.groupby('年度'):axes[0].plot(group.月,group.sales_amount/1e6,marker='o',label=str(year))
    axes[0].set(title='商场样本：按年月汇总销售额',xlabel='月份',ylabel='销售额（百万原数值单位）',xticks=range(1,13));axes[0].legend(frameon=False)
    totals=mall.groupby('产品名称').sales_minor.sum().sort_values()
    axes[1].barh(totals.index,totals.values/1e8,color='#247d86');axes[1].set(title='商品维度聚合',xlabel='销售额（百万原数值单位）')
    fig.savefig(ctx.output/'mall_sales.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,5),layout='constrained');wide=cards.pivot(index='card_type',columns='sex',values='cards').fillna(0)
    wide.plot.bar(ax=ax,color=['#247d86','#d67b28'],rot=0)
    ax.set(title='按卡对应权限客户统计性别',xlabel='卡类型',ylabel='卡数');ax.legend(frameon=False,title='客户性别')
    fig.savefig(ctx.output/'bank_card_gender.png',dpi=150);plt.close(fig)
    report=f'''# B01 关系与维度数据模型

## 业务问题与数据粒度

本实验覆盖银行8表关系模型、商场6表维度模型和销售4表星型示例。银行{bank['accounts']:,}账户、{bank['clients']:,}客户、{bank['transactions']:,}笔交易；全部8张表行数与教材数据库介绍一致，主键唯一、外键完整。课件中的“可以多个账户”等描述是模型能力，本样本的具体基数另作检查，不强行假设每个关系都有多个匹配。

![源表与重复关联](model_summary.png)

## 三个关键实现

1. 卡通过disp_id对应具体权限客户，按卡类型、性别同时输出卡数及去重持卡人数；本样本{bank['distinct_cardholders']}名持卡客户、{bank['clients_without_card']}名无卡客户。无卡客户不是未知性别或未知卡类型，不能把空白组当成一种卡。
2. 贷款先归属唯一账户所有者，再按贷款年度、所有者性别汇总，并与独立SQLite查询核对。若直接关联全部权限人，{bank['loan_records']}笔贷款会成为{bank['fanout'][1]['naive_join_records']}行，金额也被重复；它表示借助同一账户的关联人数，不能再当贷款笔数或按人可加的贷款额。
3. 交易、支付指令和贷款分别按account_id聚合后再关联。本样本直接把交易与支付指令连起来将得到{bank['fanout'][0]['naive_join_records']:,}行。分地区输出在{bank['accounts']}账户粒度保留所有事实总量。交易金额只按借/贷分别统计正量，未擅自改成净现金流，余额是存量不作求和；不同表的金额不是同一业务量。

![卡类型与性别](bank_card_gender.png)

## 维度模型与PowerBI迁移

商场{audit['rows']:,}行销售记录的产品键为小写，产品维表为大写；只对该业务键统一大写后关联。产品名、品牌、类别逐项一致，但{audit['fact_dimension_price_differences']}行的事实单价与产品维表单价不同（两个产品，见mall_price_differences.csv）。来源没有价格有效期，不能断定是历史调价或错误，更不能用维表价覆盖事实价。

逐一解析{audit['source_formula_cache_checks']:,}个原乘法公式，其缓存均与所引用单元格一致；另按“本行数量×本行单价”核对时发现{audit['row_business_mismatches']}处错误。I1587、I1588、I11238、I11239实际都引用下一行的G/H，缓存一致不代表业务公式正确。mall_formula_issues.csv保留4个坐标及原式/应有式，不执行任意Excel表达式。正式销售额按本行重算为{audit['sales_minor']/100:,.0f}，源缓存合计{audit['source_cached_sales_minor']/100:,.0f}，差{audit['cached_minus_recomputed_minor']/100:,.0f}个原数值单位。教材未明确货币单位，不擅自标注人民币。日期表730天，实际仅{audit['distinct_observed_dates']}天有销售记录，记录止于2019-12-30，不能把年度样本汇总解释为完整全年业绩。

![时间与商品维度](mall_sales.png)

mall_filter对应年份/月切片，按年月、城市、产品分组对应度量汇总。PBIX第二页有“平均值”配置但内部引用名仍叫Sum，因此结果同时保留每条记录销售额的均值与总额，避免仅按字段名误读；均值不是客单价，因为没有订单ID。创建模型示例保留原表金额（$M）单位，三个维度连接不改变2035行及总量，未与商场或银行金额相加。

原始CSV、工作簿和PBIX不改写；客户、账户、交易及商场销售行级结果仅在本地。公开输出为聚合表、图形、[模型图](schema.md)和[来源/迁移边界](source-map.md)。PBIX自动影响因素对象只记录配置，未声称复刻专有算法或验证PowerBI刷新后的界面。当前状态为运行通过，教材数字缓存核对与独立SQL控制有明确边界。
'''
    finish(ctx,{'lab_id':'B01','status':'execution_verified','mall':audit,'sales_model':{'records':len(fact),'amount_source_millions':original,'customer_key_observed_cardinality':'one_to_one'},
                'bank':bank,'pbix_visuals_inspected':len(visual_rows),'slide_table_counts_compared':8,'sql_control_groups':len(cards)+len(pd.read_csv(ctx.output/'loan_owner_gender.csv'))},report)


if __name__=='__main__':main()
