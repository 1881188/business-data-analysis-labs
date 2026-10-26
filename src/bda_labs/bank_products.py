"""Monthly bank purchase snapshot: record grain, fixed targets and explicit filters."""
import argparse
from contextlib import closing
import json,re,sqlite3,sys,zipfile
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table,compare_numeric
from .case_workbooks import money_cents,ratio
from .tabular_tools import many_to_one
from .workbook_reference import read_cached_book,coverage_table
from .pbix_audit import visual_audit

DIMENSIONS=[('风险偏好说明表','风险编号','风险说明','risk_code','risk'),('品类说明表','品类编号','品类名称','category_code','category'),
            ('学历说明表','学历编号','学历名称','education_code','education')]
HIERARCHY=['income','age_band','education','gender']


def prepare(sheets):
    columns={'风险编号':'risk_code','购买目的':'purpose','家庭年收入':'income','品类编号':'category_code','年龄':'age_band','性别':'gender',
             '选择本行的原因':'reason','学历编号':'education_code','购买金额':'amount','期限':'term','收益':'yield_amount'}
    f=sheets['销售数据'][list(columns)].rename(columns=columns).copy()
    f['source_row']=np.arange(2,len(f)+2)
    for col in ['risk_code','category_code','education_code','purpose','income','age_band','gender','reason']:
        f[col]=f[col].astype('string').str.strip()
        if f[col].isna().any() or f[col].eq('').any():raise ValueError('Missing bank snapshot descriptor; review grouping scope')
    for sheet,key,label,newkey,newlabel in DIMENSIONS:
        dim=sheets[sheet][[key,label]].rename(columns={key:newkey,label:newlabel}).copy()
        for col in [newkey,newlabel]:dim[col]=dim[col].astype('string').str.strip()
        if dim.isna().any().any() or dim.eq('').any().any():raise ValueError('Missing dimension label')
        f=many_to_one(f,dim,on=newkey)
    f['amount_cents']=money_cents(f.amount,allow_negative=False);f['yield_cents']=money_cents(f.yield_amount)
    f['term']=pd.to_numeric(f.term,errors='raise')
    if not np.isfinite(f.term.dropna()).all() or f.term.dropna().lt(0).any():raise ValueError('Term must be observed nonnegative numeric units or missing')
    return f.drop(columns=['amount','yield_amount'])


def business_context(book):
    text=book['业务描述'].get('B1','')
    goal=re.search(r'销售目标为(\d+(?:\.\d+)?)万',text);days=re.search(r'本月共(\d+)天',text);cutoff=re.search(r'本月(\d+)日',text)
    if not all([goal,days,cutoff]):raise ValueError('Review source business target and snapshot cutoff')
    target=money_cents(pd.Series([goal.group(1)]))[0]*10000
    month_days=int(days.group(1));elapsed=int(cutoff.group(1))
    if target<=0 or not 1<=elapsed<=month_days<=31:raise ValueError('Invalid monthly target or cutoff')
    return {'monthly_target_cents':int(target),'month_days':month_days,'elapsed_days':elapsed}


def progress(amount_cents,monthly_target_cents,month_days,elapsed_days):
    if monthly_target_cents<=0 or not 1<=elapsed_days<=month_days<=31:raise ValueError('Expected positive target and valid snapshot day')
    remaining=month_days-elapsed_days;gap=max(monthly_target_cents-amount_cents,0)
    return {'amount':amount_cents/100,'monthly_target':monthly_target_cents/100,'elapsed_days':elapsed_days,'month_days':month_days,
            'full_month_attainment':amount_cents/monthly_target_cents,'elapsed_time_fraction':elapsed_days/month_days,
            'time_prorated_target':monthly_target_cents/100*elapsed_days/month_days,
            'attainment_vs_time_prorated_target':amount_cents/monthly_target_cents*month_days/elapsed_days,
            'remaining_days':remaining,'remaining_monthly_gap':gap/100,'required_daily_amount_remaining':gap/100/remaining if remaining else None}


def select(frame,selection):
    f=frame.copy()
    for key in ['income','age_band','education','gender','category_code','risk_code']:
        value=selection.get(key)
        if value is not None:f=f.loc[f[key].eq(value)].copy()
    return f


