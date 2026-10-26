"""Customer-snapshot drill-down with an audit of the incorrect saved age chart."""
import re
import numpy as np
import pandas as pd
from .common import context,finish,plotting,save_table
from .case_workbooks import calendar_period,check_cell,chart_audit
from .tabular_tools import unique_key
from .workbook_reference import read_cached_book,coverage_table

BANDS=['18-25岁','26-35岁','36-49岁','50岁及以上']


def age_band(values):
    age=pd.to_numeric(values,errors='raise')
    if age.isna().any() or not age.between(0,120).all() or age.mod(1).ne(0).any():raise ValueError('Expected observed integer ages from 0 to 120')
    return pd.cut(age,[-1,17,25,35,49,120],labels=['18岁以下',*BANDS],right=True).astype('string')


def legacy_band(value):
    if isinstance(value,(int,float,np.number)):
        for left,right,label in [(18,25,'18-25岁'),(26,35,'26-35岁'),(36,49,'36-49岁')]:
            if left<=value<=right:return label
    return '50岁以上'


def age_formula(ref):
    return f'=IF(AND({ref}>=18,{ref}<=25),"18-25岁",IF(AND({ref}>=26,{ref}<=35),"26-35岁",IF(AND({ref}>=36,{ref}<=49),"36-49岁","50岁以上")))'


def prepare(raw):
    mapping={'客户ID':'customer_id','性别':'gender','年龄':'age','品类':'category','数量':'quantity','支付方式':'payment','订单月份':'month','订单年份':'year'}
    f=raw[list(mapping)].rename(columns=mapping).copy()
    for col in ['customer_id','gender','category','payment']:
        f[col]=f[col].astype('string').str.strip()
        if f[col].isna().any() or f[col].eq('').any():raise ValueError('Missing customer snapshot field')
    unique_key(f,'customer_id')
    if not f.gender.isin(['Female','Male']).all():raise ValueError('Review unexpected source gender label')
    f['age_band']=age_band(f.age);f['age']=pd.to_numeric(f.age).astype(int)
    f['quantity']=pd.to_numeric(f.quantity,errors='raise')
    if not np.isfinite(f.quantity).all() or f.quantity.le(0).any() or f.quantity.mod(1).ne(0).any():raise ValueError('Purchased quantity must be a positive integer')
    f['quantity']=f.quantity.astype('int64');f['period']=calendar_period(f.year,f.month)
    return f.drop(columns=['year','month'])


def counts(frame,key):
    g=frame.groupby(key,dropna=False,observed=True).agg(customers=('customer_id','nunique'),quantity=('quantity','sum')).reset_index()
    g['customer_share_in_scope']=g.customers/len(frame) if len(frame) else np.nan
    if int(g.customers.sum())!=len(frame) or int(g.quantity.sum())!=int(frame.quantity.sum()):raise AssertionError('Snapshot group totals differ')
    return g


def audiences(frame):
    female=frame[frame.gender.eq('Female')];older=female[female.age.ge(50)]
    target=older[older.category.isin(['Clothing','Cosmetics'])]
    scopes=pd.DataFrame([{'scope':name,'customers':len(f),'quantity':int(f.quantity.sum()),'share_of_all_customers':len(f)/len(frame) if len(frame) else np.nan}
                         for name,f in [('all',frame),('female',female),('female_50_plus',older),('female_50_plus_clothing_cosmetics',target)]])
    return female,older,target,scopes


