"""Synthetic tests for order grain, ratios, monthly goals and observation windows."""
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.province_sales import build_model as province_model, measures as province_measures, select as province_select, group as province_group
from bda_labs.apparel_analysis import build_model, demo_sources, measures, target_completion, observed_cohorts, weekly_comparison


def province_inputs():
    return {'orders':pd.DataFrame({'OrderID':[1,2],'EmployeeID':[7,99],'ShipProvince':['甲省','乙省'],'OrderDate':['2024-01-01','2024-02-01']}),
            'details':pd.DataFrame({'订单ID':[1,1,2],'产口ID':[1,2,1],'销售金额':[100,200,50],'销售成本':[60,120,30]}),
            'products':pd.DataFrame({'ProductID':[1,2],'ProductName':['同名商品','同名商品'],'CategoryID':[1,2]}),
            'categories':pd.DataFrame({'CategoryID':[1,2],'CategoryName':['甲类','乙类']}),
            'employees':pd.DataFrame({'EmployeeID':[7],'FullName':['示例员工']})}


class ProvinceTests(unittest.TestCase):
    def test_missing_employee_and_order_grain_preserved(self):
        data=province_inputs();before={k:v.copy(deep=True) for k,v in data.items()};h,f=province_model(**data)
        self.assertEqual(len(f),3);self.assertEqual(province_measures(f)['orders'],2)
        self.assertEqual(province_measures(f)['sales_cents'],35000);self.assertEqual(h.employee_missing.sum(),1)
        for key in before:pd.testing.assert_frame_equal(before[key],data[key])

    def test_same_name_products_remain_distinct(self):
        _,f=province_model(**province_inputs());g=province_group(f,['product_id','product'])
        self.assertEqual(len(g),2)

    def test_category_counts_are_not_additive(self):
        _,f=province_model(**province_inputs());g=province_group(f,['category'])
        self.assertEqual(g.orders.sum(),3);self.assertEqual(province_measures(f)['orders'],2)
        selected=province_select(f,category='乙类');self.assertEqual(province_measures(selected)['orders'],1)

    def test_filter_and_empty_denominator(self):
        _,f=province_model(**province_inputs())
        self.assertEqual(province_measures(province_select(f,year=2024,month=2))['sales_cents'],5000)
        self.assertIsNone(province_measures(province_select(f,year=2000))['margin'])
        with self.assertRaises(ValueError):province_select(f,month=13)

    def test_ambiguous_and_unmatched_keys_fail(self):
        for mode in ['duplicate','unmatched']:
            data=province_inputs()
            if mode=='duplicate':data['products']=pd.concat([data['products'],data['products'].iloc[[0]]])
            else:data['details'].loc[0,'产口ID']=999
            with self.assertRaises(ValueError):province_model(**data)


