"""Synthetic time boundaries, roster populations and exam filter-context tests."""
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
from openpyxl.utils.datetime import CALENDAR_MAC_1904
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.hr_workforce import prepare as prepare_hr,analyze,monthly,age_years,grouping
from bda_labs.student_exams import prepare as prepare_exam,select,measures,subject_statistics,class_context,query_examples,decode_birth


def staff():
    return pd.DataFrame({'员工工号':list('ABCDEF'),'姓名':['示例'+x for x in 'ABCDEF'],'性别':['男']*6,'部门':['甲部']*3+['乙部']*3,
        '职称':['演示']*6,'职级':[1]*6,'出生日期':pd.to_datetime(['1990-01-02']*6),
        '入职日期':pd.to_datetime(['2019-12-30','2019-12-31','2020-01-01','2020-01-02','2020-01-03','2019-12-31']),
        '离职日期':pd.to_datetime([None,'2020-01-01','2020-01-02','2020-01-02',None,'2020-02-01']),
        '员工状态':['在职','离职','离职','离职','在职','离职'],'文化程度':['演示学历']*6})


def school():
    s=pd.DataFrame({'学号':['S1','S2','S3','S4','S5'],'姓名':['示例'+str(i) for i in range(1,6)],
        '性别(1男生,2女生)':[1,2,1,2,1],'班级':[1,1,2,3,3],'出生日期':[36526]*5})
    t=pd.DataFrame({'班级':[1,2,3],'班主任姓名':['示例师甲','示例师乙','示例师丙']})
    e=pd.DataFrame({'学号':['S1','S2','S3','S4'],'语文':[80,80,60,59],'数学':[60,60,90,50],'英语':[100,100,np.nan,60]})
    return s,t,e


class WorkforceTests(unittest.TestCase):
    def test_stock_flow_person_days_and_future_hires(self):
        raw=staff();before=raw.copy(deep=True);f=prepare_hr(raw);snapshot,m=analyze(f,'2020-01-01','2020-01-02')
        self.assertEqual([m[k] for k in ['opening','hires','exits','closing','touched']],[3,2,3,2,5])
        self.assertEqual(m['person_days'],5);self.assertEqual(m['average_daily_headcount'],2.5)
        self.assertTrue(snapshot.loc[snapshot.employee_id.eq('E'),'service_days_asof'].isna().all())
        pd.testing.assert_frame_equal(raw,before)

    def test_same_day_join_exit_does_not_inflate_exposure(self):
        f=prepare_hr(staff()).iloc[[3]];_,m=analyze(f,'2020-01-02','2020-01-02')
        self.assertEqual(m['hires'],1);self.assertEqual(m['exits'],1);self.assertEqual(m['closing'],0)
        self.assertEqual(m['person_days'],0);self.assertIsNone(m['period_exits_per_average_headcount'])

    def test_historical_status_comes_from_dates(self):
        f=prepare_hr(staff());snapshot,_=analyze(f,'2020-01-01','2020-01-02')
        self.assertTrue(snapshot.loc[snapshot.employee_id.eq('F'),'closing'].iloc[0])
        self.assertEqual(snapshot.loc[snapshot.employee_id.eq('F'),'source_status'].iloc[0],'离职')

    def test_month_continuity_and_partial_flags(self):
        f=prepare_hr(staff());m=monthly(f,'2020-01-01','2020-02-02')
        self.assertEqual(m.loc[1,'opening'],m.loc[0,'closing']);self.assertEqual(m.loc[1,'hires'],0)
        self.assertTrue(m.loc[0,'complete_calendar_month']);self.assertFalse(m.loc[1,'complete_calendar_month'])
        _,full=analyze(f,'2020-01-01','2020-02-02');self.assertEqual(m.person_days.sum(),full['person_days'])

    def test_age_anniversary_and_leap_day(self):
        birth=pd.Series(pd.to_datetime(['2000-02-29','2000-03-01']))
        self.assertEqual(age_years(birth,'2021-02-28').tolist(),[20,20])
        self.assertEqual(age_years(birth,'2021-03-01').tolist(),[21,21])
        with self.assertRaises(ValueError):age_years(birth,'1999-01-01')

    def test_status_mismatch_is_diagnosed_without_rewriting_dates(self):
        raw=staff();raw.loc[1,'员工状态']='在职';f=prepare_hr(raw)
        self.assertEqual(f.status_date_mismatch.sum(),1)
        _,m=analyze(f,'2020-01-01','2020-01-02');self.assertEqual(m['closing'],2)

    def test_invalid_keys_dates_and_windows_fail(self):
        raw=staff();raw.loc[1,'员工工号']='A'
        with self.assertRaises(ValueError):prepare_hr(raw)
        raw=staff();raw.loc[1,'离职日期']=pd.Timestamp('2018-01-01')
        with self.assertRaises(ValueError):prepare_hr(raw)
        with self.assertRaises(ValueError):analyze(prepare_hr(staff()),'2020-02-01','2020-01-01')

    def test_empty_scope_and_age_group_conservation(self):
        f=prepare_hr(staff());snapshot,m=analyze(f.iloc[:0],'2020-01-01','2020-01-02')
        self.assertEqual(m['closing'],0);self.assertIsNone(m['period_exits_per_average_headcount'])
        self.assertEqual(grouping(snapshot,'age_band').closing.sum(),0)