def audit_reference(frame,books):
    source=books['marketing_reference']['原始数据'];sheet=books['marketing_reference']['准备区']
    private=[]
    for i,row in enumerate(frame.itertuples(index=False),2):
        addr=f'I{i}';ref=f'C{i}';actual=legacy_band(row.age)
        if source.formulas.get(addr)!=age_formula(ref) or source.get(addr)!=actual:raise AssertionError('Changed source customer age formula/cache')
        private.append({'cell':addr,'source_age':row.age,'saved':source.get(addr),'python_legacy':actual,'matched':True})
    if set(source.formulas)!={x['cell'] for x in private}:raise AssertionError('Unmapped customer formula')
    issues=[]
    for row in range(23,75):
        addr=f'D{row}';formula=sheet.formulas[addr];match=re.search(r'AND\((A\d+)>=18',formula)
        if not match or formula!=age_formula(match.group(1)):raise AssertionError('Review changed preparation formula')
        ref=match.group(1);operand=sheet.get(ref);actual=legacy_band(operand);current_age=sheet.get(f'A{row}')
        if sheet.get(addr)!=actual:raise AssertionError('Preparation formula cache differs from its actual operand')
        issues.append({'cell':addr,'actual_reference':ref,'same_row_reference':f'A{row}','source_operand':operand,
                       'row_age':current_age,'saved':sheet.get(addr),'correct_row_band':legacy_band(current_age),
                       'cache_matches_actual_formula':True,'reference_is_same_row':ref==f'A{row}',
                       'band_differs_from_row_age':actual!=legacy_band(current_age)})
    if set(sheet.formulas)!={x['cell'] for x in issues}:raise AssertionError('Unmapped preparation formula')
    records=[]
    gender=frame.groupby('gender').size()
    for row in [7,8]:check_cell(records,sheet,f'B{row}',int(gender[sheet.get(f'A{row}')]),'gender')
    check_cell(records,sheet,'B9',len(frame),'gender total')
    female,older,target,scopes=audiences(frame)
    female_ages=female.groupby('age').size();male_ages=frame[frame.gender.eq('Male')].groupby('age').size()
    for row in range(23,75):
        age=sheet.get(f'A{row}')
        check_cell(records,sheet,f'B{row}',int(female_ages.get(age,0)),'female exact age')
        check_cell(records,sheet,f'E{row}',int(male_ages.get(age,0)),'male counts under female heading')
    compat=pd.DataFrame([{'age_band':sheet.get(f'D{r}'),'male_customers':sheet.get(f'E{r}')} for r in range(23,75)]).groupby('age_band').male_customers.sum()
    for row in range(27,31):check_cell(records,sheet,f'H{row}',int(compat[sheet.get(f'G{row}')]),'wrong-reference grouped male count')
    check_cell(records,sheet,'H31',int(compat.sum()),'wrong-reference male total')
    cat=older.groupby('category').size()
    for row in range(85,93):check_cell(records,sheet,f'C{row}',int(cat.get(sheet.get(f'B{row}'),0)),'female 50+ category')
    check_cell(records,sheet,'C93',len(older),'female 50+ total')
    pay=target.groupby('payment').size()
    for row in range(110,113):check_cell(records,sheet,f'C{row}',int(pay.get(sheet.get(f'B{row}'),0)),'selected category payment')
    check_cell(records,sheet,'C113',len(target),'selected payment total')
    audit=pd.DataFrame([{'block':'customer_age_formulas','formula_cells':len(private),'saved_cache_matches':len(private),'wrong_row_references':0,'wrong_same_row_band':0},
                        {'block':'preparation_age_formulas','formula_cells':len(issues),'saved_cache_matches':len(issues),
                         'wrong_row_references':sum(not x['reference_is_same_row'] for x in issues),'wrong_same_row_band':sum(x['band_differs_from_row_age'] for x in issues)}])
    return audit,pd.DataFrame(issues),pd.DataFrame(records),pd.DataFrame(private),compat


