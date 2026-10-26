"""B02: formulas, lookup boundaries, workbook cache defects, pivots and formatting rules."""
import calendar,csv,datetime,io,math,re,zipfile
from xml.etree import ElementTree as ET
import numpy as np
import pandas as pd
from openpyxl.utils.cell import get_column_letter,coordinate_to_tuple
from .common import context,finish,plotting,save_table
from .workbook_reference import read_cached_book,coverage_table
from .tabular_tools import money_minor
from .excel_semantics import excel_round,approximate_lookup,exact_lookup,offset_address,workday,networkdays,tariff,frequency,subject_passes

SEED=20261026


class CacheChecks:
    def __init__(self):self.rows=[];self.seen=set()

    def add(self,key,sheet,cell,actual,allow_difference=False,status=None):
        identity=(key,sheet.name,cell)
        if identity in self.seen:raise AssertionError('Cached cell checked twice')
        self.seen.add(identity);expected=sheet.get(cell)
        a='' if actual is None else actual;b='' if expected is None else expected
        if isinstance(a,(datetime.datetime,datetime.date,pd.Timestamp)) and isinstance(b,(datetime.datetime,datetime.date,pd.Timestamp)):
            equal=pd.Timestamp(a)==pd.Timestamp(b)
        elif isinstance(a,(float,int,np.number)) and isinstance(b,(float,int,np.number)):
            equal=bool(np.isclose(a,b,atol=1e-10,rtol=1e-12))
        else:equal=str(a)==str(b)
        result=status or ('matched' if equal else 'confirmed_source_difference')
        if status is None and not equal and not allow_difference:raise AssertionError(f'Unexpected cached difference: {identity}: {a!r} / {b!r}')
        self.rows.append({'source':key,'sheet':sheet.name,'cell':cell,'python_value':str(a),'cached_value':str(b),
                          'status':result,'source_formula':sheet.formulas.get(cell,'')})


def simple_examples(key,sheet,checks,frozen_clock,rng):
    """Only the listed scalar demonstrations, no eval and no general Excel expression parser."""
    results={}
    for address,formula in sheet.formulas.items():
        match=re.fullmatch(r'=([A-Z]+)\((.*)\)',formula)
        if match is None:raise ValueError('Unexpected scalar demonstration formula')
        name,body=match.groups();tokens=next(csv.reader([body],skipinitialspace=True)) if body else []
        args=[]
        for token in tokens:
            if re.fullmatch(r'\$?[A-Z]+\$?\d+',token):args.append(results.get(token.replace('$',''),sheet.get(token.replace('$',''))))
            elif re.fullmatch(r'-?\d+(?:\.\d+)?',token):args.append(float(token) if '.' in token else int(token))
            else:args.append(token)
        text=lambda v:'' if v is None else str(v)
        if name=='INT':value=math.floor(args[0])
        elif name=='MOD':value=args[0]%args[1]
        elif name=='ROUND':value=excel_round(*args)
        elif name=='ABS':value=abs(args[0])
        elif name=='SQRT':value=math.sqrt(args[0])
        elif name=='MID':value=text(args[0])[int(args[1])-1:int(args[1])-1+int(args[2])]
        elif name=='LEFT':value=text(args[0])[:int(args[1])]
        elif name=='RIGHT':value=text(args[0])[-int(args[1]):] if args[1] else ''
        elif name=='LEN':value=len(text(args[0]))
        elif name=='TEXT':
            if args[1]!=0:raise ValueError('Only the source TEXT(number,0) demonstration is supported')
            value=str(int(excel_round(args[0])))
        elif name=='REPT':value=text(args[0])*int(args[1])
        elif name=='REPLACE':value=text(args[0])[:int(args[1])-1]+text(args[3])+text(args[0])[int(args[1])-1+int(args[2]):]
        elif name=='SUBSTITUTE':value=text(args[0]).replace(text(args[1]),text(args[2]))
        elif name=='DATE':value=pd.Timestamp(datetime.datetime(*map(int,args)))
        elif name=='TODAY':value=frozen_clock.normalize()
        elif name=='NOW':value=frozen_clock
        elif name=='RAND':value=float(rng.random())
        elif name=='RANDBETWEEN':value=int(rng.integers(args[0],args[1]+1))
        else:raise ValueError(f'Scalar function outside the inspected demonstrations: {name}')
        results[address]=value
        checks.add(key,sheet,address,value,
                   status='new_seeded_random_not_cache_comparison' if name in ('RAND','RANDBETWEEN') else None)
    return results