def aggregate(frame,keys,whole_amount_cents):
    g=frame.groupby(keys,dropna=False,observed=True).agg(records=('source_row','size'),amount_cents=('amount_cents','sum'),
                         observed_terms=('term','count'),mean_term=('term','mean')).reset_index()
    g['amount']=g.amount_cents/100;g['mean_purchase_per_record']=g.amount/g.records
    g['share_of_selected_amount']=ratio(g.amount_cents,frame.amount_cents.sum())
    g['share_of_whole_snapshot_amount']=ratio(g.amount_cents,whole_amount_cents)
    if int(g.records.sum())!=len(frame) or int(g.amount_cents.sum())!=int(frame.amount_cents.sum()):raise AssertionError('Bank aggregate lost snapshot rows')
    return g


def saved_path(pbix):
    with zipfile.ZipFile(pbix) as z:layout=json.loads(z.read('Report/Layout').decode('utf-16le'))
    visuals=[json.loads(c.get('config','{}')).get('singleVisual',{}) for page in layout['sections'] for c in page.get('visualContainers',[])]
    tree=[v for v in visuals if v.get('visualType')=='decompositionTreeVisual']
    if len(tree)!=1:raise ValueError('Review saved decomposition metadata')
    state=tree[0]['expansionStates'][0];levels=state['levels'];node=state['root'];result={}
    mapping={'家庭年收入':'income','年龄':'age_band','学历名称':'education','性别':'gender'}
    for level in levels:
        toggled=[c for c in node.get('children',[]) if c.get('isToggled')]
        if not toggled:break
        if len(toggled)!=1:raise ValueError('Review ambiguous saved expansion branches')
        node=toggled[0];literal=node['identityValues'][0]['Literal']['Value'];field=level['queryRefs'][0].split('.')[-1]
        if field not in mapping or not re.fullmatch(r"'(?:[^']|'')*'",literal):raise ValueError('Unexpected saved literal or field')
        result[mapping[field]]=literal[1:-1].replace("''", "'")
    return result


def path_summary(frame,path):
    rows=[];chosen=frame;filters={};whole=int(frame.amount_cents.sum())
    rows.append({'level':0,'condition':'全部快照','records':len(frame),'amount':whole/100,'share_of_whole_snapshot_amount':ratio(whole,whole).item()})
    for level,(key,value) in enumerate(path.items(),1):
        filters[key]=value;chosen=select(frame,filters);amount=int(chosen.amount_cents.sum())
        rows.append({'level':level,'condition':f'{key}={value}','records':len(chosen),'amount':amount/100,'share_of_whole_snapshot_amount':ratio(amount,whole).item()})
    return pd.DataFrame(rows)