def main(argv=None):
    ctx=context('B18',argv);paths={'marketing_raw':ctx.source('marketing_raw'),'marketing_reference':ctx.source('marketing_reference')}
    books={key:read_cached_book(path) for key,path in paths.items()}
    frame=prepare(pd.read_excel(paths['marketing_raw'],sheet_name='原始数据'))
    reference=prepare(pd.read_excel(paths['marketing_reference'],sheet_name='原始数据'))
    pd.testing.assert_frame_equal(frame,reference)
    if frame.period.nunique()!=1 or frame.period.iloc[0]!=pd.Period('2023-01'):raise ValueError('Review the intended January 2023 snapshot')
    female,older,target,scopes=audiences(frame)
    gender=counts(frame,'gender');bands=counts(frame,['gender','age_band']);categories=counts(older,'category');payments=counts(target,'payment')
    audit,issues,checks,private,compat=audit_reference(frame,books)
    save_table(frame,ctx.output/'audience_private.csv');save_table(private,ctx.output/'age_formula_checks_private.csv')
    sheet=books['marketing_reference']['准备区']
    expected=[[sheet.get(f'B{r}') for r in [7,8]],[sheet.get(f'H{r}') for r in range(27,31)],
              [sheet.get(f'C{r}') for r in range(85,93)],[sheet.get(f'C{r}') for r in range(110,113)]]
    charts,points=chart_audit(paths['marketing_reference'],['marketing_dashboard:客户性别','age_reference_comparison:错误参考与两性正确年龄段并列',
                   'marketing_dashboard:女性50岁及以上品类','marketing_dashboard:目标子集支付方式']*2,expected*2)
    for name,data in [('gender_counts',gender),('gender_age_bands',bands),('older_female_categories',categories),('target_payment',payments),
                      ('scope_counts',scopes),('formula_audit',audit),('prepare_formula_issues',issues),('reference_counts',checks),('chart_map',charts)]:save_table(data,ctx.output/(name+'.csv'))
    coverage=coverage_table(books,{('marketing_raw','原始数据'):'3926个唯一客户的单月购买快照→人数、数量、年龄段与层层筛选；ID仅本地',
        ('marketing_reference','业务需求'):'绘图文本：从两性选一群体，提出下一月活动的可验证假设',('marketing_reference','原始数据'):'8字段与原始表一致；3926个年龄段公式/缓存全核对，逐人核对表只留本地',
        ('marketing_reference','准备区'):'52个错行年龄公式、男性人数混入女性图、125项数字缓存分别核查；主分析纠正',
        ('marketing_reference','报表界面'):'8幅图包含4幅重复展示；34个图数字缓存核对，错误年龄图独立标记'},ctx.output/'workbook-map.md')
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(15,10),layout='constrained');fig.suptitle('电商营销客群 · 2023年1月购买快照',fontsize=16)
    ax[0,0].bar(gender.gender,gender.customers,color='#087f8c');ax[0,0].set(title='购买客户数（每个ID一条）',ylabel='人数')
    for i,label in enumerate(['Female','Male']):
        g=bands[bands.gender.eq(label)].set_index('age_band').reindex(BANDS);ax[0,1].bar(np.arange(4)+(i-.5)*.35,g.customers,width=.35,label=label)
    ax[0,1].set_xticks(range(4),BANDS,rotation=15);ax[0,1].set(title='修正后的两性年龄段',ylabel='人数');ax[0,1].legend()
    c=categories.sort_values('customers');ax[1,0].barh(c.category,c.customers,color='#087f8c');ax[1,0].set(title='女性50岁及以上：品类分布',xlabel='人数')
    ax[1,1].bar(payments.payment,payments.customers,color='#087f8c');ax[1,1].set(title='女性50岁及以上、服饰/护肤：支付方式',ylabel='人数')
    fig.savefig(ctx.output/'marketing_dashboard.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,6),layout='constrained');x=np.arange(4)
    ax.bar(x-.25,[compat.get(b.replace('及以上','以上'),0) for b in BANDS],width=.25,label='教材女性标题图：错位分组男性人数')
    for offset,label in [(0,'Male'),(.25,'Female')]:
        values=bands[bands.gender.eq(label)].set_index('age_band').reindex(BANDS).customers
        ax.bar(x+offset,values,width=.25,label='正确'+label)
    ax.set_xticks(x,BANDS);ax.set(title='年龄参考图纠错：缓存相符不代表业务对象正确',ylabel='人数');ax.legend(fontsize=9)
    fig.savefig(ctx.output/'age_reference_comparison.png',dpi=150);plt.close(fig)
    report=f'''# B18 电商精准营销客群分析

## 数据与活动方向

2023年1月共{len(frame)}个不同客户ID，每个ID恰有一条购买快照，共{int(frame.quantity.sum())}件商品。两份工作簿的8个原始字段逐行一致。没有订单ID、金额、未购买访客、活动成本或历史活动反馈，因此人数、件数、销售额和转化率不可混称。

女性{len(female)}人，占全部{len(female)/len(frame):.4%}；女性50岁及以上{len(older)}人。该组Clothing与Cosmetics合计{len(target)}人，占该组{len(target)/len(older):.4%}。这是以现有购买人群为基础的候选促销方向。支付方式分布用于活动入口兼容性观察，不能仅凭Card人数多就认定补贴Card带来最大新增收益。

![营销客群](marketing_dashboard.png)

可把“女性50岁及以上的服饰/护肤组合活动”作为下月试验假设，先定义触达名单和随机留出组，记录触达、购买、毛利与活动成本，再比较增量。当前样本只说明谁买过，不能代表全体访客的性别比例，也不证明该人群更容易被活动改变。年龄段宽度不同，较宽组人数多不代表每一岁购买倾向更强。受众人数筛选链和各阶段分母见scope_counts.csv；逐人名单只保存在本地。

## 教材参考中的两类错误

原始数据页3926个年龄公式及缓存均与源18—69岁相符。公式最后else把所有其他值叫“50岁以上”，边界外不安全；Python明确分18岁以下、18—25、26—35、36—49、50岁及以上，50岁属于末组。未来缺失或非法年龄需核实，不直接归入末组。

准备区D23:D74共52个年龄公式全部引用非本行单元格，前两格引用标题/表头，其余多为向上错2行。其中8格的年龄段标签与本行年龄不同。全部52个保存缓存符合其实际错位公式，故不能仅以缓存一致声称业务正确。

E23:E74的52个“客户数”实际等于各年龄男性人数；它们再按错位D列分组，得到265/313/412/565，合计1555，图标题却写女性。正确男性应为270/301/426/558；正确女性为340/460/653/918（按四年龄段顺序）。B23:B74女性逐年龄人数本身正确，后续女性50岁及以上的品类918与目标子集445仍可由原始表独立复算。

![参考图纠错](age_reference_comparison.png)

prepare_formula_issues.csv列出52格的引用及标签问题，formula_audit.csv按块汇总全部3978个公式缓存核对；逐人3926格核对表不公开。兼容旧图只用于诊断，主营销看板使用修正后的两性分组。

## 验证范围

5张工作表均有去向，125个数字缓存、3978个公式缓存和8幅图的{points}个数值缓存核对通过。状态为指定范围参考核对通过，核对同时保留上述错误及修正，不等于认可源图的业务对象。每个互斥分组的人数与件数均守恒。原工作簿和客户ID、逐行购买记录均不分发。

```powershell
python run_labs.py --lab B18
```
'''
    finish(ctx,{'lab_id':'B18','status':'reference_verified','customers':len(frame),'quantity':int(frame.quantity.sum()),'source_input_equality':True,
        'scope_counts':scopes.to_dict('records'),'source_formula_cells':int(audit.formula_cells.sum()),'formula_cells_covered':int(audit.formula_cells.sum()),
        'formula_cache_matches':int(audit.saved_cache_matches.sum()),'wrong_preparation_references':int(audit.wrong_row_references.sum()),
        'wrong_preparation_age_labels':int(audit.wrong_same_row_band.sum()),'numeric_reference_checks':len(checks),'chart_numeric_checks':points,'charts':len(charts),'workbook_coverage':coverage},report)


if __name__=='__main__':main()