def pivot_region_filter(path):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        definition=ET.fromstring(z.read('xl/pivotTables/pivotTable1.xml'))
        caches=[n for n in z.namelist() if re.fullmatch(r'xl/pivotCache/pivotCacheDefinition\d+.xml',n)]
        if len(caches)!=1:raise ValueError('Expected the single inspected pivot cache')
        field=ET.fromstring(z.read(caches[0])).find('s:cacheFields',ns)[0]
        if field.attrib['name']!='销售地区':raise ValueError('Unexpected filtered pivot field')
        values=[e.attrib.get('v') for e in field.find('s:sharedItems',ns)]
        items=definition.find('s:pivotFields',ns)[0].find('s:items',ns)
        return [values[int(item.attrib['x'])] for item in items if 'x' in item.attrib and item.attrib.get('h')!='1']


def summarize_pivots(source,reference,path,checks):
    rows=source.matrix('A2:E37');frame=pd.DataFrame(rows,columns=['region','staff','product','quantity','price'])
    refrows=reference.matrix('A2:E37')
    if rows!=refrows:raise AssertionError('Exercise and reference pivot inputs differ')
    frame['amount_minor']=money_minor(frame.price)*frame.quantity.to_numpy(dtype='int64')
    for key,sheet in [('pivot_exercises',source),('pivot_reference',reference)]:
        for i,value in enumerate(frame.amount_minor/100,2):checks.add(key,sheet,'F'+str(i),value)
    regions=pivot_region_filter(path);filtered=frame.loc[frame.region.isin(regions)]
    staff=filtered.groupby('staff',as_index=True).agg(quantity=('quantity','sum'),amount_minor=('amount_minor','sum'))
    for row in range(10,14):
        label=reference.get('K'+str(row));quantity=staff.quantity.sum() if label=='总计' else staff.loc[label,'quantity']
        amount=staff.amount_minor.sum() if label=='总计' else staff.loc[label,'amount_minor']
        for col,value in [('L',quantity),('M',amount/staff.amount_minor.sum()),('N',amount/100)]:checks.add('pivot_reference',reference,f'{col}{row}',value)
    product=frame.groupby('product').agg(quantity=('quantity','sum'),amount_minor=('amount_minor','sum'))
    for row in range(16,21):
        label=reference.get('K'+str(row));q=product.quantity.sum() if label=='总计' else product.loc[label,'quantity'];a=product.amount_minor.sum() if label=='总计' else product.loc[label,'amount_minor']
        checks.add('pivot_reference',reference,'L'+str(row),a/100);checks.add('pivot_reference',reference,'M'+str(row),q)
    product_city=frame.groupby(['product','region']).agg(quantity=('quantity','sum'),amount_minor=('amount_minor','sum'))
    current=None
    for row in range(10,27):
        label=reference.get('P'+str(row));region=reference.get('Q'+str(row))
        if label is not None:current=label
        if current=='总计':q=frame.quantity.sum();a=frame.amount_minor.sum()
        elif region is None:q=product.loc[current,'quantity'];a=product.loc[current,'amount_minor']
        else:q=product_city.loc[(current,region),'quantity'];a=product_city.loc[(current,region),'amount_minor']
        for col,value in [('R',q),('S',a/100),('T',a/frame.amount_minor.sum())]:checks.add('pivot_reference',reference,f'{col}{row}',value)
    for cell,formula in reference.formulas.items():
        if re.fullmatch(r'=[K-N]\d+',formula):checks.add('pivot_reference',reference,cell,reference.get(formula[1:]))
    return frame,staff,product,product_city,regions


