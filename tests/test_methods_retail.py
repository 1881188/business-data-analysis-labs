"""Synthetic boundary checks; course datasets are not needed in CI."""
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.analysis_methods import growth, distribution, flow_balance
from bda_labs.retail_dashboard import prepare, select, metrics, aggregate, to_cents


def source():
    return pd.DataFrame({'订单号':['A','B','C'],'订单时间':['2022-04-01 00:00:00','2022-04-01 23:59:59','2022-04-02 00:00:00'],
                         '实际支付':[0,19.99,10.01],'城市':['甲','甲','乙'],'数量':[1,2,1],
                         '商品名称':['a','b','c'],'商品类别':['x','y','x']})


class MethodsTests(unittest.TestCase):
    def test_growth_zero_baseline_is_unknown(self):
        result=growth([0,5,10,0])
        self.assertTrue(result.iloc[:2].isna().all());self.assertEqual(result.iloc[2],1);self.assertEqual(result.iloc[3],-1)

    def test_inclusive_quantiles_and_outlier_not_deleted(self):
        result=distribution([0,1,2,3,100])
        self.assertEqual(result['q1'],1);self.assertEqual(result['q3'],3)
        self.assertEqual(result['upper_fence'],6);self.assertEqual(result['outliers'],1)
        self.assertEqual(result['mean'],21.2)

    def test_invalid_distribution_and_growth_fail(self):
        for x in [[],[1,np.nan],[np.inf]]:
            with self.assertRaises(ValueError):distribution(x)
        with self.assertRaises(ValueError):growth([1,-1])

    def test_flow_gain_is_exposed_without_repair(self):
        edges=pd.DataFrame({'source':['home','blog','blog'],'target':['blog','a','b'],'flow':[250,150,120]})
        before=edges.copy(deep=True);_,nodes=flow_balance(edges)
        blog=nodes.set_index('node').loc['blog']
        self.assertEqual(blog.outgoing_minus_incoming,20);self.assertTrue(blog.unexplained_gain)
        pd.testing.assert_frame_equal(before,edges)

    def test_negative_flow_rejected(self):
        with self.assertRaises(ValueError):flow_balance(pd.DataFrame({'source':['a'],'target':['b'],'flow':[-1]}))


class RetailTests(unittest.TestCase):
    def test_exact_cents_zero_and_quantity(self):
        raw=source();before=raw.copy(deep=True);f=prepare(raw);m=metrics(f)
        self.assertEqual(m['payment_cents'],3000);self.assertEqual(m['payment'],30)
        self.assertEqual(m['quantity'],4);self.assertEqual(m['zero_payment_rows'],1)
        self.assertEqual(m['payment_per_order'],10)
        pd.testing.assert_frame_equal(raw,before)

    def test_end_date_includes_entire_day(self):
        f=prepare(source());selected=select(f,'2022-04-01','2022-04-01')
        self.assertEqual(selected.order_id.tolist(),['A','B'])

    def test_all_filters_share_population(self):
        f=prepare(source());chosen=select(f,'2022-04-01','2022-04-01','甲','y')
        self.assertEqual(metrics(chosen)['payment_cents'],1999)
        self.assertEqual(aggregate(chosen,['city']).quantity.sum(),2)

    def test_empty_selection_has_no_denominator(self):
        f=select(prepare(source()),city='不存在');m=metrics(f)
        self.assertEqual(m['order_count'],0);self.assertEqual(m['payment_cents'],0)
        self.assertIsNone(m['payment_per_order']);self.assertTrue(aggregate(f,['date']).empty)

    def test_multiline_count_and_conflicting_order(self):
        raw=source();raw.loc[1,'订单号']='A';raw.loc[1,'订单时间']=raw.loc[0,'订单时间']
        m=metrics(prepare(raw));self.assertEqual(m['order_count'],2);self.assertEqual(m['nonnull_order_id_count'],3)
        self.assertEqual(m['payment_per_order'],15)
        raw.loc[1,'城市']='乙'
        with self.assertRaises(ValueError):prepare(raw)

    def test_unreviewed_data_rejected(self):
        for column,value in [('实际支付',None),('实际支付',-1),('实际支付',1.001),('数量',0),('数量',1.5),('城市','')]:
            raw=source();raw[column]=raw[column].astype(object);raw.loc[0,column]=value
            with self.assertRaises(ValueError):prepare(raw)
        raw=source()
        with self.assertRaises(ValueError):prepare(pd.concat([raw,raw.iloc[[0]]],ignore_index=True))

    def test_date_and_money_boundaries(self):
        f=prepare(source())
        for start,end in [('2022-04-02','2022-04-01'),('2022-04-01 12:00','2022-04-02')]:
            with self.assertRaises(ValueError):select(f,start,end)
        self.assertEqual(to_cents('0.10'),10)
        for value in ['NaN','Infinity','1.005']:
            with self.assertRaises(ValueError):to_cents(value)


if __name__=='__main__':unittest.main()
