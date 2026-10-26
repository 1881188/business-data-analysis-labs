"""Calendar/window endpoints, tied balances and chronological forecasting boundaries."""
from pathlib import Path
from contextlib import closing
import sys,json,sqlite3,tempfile,unittest,zipfile
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.channel_attribution import prepare as applications,analyze as channels
from bda_labs.sql_profiles import card_base,historical_features,sql_profile_checks
from bda_labs.effect_forecasting import regular_series,predict,seasonal_naive,error_metrics,evaluate,decompose
from bda_labs.closure_tools import chart_caches
from bda_labs.workbook_reference import Sheet


def application_data(rows):return applications(pd.DataFrame(rows,columns=['申请书编号（主键）','申请日期','申请渠道']))


class ChannelTests(unittest.TestCase):
    def test_decline_signs_and_offsetting_channel(self):
        f=application_data([['A','2021-04-01','柜台'],['B','2021-04-02','柜台'],['C','2021-04-03','APP'],['D','2021-05-01','APP'],['E','2021-05-02','自助']])
        m,c,s,g=channels(f);g=g.set_index('channel')
        self.assertEqual(g.delta.sum(),-1);self.assertEqual(g.loc['柜台','signed_share_of_net_change'],2)
        self.assertEqual(g.loc['自助','signed_share_of_net_change'],-1)
        self.assertAlmostEqual(g.growth_contribution_pp.sum(),-100/3)

    def test_no_net_change_is_unknown_share_not_zero(self):
        f=application_data([['A','2021-04-01','柜台'],['B','2021-05-01','APP']]);g=channels(f)[3]
        self.assertEqual(g.delta.sum(),0);self.assertTrue(g.signed_share_of_net_change.isna().all())

    def test_missing_month_unknown_absent_channel_observed_month_zero(self):
        f=application_data([['A','2021-03-01','柜台'],['B','2021-05-01','APP']]);m,c,s,g=channels(f)
        self.assertTrue(pd.isna(m.set_index('period').loc[pd.Period('2021-04'),'applications']))
        self.assertEqual(c.set_index('period').loc[pd.Period('2021-05'),'柜台'],0)
        self.assertTrue(g.delta.isna().all())

    def test_duplicate_application_and_bad_dates_rejected(self):
        with self.assertRaises(ValueError):application_data([['A','2021-04-01','柜台'],[' A ','2021-05-01','APP']])
        with self.assertRaises(ValueError):application_data([['A',None,'柜台']])
        with self.assertRaises(ValueError):application_data([['A','2021-04-01 12:00','柜台']])

    def test_source_preserved_and_all_channel_counts_conserve(self):
        raw=pd.DataFrame([['A','2021-04-01','柜台'],['B','2021-05-01','APP']],columns=['申请书编号（主键）','申请日期','申请渠道']);before=raw.copy(deep=True)
        f=applications(raw);pd.testing.assert_frame_equal(raw,before);m,c,s,g=channels(f)
        self.assertEqual(m.applications.sum(),2);self.assertEqual(c.drop(columns='period').to_numpy().sum(),2)
        self.assertTrue(np.allclose(s.drop(columns='period').sum(axis=1),1))

    def test_nonconsecutive_comparison_and_empty_input_rejected(self):
        f=application_data([['A','2021-04-01','柜台']])
        with self.assertRaises(ValueError):channels(f,'2021-03','2021-05')
        with self.assertRaises(ValueError):channels(f.iloc[:0])


def profile_case():
    card=pd.DataFrame({'card_id':[1,2],'disp_id':[11,12],'issued':['2020-03-01']*2,'type':['示例卡']*2})
    disp=pd.DataFrame({'disp_id':[11,12],'client_id':[21,22],'account_id':[31,32]})
    clients=pd.DataFrame({'client_id':[21,22],'sex':['女','男'],'birth_date':['2000-02-29','1990-03-02']})
    base=card_base(card,disp,clients)
    days=[0,1,1,179,180,364,365,400];end=pd.Timestamp('2020-03-01')
    t=pd.DataFrame({'trans_id':range(1,9),'account_id':[31]*8,'date':[(end-pd.Timedelta(days=d)).strftime('%Y-%m-%d') for d in days],
                    'type':['贷','借','贷','借','贷','借','贷','借'],'amount_cents':[100]*8,'balance_cents':[999,1000,3000,2000,3000,4000,5000,6000]})
    return base,t


