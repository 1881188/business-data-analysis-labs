"""Independent small-data oracles for advanced migrations; no course data needed."""
from itertools import combinations, product
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
import networkx as nx
from sklearn.base import clone

from bda_labs.advanced_rules import frequent_itemsets,association_rules,sequence_patterns,contains_sequence
from bda_labs.advanced_networks import search_path,pagerank_matrix
from bda_labs.advanced_engineering import CalendarFeatures,HistoricalFeatures
from bda_labs.advanced_timeseries import windows
from bda_labs.advanced_finance import behavioral_features,read_mysql_dump
from bda_labs.advanced_regression import classification_metrics
from bda_labs.advanced_optimization import parse_linear_lp
from bda_labs.advanced_financial_fraud import historical_network_features,IncomeFeatures
from bda_labs.advanced_explanation import marginal_response


class RulesTests(unittest.TestCase):
    def test_customer_support_and_brute_force(self):
        baskets=[['a','a','b'],['a','b','c'],['b','c'],['a']]
        actual=frequent_itemsets(baskets,.5)
        expected={}
        for k in range(1,4):
            for s in combinations('abc',k):
                count=sum(set(s)<=set(b) for b in baskets)
                if count>=2:expected[frozenset(s)]=count
        self.assertEqual(actual,expected)
        rule=next(r for r in association_rules(actual,4) if r['antecedents']=='a' and r['consequents']=='b')
        self.assertAlmostEqual(rule['support'],.5)
        self.assertAlmostEqual(rule['confidence'],2/3)
        self.assertAlmostEqual(rule['lift'],8/9)

    def test_sequence_full_enumeration(self):
        sequences=[[set('ab'),set('c')],[set('a'),set('bc')],[set('a'),set('b'),set('c')]]
        found=sequence_patterns(sequences,2)
        patterns={}
        itemsets=[frozenset(s) for k in range(1,4) for s in combinations('abc',k)]
        for length in range(1,4):
            for candidate in product(itemsets,repeat=length):
                count=sum(contains_sequence(s,candidate) for s in sequences)
                if count>=2:patterns[candidate]=count
        self.assertEqual(found,patterns)
        self.assertNotIn((frozenset('ab'),),found)
        self.assertIn((frozenset('a'),frozenset('b')),found)

    def test_sequence_repeats_count_once(self):
        found=sequence_patterns([[{'a'},{'a'},{'b'}],[{'b'}]],1)
        self.assertEqual(found[(frozenset('a'),)],1)
        self.assertEqual(found[(frozenset('a'),frozenset('a'))],1)
        self.assertNotIn((frozenset('a'),frozenset('a'),frozenset('a')),found)


class GraphTests(unittest.TestCase):
    def test_traversal_boundaries(self):
        graph={0:[1,2],1:[0,3],2:[0],3:[1],4:[]}
        for depth in [False,True]:
            self.assertEqual(search_path(graph,0,0,depth_first=depth),[0])
            self.assertEqual(search_path(graph,0,3,depth_first=depth),[0,1,3])
            self.assertIsNone(search_path(graph,0,4,depth_first=depth))

    def test_pagerank_dangling_node(self):
        adjacency=np.array([[0,1,0],[0,0,1],[0,0,0]],float)
        result,_=pagerank_matrix(adjacency)
        reference=nx.pagerank(nx.from_numpy_array(adjacency,create_using=nx.DiGraph),tol=1e-13)
        np.testing.assert_allclose(result,list(reference.values()),atol=1e-10)
        self.assertAlmostEqual(result.sum(),1)

    def test_pagerank_invalid_and_nonconvergence(self):
        with self.assertRaises(ValueError):pagerank_matrix([[-1]])
        with self.assertRaises(RuntimeError):pagerank_matrix([[0,1],[0,0]],max_iter=1)

    def test_historical_network_no_future_or_own_bad_status(self):
        source=pd.DataFrame({'userid':['a','b','a','c'],'connid':['x','x','y','y'],
                             'in_date':[1,2,3,4],'flag':[1,0,1,0],'flag_date':[9,np.nan,9,np.nan]})
        original=historical_network_features(source)
        changed=source.copy();changed.loc[changed.userid=='a','flag_date']=10
        alternate=historical_network_features(changed)
        pd.testing.assert_frame_equal(original,alternate)
        self.assertEqual(original['percentage'].sum(),0)
        source.loc[source.userid=='a','flag_date']=2
        result=historical_network_features(source).set_index('userid')
        self.assertEqual(result.loc['a','percentage'],0)
        self.assertGreater(result.loc['c','percentage'],0)
        self.assertEqual(result.loc['b','percentage'],0)  # same-day fraud is not visible


