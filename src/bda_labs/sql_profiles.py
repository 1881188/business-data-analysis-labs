"""Portable SQL lessons and card-at-issue profiles with strict historical windows."""
from contextlib import closing
import json,re,sqlite3,zipfile
from xml.etree import ElementTree as ET
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table,compare_numeric,write_json
from .tabular_tools import unique_key,many_to_one,money_minor
from .case_workbooks import ratio
from .workbook_reference import read_cached_book,coverage_table


def card_base(card,disp,clients):
    f=many_to_one(card.rename(columns={'type':'card_type'}),disp[['disp_id','client_id','account_id']],on='disp_id')
    f=many_to_one(f,clients[['client_id','sex','birth_date']],on='client_id');unique_key(f,'card_id')
    for col in ['issued','birth_date']:f[col]=pd.to_datetime(f[col],format='%Y-%m-%d',errors='raise')
    if f[['issued','birth_date']].isna().any().any() or f.birth_date.gt(f.issued).any():raise ValueError('Invalid card issue/birth dates')
    before=(f.issued.dt.month<f.birth_date.dt.month)|((f.issued.dt.month==f.birth_date.dt.month)&(f.issued.dt.day<f.birth_date.dt.day))
    f['age_at_issue']=f.issued.dt.year-f.birth_date.dt.year-before.astype(int)
    f['legacy_age_days_over_365']=(f.issued-f.birth_date).dt.days/365
    return f


def historical_features(base,transactions):
    t=transactions.copy();unique_key(t,'trans_id');t['date']=pd.to_datetime(t.date,format='%Y-%m-%d',errors='raise')
    if t.date.isna().any() or not t.type.isin(['借','贷']).all():raise ValueError('Unknown transaction date/type')
    f=base.merge(t[['trans_id','account_id','date','type','amount_cents','balance_cents']],on='account_id',how='left',validate='many_to_many')
    f['days_before_issue']=(f.issued-f.date).dt.days;before=f[f.days_before_issue.gt(0)].copy()
    latest=before.groupby('card_id').date.transform('max');last=before[before.date.eq(latest)]
    last_stats=last.groupby('card_id').agg(last_days=('days_before_issue','min'),last_day_rows=('trans_id','count'),
        last_day_balance_mean_cents=('balance_cents','mean'),last_day_balance_min_cents=('balance_cents','min'),last_day_balance_max_cents=('balance_cents','max'))
    result=base.merge(last_stats,on='card_id',how='left',validate='one_to_one')
    for window in [180,365]:
        selected=before[before.days_before_issue.lt(window)].copy()
        selected['debit_cents']=selected.amount_cents.where(selected.type.eq('借'),0)
        selected['credit_cents']=selected.amount_cents.where(selected.type.eq('贷'),0)
        g=selected.groupby('card_id').agg(records=('trans_id','count'),debit_cents=('debit_cents','sum'),credit_cents=('credit_cents','sum'),transaction_weighted_balance_cents=('balance_cents','mean'))
        g=g.add_prefix(f'w{window}_');result=result.merge(g,on='card_id',how='left',validate='one_to_one')
        for key in ['records','debit_cents','credit_cents']:result[f'w{window}_{key}']=result[f'w{window}_{key}'].fillna(0).astype('int64')
        result[f'w{window}_credit_over_debit']=ratio(result[f'w{window}_credit_cents'],result[f'w{window}_debit_cents'])
        result[f'w{window}_credit_over_transaction_mean_balance']=ratio(result[f'w{window}_credit_cents'],result[f'w{window}_transaction_weighted_balance_cents'])
    return result