class ExamTests(unittest.TestCase):
    def setUp(self):
        self.s,self.t,self.e=school();self.f=prepare_exam(self.s,self.t,self.e)

    def test_roster_preserved_missing_scores_not_zero(self):
        m=measures(self.f);self.assertEqual(m['enrolled'],5);self.assertEqual(m['exam_records'],4)
        self.assertEqual(m['complete_exams'],3);self.assertEqual(m['failure_outcome_unknown'],2)
        self.assertEqual(m['known_any_failed'],1);self.assertEqual(m['known_all_passed'],2)
        self.assertTrue(self.f.loc[self.f.student_id.eq('S5'),'total'].isna().all())

    def test_partial_failure_is_known_but_other_missing_outcome_unknown(self):
        self.assertTrue(pd.isna(self.f.loc[self.f.student_id.eq('S3'),'any_failed'].iloc[0]))
        self.e.loc[self.e['学号'].eq('S3'),'语文']=59
        f=prepare_exam(self.s,self.t,self.e)
        self.assertTrue(f.loc[f.student_id.eq('S3'),'any_failed'].iloc[0])

    def test_subject_denominators_and_inclusive_pass_boundary(self):
        q=subject_statistics(self.f).set_index('subject');self.assertEqual(q.loc['语文','passed'],3)
        self.assertEqual(q.loc['语文','pass_rate_observed'],.75);self.assertEqual(q.loc['语文','pass_fraction_enrolled'],.6)
        self.assertEqual(q.loc['英语','pass_rate_observed'],1)

    def test_total_rank_ties_and_filter_rank(self):
        ranks=self.f.set_index('student_id').global_total_rank
        self.assertEqual(ranks['S1'],1);self.assertEqual(ranks['S2'],1);self.assertEqual(ranks['S4'],3)
        chosen=select(self.f,[3]).set_index('student_id');self.assertEqual(chosen.loc['S4','selected_total_rank'],1)
        self.assertEqual(chosen.loc['S4','global_total_rank'],3)

    def test_fixed_grade_denominator_survives_class_filter(self):
        chosen=select(self.f,[3]);q=class_context(chosen,self.f)
        self.assertEqual(q.class_share_of_grade.iloc[0],2/5)
        examples=query_examples(chosen,self.f).set_index('query')['count']
        self.assertEqual(examples['全年级1班：移除班级筛选'],2);self.assertEqual(examples['当前范围与1班交集'],0)

    def test_range_endpoints_and_boolean_complements(self):
        q=query_examples(self.f,self.f).set_index('query')['count']
        self.assertEqual(q['语文60至80：含两个端点'],3);self.assertEqual(q['语文60至80：不含80'],1)
        self.assertEqual(q['数学60至90：含两个端点'],3);self.assertEqual(q['数学60至90：不含90'],2)
        self.assertEqual(q['当前范围1班或3班']+q['当前范围不属于1班或3班'],5)
        self.assertEqual(q['语文>=60：SQLite去重计数'],3)

    def test_excel_epoch_and_fictitious_day(self):
        self.assertEqual(decode_birth(pd.Series([1])).iloc[0],pd.Timestamp('1900-01-01'))
        self.assertEqual(decode_birth(pd.Series([1]),CALENDAR_MAC_1904).iloc[0],pd.Timestamp('1904-01-02'))
        with self.assertRaises(ValueError):decode_birth(pd.Series([60]))

    def test_duplicate_or_unmatched_exam_and_teacher_key_rejected(self):
        with self.assertRaises(ValueError):prepare_exam(self.s,self.t,pd.concat([self.e,self.e.iloc[[0]]]))
        e=self.e.copy();e.loc[0,'学号']='UNKNOWN'
        with self.assertRaises(ValueError):prepare_exam(self.s,self.t,e)
        with self.assertRaises(ValueError):prepare_exam(self.s,pd.concat([self.t,self.t.iloc[[0]]]),self.e)

    def test_score_range_and_input_preservation(self):
        s,t,e=school();prepare_exam(s,t,e)
        pd.testing.assert_frame_equal(s,self.s);pd.testing.assert_frame_equal(e,self.e)
        for value in [-1,101,np.inf]:
            bad=self.e.copy();bad['语文']=bad['语文'].astype(float);bad.loc[0,'语文']=value
            with self.assertRaises(ValueError):prepare_exam(self.s,self.t,bad)

    def test_empty_selection_keeps_rates_unknown(self):
        chosen=select(self.f,[99]);m=measures(chosen);q=subject_statistics(chosen)
        self.assertEqual(m['enrolled'],0);self.assertIsNone(m['mean_total_complete'])
        self.assertTrue(q.pass_rate_observed.isna().all());self.assertTrue(q.pass_fraction_enrolled.isna().all())


if __name__=='__main__':unittest.main()
