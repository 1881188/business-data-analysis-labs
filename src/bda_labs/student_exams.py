"""One-exam roster model: missing scores, filter denominators and tied ranks."""
import argparse
from contextlib import closing
from datetime import datetime,date
import json
import numbers
import sqlite3
import sys
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.utils.datetime import from_excel,CALENDAR_WINDOWS_1900
from .common import context, finish, plotting, save_table
from .tabular_tools import unique_key,many_to_one
from .workbook_reference import read_cached_book,coverage_table
from .pbix_audit import visual_audit

SUBJECTS=['chinese','math','english']
SUBJECT_LABELS={'chinese':'语文','math':'数学','english':'英语'}


def decode_birth(values,epoch=CALENDAR_WINDOWS_1900):
    out=[]
    for raw in values:
        if pd.isna(raw):raise ValueError('Missing birth date needs source review')
        if isinstance(raw,numbers.Real) and not isinstance(raw,bool):
            if epoch==CALENDAR_WINDOWS_1900 and 60<=raw<61:raise ValueError('Excel fictitious 1900-02-29 is not a real birth date')
            value=from_excel(float(raw),epoch=epoch)
            if not isinstance(value,(datetime,date)):raise ValueError('Excel value is not a calendar date')
        else:value=pd.Timestamp(raw)
        stamp=pd.Timestamp(value)
        if stamp.tzinfo is not None or stamp!=stamp.normalize():raise ValueError('Expected a birth date without time')
        out.append(stamp)
    return pd.Series(out,index=values.index,dtype='datetime64[ns]')


def prepare(students,teachers,exams,epoch=CALENDAR_WINDOWS_1900):
    s=students.rename(columns={'学号':'student_id','姓名':'name','性别(1男生,2女生)':'gender_code','班级':'class_id','出生日期':'birth'}).copy()
    t=teachers.rename(columns={'班级':'class_id','班主任姓名':'teacher'}).copy()
    e=exams.rename(columns={'学号':'student_id','语文':'chinese','数学':'math','英语':'english'}).copy()
    for f in [s,e]:
        f['student_id']=f.student_id.astype('string').str.strip()
        if f.student_id.eq('').any():raise ValueError('Blank student ID')
        unique_key(f,'student_id')
    unique_key(t,'class_id')
    if s.class_id.isna().any() or t.teacher.isna().any():raise ValueError('Missing class or homeroom teacher')
    s['birth']=decode_birth(s.birth,epoch)
    if not s.gender_code.isin([1,2]).all():raise ValueError('Unexpected source gender code')
    s=many_to_one(s,t[['class_id','teacher']],on='class_id')
    if (~e.student_id.isin(s.student_id)).any():raise ValueError('Exam record without roster student')
    for col in SUBJECTS:
        e[col]=pd.to_numeric(e[col],errors='raise').astype(float)
        observed=e[col].dropna()
        if not np.isfinite(observed).all() or not observed.between(0,100).all():raise ValueError('Scores must be finite and within the declared 0–100 scale')
    e['exam_present']=True
    f=s.merge(e[['student_id',*SUBJECTS,'exam_present']],on='student_id',how='left',validate='one_to_one')
    f['exam_present']=f.exam_present.eq(True)
    f['complete']=f[SUBJECTS].notna().all(axis=1)
    f['total']=f[SUBJECTS].sum(axis=1,min_count=len(SUBJECTS))
    f['global_total_rank']=f.total.rank(ascending=False,method='min').astype('Int64')
    failed=f[SUBJECTS].lt(60).any(axis=1)
    f['any_failed']=pd.Series(pd.NA,index=f.index,dtype='boolean')
    f.loc[failed,'any_failed']=True;f.loc[f.complete&~failed,'any_failed']=False
    f['total_band']=pd.cut(f.total,[-np.inf,180,240,np.inf],right=False,labels=['总分<180','180≤总分<240','240≤总分≤300'])
    return f


def select(frame,classes=None):
    chosen=frame.copy() if classes is None else frame[frame.class_id.isin(classes)].copy()
    chosen['selected_total_rank']=chosen.total.rank(ascending=False,method='min').astype('Int64')
    return chosen


def measures(f):
    complete=f.loc[f.complete,'total'];observed=f[SUBJECTS].stack()
    return {'enrolled':len(f),'distinct_teacher_names':int(f.teacher.nunique()),'exam_records':int(f.exam_present.sum()),
            'students_with_observed_scores':int(f[SUBJECTS].notna().any(axis=1).sum()),'complete_exams':len(complete),
            'mean_total_complete':float(complete.mean()) if len(complete) else None,
            'max_total_complete':float(complete.max()) if len(complete) else None,'min_total_complete':float(complete.min()) if len(complete) else None,
            'mean_observed_subject_score':float(observed.mean()) if len(observed) else None,
            'known_any_failed':int(f.any_failed.eq(True).sum()),'known_all_passed':int(f.any_failed.eq(False).sum()),
            'failure_outcome_unknown':int(f.any_failed.isna().sum())}