def sql_profile_checks(conn,expected):
    queries={}
    for window in [180,365]:
        query=f'''SELECT c.card_id, COUNT(t.trans_id) AS records,
            SUM(CASE WHEN t.type='借' THEN t.amount_cents ELSE 0 END) AS debit_cents,
            SUM(CASE WHEN t.type='贷' THEN t.amount_cents ELSE 0 END) AS credit_cents,
            AVG(t.balance_cents) AS transaction_weighted_balance_cents
            FROM card_base c LEFT JOIN trans t ON c.account_id=t.account_id
              AND t.date<c.issued AND t.date>date(c.issued,'-{window} days')
            GROUP BY c.card_id ORDER BY c.card_id'''
        actual=pd.read_sql_query(query,conn);cols=['records','debit_cents','credit_cents','transaction_weighted_balance_cents']
        compare_numeric(actual[cols],expected.sort_values('card_id')[[f'w{window}_{col}' for col in cols]],f'Historical SQL {window}')
        queries[f'profile_{window}']=query
    query='''WITH last_dates AS (SELECT c.card_id, MAX(t.date) AS last_date FROM card_base c
        LEFT JOIN trans t ON c.account_id=t.account_id AND t.date<c.issued GROUP BY c.card_id)
        SELECT c.card_id, julianday(c.issued)-julianday(l.last_date) AS last_days,
          COUNT(t.trans_id) AS last_day_rows, AVG(t.balance_cents) AS last_day_balance_mean_cents,
          MIN(t.balance_cents) AS last_day_balance_min_cents, MAX(t.balance_cents) AS last_day_balance_max_cents
        FROM card_base c LEFT JOIN last_dates l ON c.card_id=l.card_id
        LEFT JOIN trans t ON c.account_id=t.account_id AND t.date=l.last_date
        GROUP BY c.card_id ORDER BY c.card_id'''
    actual=pd.read_sql_query(query,conn);cols=['last_days','last_day_rows','last_day_balance_mean_cents','last_day_balance_min_cents','last_day_balance_max_cents']
    want=expected.sort_values('card_id')[cols].copy();want.last_day_rows=want.last_day_rows.fillna(0)
    compare_numeric(actual[cols],want,'Latest-day SQL');queries['last_day']=query
    return queries,len(expected)*13


