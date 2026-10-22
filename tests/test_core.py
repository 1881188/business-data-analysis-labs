"""Meaningful grain, boundary, label and join checks using synthetic data only."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import pandas as pd
from bda_labs.rfm import AS_OF,calculate,money_cents
from bda_labs.cleaning import cap,merge_tables
from bda_labs.churn import choose_threshold,evaluate,fit_regularized,MODEL_NUMERIC,MODEL_CATEGORICAL
import numpy as np


class RFMTests(unittest.TestCase):
    def test_receipt_grain_and_amount_conservation(self):
        data=pd.DataFrame({'流水号':['a','a','b'],'用户编号':['1','1','2'],
                           '销售日期':[AS_OF-pd.Timedelta(days=1)]*3,'销售金额':[10,15,20]})
        result=calculate(data).set_index('customer_id')
        self.assertEqual(result.loc['1','frequency'],1)
        self.assertEqual(result.loc['1','line_count'],2)
        self.assertEqual(result.loc['1','monetary_cents'],2500)
        self.assertEqual(result.monetary_cents.sum(),4500)

    def test_equal_to_mean_is_low(self):
        data=pd.DataFrame({'流水号':['a','b'],'用户编号':['1','2'],
                           '销售日期':[AS_OF-pd.Timedelta(days=1)]*2,'销售金额':[10,10]})
        self.assertEqual(calculate(data)['segment'].tolist(),['一般挽留用户']*2)

    def test_future_and_shared_receipt_rejected(self):
        data=pd.DataFrame({'流水号':['a','a'],'用户编号':['1','2'],
                           '销售日期':[AS_OF]*2,'销售金额':[10,10]})
        with self.assertRaises(ValueError):calculate(data)
        data['流水号']=['a','b']
        data['销售日期']=AS_OF+pd.Timedelta(days=1)
        with self.assertRaises(ValueError):calculate(data)

    def test_sub_cent_money_rejected(self):
        with self.assertRaises(ValueError):money_cents(pd.Series([1.001]))


class CleaningTests(unittest.TestCase):
    def test_cap_preserves_original(self):
        values=pd.Series([0.,1.,2.,3.,100.])
        before=values.copy()
        self.assertEqual(cap(values,.25,.75).tolist(),[1.,1.,2.,3.,3.])
        pd.testing.assert_series_equal(values,before)

    def test_duplicate_join_key_is_not_silently_multiplied(self):
        with self.assertRaises(pd.errors.MergeError):
            merge_tables(pd.DataFrame({'id':[1]}),pd.DataFrame({'id':[1,1]}))


class ChurnTests(unittest.TestCase):
    def test_positive_class_and_denominators(self):
        result=evaluate([0,0,1,1],[.1,.8,.7,.2],.5)
        self.assertEqual([result[k] for k in ['tn','fp','fn','tp']],[1,1,1,1])
        for key in ['precision','recall','specificity','f1']:self.assertEqual(result[key],.5)

    def test_validation_cutoff_and_equality(self):
        threshold,youden=choose_threshold([0,0,1,1],[.1,.2,.8,.9])
        self.assertEqual(threshold,.8)
        self.assertEqual(youden,1.)
        self.assertEqual(evaluate([0,0,1,1],[.1,.2,.8,.9],threshold)['recall'],1.)

    def test_preprocessing_does_not_fit_on_prediction_data(self):
        rng=np.random.RandomState(42)
        train=pd.DataFrame({name:rng.normal(size=80) for name in MODEL_NUMERIC})
        for name in MODEL_CATEGORICAL:train[name]=rng.randint(0,2,size=80)
        train['churn']=rng.randint(0,2,size=80)
        model=fit_regularized(train)
        scaler=model.named_steps['prepare'].named_transformers_['numeric']
        np.testing.assert_allclose(scaler.mean_,train[MODEL_NUMERIC].mean())
        before=scaler.mean_.copy()
        changed=train.copy()
        changed[MODEL_NUMERIC]+=1000
        model.predict_proba(changed)
        np.testing.assert_array_equal(scaler.mean_,before)

    def test_id_does_not_enter_predictors(self):
        self.assertNotIn('subscriberID',MODEL_NUMERIC+MODEL_CATEGORICAL)


if __name__=='__main__':unittest.main()
