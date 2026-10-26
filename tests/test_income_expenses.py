"""Synthetic boundaries, independent arithmetic and source-preservation checks."""
from pathlib import Path
import sys,unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.case_workbooks import money_cents,calendar_period,ratio,check_cell
from bda_labs.income_trends import prepare as income_prepare,totals,province_bridge
from bda_labs.expense_breakdown import prepare as expense_prepare,changes,reconcile,analyze,snapshot_differences
from bda_labs.workbook_reference import Sheet


def income(rows):return income_prepare(pd.DataFrame(rows,columns=['订单年份','订单月份','销售省份','销售额']))


def expense(rows,total=False):
    return expense_prepare(pd.DataFrame(rows,columns=['year','month','amount'] if total else ['year','month','category','amount']),not total)


class IncomeBoundaryTests(unittest.TestCase):
    def test_prior_year_denominator_and_no_mean_of_rates(self):
        f=income([(2019,1,'A',100),(2019,1,'B',900),(2020,1,'A',200),(2020,1,'B',900)])
        monthly,_=totals(f);row=monthly.set_index('period').loc[pd.Period('2020-01')]
        self.assertAlmostEqual(row.yoy_growth,.1)
        b=province_bridge(f,'2020-01','2019-01');self.assertAlmostEqual(b.contribution_to_observed_growth_pp.sum(),10)
        self.assertNotAlmostEqual(b.yoy_growth.mean(),row.yoy_growth)

    def test_missing_calendar_month_does_not_shift_last_observation(self):
        monthly,_=totals(income([(2020,1,'A',100),(2020,3,'A',200)]));m=monthly.set_index('period')
        self.assertTrue(pd.isna(m.loc[pd.Period('2020-02'),'amount']))
        self.assertTrue(pd.isna(m.loc[pd.Period('2020-03'),'mom_growth']))

    def test_previous_december_is_january_mom_base(self):
        monthly,_=totals(income([(2019,12,'A',100),(2020,1,'A',125)]))
        self.assertEqual(monthly.iloc[-1].mom_growth,.25)

    def test_true_zero_current_is_minus_one_not_unknown(self):
        b=province_bridge(income([(2019,1,'A',100),(2020,1,'A',0)]),'2020-01','2019-01').iloc[0]
        self.assertTrue(b.current_observed);self.assertEqual(b.yoy_growth,-1)
        self.assertTrue(pd.isna(b.textbook_current_denominator))

    def test_missing_province_is_not_imputed_as_observed_zero(self):
        f=income([(2019,1,'A',100),(2019,1,'B',50),(2020,1,'A',120),(2020,1,'C',20)])
        b=province_bridge(f,'2020-01','2019-01').set_index('province')
        self.assertFalse(b.loc['B','current_observed']);self.assertTrue(pd.isna(b.loc['B','current_amount']))
        self.assertTrue(pd.isna(b.loc['B','yoy_growth']));self.assertTrue(pd.isna(b.loc['C','yoy_growth']))
        self.assertEqual(b.observed_sum_delta.sum(),-10)

    def test_whole_period_absence_keeps_bridge_unknown(self):
        b=province_bridge(income([(2019,1,'A',100)]),'2020-01','2019-01')
        self.assertTrue(b.observed_sum_delta.isna().all());self.assertTrue(b.contribution_to_observed_growth_pp.isna().all())

    def test_duplicate_key_after_whitespace_normalization_rejected(self):
        with self.assertRaises(ValueError):income([(2020,1,'A',1),(2020,1,' A ',2)])
        for rows in [[(2020,13,'A',1)],[(2020,1,'',1)],[(2020,1,'A',-1)],[(2020,1,'A',None)]]:
            with self.assertRaises(ValueError):income(rows)

    def test_annual_month_coverage_and_input_preserved(self):
        raw=pd.DataFrame([(2020,1,'A',.1),(2020,2,'A',.2)],columns=['订单年份','订单月份','销售省份','销售额'])
        original=raw.copy(deep=True);f=income_prepare(raw);_,annual=totals(f)
        pd.testing.assert_frame_equal(raw,original);self.assertEqual(f.amount_cents.sum(),30)
        self.assertEqual(annual.iloc[0].months_observed,2);self.assertFalse(annual.iloc[0].calendar_months_present)


class ExpenseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.total=expense([(2020,6,100),(2020,7,130)],True)
        self.period=expense([(2020,6,'管理费用',80),(2020,7,'管理费用',90),(2020,6,'财务费用',20),(2020,7,'财务费用',15)])
        self.detail=expense([(2020,6,'薪酬',60),(2020,7,'薪酬',65),(2020,6,'其他',20),(2020,7,'其他',25)])

    def test_residual_bridge_not_forced_to_zero(self):
        r,c,a,m=analyze(self.total,self.period,self.detail)
        self.assertEqual(m['reported_delta'],30);self.assertEqual(m['observed_period_delta'],5)
        self.assertEqual(m['total_residual_delta'],25);self.assertEqual(m['admin_residual_delta'],0)
        self.assertAlmostEqual(c.contribution_to_parent_growth_pp.sum()+25,30)
        self.assertEqual(a.delta.sum(),10)

    def test_child_parent_difference_not_silently_allocated(self):
        detail=self.detail.copy();detail.loc[detail.period.eq(pd.Period('2020-07')),'amount_cents']+=100
        r,c,a,m=analyze(self.total,self.period,detail)
        self.assertEqual(m['admin_residual_delta'],-2);self.assertEqual(a.delta.sum(),12)
        self.assertEqual(a.delta.sum()+m['admin_residual_delta'],m['admin_delta'])

    def test_signed_contribution_and_zero_net_change(self):
        total=self.total.copy();total.loc[total.period.eq(pd.Period('2020-07')),'amount_cents']=10000
        _,c,_,m=analyze(total,self.period,self.detail)
        self.assertEqual(m['reported_delta'],0);self.assertTrue(c.signed_share_of_parent_change.isna().all())
        self.assertTrue(c.loc[c.category.eq('财务费用'),'contribution_to_parent_growth_pp'].item()<0)

    def test_zero_base_and_negative_credit_are_distinct(self):
        f=expense([(2020,6,'A',0),(2020,7,'A',-5),(2020,6,'B',10),(2020,7,'B',0)])
        c=changes(f,'2020-06','2020-07').set_index('category')
        self.assertTrue(pd.isna(c.loc['A','growth']));self.assertEqual(c.loc['A','delta'],-5)
        self.assertEqual(c.loc['B','growth'],-1)

    def test_missing_category_is_unknown_not_zero(self):
        c=changes(expense([(2020,6,'A',10),(2020,7,'B',20)]),'2020-06','2020-07')
        self.assertTrue(c.delta.isna().all());self.assertTrue(c.growth.isna().all())

    def test_text_month_label_and_blank_row_handling(self):
        raw=pd.DataFrame([[2020,'6月',' 管理费用 ',.10],[2020,'7月','管理费用',.20],[None,None,None,None]])
        original=raw.copy(deep=True);f=expense_prepare(raw)
        self.assertEqual(f.amount_cents.tolist(),[10,20]);self.assertEqual(f.category.unique().tolist(),['管理费用'])
        pd.testing.assert_frame_equal(raw,original)

    def test_duplicate_and_nonconsecutive_comparison_rejected(self):
        with self.assertRaises(ValueError):expense([(2020,6,'A',10),(2020,6,' A ',20)])
        with self.assertRaises(ValueError):changes(self.period,'2020-05','2020-07')

    def test_missing_entire_layer_keeps_residual_unknown(self):
        period=self.period[self.period.period.eq(pd.Period('2020-06'))]
        r=reconcile(self.total,period,self.detail).set_index('period')
        self.assertTrue(pd.isna(r.loc[pd.Period('2020-07'),'observed_period']))
        self.assertTrue(pd.isna(r.loc[pd.Period('2020-07'),'total_residual']))

    def test_snapshot_differences_by_keys_and_layer(self):
        alternate=self.period.copy();alternate.loc[0,'amount_cents']+=500
        differences=snapshot_differences([self.total,self.period,self.detail],[self.total,alternate.iloc[::-1],self.detail])
        changed=differences[~differences.same_observed_amount]
        self.assertEqual(len(changed),1);self.assertEqual(changed.iloc[0].level,'period');self.assertEqual(changed.iloc[0].complete_minus_raw,5)


class WorkbookContractTests(unittest.TestCase):
    def test_money_and_calendar_reject_ambiguous_values(self):
        for value in [np.nan,np.inf,None,.001,'text']:
            with self.assertRaises(ValueError):money_cents(pd.Series([value]))
        self.assertEqual(calendar_period(pd.Series([2020]),pd.Series([' 6月 '])).iloc[0],pd.Period('2020-06'))
        for y,m in [(2020,0),(2020,13),(2020,1.5),(None,1),(2020.5,1)]:
            with self.assertRaises(ValueError):calendar_period(pd.Series([y]),pd.Series([m]))
        self.assertTrue(np.isnan(ratio(0,0)));self.assertTrue(np.isnan(ratio(np.nan,1)))

    def test_reference_formula_drift_and_bad_cache_are_not_hidden(self):
        sheet=Sheet('test',{'C1':.1},{'C1':'=(B1-A1)/A1'},{});records=[]
        check_cell(records,sheet,'C1',.1,'synthetic','=(B1-A1)/A1')
        with self.assertRaises(AssertionError):check_cell([],sheet,'C1',.2,'bad value')
        with self.assertRaises(AssertionError):check_cell([],sheet,'C1',.1,'bad formula','=(B1-A1)/B1')


if __name__=='__main__':unittest.main()