def subject_statistics(f):
    rows=[]
    for col in SUBJECTS:
        values=f[col].dropna();passed=int(values.ge(60).sum());n=len(values)
        rows.append({'subject':SUBJECT_LABELS[col],'observed':n,'missing':len(f)-n,'passed':passed,
                     'pass_rate_observed':passed/n if n else None,'pass_fraction_enrolled':passed/len(f) if len(f) else None,
                     'mean':float(values.mean()) if n else None,'minimum':float(values.min()) if n else None,'maximum':float(values.max()) if n else None})
    result=pd.DataFrame(rows)
    for name in ['pass_rate_observed','pass_fraction_enrolled','mean','minimum','maximum']:result[name]=result[name].astype(float)
    return result


def class_context(frame,whole_grade):
    rows=[];grade_pass=int(whole_grade.chinese.ge(60).sum())
    for class_id,g in frame.groupby('class_id'):
        rows.append({'class_id':class_id,**measures(g),'class_share_of_grade':len(g)/len(whole_grade) if len(whole_grade) else None,
                     'chinese_passed':int(g.chinese.ge(60).sum()),
                     'chinese_pass_share_of_grade':int(g.chinese.ge(60).sum())/grade_pass if grade_pass else None})
    return pd.DataFrame(rows,columns=['class_id',*measures(frame),'class_share_of_grade','chinese_passed','chinese_pass_share_of_grade'])


def query_examples(f,whole_grade):
    queries={
        '语文>=60：逻辑掩码人数':int(f.chinese.ge(60).sum()),
        '语文>=60：筛选后学号去重':int(f.loc[f.chinese.ge(60),'student_id'].nunique()),
        '语文60至80：含两个端点':int(f.chinese.between(60,80,inclusive='both').sum()),
        '语文60至80：不含80':int(f.chinese.between(60,80,inclusive='left').sum()),
        '数学60至90：含两个端点':int(f.math.between(60,90,inclusive='both').sum()),
        '数学60至90：不含90':int(f.math.between(60,90,inclusive='left').sum()),
        '任意一科已知不及格':int(f.any_failed.eq(True).sum()),
        '语文>80且至少一科不及格':int((f.chinese.gt(80)&f.any_failed.eq(True)).sum()),
        '当前范围1班或3班':int(f.class_id.isin([1,3]).sum()),
        '当前范围不属于1班或3班':int((~f.class_id.isin([1,3])).sum()),
        '全年级1班：移除班级筛选':int(whole_grade.class_id.eq(1).sum()),
        '当前范围与1班交集':int(f.class_id.eq(1).sum())}
    with closing(sqlite3.connect(':memory:')) as conn:
        f[['student_id',*SUBJECTS]].to_sql('scores',conn,index=False)
        sql=int(conn.execute('SELECT COUNT(DISTINCT student_id) FROM scores WHERE chinese >= 60').fetchone()[0])
    if sql!=queries['语文>=60：逻辑掩码人数'] or sql!=queries['语文>=60：筛选后学号去重']:raise AssertionError('Three pass-count implementations differ')
    queries['语文>=60：SQLite去重计数']=sql
    return pd.DataFrame([{'query':name,'count':value} for name,value in queries.items()])