def lesson_queries(conn,tables,transactions):
    sale=tables['sale'];a=tables['table1'];b=tables['table2'];one=tables['one'];two=tables['two'];checks=[];queries={}
    def verify(name,group,query,wanted):
        got=pd.read_sql_query(query,conn)
        if set(got.columns)!=set(wanted.columns):raise AssertionError(f'Lesson columns differ: {name}')
        got=got[list(wanted.columns)]
        # SQL sets have no inherent order; compare rows with a shared canonical order.
        def ordered(f):return f.where(f.notna(),np.nan).sort_values(list(f.columns),na_position='first').reset_index(drop=True)
        pd.testing.assert_frame_equal(ordered(got),ordered(wanted),check_dtype=False,check_exact=False,rtol=1e-11,atol=1e-8)
        checks.append({'lesson':group,'query':name,'sql_rows':len(got),'pandas_rows':len(wanted),'matched':True});queries[name]=query
    verify('select_columns',2,'SELECT year,market,sale,profit FROM sale',sale)
    verify('distinct_years',2,'SELECT DISTINCT year FROM sale',sale[['year']].drop_duplicates())
    verify('filter_2012',2,'SELECT * FROM sale WHERE year=2012',sale[sale.year.eq(2012)])
    verify('sort_year',2,'SELECT * FROM sale ORDER BY year',sale)
    rates=sale.assign(rate=sale.profit/sale.sale.replace(0,np.nan))
    verify('ratio_filter',3,'SELECT *, 1.0*profit/NULLIF(sale,0) AS rate FROM sale WHERE 1.0*profit/NULLIF(sale,0)<.07',rates[rates.rate.lt(.07)])
    t=transactions.copy();dates=pd.to_datetime(t.date);chosen=t[dates.between('1998-12-01','1998-12-31')&t.k_symbol.eq('房屋贷款')].copy()
    chosen['weekday']=pd.to_datetime(chosen.date).dt.dayofweek;chosen['weekday_group']=np.where(chosen.weekday.ge(5),'周末','工作日')
    verify('date_and_case',4,"SELECT trans_id, (CAST(strftime('%w',date) AS INTEGER)+6)%7 AS weekday, CASE WHEN (CAST(strftime('%w',date) AS INTEGER)+6)%7>=5 THEN '周末' ELSE '工作日' END AS weekday_group FROM trans WHERE date BETWEEN '1998-12-01' AND '1998-12-31' AND k_symbol='房屋贷款'",chosen[['trans_id','weekday','weekday_group']])
    grouped=t.groupby('date').agg(records=('trans_id','size'),mean_amount_cents=('amount_cents','mean'),sum_amount_cents=('amount_cents','sum')).reset_index();grouped=grouped[grouped.records.gt(300)]
    verify('group_having',5,'SELECT date,COUNT(*) AS records,AVG(amount_cents) AS mean_amount_cents,SUM(amount_cents) AS sum_amount_cents FROM trans GROUP BY date HAVING COUNT(*)>300',grouped)
    aa=a.rename(columns={'id':'left_id','value':'left_value'});bb=b.rename(columns={'id':'right_id','value':'right_value'})
    for how in ['cross','inner','left','right','outer']:
        wanted=aa.merge(bb,how=how,**({} if how=='cross' else {'left_on':'left_id','right_on':'right_id'}))
        if how=='outer':q='SELECT a.id left_id,a.value left_value,b.id right_id,b.value right_value FROM table1 a LEFT JOIN table2 b ON a.id=b.id UNION ALL SELECT a.id,a.value,b.id,b.value FROM table2 b LEFT JOIN table1 a ON a.id=b.id WHERE a.id IS NULL'
        elif how=='right':q='SELECT a.id left_id,a.value left_value,b.id right_id,b.value right_value FROM table2 b LEFT JOIN table1 a ON a.id=b.id'
        else:q=f'SELECT a.id left_id,a.value left_value,b.id right_id,b.value right_value FROM table1 a {"CROSS" if how=="cross" else how.upper()} JOIN table2 b'+('' if how=='cross' else ' ON a.id=b.id')
        verify('join_'+how,6,q,wanted)
    loans=tables['loans'];bad_accounts=set(loans.loc[loans.status.eq('B'),'account_id'])
    verify('in_subquery',7,"SELECT trans_id FROM trans WHERE account_id IN (SELECT account_id FROM loans WHERE status='B')",t.loc[t.account_id.isin(bad_accounts),['trans_id']])
    bad=loans[loans.status.eq('B')][['account_id','date']].rename(columns={'date':'loan_date'})
    linked=t.merge(bad,on='account_id');keep=linked[linked.date.lt(linked.loan_date)][['trans_id']].drop_duplicates()
    verify('correlated_exists',7,"SELECT trans_id FROM trans t WHERE EXISTS (SELECT 1 FROM loans l WHERE l.status='B' AND l.account_id=t.account_id AND t.date<l.date)",keep)
    joined=loans[['loan_id','account_id','date']].rename(columns={'date':'loan_date'}).merge(t[['account_id','date']],on='account_id',how='left')
    days=(pd.to_datetime(joined.loan_date)-pd.to_datetime(joined.date)).dt.days
    matched=joined[days.gt(0)&days.le(365)].groupby('loan_id').size().reindex(loans.loan_id,fill_value=0).rename('records').reset_index()
    verify('non_equi_calendar_join',6,"SELECT l.loan_id,COUNT(t.trans_id) records FROM loans l LEFT JOIN trans t ON l.account_id=t.account_id AND t.date<l.date AND t.date>=date(l.date,'-365 days') GROUP BY l.loan_id",matched)
    combined=pd.concat([one,two],ignore_index=True)
    verify('union_all',8,'SELECT * FROM one UNION ALL SELECT * FROM two',combined)
    verify('union_distinct',8,'SELECT * FROM one UNION SELECT * FROM two',combined.drop_duplicates())
    conn.execute('CREATE TEMP TABLE lesson_test AS SELECT * FROM sale WHERE year IN (2010,2011)');conn.execute('CREATE TEMP VIEW lesson_view AS SELECT * FROM sale')
    verify('create_table_as',9,'SELECT * FROM lesson_test',sale[sale.year.isin([2010,2011])]);verify('create_view',9,'SELECT * FROM lesson_view',sale)
    return pd.DataFrame(checks),queries