def sql_checks(frame):
    with closing(sqlite3.connect(':memory:')) as conn:
        frame[['category_code','amount_cents','term']].to_sql('purchases',conn,index=False)
        sql=pd.read_sql_query('SELECT category_code, COUNT(*) AS records, SUM(amount_cents) AS amount_cents, COUNT(term) AS observed_terms, AVG(term) AS mean_term FROM purchases GROUP BY category_code ORDER BY category_code',conn)
    python=aggregate(frame,'category_code',int(frame.amount_cents.sum())).sort_values('category_code').reset_index(drop=True)
    if python.category_code.tolist()!=sql.category_code.tolist():raise AssertionError('SQL categories differ')
    compare_numeric(python[['records','amount_cents','observed_terms','mean_term']],sql[['records','amount_cents','observed_terms','mean_term']],'Bank SQL aggregate')
    return len(sql)*4


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False)
    for option in ['income','age-band','education','gender','category-code','risk-code']:parser.add_argument('--'+option)
    parser.add_argument('--saved-path',action='store_const',const=True,default=None)
    options,remaining=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    ctx=context('B19',remaining);workbook=ctx.source('bank_products_data');pbix=ctx.source('bank_products_pbix')
    book=read_cached_book(workbook);full=prepare(pd.read_excel(workbook,sheet_name=None));business=business_context(book)
    path=saved_path(pbix);selection=vars(options).copy()
    if options.saved_path:
        if any(v is not None for k,v in selection.items() if k!='saved_path'):raise ValueError('Use the saved path or explicit filters in one run')
        selection.update(path)
    f=select(full,selection);whole=int(full.amount_cents.sum());amount=int(f.amount_cents.sum());checks=sql_checks(f)
    overall_progress=progress(whole,**business);selected_progress=progress(amount,**business)
    products=aggregate(f,['category_code','category'],whole);risks=aggregate(f,['category_code','category','risk_code','risk'],whole)
    tables={'product_profile':products,'product_risk':risks}
    for key in HIERARCHY:tables['segment_'+key]=aggregate(f,key,whole)
    for key in ['reason','purpose']:tables[key+'_counts']=aggregate(f,key,whole)
    tables['saved_path']=path_summary(full,path)
    for name,data in tables.items():save_table(data,ctx.output/(name+'.csv'))
    save_table(f,ctx.output/'purchases_private.csv')
    tree=[]
    for depth in range(1,5):
        data=aggregate(f,HIERARCHY[:depth],whole);data['depth']=depth;tree.append(data)
    save_table(pd.concat(tree,ignore_index=True),ctx.output/'decomposition_private.csv')
    coverage=coverage_table({'bank_products_data':book},{('bank_products_data','风险偏好说明表'):'风险编号唯一维度→风险说明，多对一校验',('bank_products_data','品类说明表'):'品类编号唯一维度→产品类别，多对一校验',
        ('bank_products_data','学历说明表'):'学历编号唯一维度→学历名称，多对一校验',('bank_products_data','销售数据'):'440条无客户/订单ID的购买记录；日期、收益期间及期限单位未提供；明细只本地',
        ('bank_products_data','业务描述'):'B1文字明确月目标2500万、31天、第29天快照，冻结进度口径'},ctx.output/'workbook-map.md')
    visuals=visual_audit(pbix,['月度快照金额、整月目标达成、按时间进度达成分列；未知隐藏MTD公式不猜测',
        'income→age_band→education→gender层级汇总仅本地；公开一维分布与保存展开路径；CLI显式筛选',
        'product_risk：产品→风险，多组金额与总额占比；所有图同一筛选上下文',
        'product_profile：平均每条购买金额与算术平均期限；Function=1，不按queryRef的Sum误读',
        'reason_counts：原短语非空次数条形图；Function=5，未执行WordCloud插件',
        'purpose_counts：购买目的非空次数；源标题“选择产品原因”按实际字段澄清'])
    save_table(visuals,ctx.output/'pbix_visual_map.csv')
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(16,11),layout='constrained');fig.suptitle('银行购买记录看板 · 第29日月内快照',fontsize=16)
    ax[0,0].axis('off')
    lines=[f'当前筛选购买记录：{len(f)}条',f'购买金额：{amount/100:,.0f}',f'全月机构目标：{business["monthly_target_cents"]/100:,.0f}',
           f'筛选金额/全月机构目标：{selected_progress["full_month_attainment"]:.2%}',f'全快照/按29/31折算目标：{overall_progress["attainment_vs_time_prorated_target"]:.2%}']
    for i,line in enumerate(lines):ax[0,0].text(.03,.9-i*.17,line,transform=ax[0,0].transAxes,fontsize=13)
    p=products.sort_values('amount');ax[0,1].barh(p.category,p.amount/10000,color='#087f8c');ax[0,1].set(title='各产品购买金额',xlabel='金额（万元）')
    ax[1,0].barh(p.category,p.mean_purchase_per_record/10000,color='#087f8c');ax[1,0].set(title='每条购买记录平均金额',xlabel='金额（万元/记录）')
    ax[1,1].barh(p.category,p.mean_term,color='#087f8c');ax[1,1].set(title='算术平均期限（仅已知期限）',xlabel='期限（源单位未注明）')
    fig.savefig(ctx.output/'bank_dashboard.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(2,2,figsize=(15,11),layout='constrained')
    labels={'income':'家庭年收入标签','age_band':'源年龄组标签','education':'学历标签','gender':'性别标签'}
    for axis,key in zip(ax.flat,HIERARCHY):
        g=tables['segment_'+key].sort_values('amount');axis.barh(g[key],g.amount/10000,color='#087f8c');axis.set(title=labels[key]+'下的购买金额',xlabel='万元')
    fig.savefig(ctx.output/'bank_demographics.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(16,6),layout='constrained')
    for axis,key,title in [(ax[0],'reason','选择本行原因'),(ax[1],'purpose','购买目的')]:
        g=tables[key+'_counts'].sort_values('records');axis.barh(g[key],g.records,color='#087f8c');axis.set(title=title+'：整段短语频次',xlabel='非空购买记录数')
    fig.savefig(ctx.output/'bank_reasons.png',dpi=150);plt.close(fig)
    report=f'''# B19 银行产品购买看板

## 业务范围与目标进度

源表{len(full)}条购买记录，无客户编号、订单ID、交易日期和具体年月，不能称作{len(full)}名独立客户，也不能计算去重客户客单价、留存或每日趋势。业务描述B1明确：本月31天，当前第29日，月目标25,000,000元。仅作为提供的月内快照，不使用运行当天时间。当前筛选为{json.dumps(selection,ensure_ascii=False)}，选中{len(f)}条。

全快照金额{whole/100:,.0f}元；全月目标达成{overall_progress['full_month_attainment']:.6%}。按29/31线性折算的时间进度目标为{overall_progress['time_prorated_target']:,.2f}元，实际/该进度目标为{overall_progress['attainment_vs_time_prorated_target']:.6%}。剩余2天，全月目标尚差{overall_progress['remaining_monthly_gap']:,.0f}元，平均每天需{overall_progress['required_daily_amount_remaining']:,.0f}元。这是均匀进度比较，不是统计预测。

![银行看板](bank_dashboard.png)

PBIX卡片中MTD销售额使用购买金额SUM，但隐藏“MTD销售目标达成率”公式未解码，不能断言对应以上哪个分母。Python两种率分列；在任意客群/产品筛选后，机构目标仍固定，选中金额/全机构目标只是贡献，不虚构客群目标。summary中whole_snapshot_progress与selected_amount_against_institution_target分别保存，公开只采用默认全量运行。

## 产品、客群和平均数

三个维表均以唯一编号多对一关联，丢失或重复维度键会报错。产品/风险汇总、四种客群汇总及原因/目的汇总的人数口径均为记录数，金额与记录守恒。category与risk使用编号筛选，避免按名称误并。

“客单”源图虽然queryRef包含Sum，实际Function=1是购买金额的算术平均；Python称“每条购买记录平均金额”，不推断每名客户金额。期限亦用已知期限记录的算术平均，observed_terms明确分母，不按金额加权。期限1—5的单位没有给出，收益字段没有持有期间，不能称年化收益率或据此比较真实产品投资回报；源负收益保留，未当异常删掉。

![客群分布](bank_demographics.png)

收入和年龄是源分组标签，不从字符串造精确年龄或收入。源“41-50岁”和“50-60岁”文字边界重叠，保持标签，不能确定50岁的真实归组规则。分解树保存展开路径为{json.dumps(path,ensure_ascii=False)}，对应37条、1,994,382元。这是保存的展开分支，不等于已激活筛选。默认全量；--saved-path才显式选择该分支。完整四级组合仅在本地decomposition_private.csv，公开一维分布及该展开路径，避免把逐条特征组合作为公开明细。

## 原因、目的与源页面

![原因与目的](bank_reasons.png)

源两个WordCloud视图按非空短语计数（Function=5），queryRef名称Min不代表取最小值。Python用整段短语频次条形图，保留可核对人数，不执行或分发pbiviz插件，不做未知中文分词。第二图实际字段是购买目的，原“选择产品原因”标题据字段澄清。

源页6个容器全部登记。两个图间存在交互关系，但二进制模型及DAX未解码，不宣称完整复制跨图筛选传播；Python所有分组共享同一组显式筛选。没有独立参考显示数值，本实验为运行通过。按产品编号独立SQLite核对记录数、金额和期限分母/均值共{checks}个数值；全默认输入10个产品为40项。

```powershell
python run_labs.py --lab B19
python labs/cda1_business/b19_bank_products/main.py --saved-path --output-root outputs/filtered
python labs/cda1_business/b19_bank_products/main.py --category-code c01 --risk-code S1 --output-root outputs/filtered
```

其他筛选：--income、--age-band、--education、--gender。源购买明细、四级组合仅在本地outputs；原表和PBIX不随仓库分发。描述性倾向只用于理解教材样本，不证明营销干预效果。
'''
    finish(ctx,{'lab_id':'B19','status':'execution_verified','selection':selection,'source_records':len(full),'selected_records':len(f),
        'whole_snapshot_progress':overall_progress,'selected_amount_against_institution_target':selected_progress,'saved_expansion_path':path,
        'sql_numeric_checks':checks,'conservation_tables':8,'negative_yield_records':int(full.yield_cents.lt(0).sum()),
        'exact_duplicate_source_rows':int(full.drop(columns='source_row').duplicated().sum()),'pbix_visuals':len(visuals),'workbook_coverage':coverage},report)


if __name__=='__main__':main()
