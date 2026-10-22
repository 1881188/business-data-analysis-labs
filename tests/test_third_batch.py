"""Test sampling contracts, data preservation and precision-aware reference checks."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.correlation import calculate as correlation
from bda_labs.descriptive import describe_price
from bda_labs.sampling import get_sample
from bda_labs.preprocessing import clean_income
from bda_labs.visualization import prepare_stock, demonstration_data
from bda_labs.notebook_reference import compare_displayed


class SamplingTests(unittest.TestCase):
    def test_systematic_achieves_size_that_old_step_missed(self):
        frame = pd.DataFrame({'id':range(100)})
        result = get_sample(frame, ''.join(['sys','tematic']), 50)
        self.assertEqual(len(result), 50)
        self.assertEqual(result.id.nunique(), 50)
        self.assertEqual(len(get_sample(frame, 'systematic', 100)), 100)
        self.assertEqual(len(get_sample(frame, 'systematic', .13)), 13)

    def test_seed_repeats_random_start_and_can_change_selection(self):
        frame = pd.DataFrame({'id':range(100)})
        a = get_sample(frame, 'systematic', 5, random_state=1)
        pd.testing.assert_frame_equal(a, get_sample(frame, 'systematic', 5, random_state=1))
        self.assertFalse(a.equals(get_sample(frame, 'systematic', 5, random_state=2)))

    def test_each_stratum_rounded_separately_and_missing_keys_retained(self):
        frame = pd.DataFrame({'id':range(7), 'stratum':['a','a','a','b','b',None,None]})
        result = get_sample(frame, 'stratified', .5, ['stratum'])
        counts = result.groupby('stratum',dropna=False).size()
        self.assertEqual(len(result),4)
        self.assertEqual(counts.loc['a'],2)
        self.assertEqual(counts.loc['b'],1)
        self.assertEqual(result.stratum.isna().sum(),1)

    def test_multicolumn_groups_and_duplicate_index_use_row_positions(self):
        frame = pd.DataFrame({'id':range(8),'a':['x']*4+['y']*4,'b':[1,1,2,2]*2}, index=[0]*8)
        result = get_sample(frame,'stratified',1,['a','b'])
        self.assertEqual(result.id.nunique(),4)
        self.assertTrue(result.groupby(['a','b']).size().eq(1).all())

    def test_small_stratum_rejected_even_when_overall_population_large(self):
        frame = pd.DataFrame({'stratum':['a']*9+['b']})
        with self.assertRaises(ValueError):
            get_sample(frame,'stratified',2,['stratum'])

    def test_invalid_sizes_and_methods_rejected(self):
        frame = pd.DataFrame({'x':range(5)})
        for k in [True,0,-1,1.,6,np.nan,np.inf]:
            with self.subTest(k=k), self.assertRaises(ValueError):
                get_sample(frame,k=k)
        with self.assertRaises(ValueError):
            get_sample(frame,'unknown')
        with self.assertRaises(ValueError):
            get_sample(frame.iloc[:0],k=.1)


class StatisticalContractTests(unittest.TestCase):
    def test_linear_fit_and_constant_or_incomplete_pairs(self):
        raw = pd.DataFrame({'x':[1,2,3],'y':[3,5,7]})
        _, result = correlation(raw)
        self.assertAlmostEqual(result['slope'],2)
        self.assertAlmostEqual(result['intercept'],1)
        self.assertAlmostEqual(result['r_squared'],1)
        for bad in [raw.assign(x=1),raw.assign(y=[3,np.nan,7]),raw.assign(x=[1,2,np.inf])]:
            with self.assertRaises(ValueError):
                correlation(bad)

    def test_sample_standard_deviation_and_quartile_definition(self):
        _, metrics, _ = describe_price(pd.DataFrame({'AREA':[1,2,3,4],'price':[1,2,3,4]}))
        self.assertAlmostEqual(metrics['variance'],5/3)
        self.assertAlmostEqual(metrics['q25'],1.75)
        self.assertAlmostEqual(metrics['q75'],3.25)

    def test_display_precision_does_not_allow_large_relative_tolerance(self):
        compare_displayed(61151.8109192,'61151.810919')
        compare_displayed(.95299,'0.953')
        with self.assertRaises(AssertionError):
            compare_displayed(61151.82,'61151.810919')
        with self.assertRaises(AssertionError):
            compare_displayed(np.nan,'0.953')


class DataPreservationTests(unittest.TestCase):
    def test_only_income_zero_is_converted_and_existing_missing_is_distinct(self):
        raw = pd.DataFrame({'AvgIncome':[0,10,np.nan],'AvgHomeValue':[0,20,30],'other':[0,1,2]})
        original = raw.copy(deep=True)
        clean = clean_income(raw)
        pd.testing.assert_frame_equal(raw,original)
        self.assertEqual(clean.AvgIncome.isna().sum(),2)
        self.assertEqual(clean.AvgIncome_was_zero.tolist(),[True,False,False])
        pd.testing.assert_series_equal(clean.AvgHomeValue,raw.AvgHomeValue)
        pd.testing.assert_series_equal(clean.other,raw.other)

    def test_negative_or_infinite_income_is_not_silently_cleaned(self):
        for value in [-1,np.inf]:
            with self.assertRaises(ValueError):
                clean_income(pd.DataFrame({'AvgIncome':[value],'AvgHomeValue':[10]}))

    def test_stock_sorted_without_changing_values_or_input(self):
        raw = pd.DataFrame({'日期':['2017-09-02','2017-09-01'],'收盘价':[10,11],
                            '开盘价':[11,12],'最高价':[12,13],'最低价':[9,10]})
        original = raw.copy(deep=True)
        result = prepare_stock(raw)
        self.assertTrue(result['日期'].is_monotonic_increasing)
        self.assertEqual(result['收盘价'].tolist(),[11,10])
        pd.testing.assert_frame_equal(raw,original)
        with self.assertRaises(ValueError):
            prepare_stock(raw.assign(最高价=1))
        with self.assertRaises(ValueError):
            prepare_stock(raw.assign(日期='2017-09-01'))

    def test_visualization_uses_local_random_streams(self):
        before = np.random.get_state()
        first = demonstration_data()
        after = np.random.get_state()
        np.testing.assert_array_equal(before[1],after[1])
        self.assertEqual(before[2:],after[2:])
        self.assertEqual(first[0].votes.tolist(),[47,22,82,19,85])
        np.testing.assert_array_equal(first[1],demonstration_data()[1])


if __name__ == '__main__':
    unittest.main()