def main(argv=None):
    ctx=context('B02',argv)
    keys=['basic_functions','lookup_functions','wps_functions','pivot_exercises','pivot_reference']
    paths={key:ctx.source(key) for key in keys};books={key:read_cached_book(path) for key,path in paths.items()}
    basic,lookup,wps,exercise,reference=[books[key] for key in keys]
    checks=CacheChecks();rng=np.random.default_rng(SEED)
    frozen_clock=pd.Timestamp(basic['常用函数应用'].get('L8'))
    for key,book in [('basic_functions',basic),('wps_functions',wps)]:simple_examples(key,book['常用函数应用'],checks,frozen_clock,rng)
    private={};summary=[]
    for key,book,label in [('basic_functions',basic,'1IF+AND+OR例子'),('wps_functions',wps,'1、IF+AND+OR例子')]:
        sheet=book[label];scores=np.asarray(sheet.matrix('E2:G10'),dtype=float)
        all_pass,any_pass=subject_passes(scores)
        for i in range(9):
            checks.add(key,sheet,'A'+str(i+2),str(sheet.get('B'+str(i+2)))[:3])
            if key=='wps_functions':
                checks.add(key,sheet,'H'+str(i+2),'通过' if all_pass[i] else '未通过')
                checks.add(key,sheet,'I'+str(i+2),'通过' if any_pass[i] else '未通过',allow_difference=True)
        private[key+'_pass']=pd.DataFrame({'all_subjects_pass':all_pass,'any_subject_pass':any_pass})
        summary.extend([{'exercise':key+'_AND','result':int(all_pass.sum())},{'exercise':key+'_OR_corrected_E_F_G','result':int(any_pass.sum())}])
    for key,book,label in [('basic_functions',basic,'3COUNTIF-统计'),('wps_functions',wps,'2、COUNTIF-统计')]:
        sheet=book[label];states=np.asarray(sheet.matrix('B2:K11'))
        if not set(states.ravel()).issubset({'a','b','c'}):raise ValueError('Unknown attendance code')
        counts=pd.DataFrame({'late':(states=='b').sum(axis=1),'absent':(states=='c').sum(axis=1)})
        private[key+'_attendance']=counts
        if key=='wps_functions':
            for i in range(10):
                checks.add(key,sheet,'L'+str(i+2),counts.late.iloc[i]);checks.add(key,sheet,'M'+str(i+2),counts.absent.iloc[i])
            checks.add(key,sheet,'C19',int(((states[:,0]=='b')&(states[:,1]=='b')).sum()))
        summary.append({'exercise':key+'_late_events','result':int(counts.late.sum())})
    charges=basic['2IF-水电气费'];bills=[]
    for policy in ['whole_tier','progressive']:
        for row in range(3,7):
            water=tariff(charges.get('B'+str(row)),[120,176],[charges.get('B12'),charges.get('C12'),charges.get('D12')],policy)
            power=tariff(charges.get('C'+str(row)),[240,400],[charges.get('B11'),charges.get('C11'),charges.get('D11')],policy)
            gas=tariff(charges.get('D'+str(row)),[],[charges.get('B10')],policy)
            bills.append({'policy':policy,'source_row':row,'water_fee':water,'power_fee':power,'gas_fee':gas,'total':excel_round(water+power+gas,2)})
    bills=pd.DataFrame(bills);private['tariff_details']=bills
    save_table(bills.groupby('policy',as_index=False)[['water_fee','power_fee','gas_fee','total']].sum().round(2),ctx.output/'tariff_comparison.csv')
    ledger=basic['4借贷-sumif'];entries=pd.DataFrame(ledger.matrix('A3:I14'),columns=['voucher','date','subject','direction','bank','cheque','client','amount','note'])
    entries['minor']=money_minor(entries.amount)
    for direction in ['借','贷']:summary.append({'exercise':'SUMIF_'+direction,'result':int(entries.loc[entries.direction.eq(direction),'minor'].sum())/100})
    condition=entries.direction.eq('借')&entries.bank.eq('工行')
    summary.extend([{'exercise':'SUMIFS_工行借方','result':int(entries.loc[condition,'minor'].sum())/100},
                    {'exercise':'AVERAGEIFS_工行借方','result':float(entries.loc[condition,'minor'].mean()/100)}])
    dates=basic['6计算日期'];holidays=[dates.get('D'+str(row)) for row in range(5,12)]
    date_rows=[{'exercise':'WORKDAY_with_supplied_holidays','input':str(dates.get('D2')),'result':str(workday(dates.get('D2'),dates.get('E2'),holidays).date())},
               {'exercise':'NETWORKDAYS_inclusive_with_supplied_holidays','input':str(dates.get('H2'))+' to '+str(dates.get('I2')),'result':str(networkdays(dates.get('H2'),dates.get('I2'),holidays))},
               {'exercise':'EDATE_probation','input':str(dates.get('H7')),'result':str((pd.Timestamp(dates.get('H7'))+pd.DateOffset(months=int(dates.get('I7')))).date())}]
    for row in range(2,22):
        value=pd.Timestamp(dates.get('A'+str(row)));date_rows.append({'exercise':'WEEKDAY_weekend','input':str(value.date()),'result':str(value.weekday()>=5)})
    for row in range(2,19):
        value=basic['5最后1天等'].get('A'+str(row))
        if not isinstance(value,(datetime.datetime,datetime.date,pd.Timestamp)):continue
        date=pd.Timestamp(value);date_rows.append({'exercise':'EOMONTH','input':str(date.date()),'result':str((date+pd.offsets.MonthEnd(0)).date())})
        date_rows.append({'exercise':'days_in_month','input':str(date.date()),'result':str(date.days_in_month)})
    for row in range(2,14):
        year=basic['7MOD判断闰年'].get('A'+str(row))
        if not isinstance(year,(int,float)):continue
        date_rows.append({'exercise':'leap_year','input':str(year),'result':str(calendar.isleap(int(year)))})
    # Fixed source clock makes temporal demonstrations reviewable; it is not the execution date.
    start=pd.Timestamp(dates.get('H2'));end=pd.Timestamp(dates.get('I2'));months=(end.year-start.year)*12+end.month-start.month-(end.day<start.day)
    date_rows.extend([{'exercise':'DATEDIF_complete_months','input':f'{start.date()} to {end.date()}','result':str(months)},
                      *[{'exercise':name,'input':str(frozen_clock),'result':str(value)} for name,value in [('YEAR',frozen_clock.year),('MONTH',frozen_clock.month),('DAY',frozen_clock.day)]]])
    save_table(pd.DataFrame(date_rows),ctx.output/'date_examples.csv')
    phone=basic['8隐藏几位手机号'];phones=[str(v) for address,v in phone.values.items() if re.fullmatch(r'A\d+',address) and address!='A1']
    if not all(re.fullmatch(r'\d{11}',value) for value in phones):raise ValueError('Expected eleven-digit telephone strings')
    private['masked_phones']=pd.DataFrame({'masked_positions_8_to_10':[v[:7]+'***'+v[10:] for v in phones]})
    for key,label in [('lookup_functions','1.VLOOKUP精确查找'),('wps_functions','3、VLOOKUP精确查找')]:
        sheet=books[key][label]
        mapping=[(sheet.get('G'+str(i)),sheet.get('H'+str(i))) for i in range(2,3378) if sheet.get('G'+str(i)) is not None]
        invalid=[pair for pair in mapping if pair[0] in {'#VALUE!','#N/A','#REF!','#DIV/0!','#NUM!','#NAME?','#NULL!'}]
        mapping=[pair for pair in mapping if pair not in invalid]
        private[key+'_invalid_dictionary_keys']=pd.DataFrame(invalid,columns=['source_error','label'])
        values=[sheet.get('A'+str(i)) for i in range(2,3378) if sheet.get('A'+str(i)) is not None]
        labels=exact_lookup(values,[v[0] for v in mapping],[v[1] for v in mapping])
        private[key+'_exact_lookup']=pd.DataFrame({'product_code':values,'product_name':labels})
        summary.extend([{'exercise':key+'_exact_lookup_rows','result':len(values)},{'exercise':key+'_unmatched','result':int(labels.isna().sum())},
                        {'exercise':key+'_dictionary_error_rows_quarantined','result':len(invalid)}])
    a=lookup['1.VLOOKUP近似查找'];actions=approximate_lookup([a.get('C'+str(i)) for i in range(2,8)],[a.get('H'+str(i)) for i in range(2,5)],[a.get('I'+str(i)) for i in range(2,5)])
    private['approximate_action']=pd.DataFrame({'action':actions})
    cat=lookup['3.查找品类名称'];pairs=[(cat.get('F'+str(i)),cat.get('E'+str(i))) for i in range(2,3316) if cat.get('F'+str(i)) is not None]
    values=[cat.get('B'+str(i)) for i in range(2,3316)]
    labels=exact_lookup(values,[p[0] for p in pairs],[p[1] for p in pairs]);private['index_match_categories']=pd.DataFrame({'category':labels})
    summary.append({'exercise':'INDEX_MATCH_category_unmatched','result':int(labels.isna().sum())})
    for origin,dr,dc,h,w in [('A1',3,3,4,4),('I4',-1,3,5,4),('B11',5,3,3,2),('K18',-7,-1,7,2)]:
        address=offset_address(origin,dr,dc,h,w);values=lookup['OFFSET-练习自学'].matrix(address)
        flattened=[v for row in values for v in row];summary.append({'exercise':'OFFSET_'+address,'result':sum(flattened) if all(isinstance(v,(int,float)) for v in flattened) else len(flattened)})
    private['offset_gray']=pd.DataFrame(lookup['2.OFFSET函数'].matrix(offset_address('A1',5,1,3,3)),columns=['name','sex','age'])
    summary.extend([{'exercise':'INDEX_B2H17_row5_col4','result':lookup['3.INDEX理解'].matrix('B2:H17')[4][3]},
                    {'exercise':'MATCH_100_C2C14','result':[row[0] for row in lookup['3.MATCH理解'].matrix('C2:C14')].index(100)+1},
                    {'exercise':'MATCH_中国_F4L4','result':lookup['3.MATCH理解'].matrix('F4:L4')[0].index('中国')+1},
                    {'exercise':'ROW_COLUMN_E6','result':'6,5'}])
    admin=lookup['行政区划分'];province=admin.get('A1');cities=[admin.get('A'+str(i)) for i in range(2,36) if admin.get('A'+str(i)) is not None]
    summary.extend([{'exercise':'INDIRECT_'+province+'_provided_cities','result':len(cities)},{'exercise':'HLOOKUP_'+province+'_row2','result':cities[0]}])
    frame,staff,product,product_city,regions=summarize_pivots(exercise['数据透视表'],reference['数据透视表'],paths['pivot_reference'],checks)
    product=product.reset_index();product['sales_amount']=product.amount_minor/100
    city=product_city.reset_index();city['sales_amount']=city.amount_minor/100
    save_table(product.drop(columns='amount_minor'),ctx.output/'pivot_product_totals.csv');save_table(city.drop(columns='amount_minor'),ctx.output/'pivot_product_city.csv')
    anonymized=staff.reset_index(drop=True).assign(staff_code=[f'S{i+1}' for i in range(len(staff))]);anonymized['sales_amount']=anonymized.amount_minor/100;anonymized['selected_region']=';'.join(regions)
    save_table(anonymized.drop(columns='amount_minor'),ctx.output/'pivot_filtered_staff.csv')
    multiplication=[];sheet=reference['单元格引用']
    for row in range(2,11):
        output={'multiplier':row-1}
        for col in range(2,11):
            value=f'{row-1}*{col-1}={(row-1)*(col-1)}' if row>=col else ''
            checks.add('pivot_reference',sheet,f'{get_column_letter(col)}{row}',value);output[str(col-1)]=value
        multiplication.append(output)
    save_table(pd.DataFrame(multiplication),ctx.output/'multiplication_table.csv')
    grade=reference['查找'];bounds=[grade.get('F'+str(r)) for r in range(2,7)];bands=[grade.get('G'+str(r)) for r in range(2,7)]
    scores=np.asarray([grade.get('B'+str(r)) for r in range(2,42)],dtype=float);labels=approximate_lookup(scores,bounds,bands)
    for r,label in enumerate(labels,2):checks.add('pivot_reference',grade,'C'+str(r),label)
    distribution=pd.DataFrame({'grade':bands,'records':[int((labels==label).sum()) for label in bands]});save_table(distribution,ctx.output/'grade_distribution.csv')
    private['grade_ranks']=pd.DataFrame({'score':scores,'grade':labels,'rank_descending_with_ties':pd.Series(scores).rank(method='min',ascending=False)})
    counts=frequency(scores,[60,70,80,90,100]);summary.extend([{'exercise':f'FREQUENCY_upper_bin_{i}','result':int(v)} for i,v in enumerate(counts)])
    summary.extend([{'exercise':'MAX_scores','result':scores.max()},{'exercise':'MIN_scores','result':scores.min()},
                    {'exercise':'SUM_scores','result':scores.sum()},{'exercise':'AVERAGE_scores','result':scores.mean()},
                    {'exercise':'COUNT_scores','result':len(scores)},{'exercise':'COUNTA_basic_C3_C21','result':sum(basic['常用函数应用'].get('C'+str(i)) is not None for i in range(3,22))},
                    {'exercise':'AVERAGEIF_Jinan','result':frame.loc[frame.region.isin(regions),'amount_minor'].mean()/100},
                    {'exercise':'COUNTIFS_selected_region_and_notebook','result':int((frame.region.isin(regions)&frame['product'].eq('笔记本')).sum())},
                    {'exercise':'NOT_all_pass_wps','result':int((~private['wps_functions_pass'].all_subjects_pass).sum())}])
    cf=reference['条件格式'];flags=[]
    for r in range(3,8):flags.append({'rule':'between_15_25','cell':'K'+str(r),'selected':15<=cf.get('K'+str(r))<=25})
    for r in range(19,24):
        for col in ['G','H']:
            index=coordinate_to_tuple(col+str(r))[1];left=cf.get(get_column_letter(index)+str(r),0);right=cf.get(get_column_letter(index+1)+str(r),0)
            flags.append({'rule':'relative_G19_less_than_H19','cell':col+str(r),'selected':left<right})
        for col in ['J','K']:flags.append({'rule':'even_excel_row','cell':col+str(r),'selected':r%2==0})
    for r in range(28,33):
        for col in ['G','H']:flags.append({'rule':'even_cell_value','cell':col+str(r),'selected':cf.get(col+str(r))%2==0})
    save_table(pd.DataFrame(flags),ctx.output/'conditional_flags.csv')
    for name,data in private.items():save_table(data,ctx.output/('private_'+name+'.csv'))
    formulas={(key,name,cell) for key,book in books.items() for name,sheet in book.items() for cell in sheet.formulas}
    if not formulas.issubset(checks.seen):raise AssertionError(f'Unmapped cached formulas: {formulas-checks.seen}')
    check_frame=pd.DataFrame(checks.rows)
    # The source contains three staff-name copy formulas; public evidence keeps the check and address, not the names.
    staff_labels=check_frame.source.eq('pivot_reference')&check_frame.sheet.eq('数据透视表')&check_frame.cell.isin(['H29','H30','H31'])
    check_frame.loc[staff_labels,['python_value','cached_value']]='人员标签已在本地核对'
    save_table(check_frame,ctx.output/'formula_checks.csv')
    differences=check_frame.loc[check_frame.status.eq('confirmed_source_difference')];save_table(differences,ctx.output/'cache_differences.csv')
    summaries=pd.DataFrame(summary);save_table(summaries,ctx.output/'exercise_summary.csv')
    groups={
        'INT MOD ROUND ABS SQRT RAND RANDBETWEEN':'simple_examples：负数取整、十进制舍入与新固定种子随机演示',
        'MID LEFT RIGHT LEN TEXT REPT REPLACE SUBSTITUTE':'simple_examples及手机号第8至10位掩码；保留1基起点语义',
        'MAX MIN SUM COUNT COUNTA AVERAGE COUNTIF COUNTIFS SUMIF SUMIFS AVERAGEIF AVERAGEIFS FREQUENCY RANK':'成绩、考勤、借贷清单与透视源数据；频数为上界包含，排名使用min处理并列',
        'IF AND OR NOT':'三门原始成绩数值比较；修正OR错引文字评价列；水电费双口径说明',
        'YEAR MONTH DAY TODAY NOW DATE EDATE EOMONTH DATEDIF WORKDAY NETWORKDAYS WEEKDAY':'固定教材时钟和实际给定日期；包括端点与给定假日，不推测调休',
        'VLOOKUP XLOOKUP INDEX MATCH OFFSET INDIRECT ROW COLUMN HLOOKUP':'唯一键精确查找、升序下界近似查找、实际坐标切片和提供的省市依赖选择'}
    mapping=pd.DataFrame([{'function':name,'implementation_and_scope':scope} for names,scope in groups.items() for name in names.split()]);save_table(mapping,ctx.output/'function_map.csv')
    descriptions={}
    for key,book in books.items():
        for name in book:
            descriptions[(key,name)]=('标量演示按白名单函数重算；时间固定到教材快照，随机项只检查新种子输出范围' if name=='常用函数应用' else
                '三门数值成绩IF/AND/OR，修正错引H列文字，保留缓存差异' if 'IF+AND' in name else
                '源截图错列不沿用，修正输入列；整体档位与累进收费并列，气费按唯一给定价' if '水电气' in name else
                '10日考勤事件计数，不当作去重人数，WPS缓存含双条件计数' if 'COUNTIF' in name else
                '按借/贷及工行借方条件求和和平均，原清单分录均保留' if 'sumif' in name else
                'EOMONTH、工作日、给定假日、EDATE、闰年和指定位置掩码' if any(t in name for t in ['最后','日期','闰年','手机号']) else
                '查找输入、字典、坐标定位和省市依赖选择；没有缓存答案的不冒充参考核对' if key=='lookup_functions' or '精确查找' in name else
                '36条源金额、三个透视区域（包括济南筛选）、混合引用九九表、40条近似等级及条件格式' )
    coverage=coverage_table(books,descriptions,ctx.output/'workbook-map.md')
    plt=plotting();fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    axes[0].barh(product['product'],product.sales_amount/1e6,color='#247d86');axes[0].set(title='全样本商品销售额',xlabel='百万示例金额单位')
    axes[1].bar(distribution.grade,distribution.records,color='#d67b28');axes[1].set(title='下界包含的成绩分档',ylabel='记录数')
    fig.savefig(ctx.output/'function_diagnostics.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(12,5),layout='constrained')
    values=np.array([cf.get('G'+str(r)) for r in range(10,15)]);axes[0].barh(range(5),values,color='#247d86');axes[0].set(title='数据条示意：原始值',yticks=range(5),yticklabels=[f'G{r}' for r in range(10,15)])
    colors=np.array([[cf.get('H'+str(r))] for r in range(10,15)]);axes[1].imshow(colors,cmap='RdYlBu',aspect='auto');axes[1].set(title='三色色阶示意',xticks=[],yticks=range(5),yticklabels=[f'H{r}' for r in range(10,15)])
    icon=np.array([cf.get('I'+str(r)) for r in range(10,15)]);bounds_icon=icon.min()+np.array([.33,.67])*(icon.max()-icon.min());groups_icon=np.searchsorted(bounds_icon,icon,side='right')
    axes[2].scatter(icon,range(5),c=np.array(['#d67b28','#bdcbd4','#247d86'])[groups_icon],s=180);axes[2].set(title='图标等级：取值范围33%/67%',yticks=range(5),yticklabels=[f'I{r}' for r in range(10,15)],xlabel='原始比例值')
    fig.savefig(ctx.output/'conditional_formatting.png',dpi=150);plt.close(fig)
    report=f'''# B02 Excel与WPS函数、引用、透视

5个工作簿的全部{coverage['source_sheets']}张工作表已映射为独立Python步骤。覆盖全部{len(formulas)}个已保存公式单元格；其中随机数2格只生成新固定种子演示，不与旧随机状态逐值比较。另核对三个透视区域的数值，所有检查及确认差异见formula_checks.csv、cache_differences.csv。没有缓存答案的练习标记为运行与规则验证，不假装有参考数值。

## 发现并修正的教材问题

两个版本D7的公式不同：Excel基础文件是ROUND(C7,3)，结果21.346；WPS文件是ROUND(C7,1)，结果21.3。两者缓存都正确，不能把显示差异误判为错误。本次按各自精度用Decimal的ROUND_HALF_UP重算，避免把Python默认的银行家舍入当作Excel四舍五入。OR练习误把H列文字评价放进>=60判断，应检查E/F/G三门原始数值；本组9条样本修正前后恰好相同，不代表原式对其他分数也正确。合成边界样例验证三门都不及格必须返回未通过。本次确认的缓存数值差异{len(differences)}格，检查表仍保留原值、重算值和公式。函数定义参照[Microsoft ROUND文档](https://support.microsoft.com/en-us/excel/functions/round-function)。

水电气截图还存在错列：气费截图引用E3自身，水费引用C列电用量，电费引用D列气用量。本实验修正为B列水、C列电、D列气。截图的档位算法对全部用量使用一个档位价格，和分段累进收费不同；两种口径并列输出，不擅自把其中之一说成教材唯一答案或现实账单。只有案例给定的价和阈值，气费无分段阈值，按3.27计算；各项先舍入到分再合计。

## 查找、日期与透视的关键口径

精确查找先隔离字典中62条#VALUE!错误键，再检查有效键唯一及标签非空；错误标记不是一种商品编码。100条查询未匹配时保留缺失并计数，不默取重复键第一条。近似查找要求下界严格升序，60、70、80、90归入从该分值开始的档。INDEX/MATCH、OFFSET用实际坐标演示，灰色区域B6:D8与4个偏移练习均有结果。INDIRECT迁移为教材所给省市词表的依赖选择，不运行字符串代码，也不把旧行政区划当现行名录。

日期演示使用教材NOW快照{frozen_clock}，不是执行当天。WORKDAY从起始日之后计数，NETWORKDAYS包含两个端点；采用表中明确给出的2017-10-01至10-07假日，不补造其他调休。闰年含世纪规则、月末与EDATE按日历处理，手机号按题意隐藏第8至10位，明细仅留本地。

![商品透视与成绩分档](function_diagnostics.png)

透视原始36行总金额{frame.amount_minor.sum()/100:,.0f}，数量{frame.quantity.sum()}。第一个人员透视在缓存定义中筛选销售地区{';'.join(regions)}，所以合计2,000,000，不是全表5,049,500；占比分母与筛选后的集合一致。另两个透视按商品、商品×地区汇总；交叉检查各小计与总计。公开人员汇总用S1/S2/S3匿名标签。

九九乘法表保留上三角空白与45个等式，全部81格对照；成绩40条以升序下界近似查找，频数FREQUENCY的区间则是上界包含，60分的频数位置与等级口径不同。函数清单和各步骤去向见function_map.csv，额外重复显示合并为说明。

## 条件格式的迁移边界

![条件格式示意](conditional_formatting.png)

条件格式输出数值阈值、相对引用、偶数行和偶数值的布尔标记；G19<H19会随目标列平移，不能把一次比较结果复制给整行。图标分段按min到max范围的33%/67%，不是将数值直接与0.33/0.67比较。源同一H区间同时保存两套色阶，Python图仅作数据条/三色色阶/图标等级示意，未声称Excel交互或像素级复刻。切片器迁移为明确地区筛选，数据验证列表迁移为给定词表选择。全部来源保留只读，[逐工作表对照](workbook-map.md)说明实现范围。
'''
    finish(ctx,{'lab_id':'B02','status':'execution_verified','workbook_coverage':coverage,'source_formula_cells':len(formulas),
                'formula_cells_covered':len(formulas&checks.seen),'all_cached_cells_checked':len(check_frame),
                'matched_cached_cells':int(check_frame.status.eq('matched').sum()),'confirmed_source_differences':len(differences),
                'random_cells_not_compared':int(check_frame.status.eq('new_seeded_random_not_cache_comparison').sum()),
                'seed':SEED,'frozen_textbook_clock':str(frozen_clock),'pivot_region_filter':regions,
                'pivot_records':len(frame),'pivot_amount':int(frame.amount_minor.sum())/100,'functions_documented':len(mapping)},report)


if __name__=='__main__':main()