class HistoryTests(unittest.TestCase):
    def test_calendar_is_cloneable_and_does_not_mutate(self):
        source=pd.DataFrame({'timestamp':['2024-02-29 21:00:00','2024-03-01 22:00:00']})
        before=source.copy()
        transformer=clone(CalendarFeatures(public_vacations=['20240229']))
        result=transformer.fit_transform(source)
        self.assertTrue(result.loc[0,'is_leap_year'])
        self.assertTrue(result.loc[0,'is_mth_end'])
        self.assertTrue(result.loc[0,'is_public_holiday'])
        self.assertFalse(result.loc[1,'is_working'])
        pd.testing.assert_frame_equal(source,before)

    def test_group_windows_and_future_invariance(self):
        source=pd.DataFrame({'id':['a']*6+['b']*6,'value':list(range(6))+list(range(10,16))})
        transformer=HistoricalFeatures(cols=['value'],group_col='id')
        result=clone(transformer).fit_transform(source)
        self.assertTrue(pd.isna(result.loc[6,'value-1day']))
        self.assertEqual(result.loc[3,'value-3day'],0)
        self.assertEqual(result.loc[3,'value_last_3_day_mean'],1)
        changed=source.copy();changed.loc[5,'value']=9999
        pd.testing.assert_frame_equal(result.iloc[:5],transformer.transform(changed).iloc[:5])

    def test_lstm_windows_use_past_only(self):
        values=np.arange(20).reshape(10,2)
        x,y=windows(values,3)
        np.testing.assert_array_equal(x[0],values[:3])
        np.testing.assert_array_equal(y[0],values[3])
        np.testing.assert_array_equal(x[-1],values[-4:-1])
        with self.assertRaises(ValueError):windows(values,10)


class FinancialTests(unittest.TestCase):
    def test_binary_grid_partial_dependence(self):
        class KnownResponse:
            def predict_proba(self,frame):
                p=(frame['a'].to_numpy()+frame['b'].to_numpy())/20
                return np.column_stack([1-p,p])
        source=pd.DataFrame({'a':[2,2,2],'b':[0,1,2]})
        before=source.copy()
        values=marginal_response(KnownResponse(),source,'a',[0,1])
        np.testing.assert_allclose(values,[.05,.1])
        pd.testing.assert_frame_equal(source,before)

    def test_behavior_windows_spend_cv_and_unique_suffixes(self):
        balance=pd.DataFrame({'Cust_ID':[1]*12,'Account_ID':[10]*12,'Period':range(1,13),
                              'Balance':[100]*12,'Payment':[50]*12,'Spend':list(range(10,130,10)),
                              'Delq1':[0]*11+[1],'Delq2':[0]*12,'Delq3':[0]*12})
        labels=pd.DataFrame({'Cust_ID':[1],'Account_ID':[10],'Credit_Limit':[200],'label':[1]})
        result=behavioral_features(balance,labels)
        self.assertTrue(result.columns.is_unique)
        self.assertAlmostEqual(result.loc[1,'Pay_Ratio_AVG_AMT_L3M'],.5)
        self.assertAlmostEqual(result.loc[1,'Delq1_Percent_L3M'],1/3)
        self.assertAlmostEqual(result.loc[1,'Delq1_Percent_L12M'],1/12)
        self.assertEqual(result.loc[1,'Balance_CV_AVG_ACC_L3M'],0)
        self.assertGreater(result.loc[1,'Spend_CV_AVG_ACC_L3M'],0)
        self.assertFalse(any('_L3M_L' in c for c in result))
        future=balance.iloc[[-1]].copy()
        future['Period']=13;future['Balance']=999999;future['Spend']=888888;future['Delq3']=1
        augmented=pd.concat([balance,future],ignore_index=True)
        pd.testing.assert_frame_equal(result,behavioral_features(augmented,labels))

    def test_behavior_join_rejects_fanout(self):
        with self.assertRaises(ValueError):behavioral_features(pd.DataFrame(),pd.DataFrame({'Account_ID':[1,1]}))

    def test_mysql_literals_are_not_executed(self):
        source="CREATE TABLE `t` (\n `a` varchar(99),\n `b` decimal(2,0)\n) ENGINE=InnoDB;\nINSERT INTO `t` VALUES ('__import__(something)', 3);"
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'data.sql';p.write_text(source,encoding='utf-8')
            result=read_mysql_dump(p,'t')
        self.assertEqual(result.loc[0,'a'],'__import__(something)')
        self.assertEqual(result.loc[0,'b'],'3')

    def test_positive_class_metric_names(self):
        result=classification_metrics([0,0,0,1,1],[.1,.2,.8,.7,.9])
        self.assertEqual(result['TP'],2)
        self.assertAlmostEqual(result['precision'],2/3)
        self.assertAlmostEqual(result['recall'],1)
        self.assertAlmostEqual(result['specificity'],2/3)
        with self.assertRaises(ValueError):classification_metrics([0,1],[0,1.1])

    def test_lp_integer_declarations_not_assumed(self):
        text='Maximize\n obj: 3 x1 + 5 x2\nSubject To\n r1: x1 + x2 <= 2\nBounds\n 0 <= x1 <= 1\n 0 <= x2 <= 1\nGenerals\n x1\nEnd\n'
        model=parse_linear_lp(text)
        np.testing.assert_array_equal(model[-1],[1,0])
        np.testing.assert_array_equal(model[2],[3,5])
        with self.assertRaises(ValueError):parse_linear_lp(text.replace('x1 + x2','x1 * x2'))

    def test_income_transform_fit_state_independent_of_test(self):
        train=pd.DataFrame({'age':[20,30,40,50],'income':[10,25,35,60],
                            'gender':[0,1,0,1],'edu':[1,2,1,2],'city_level':[1,1,2,2]})
        model=clone(IncomeFeatures()).fit(train)
        before=model.transform(train)
        changed=train.copy();changed['income']=100000
        model.transform(changed)
        pd.testing.assert_frame_equal(before,model.transform(train))


if __name__=='__main__':unittest.main()