def main(argv=None):
    ctx=context('B21',argv)
    references={key:ctx.source(key) for key in ['sql_basics','profile_sql','profile_slides','metrics_slides']}
    source_sql=references['sql_basics'].read_text(encoding='utf-8-sig');profile_source=references['profile_sql'].read_text(encoding='utf-8-sig')
    if not all(word in profile_source for word in ['180','365','max(trans_date)','avg(a.balance)']):raise AssertionError('Review the profile source windows')
    enc={'accounts':'gbk','clients':'gbk','disp':'gbk','card':'gbk','loans':'utf-8','order':'gbk','district':'utf-8'}
    tables={name:pd.read_csv(ctx.source('profile_'+name),encoding=encoding) for name,encoding in enc.items()}
    keys={'accounts':'account_id','clients':'client_id','disp':'disp_id','card':'card_id','loans':'loan_id','order':'order_id','district':'A1'}
    for name,key in keys.items():unique_key(tables[name],key)
    for left,right,key in [(tables['disp'],tables['accounts'],'account_id'),(tables['disp'],tables['clients'],'client_id'),
                            (tables['card'],tables['disp'],'disp_id'),(tables['loans'],tables['accounts'],'account_id'),(tables['order'],tables['accounts'],'account_id')]:many_to_one(left,right[[key]],on=key)
    t=pd.read_csv(ctx.source('profile_trans'),encoding='gbk',usecols=['trans_id','account_id','date','type','amount','balance','k_symbol'],dtype={'amount':'string','balance':'string'},low_memory=False)
    for field in ['amount','balance']:
        text=t[field].str.replace(r'^\$','',regex=True);t[field+'_cents']=money_minor(text,grouped=True)
    t=t.drop(columns=['amount','balance']);unique_key(t,'trans_id');many_to_one(t[['account_id']],tables['accounts'][['account_id']],on='account_id')
    if t.amount_cents.lt(0).any():raise ValueError('Expected unsigned transaction magnitudes with a separate type')
    for name in ['sale','table1','table2','one','two']:
        tables[name]=pd.read_csv(ctx.source('sql_'+name),encoding='gbk',header=None,names=['year','market','sale','profit'] if name=='sale' else ['id','value'])
    base=card_base(tables['card'],tables['disp'],tables['clients']);features=historical_features(base,t)
    with closing(sqlite3.connect(':memory:')) as conn:
        t.to_sql('trans',conn,index=False,chunksize=20000);conn.execute('CREATE INDEX trans_window ON trans(account_id,date)')
        sql_base=base.copy()
        for col in ['issued','birth_date']:sql_base[col]=sql_base[col].dt.strftime('%Y-%m-%d')
        sql_base.to_sql('card_base',conn,index=False)
        for name in ['loans','sale','table1','table2','one','two']:tables[name].to_sql(name,conn,index=False)
        conn.execute('CREATE INDEX loan_lookup ON loans(account_id,status,date)')
        profile_queries,profile_values=sql_profile_checks(conn,features);lesson_checks,lesson_text=lesson_queries(conn,tables,t)
    query_file='-- New SQLite queries for the normalized tables constructed by B21 main.py.\n-- Original MySQL server/import scripts are read-only references.\n\n'
    for name,query in {**lesson_text,**profile_queries}.items():
        if name=='create_table_as':query_file+='CREATE TEMP TABLE lesson_test AS SELECT * FROM sale WHERE year IN (2010,2011);\n'
        if name=='create_view':query_file+='CREATE TEMP VIEW lesson_view AS SELECT * FROM sale;\n'
        query_file+=f'-- {name}\n{query};\n\n'
    (ctx.output/'portable_queries.sql').write_text(query_file.rstrip()+'\n',encoding='utf-8')
    save_table(lesson_checks,ctx.output/'sql_checks.csv');save_table(features,ctx.output/'card_features_private.csv')
    profile=features.groupby(['card_type','sex']).agg(cards=('card_id','size'),distinct_clients=('client_id','nunique'),mean_issue_age=('age_at_issue','mean'),
        mean_last_gap_days=('last_days','mean'),known_last_balances=('last_day_balance_mean_cents','count'),mean_last_day_balance_cents=('last_day_balance_mean_cents','mean'),
        mean_w180_records=('w180_records','mean'),mean_w365_records=('w365_records','mean')).reset_index()
    profile['mean_last_day_balance']=profile.pop('mean_last_day_balance_cents')/100
    issued=features.assign(year=features.issued.dt.year).groupby(['year','card_type']).size().rename('cards').reset_index()
    save_table(profile,ctx.output/'card_profiles.csv');save_table(issued,ctx.output/'issue_year_counts.csv')
    table_counts=pd.DataFrame([{'table':name,'records':len(frame),'grain':keys.get(name,'teaching row')} for name,frame in tables.items()]+[{'table':'trans','records':len(t),'grain':'trans_id'}]);save_table(table_counts,ctx.output/'source_table_counts.csv')
    dictionary=pd.DataFrame([{'field':name,'grain':'card_id at issued','definition':meaning,'missing_rule':missing} for name,meaning,missing in [
        ('age_at_issue','发卡日已满周岁，另保留DATEDIFF/365兼容值','出生/发卡缺失报错'),('last_days','所有发卡日之前交易中最近日期间隔','无历史保持未知'),
        ('last_day_balance_mean_cents','同一最近交易日的余额均值，不冒充日终','同日多笔保留数量/最小/最大；无历史未知'),
        ('w180_records','0<发卡日−交易日<180的交易笔数','完整输入下无匹配为0'),('w365_records','0<发卡日−交易日<365的交易笔数','完整输入下无匹配为0'),
        ('debit/credit_cents','各窗口内原借/原贷标签的金额和','无匹配为0，不擅自重命名流入流出'),('transaction_weighted_balance','窗口内交易行余额均值，不是平均每日资产','无匹配未知'),
        ('credit_over_debit','原贷金额/原借金额；用于复核源SQL所谓出入比','分母0未知'),('credit_over_transaction_mean_balance','原贷金额/交易行加权平均余额','分母0未知'),
        ('unavailable_tags','职业、婚姻、收入、APP行为等模板字段缺上游数据','不造标签、不生成虚构典型个人')]])
    save_table(dictionary,ctx.output/'profile_dictionary.csv')
    books={key:read_cached_book(ctx.source(key)) for key in ['metric_template','base_standard_template','metric_standard_template','marketing_tags','antifraud_tags']}
    template_rows=[];descriptions={}
    for key,book in books.items():
        for name,sheet in book.items():
            role='标签/特征字典参考；无对应事实不伪造计算' if 'tags' in key else '指标/维度/责任与数据标准参考；落实为本实验窗口字典及质量规则'
            descriptions[(key,name)]=role;template_rows.append({'source':key,'sheet':name,'nonempty_cells':len(sheet.values),'formula_cells':len(sheet.formulas),'role':role})
    coverage=coverage_table(books,descriptions,ctx.output/'workbook-map.md');save_table(pd.DataFrame(template_rows),ctx.output/'template_coverage.csv')
    headings=list(re.finditer(r'/\*\s*SQL\d|/\*\s*SQl\d',source_sql))
    lesson_map=[]
    for number in range(1,10):
        mapped=lesson_checks.loc[lesson_checks.lesson.eq(number),'query'].tolist()
        if number==1:mapped=['本地SQLite内存库、13张输入表清单与列类型']
        lesson_map.append({'source_section':f'SQL{number}','portable_examples':'; '.join(mapped),'boundary':'新建临时表/视图仅在内存库；不执行原服务器建库、导入或文件路径语句'})
    save_table(pd.DataFrame(lesson_map),ctx.output/'sql_lesson_map.csv')
    diagnostics={'cards':len(features),'distinct_cardholders':int(features.client_id.nunique()),'transactions':len(t),
        'cards_without_preissue_history':int(features.last_days.isna().sum()),'cards_with_latest_day_ties':int(features.last_day_rows.gt(1).sum()),
        'latest_day_join_rows':int(features.last_day_rows.fillna(0).sum()),'max_w180_records':int(features.w180_records.max()),
        'windows_differing_cards':int(features.w180_records.ne(features.w365_records).sum()),'sql_profile_numeric_checks':profile_values,'sql_lesson_queries':len(lesson_checks)}
    write_json(ctx.output/'profile_diagnostics.json',diagnostics)
    plt=plotting();fig,ax=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    wide=profile.pivot(index='card_type',columns='sex',values='cards');wide.plot.bar(ax=ax[0],rot=0);ax[0].set(title='按卡类型与性别的卡数',xlabel='卡类型',ylabel='卡数')
    features.groupby('card_type')[['w180_records','w365_records']].mean().plot.bar(ax=ax[1],rot=0);ax[1].set(title='发卡前窗口不同，不合并为同一特征',xlabel='卡类型',ylabel='每卡平均交易笔数')
    fig.savefig(ctx.output/'card_profile.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained');ax.bar(lesson_checks['query'],lesson_checks.sql_rows,color='#087f8c');ax.set_yscale('symlog',linthresh=1);ax.tick_params(axis='x',rotation=70);ax.set(title='SQL与pandas逐表结果一致（记录数为对称对数轴）',ylabel='结果行数')
    fig.savefig(ctx.output/'sql_validation.png',dpi=150);plt.close(fig)
    report=f'''# B21 SQL取数与信用卡时点画像

## 重建范围

第8章SQL1—SQL9全部教学主题分别对应独立SQLite/pandas实现，{len(lesson_checks)}组查询逐表一致，包含去重、过滤、日期/CASE、GROUP BY/HAVING、五种连接、非等值窗口、IN/相关子查询、UNION/UNION ALL、临时表和视图。无表头的sale/One/Two/Table1/Table2按无表头读取，第一行不丢失；所有新建对象仅在内存库。源MySQL脚本含旧注释、服务器建库/导入路径，不原样执行，不要求本机安装MySQL。portable_queries.sql为新写的可移植查询，原SQL只读。

8张银行实体表共{len(t):,}笔交易，{len(features)}张卡，关联disp确定该卡的具体权限客户。客户号不作模型变量，也不从账户所有者替代真实持卡人。源金额有$和千分位，只按源金额单位处理，不据符号假定真实币种。

![画像汇总](card_profile.png)

## 发卡时点和窗口

所有特征严格使用交易日<发卡日，同日交易排除。原SQL简版注明180天，复杂版实际365天，二者分别计算0<days<180与0<days<365；不是“功能完全相同”。源a.issued-180这类日期减整数写法迁移为明确日历日期运算，贷款非等值教学例另保留<=365端点。

年龄以发卡日已满周岁为主，另存DATEDIFF/365兼容值。最近交易日有{diagnostics['cards_with_latest_day_ties']}张卡并列，直接关联得到{diagnostics['latest_day_join_rows']}行；画像仍保持{len(features)}行。无法确定当日顺序，不按交易ID猜日终余额；保留当日余额均值、最小/最大和笔数。窗口余额均值按交易行加权，并非每日资产均值。

源SQL把借标签金额称“入”、贷标签称“出”，主实现保留借/贷原标签及兼容比值，不在缺明确映射时宣称真实现金流方向。无交易窗口计数与金额0，余额/最近间隔未知，零分母比率未知。不能把365天金额当月收入，也不将已有持卡类别当未来营销响应标签。

## 独立验证与指标规范

两窗口的笔数、借/贷金额和交易行余额均值，以及最近日期/并列笔数/余额均值最小最大，合计{profile_values}个数值由独立SQL逐卡核对。完整SQL/pandas结果不公开，只发布核对计数、卡类型/性别聚合和分年度发卡数量。

![SQL验证](sql_validation.png)

第7章指标设计、两份第13章数据标准、营销/反欺诈模板共{coverage['source_sheets']}张表都有去向：将粒度、时点、窗口、分母、缺失和发布规则落实为profile_dictionary。模板中的职业、婚姻、设备/手机号网络等缺上游事实，不伪造标签或典型个人；模板含XXX占位SQL，不当可执行事实查询。信用卡画像PPT要求的业务描述、卡类型/性别、年龄和办卡前行为已按现有字段落实；未来金卡响应预测缺观察后标签，不冒充完成预测模型。无独立保存数值参考，状态为运行通过。

```powershell
python run_labs.py --lab B21
```

客户/卡/交易标识、日期及逐卡特征只留本地card_features_private.csv。导入脚本及重复CSV资源仅记录去向，不把未执行服务器脚本计作执行通过。
'''
    finish(ctx,{'lab_id':'B21','status':'execution_verified',**diagnostics,'sql_lesson_groups':9,'source_table_counts':dict(zip(table_counts.table,table_counts.records)),'workbook_coverage':coverage},report)


if __name__=='__main__':main()
