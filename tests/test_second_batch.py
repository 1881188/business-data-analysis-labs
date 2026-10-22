"""Business boundaries for the second migration batch; no textbook records required."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
from bda_labs.bcg import calculate as bcg,quadrant
from bda_labs.loyalty import calculate as loyalty,quantile_score
from bda_labs.cohort import calculate as cohort
from bda_labs.funnel import calculate as funnel


class BCGTests(unittest.TestCase):
    def data(self):
        return pd.DataFrame({'订单ID':[1,2,3,4],'销售日期':['2021-07-01','2021-08-01']*2,
            '品牌':['A','A','B','B'],'单价':[100,300,100,100],'销量':[1]*4})

    def test_share_uses_both_months_and_money_is_conserved(self):
        frame,totals=bcg(self.data())
        self.assertAlmostEqual(frame.set_index('brand').loc['A','sales_share'],2/3)
        self.assertEqual(frame.combined_cents.sum(),60000)
        self.assertAlmostEqual(totals['market_growth'],1.)

    def test_new_brand_has_no_invented_growth(self):
        raw=self.data();raw.loc[2,'销量']=0
        frame,_=bcg(raw)
        b=frame.set_index('brand').loc['B']
        self.assertTrue(np.isnan(b.growth))
        self.assertEqual(b.quadrant,'无法比较')

    def test_equality_is_explicitly_high(self):
        self.assertEqual(quadrant(.1,.2,.1,.2),'明星产品')


class LoyaltyTests(unittest.TestCase):
    def data(self):
        return pd.DataFrame({'订单编号':list('abcdefg'),'会员编号':['risk','new','edge','d','d','e','e'],
            '消费日期':['2020-10-01','2020-10-03','2020-10-02','2020-01-01','2020-12-01','2020-11-01','2020-12-01'],
            '消费金额':[10,10,10,10,10,10,10]})

    def test_special_groups_precede_quantile_scores_and_boundary_is_visible(self):
        exact,t=loyalty(self.data())
        inclusive,_=loyalty(self.data(),recent_inclusive=True)
        labels=exact.set_index('customer_id').segment
        self.assertEqual(labels['risk'],'易流失用户')
        self.assertEqual(labels['new'],'潜在用户')
        self.assertNotEqual(labels['edge'],'潜在用户')
        self.assertEqual(inclusive.set_index('customer_id').loc['edge','segment'],'潜在用户')
        self.assertEqual(t['scored_members'],3)
        self.assertTrue(exact.set_index('customer_id').loc['risk',['f_score','m_score']].isna().all())

    def test_quantile_equalities_remain_middle(self):
        self.assertEqual(quantile_score(pd.Series([3,4,7,8]),4,7).tolist(),[1,2,2,3])

    def test_product_lines_do_not_inflate_frequency_or_disappear_from_money(self):
        raw=self.data()
        raw=pd.concat([raw,raw.iloc[[3]].assign(消费金额=15)],ignore_index=True)
        result,_=loyalty(raw)
        row=result.set_index('customer_id').loc['d']
        self.assertEqual(row.frequency,2)
        self.assertEqual(row.monetary_cents,3500)


class CohortTests(unittest.TestCase):
    def data(self):
        return pd.DataFrame({'用户编号':['a','a','a','b'],
            '注册日期':['2020-07-01','2020-07-01','2020-07-01','2020-07-02'],
            '登录时点':['2020-07-01 01:00','2020-07-01 02:00','2020-07-02 08:00','2020-07-02 09:00']})

    def test_user_day_dedup_and_unobserved_cells(self):
        daily,counts,rates,overall,info=cohort(self.data(),'2020-07-02',3)
        self.assertEqual(counts.iloc[0,0],1)
        self.assertTrue(np.isnan(rates.iloc[1,1]))
        self.assertTrue(np.isnan(rates.iloc[0,2]))
        self.assertEqual(info['users'],2)
        self.assertEqual(overall.iloc[1].retention,1.)
        self.assertEqual(overall.iloc[1].textbook_fixed_denominator_retention,.5)
        self.assertEqual(daily.loc['2020-07-02','active_users'],2)

    def test_observed_no_return_is_zero(self):
        raw=self.data().iloc[[0,3]]
        _,_,rates,_,_=cohort(raw,'2020-07-02',2)
        self.assertEqual(rates.iloc[0,1],0.)
        self.assertTrue(np.isnan(rates.iloc[1,1]))

    def test_conflicting_registration_and_pre_registration_login_rejected(self):
        bad=self.data();bad.loc[1,'注册日期']='2020-06-30'
        with self.assertRaises(ValueError):cohort(bad,'2020-07-02')
        bad=self.data();bad.loc[0,'登录时点']='2020-06-30 00:00'
        with self.assertRaises(ValueError):cohort(bad,'2020-07-02')


class FunnelTests(unittest.TestCase):
    def test_two_denominators_and_conservation(self):
        result=funnel(['a','b','c'],[100,90,80])
        self.assertAlmostEqual(result.iloc[2].step_conversion,80/90)
        self.assertEqual(result.iloc[2].cumulative_conversion,.8)
        self.assertEqual(result.lost_from_previous.sum(),20)

    def test_zero_denominator_is_unavailable(self):
        result=funnel(['a','b','c'],[100,0,0])
        self.assertTrue(np.isnan(result.iloc[2].step_conversion))
        self.assertEqual(result.iloc[2].cumulative_conversion,0.)
        self.assertTrue(funnel(['a','b'],[0,0]).cumulative_conversion.isna().all())

    def test_noncomparable_counts_rejected(self):
        for counts in [[1,2],[-1,0],[1.5,1]]:
            with self.assertRaises(ValueError):funnel(['a','b'],counts)


if __name__=='__main__':unittest.main()