class ProfileTests(unittest.TestCase):
    def test_age_at_issue_anniversary_not_runtime_day(self):
        base,t=profile_case();self.assertEqual(base.age_at_issue.tolist(),[20,29])
        self.assertNotEqual(base.loc[0,'legacy_age_days_over_365'],20)

    def test_strict_window_endpoints_and_same_day_exclusion(self):
        base,t=profile_case();f=historical_features(base,t).set_index('card_id')
        self.assertEqual(f.loc[1,'w180_records'],3);self.assertEqual(f.loc[1,'w365_records'],5)
        self.assertEqual(f.loc[1,'w180_debit_cents'],200);self.assertEqual(f.loc[1,'w180_credit_cents'],100)

    def test_latest_day_ties_mean_range_without_arbitrary_order(self):
        base,t=profile_case();f=historical_features(base,t).set_index('card_id')
        self.assertEqual(f.loc[1,'last_days'],1);self.assertEqual(f.loc[1,'last_day_rows'],2)
        self.assertEqual(f.loc[1,'last_day_balance_mean_cents'],2000)
        self.assertEqual(f.loc[1,'last_day_balance_min_cents'],1000);self.assertEqual(f.loc[1,'last_day_balance_max_cents'],3000)

    def test_no_history_zero_counts_unknown_balances(self):
        base,t=profile_case();f=historical_features(base,t).set_index('card_id')
        self.assertEqual(f.loc[2,'w365_records'],0);self.assertEqual(f.loc[2,'w365_credit_cents'],0)
        self.assertTrue(pd.isna(f.loc[2,'last_days']));self.assertTrue(pd.isna(f.loc[2,'w365_credit_over_debit']))

    def test_old_history_for_last_date_not_discarded_by_window(self):
        base,t=profile_case();f=historical_features(base,t.iloc[[-1]]).set_index('card_id')
        self.assertEqual(f.loc[1,'last_days'],400);self.assertEqual(f.loc[1,'w365_records'],0)

    def test_independent_sql_reconciles_nulls_windows_and_ties(self):
        base,t=profile_case();f=historical_features(base,t)
        with closing(sqlite3.connect(':memory:')) as conn:
            b=base.copy();b['issued']=b.issued.dt.strftime('%Y-%m-%d');b['birth_date']=b.birth_date.dt.strftime('%Y-%m-%d')
            b.to_sql('card_base',conn,index=False);t.to_sql('trans',conn,index=False)
            queries,n=sql_profile_checks(conn,f);self.assertEqual(n,26);self.assertEqual(len(queries),3)

    def test_duplicate_transactions_unknown_type_and_orphan_key_rejected(self):
        base,t=profile_case()
        with self.assertRaises(ValueError):historical_features(base,pd.concat([t,t.iloc[[0]]]))
        bad=t.copy();bad.loc[0,'type']='unknown'
        with self.assertRaises(ValueError):historical_features(base,bad)
        card=pd.DataFrame({'card_id':[1],'disp_id':[999],'issued':['2020-01-01'],'type':['例']})
        with self.assertRaises(ValueError):card_base(card,pd.DataFrame({'disp_id':[11],'client_id':[21],'account_id':[31]}),pd.DataFrame({'client_id':[21],'sex':['女'],'birth_date':['2000-01-01']}))

    def test_input_frames_preserved(self):
        base,t=profile_case();b=base.copy(deep=True);raw=t.copy(deep=True);historical_features(base,t)
        pd.testing.assert_frame_equal(base,b);pd.testing.assert_frame_equal(t,raw)