class ApparelTests(unittest.TestCase):
    def setUp(self):
        self.book=demo_sources();self.h,self.f,self.t,self.diag=build_model(self.book);self.stores=self.t['店铺表']

    def test_order_header_detail_reconciliation_and_source_unchanged(self):
        before=demo_sources()
        self.assertEqual(self.diag['order_reconciliation_values'],18)
        for name in self.book:pd.testing.assert_frame_equal(self.book[name],before[name])
        self.book['零售单'].loc[0,'成交金额']+=1
        with self.assertRaises(ValueError):build_model(self.book)

    def test_weighted_discount_order_unit_ratios_and_area(self):
        m=measures(self.f,self.stores)
        self.assertEqual(m['paid'],735);self.assertEqual(m['orders'],6);self.assertEqual(m['quantity'],7)
        self.assertAlmostEqual(m['discount'],735/900)
        self.assertNotAlmostEqual(m['discount'],self.f.saved_discount.mean())
        self.assertAlmostEqual(m['attachment'],7/6);self.assertEqual(m['sales_per_area'],735/300)

    def test_blank_member_not_counted_and_revenue_same_population(self):
        self.book['零售单'].loc[self.book['零售单']['会员id'].eq(102),'会员id']=np.nan
        _,f,t,_=build_model(self.book);m=measures(f,t['店铺表'])
        self.assertEqual(m['members'],2);self.assertEqual(m['member_sales'],555);self.assertEqual(m['member_average'],277.5)

    def test_empty_measures_keep_unknown_ratios(self):
        m=measures(self.f.iloc[:0],self.stores)
        self.assertEqual(m['paid'],0);self.assertEqual(m['orders'],0)
        self.assertIsNone(m['discount']);self.assertIsNone(m['member_average']);self.assertIsNone(m['attachment'])

    def test_units_are_not_detail_row_count(self):
        self.book['零售单'].loc[self.book['零售单']['订单id'].eq(6),['数量','零售金额','成交金额']]=[2,200,150]
        self.book['零售单明细'].loc[self.book['零售单明细']['订单明细id'].eq(7),['数量','零售金额','成交金额']]=[2,200,150]
        _,f,t,_=build_model(self.book)
        self.assertEqual(len(f),7);self.assertEqual(measures(f,t['店铺表'])['quantity'],8)

    def test_staff_blanks_and_current_store_do_not_override_order(self):
        self.book['员工表'].loc[0,'店铺id']=2
        h,_,_,diag=build_model(self.book)
        self.assertEqual(h.loc[h.order_id.eq(1),'store_id'].iloc[0],1)
        self.assertEqual(diag['employee_unfilled_orders'],1);self.assertGreater(diag['employee_registered_store_differences'],0)

    def test_targets_are_once_per_month_and_missing_not_zero(self):
        q=target_completion(self.h,self.t['店铺月目标表'],'store_id')
        jan=q[(q.month=='2024-01')&(q.store_id==1)].iloc[0]
        self.assertEqual(jan.base_cents,50000);self.assertEqual(jan.paid_cents,24000)
        self.assertEqual(jan.base_completion,.48)
        missing=q[(q.month=='2024-01')&(q.store_id==2)].iloc[0]
        self.assertFalse(missing.target_present);self.assertTrue(pd.isna(missing.base_completion))

    def test_future_target_is_unknown_and_zero_target_undefined(self):
        targets=self.t['店铺月目标表'].copy()
        extra=targets.iloc[[0]].copy();extra['month']='2024-04';extra['year_month']=202404
        q=target_completion(self.h,pd.concat([targets,extra],ignore_index=True),'store_id')
        self.assertTrue(q.loc[q.month.eq('2024-04'),'paid_cents'].isna().all())
        targets['base_cents']=0;q=target_completion(self.h,targets,'store_id')
        self.assertTrue(q.base_completion.isna().all())

    def test_duplicate_target_key_is_rejected(self):
        targets=self.t['店铺月目标表']
        with self.assertRaises(ValueError):target_completion(self.h,pd.concat([targets,targets.iloc[[0]]]),'store_id')

    def test_cohort_deduplication_future_and_partial_month(self):
        q=observed_cohorts(self.h)
        january=q[q.cohort.eq('2024-01')].set_index('age_month')
        self.assertEqual(january.loc[0,'cohort_members'],2);self.assertEqual(january.loc[1,'repeat_rate'],.5)
        february=q[q.cohort.eq('2024-02')].set_index('age_month')
        self.assertFalse(february.loc[2,'observed']);self.assertTrue(pd.isna(february.loc[2,'repeat_rate']))
        self.assertFalse(january.loc[2,'complete_calendar_month'])
        repeated=pd.concat([self.h,self.h.iloc[[0]]],ignore_index=True)
        pd.testing.assert_frame_equal(q,observed_cohorts(repeated))

    def test_weekly_delta_modes_and_outside_window_unknown(self):
        frame=self.f[self.f.order_id.eq(1)].copy();prior=frame.copy();prior['date']=frame.date+pd.Timedelta(days=7)
        prior['paid_cents']=prior.paid_cents//2
        both=pd.concat([frame,prior],ignore_index=True)
        q=weekly_comparison(both,self.stores,'2024-01-12').set_index('metric')
        self.assertAlmostEqual(q.loc['paid','change'],-.5);self.assertEqual(q.loc['orders','change'],0)
        self.assertEqual(q.loc['discount','change_kind'],'percentage_point_fraction')
        q=weekly_comparison(self.f,self.stores,'2024-01-05')
        self.assertTrue(q.change.isna().all())

    def test_price_anomalies_not_clipped(self):
        self.book['零售单'].loc[0,'成交金额']=400
        d=self.book['零售单明细'];d.loc[d['订单明细id'].eq(1),'成交金额']=250
        h,f,t,diag=build_model(self.book)
        self.assertGreater(diag['discount_above_one_rows'],0)
        self.assertGreater(f.discount.max(),1)

    def test_invalid_dimension_and_quantity_fail(self):
        self.book['店铺表']=pd.concat([self.book['店铺表'],self.book['店铺表'].iloc[[0]]])
        with self.assertRaises(ValueError):build_model(self.book)
        self.book=demo_sources();self.book['零售单明细'].loc[0,'数量']=0
        with self.assertRaises(ValueError):build_model(self.book)


if __name__=='__main__':unittest.main()