def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--classes',nargs='+',type=int)
    options,remaining=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    ctx=context('B15',remaining);info=ctx.source('exam_roster');scores=ctx.source('exam_scores');pbix=ctx.source('exam_pbix')
    wb=openpyxl.load_workbook(info,read_only=True,data_only=True);epoch=wb.epoch;wb.close()
    raw=pd.read_excel(info,sheet_name=None);exams=pd.read_excel(scores,sheet_name='考试记录')
    full=prepare(raw['学生信息'],raw['教师信息'],exams,epoch);f=select(full,options.classes);m=measures(f)
    subjects=subject_statistics(f);classes=class_context(f,full);queries=query_examples(f,full)
    band=f.groupby('total_band',observed=False).size().rename('students').reset_index()
    if int(band.students.sum())!=m['complete_exams']:raise AssertionError('Total bands lost complete exams')
    if m['known_any_failed']+m['known_all_passed']+m['failure_outcome_unknown']!=m['enrolled']:raise AssertionError('Outcome categories do not reconcile')
    for name,data in [('subject_statistics',subjects),('class_context',classes),('query_examples',queries),('total_bands',band)]:save_table(data,ctx.output/(name+'.csv'))
    save_table(f,ctx.output/'students_private.csv')
    save_table(f[['student_id','name','class_id',*SUBJECTS,'total','global_total_rank','selected_total_rank']],ctx.output/'ranking_private.csv')
    coverage=coverage_table({'exam_roster':read_cached_book(info),'exam_scores':read_cached_book(scores)},
        {('exam_roster','学生信息'):'学生主键、班级、Excel日期序列；身份和生日只在本地',('exam_roster','教师信息'):'班级唯一维度→班主任标签；公开按班级编号展示',
         ('exam_scores','考试记录'):'一次三科快照→缺失、总分、并列排名、及格率与筛选示例'},ctx.output/'workbook-map.md')
    destinations=[
        '不同班主任姓名数，源没有教师ID，不能断言姓名即真实唯一身份','当前学生名册人数',
        'subject_statistics：三科及格人数、已知成绩分母及名册分母','classes参数；保存数值边界不直接解释成已激活筛选',
        'class_context：明确平均个人总分；另给逐科均值','语文>=60掩码实现','语文>=60筛选去重实现','语文[60,80]及[60,80)端点诊断',
        'class_context及固定班级/全年级分母；班主任姓名不公开',
        '任意科不及格及语文>80子集分别计算，未知DAX不猜测','数学[60,90]及[60,90)端点诊断',
        'class_id属于{1,3}','class_id不属于{1,3}',
        '原创考试看板标题','classes显式筛选','最高/最低/平均个人总分，另列逐科均值',
        'subject_statistics三科及格人数','subject_statistics：不同缺考分母明确列示',
        'total_bands：明示总分区间，缺完整总分不强行分组','ranking_private：三科、总分、全年级及选中范围并列排名，仅本地']
    visuals=visual_audit(pbix,destinations);save_table(visuals,ctx.output/'pbix_visual_map.csv')
    plt=plotting();fig,ax=plt.subplots(2,2,figsize=(14,10),layout='constrained');fig.suptitle('学生考试分析 · '+('全年级' if options.classes is None else '班级'+','.join(map(str,options.classes))),fontsize=16)
    ax[0,0].axis('off')
    for i,(label,value) in enumerate([('学生名册人数',m['enrolled']),('班主任姓名数',m['distinct_teacher_names']),('完整三科人数',m['complete_exams']),('平均个人总分',m['mean_total_complete'])]):
        x=.03+(i%2)*.52;y=.84-(i//2)*.45;ax[0,0].text(x,y,label,transform=ax[0,0].transAxes);ax[0,0].text(x,y-.16,'未知' if value is None else f'{value:.2f}' if isinstance(value,float) else str(value),transform=ax[0,0].transAxes,color='#087f8c',fontsize=26,weight='bold')
    ax[0,1].bar(subjects.subject,subjects.passed,color='#087f8c');ax[0,1].set(title='三科及格人数（>=60）',ylabel='人数')
    if len(classes):ax[1,0].bar(classes.class_id.astype(str),pd.to_numeric(classes.mean_total_complete,errors='coerce'),color='#087f8c')
    ax[1,0].set(title='各班平均个人总分（完整三科，满分300）',xlabel='班级',ylabel='分')
    ax[1,1].bar(band.total_band.astype(str),band.students,color='#087f8c');ax[1,1].tick_params(axis='x',rotation=20);ax[1,1].set(title='完整个人总分分组',ylabel='人数')
    fig.savefig(ctx.output/'exam_dashboard.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    x=np.arange(len(subjects));ax[0].bar(x-.18,subjects.pass_rate_observed*100,width=.36,label='以已知成绩人数为分母');ax[0].bar(x+.18,subjects.pass_fraction_enrolled*100,width=.36,label='以名册人数为分母');ax[0].set_xticks(x,subjects.subject);ax[0].set(title='同一及格人数，不同分母',ylabel='比例（%）',ylim=(0,105));ax[0].legend(fontsize=9)
    if len(classes):
        x=np.arange(len(classes));ax[1].bar(x-.18,classes.class_share_of_grade*100,width=.36,label='班级人数/全年级人数');ax[1].bar(x+.18,classes.chinese_pass_share_of_grade*100,width=.36,label='本班语文及格/全年级语文及格');ax[1].set_xticks(x,classes.class_id.astype(str))
    ax[1].set(title='班级筛选与固定全年级分母',xlabel='班级',ylabel='占全年级比例（%）')
    if len(classes):ax[1].legend(fontsize=9)
    fig.savefig(ctx.output/'exam_denominators.png',dpi=150);plt.close(fig)
    rows=['| 科目 | 已知成绩 | 缺失/缺考 | 及格 | 已知成绩及格率 | 占名册比例 |','|---|---:|---:|---:|---:|---:|']
    for row in subjects.itertuples():
        rate='未知' if pd.isna(row.pass_rate_observed) else f'{row.pass_rate_observed:.4%}'
        share='未知' if pd.isna(row.pass_fraction_enrolled) else f'{row.pass_fraction_enrolled:.4%}'
        rows.append(f'| {row.subject} | {row.observed} | {row.missing} | {row.passed} | {rate} | {share} |')
    report=f'''# B15 学生考试多表分析

## 范围与结果

输入为一张学生名册、一张班主任表及一次三科考试快照；没有考试日期或考试ID。按学号一对一关联成绩，再按班级多对一关联班主任。本次班级筛选为{options.classes if options.classes is not None else '全年级'}，名册{m['enrolled']}人、考试记录{m['exam_records']}条、完整三科{m['complete_exams']}人；不同班主任姓名{m['distinct_teacher_names']}个，源无教师ID，姓名数不推广为真实唯一身份计数。

{chr(10).join(rows)}

![考试看板](exam_dashboard.png)

平均个人总分为{f"{m['mean_total_complete']:.6f}" if m['mean_total_complete'] is not None else '未知'}，按完整三科学生计算、满分300；另有所有已知单科成绩的均值，两个分母不同，不混称“平均分”。各科0—100分、>=60及格是本实现明示规则。

已知至少一科不及格{m['known_any_failed']}人、已知三科全及格{m['known_all_passed']}人、尚不能判断{m['failure_outcome_unknown']}人。多科不及格可能属于同一学生，不能把各科不及格人数相加当作总人数。

## 缺失、区间与排名

无成绩不填0、不当成不及格；任何已知科目低于60可确认至少一科不及格，剩余科目缺失且尚无失败时结论未知。只有三科齐全才算总分并进入总分段。总分段明确为<180、[180,240)、[240,300]，不是另行定义“三科全部及格”。

并列总分采用竞争排名：1、1、3；完整全年级排名在筛选前算，选中范围排名在筛选后重算，两者均留在本地ranking_private.csv。多次考试没有日期无法选择最近一次，因此学号重复记录明确报错，不求和或猜测最新记录。

语文60—80、数学60—90的文字标题未公开DAX端点，query_examples.csv同时给出双端包含与不含上端点的结果。任意科不及格与“语文>80且任意科不及格”分别计算，不从计算表名称猜测隐藏公式。1班或3班使用集合包含，其补集明确为不属于两班。

## 筛选上下文与验证

![分母对照](exam_denominators.png)

班级占全年级比例及本班语文及格占全年级语文及格比例，分母固定来自完整名册；当前范围与1班交集和移除班级筛选后的1班人数分别展示。语文及格人数用掩码、筛选去重及SQLite三种方法交叉核对，不把这些新增等价实现冒充原DAX的三个版本。

原PBIX20个容器均有迁移去向。保存的Basic切片器有2/2数值边界，但未见显式成员过滤，不能仅据此认定原报告默认已选2班。内嵌DataModel未解码，所以最高/最低/平均分、分组、排名和重复及格度量均明示Python定义，不宣称完整DAX逐值复现。

生日数值按源工作簿日期系统解码，不当Unix时间或普通整数；源1900日期系统的虚构1900-02-29会明确报错。没有考试日期，不计算考试年龄。公开只含聚合表和新图，学生/教师姓名、学号、生日、逐人成绩和排名均留本地。班级差异是该快照描述，不用于推断教学因果或学生长期能力。状态为运行通过。

```powershell
python run_labs.py --lab B15
python labs/cda1_business/b15_exams/main.py --classes 1 3 --output-root outputs/filtered
```

筛选运行写入独立目录，公开报告仅使用无班级筛选的完整名册。
'''
    finish(ctx,{'lab_id':'B15','status':'execution_verified','selection':{'classes':options.classes},'metrics':m,
                'source_students':len(full),'source_exam_records':len(exams),'source_teacher_rows':len(raw['教师信息']),
                'pass_count_implementations_agree':True,'outcome_partition_check':True,'complete_total_band_check':True,
                'date_epoch':str(epoch.date()),'workbook_coverage':coverage,'pbix_visuals':len(visuals)},report)


if __name__=='__main__':main()