class ForecastTests(unittest.TestCase):
    def test_regular_dates_do_not_silently_fill_or_sort(self):
        for dates in [['2020-01-01','2020-01-03'],['2020-01-01','2020-01-01'],['2020-01-02','2020-01-01']]:
            with self.assertRaises(ValueError):regular_series(dates,[1,2],'D')

    def test_linear_plus_seasonal_recovers_known_future(self):
        t=np.arange(42);signal=100+.3*t+np.array([0,1,3,-2,4,2,-1])[t%7]
        p=predict(signal[:28],14,7)
        np.testing.assert_allclose(p.prediction,signal[28:],rtol=1e-11,atol=1e-10)

    def test_holdout_future_changes_do_not_change_training_predictions(self):
        dates=pd.date_range('2020-01-01',periods=35,freq='D');s=pd.Series(100+np.arange(35)+np.sin(np.arange(35)),index=dates)
        a=evaluate(s,7,7)[1];changed=s.copy();changed.iloc[-7:]+=1000;b=evaluate(changed,7,7)[1]
        np.testing.assert_allclose(a.prediction,b.prediction);self.assertFalse(np.allclose(a.actual,b.actual))

    def test_log_model_back_transform_and_positive_intervals(self):
        t=np.arange(35);s=np.exp(4+.01*t+.1*(t%7));p=predict(s[:28],7,7,log=True)
        np.testing.assert_allclose(p.prediction,s[28:],rtol=1e-10);self.assertTrue(p.lower_95_model.gt(0).all())

    def test_short_history_and_nonpositive_log_rejected(self):
        with self.assertRaises(ValueError):predict(np.ones(13),7,7)
        with self.assertRaises(ValueError):predict(np.arange(28),7,7,log=True)
        with self.assertRaises(ValueError):predict(np.ones(28),0,7)

    def test_seasonal_naive_repeats_last_cycle(self):
        self.assertEqual(seasonal_naive([1,2,3,4],7,3).tolist(),[2,3,4,2,3,4,2])

    def test_metrics_zero_actual_and_zero_training_scale_remain_unknown(self):
        m=error_metrics([0,1],[1,2],np.ones(14),7)
        self.assertIsNone(m['mape']);self.assertIsNone(m['mase_seasonal']);self.assertEqual(m['mae'],1)

    def test_mase_uses_only_training_scale_and_preserves_units(self):
        m=error_metrics([10,12],[12,10],np.arange(21),7)
        self.assertAlmostEqual(m['mase_seasonal'],2/7);self.assertEqual(m['rmse'],2)

    def test_centered_decomposition_edges_unknown_reconstruction(self):
        s=pd.Series(100+np.arange(35)+np.sin(np.arange(35)),index=pd.date_range('2020-01-01',periods=35))
        f=decompose(s,7);self.assertTrue(pd.isna(f.trend.iloc[0]));self.assertTrue(pd.isna(f.residual.iloc[-1]))
        g=f.dropna();np.testing.assert_allclose(g.trend+g.seasonal+g.residual,g.observed_scale)

    def test_prediction_bounds_and_chronological_cutoff(self):
        s=pd.Series(100+np.arange(35)+np.sin(np.arange(35)),index=pd.date_range('2020-01-01',periods=35));m,p=evaluate(s,7,7)
        self.assertEqual(set(m.train_end),{'2020-01-28'});self.assertEqual(set(m.training_observations),{28})
        valid=p.dropna(subset=['lower_95_model']);self.assertTrue(valid.lower_95_model.le(valid.prediction).all());self.assertTrue(valid.upper_95_model.ge(valid.prediction).all())


class SparseChartTests(unittest.TestCase):
    def check(self,points,values):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'chart.xlsx';xml='<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:ser><c:val><c:numRef><c:f>Sheet1!$A$1:$A$3</c:f><c:numCache>'+''.join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i,v in points)+'</c:numCache></c:numRef></c:val></c:ser></c:chartSpace>'
            with zipfile.ZipFile(p,'w') as z:z.writestr('xl/charts/chart1.xml',xml)
            return chart_caches(p,{'Sheet1':Sheet('Sheet1',values,{},{})},['test'])

    def test_sparse_cache_retains_positions(self):
        f=self.check([(0,10),(2,30)],{'A1':10,'A3':30});self.assertEqual(f.cached_numeric_points.item(),2);self.assertEqual(f.sparse_positions.item(),1)

    def test_point_at_missing_cell_rejected(self):
        with self.assertRaises(AssertionError):self.check([(1,20)],{'A1':10,'A3':30})

    def test_wrong_numeric_cache_rejected(self):
        with self.assertRaises(AssertionError):self.check([(2,31)],{'A1':10,'A3':30})


if __name__=='__main__':unittest.main()
