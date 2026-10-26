"""B03: preserve valid zeros and record grain while cleaning, splitting and joining."""
import ipaddress,re
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table
from .tabular_tools import unique_key,many_to_one,money_minor,append_aligned
from .workbook_reference import read_cached_book,coverage_table


def clean_orders(raw):
    """The title/header have already been handled; preserve source row numbers and unknowns."""
    frame=raw.copy(deep=True)
    blank=frame.isna().all(axis=1)
    frame=frame.loc[~blank].copy()
    frame.insert(0,'source_excel_row',frame.index.to_numpy()+3)
    errors=[]
    excel_errors={'#N/A','#VALUE!','#REF!','#DIV/0!','#NAME?','#NUM!','#NULL!'}
    for col in raw.columns:
        if frame[col].dtype=='object' or pd.api.types.is_string_dtype(frame[col]):
            for row,value in frame[col].items():
                if isinstance(value,str) and value.strip() in excel_errors:
                    errors.append({'source_excel_row':int(row)+3,'field':col,'source_error':value})
                    frame.loc[row,col]=pd.NA
            frame[col]=frame[col].map(lambda v:v.strip() if isinstance(v,str) else v)
    if frame.订单号.isna().any():raise ValueError('A nonempty detail record needs an order identifier')
    amounts=money_minor(frame.实付金额)
    quantities=pd.to_numeric(frame.下单数量,errors='raise')
    if (amounts<0).any() or quantities.isna().any() or (quantities<0).any() or (quantities%1!=0).any():raise ValueError('Expected finite nonnegative paid amounts and whole quantities')
    frame['paid_minor']=amounts;frame['quantity']=quantities.astype('int64')
    frame['order_date_clean']=pd.to_datetime(frame.order_date,errors='raise').dt.normalize()
    components=frame[['year','month','day']].apply(pd.to_numeric,errors='raise')
    assembled=pd.to_datetime(components,errors='raise')
    if not assembled.eq(frame.order_date_clean).all():raise ValueError('Split date columns conflict with order_date')
    frame['product_known']=frame.商品id.notna()
    def valid_ip(value):
        if pd.isna(value):return False
        try:ipaddress.ip_address(str(value));return True
        except ValueError:return False
    frame['ip_is_valid_address']=frame.ip地址.map(valid_ip)
    audit={'input_rows_below_header':len(raw),'blank_rows_removed':int(blank.sum()),'retained_details':len(frame),
           'excel_error_cells':len(errors),'genuine_zero_paid_details':int((amounts==0).sum()),
           'unknown_product_details':int((~frame.product_known).sum()),'non_ip_details':int((~frame.ip_is_valid_address).sum()),
           'duplicate_order_ids':int(frame.订单号.duplicated().sum()),'exact_duplicate_details':int(raw.loc[~blank].duplicated().sum()),
           'paid_minor_total':int(amounts.sum()),'quantity_total':int(quantities.sum())}
    return frame,audit,pd.DataFrame(errors,columns=['source_excel_row','field','source_error'])


def split_records(raw):
    required=['订单号','收货地址','商品名称','数量','客户姓名']
    if raw[required].isna().any().any():raise ValueError('The split example requires all five source fields')
    rows=[];bridge=[]
    for number,record in enumerate(raw.to_dict('records'),1):
        ids=[part.strip() for part in str(record['订单号']).split(',')]
        if not ids or any(not part for part in ids) or len(set(ids))!=len(ids):raise ValueError('Order tokens must be nonempty and distinct within a source row')
        address=re.fullmatch(r'(?P<province>.+?省)(?P<city>.+?市)(?P<district>.+)',record['收货地址'])
        quantity=re.fullmatch(r'(?P<count>\d+)(?P<unit>\D+)',record['数量'].strip())
        name_parts=re.findall(r'[A-Z][a-z]*',record['客户姓名'])
        if address is None or quantity is None or ''.join(name_parts)!=record['客户姓名']:raise ValueError('Source pattern outside this two-row teaching example')
        row={'source_record':number,'product':record['商品名称'],'quantity':int(quantity['count']),'unit':quantity['unit'],
             **address.groupdict(),'name_parts':' | '.join(name_parts)}
        row.update({f'order_part_{i}':value for i,value in enumerate(ids,1)});rows.append(row)
        for token in ids:bridge.append({'source_record':number,'order_id':token})
    # No quantities or amounts enter the bridge: there is no supplied allocation rule.
    return pd.DataFrame(rows),pd.DataFrame(bridge)


def join_courses(students,courses,enrollments):
    unique_key(students,'学号');unique_key(courses,'课程号')
    details=many_to_one(enrollments,students[['学号','系别']],on='学号')
    details=many_to_one(details,courses,on='课程号')
    if len(details)!=len(enrollments):raise AssertionError('Dimension join multiplied enrollment rows')
    score=pd.to_numeric(details.成绩,errors='raise')
    if score.isna().any() or not score.between(0,100).all():raise ValueError('Expected observed scores from 0 to 100')
    details['passed']=score.ge(60)
    summary=details.groupby(['课程号','课程名'],as_index=False).agg(enrollment_records=('学号','size'),students=('学号','nunique'),mean_score=('成绩','mean'),passes=('passed','sum'))
    summary['pass_fraction']=summary.passes/summary.enrollment_records
    return details,summary,{'enrollment_records':len(details),'enrolled_students':int(details.学号.nunique()),
                            'students_without_enrollments':int((~students.学号.isin(details.学号)).sum())}


def main(argv=None):
    ctx=context('B03',argv);ctx.source('pbi_basics_slides')
    source_keys=['etl_dirty_orders','etl_split_orders','etl_course_join','etl_append_same','etl_append_different']
    paths={key:ctx.source(key) for key in source_keys};books={key:read_cached_book(path) for key,path in paths.items()}
    source=books['etl_dirty_orders']['sheet1']
    # pandas.read_excel turns #N/A into NaN before an audit can distinguish errors from blanks.
    raw=pd.DataFrame(source.matrix('A3:P32'),columns=source.matrix('A2:P2')[0])
    cleaned,audit,error_rows=clean_orders(raw)
    save_table(cleaned,ctx.output/'private_cleaned_details.csv');save_table(error_rows,ctx.output/'private_source_errors.csv')
    quality=pd.DataFrame([{'check':key,'value':value} for key,value in audit.items()]);save_table(quality,ctx.output/'etl_quality.csv')
    groups=cleaned.groupby('一级类别',as_index=False,dropna=False).agg(details=('paid_minor','size'),units=('quantity','sum'),paid_minor=('paid_minor','sum'))
    groups['paid_amount']=groups.paid_minor/100
    if groups.paid_minor.sum()!=cleaned.paid_minor.sum():raise AssertionError('Cleaning changed retained payment totals')
    save_table(groups.drop(columns='paid_minor'),ctx.output/'etl_category_totals.csv')
    split,bridge=split_records(pd.read_excel(paths['etl_split_orders'],sheet_name='Sheet2'))
    save_table(split,ctx.output/'private_split_columns.csv');save_table(bridge,ctx.output/'private_order_bridge.csv')
    unit_totals=split.groupby('unit',as_index=False).quantity.sum();save_table(unit_totals,ctx.output/'split_units.csv')
    join_inputs=pd.read_excel(paths['etl_course_join'],sheet_name=None)
    joined,course_summary,join_audit=join_courses(join_inputs['学生表'],join_inputs['课程表'],join_inputs['选课表'])
    save_table(joined,ctx.output/'private_enrollment_details.csv');save_table(course_summary,ctx.output/'course_summary.csv')
    same=pd.read_excel(paths['etl_append_same'],sheet_name=None);different=pd.read_excel(paths['etl_append_different'],sheet_name=None)
    a=append_aligned(list(same.values()));b=append_aligned(list(different.values()),[{}, {'金额':'销售额'}])
    pd.testing.assert_frame_equal(a,b)
    naive=pd.concat(list(different.values()),ignore_index=True)
    append=[]
    for label,frame in [('same_schema',a),('explicit_amount_mapping',b)]:
        append.append({'branch':label,'records':len(frame),'units':int(frame.销售数量.sum()),'sales_amount':float(frame.销售额.sum()),'missing_amounts':int(frame.销售额.isna().sum())})
    append.append({'branch':'INVALID_naive_append_different_names','records':len(naive),'units':int(naive.销售数量.sum()),'sales_amount':float(naive.销售额.sum()),'missing_amounts':int(naive.销售额.isna().sum())})
    append=pd.DataFrame(append);save_table(append,ctx.output/'append_summary.csv');save_table(b,ctx.output/'local_appended_stores.csv')
    descriptions={}
    for key,book in books.items():
        for name in book:
            descriptions[(key,name)]=('空白工作表，不生成伪造记录' if not book[name].values else
                '去标题行、保留源行号，空白/错误/真实零分开；源ip地址字段不强行解释为IP' if key=='etl_dirty_orders' else
                '订单号横向拆列、地址和数量拆分；另建不带数量的订单桥，保持原行粒度' if key=='etl_split_orders' else
                '学生和课程维度键唯一，选课记录作事实，关联后行数守恒；不把选课行数当去重人数' if key=='etl_course_join' else
                'concat显式对齐字段；金额仅在此受控示例映射为销售额，不猜测门店A/A1对应')
    coverage=coverage_table(books,descriptions,ctx.output/'workbook-map.md')
    plt=plotting();fig,axes=plt.subplots(1,3,figsize=(16,5),layout='constrained')
    metrics=[('保留明细',audit['retained_details']),('去除全空白行',audit['blank_rows_removed']),('真实零支付',audit['genuine_zero_paid_details']),('未知商品明细',audit['unknown_product_details'])]
    axes[0].barh([x[0] for x in metrics],[x[1] for x in metrics],color=['#247d86','#bdcbd4','#d67b28','#79609c'])
    axes[0].set(title='清洗事件分别记账',xlabel='行数（各类别可重叠，不相加）')
    for i,(_,value) in enumerate(metrics):axes[0].text(value+.2,i,str(value),va='center')
    axes[0].set_xlim(0,max(x[1] for x in metrics)*1.15)
    axes[1].bar(groups.一级类别,groups.paid_amount,color='#247d86');axes[1].set(title='按类别保留支付总额',ylabel='实付金额（原表金额单位）')
    axes[2].bar(['名称一致','显式映射','错误直接追加'],append.sales_amount,color=['#247d86','#247d86','#d67b28'])
    axes[2].set(title='异名字段未经映射会漏计',ylabel='销售额（示例原数值单位）')
    for i,value in enumerate(append.sales_amount):axes[2].text(i,value,f'{value:,.0f}',ha='center',va='bottom')
    fig.savefig(ctx.output/'etl_diagnostics.png',dpi=150);plt.close(fig)
    report=f'''# B03 ETL清洗、拆列与合并

## 清洗不是删除所有异常记录

从“数据清洗示例数据”的第二行读取列名，保留Excel源行号。标题下{audit['input_rows_below_header']}行中去除{audit['blank_rows_removed']}条全空白行，保留{audit['retained_details']}条明细。{audit['excel_error_cells']}个Excel错误单元格变为显式缺失并记录原坐标；{audit['genuine_zero_paid_details']}条真实零支付与零数量明细保留，未知商品并不自动等于无效订单。按订单号不能贸然去重，因为原表名是订单明细，没有完整业务行键；本次同订单号重复{audit['duplicate_order_ids']}条、完全相同明细{audit['exact_duplicate_details']}条。

金额从字符串严格转成整数分，不把解析失败改成0；日期列和year/month/day独立拼装核对一致。商品名称仅修剪首尾空白，不重写中间文本。源列“ip地址”实际含城市名、-911、其他或错误值；{audit['non_ip_details']}条都不是有效IP地址。本实现保留原文本、另标记异常，不把它转成IP，也不把其他城市直接改成下单城市。

![ETL质量与守恒](etl_diagnostics.png)

## 拆列保持源粒度

2行示例各有3个逗号分隔订单号，先横向拆成3列，分别把地址拆为省/市/区、数量拆为数值/单位、CamelCase名字拆成片段。另建{len(bridge)}行订单桥，仅含源行号与订单号，不带数量。原8件和10本对应的是哪一订单、是否每单都有相同数量，教材未说明，不能展开后复制成24件和30本；也不把件和本混成一个总数量。地址规则只针对这两个省市示例，不是通用全国地址解析器；名字片段不当作已确认的姓/名。

## 横向关联与纵向追加

课程表、学生表先查唯一键，再用选课表作为事实进行many_to_one连接。{join_audit['enrollment_records']}条选课、{join_audit['enrolled_students']}名去重学生，{join_audit['students_without_enrollments']}名学生无选课；课程通过率按选课记录为分母，不把总选课行数叫总学生数。姓名、手机号和逐人分数仅留本地。

季度追加保留8条原记录；异名示例明确将“金额”映射为“销售额”，与同名示例结果逐值相同。若直接concat，第二季度的4条销售额落入另一列，sum会漏掉406；正确合计1212，错误分支806。两文件门店A1与A等未提供关系，不擅自统一编码。

5个工作簿的全部{coverage['source_sheets']}张工作表（含2张空表）见[迁移对照](workbook-map.md)。本章课件第24至26页的合并列、提取、拆列、合并及追加分别落实到这些函数；没有数据分配规则的地方不伪造答案。原件只读，公开聚合结果及过程说明，明细和订单桥只留本地。
'''
    finish(ctx,{'lab_id':'B03','status':'execution_verified','cleaning':audit,'course_join':join_audit,
                'split_source_rows':len(split),'bridge_rows_without_measures':len(bridge),'append':append.to_dict('records'),
                'workbook_coverage':coverage},report)


if __name__=='__main__':main()
