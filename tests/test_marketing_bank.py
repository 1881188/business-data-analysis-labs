"""Synthetic audience boundaries and bank snapshot/target contracts."""
from pathlib import Path
import sys,json,tempfile,unittest,zipfile
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.marketing_audience import age_band,legacy_band,age_formula,prepare as marketing_prepare,counts,audiences
from bda_labs.bank_products import prepare as bank_prepare,progress,select,aggregate,sql_checks,business_context,saved_path,path_summary
from bda_labs.workbook_reference import Sheet


def market():
    return pd.DataFrame([['A','Female',50,'Clothing',5,'Card',1,2023],['B','Female',49,'Cosmetics',1,'Alipay',1,2023],
                         ['C','Female',60,'Cosmetics',2,'Card',1,2023],['D','Male',70,'Clothing',4,'Card',1,2023],
                         ['E','Female',51,'Books',3,'Alipay',1,2023]],columns=['客户ID','性别','年龄','品类','数量','支付方式','订单月份','订单年份'])


def bank():
    return {'风险偏好说明表':pd.DataFrame({'风险编号':['S1','S2'],'风险说明':['低风险','中风险']}),
            '品类说明表':pd.DataFrame({'品类编号':['P1','P2'],'品类名称':['同名产品','同名产品']}),
            '学历说明表':pd.DataFrame({'学历编号':['E1'],'学历名称':['示例学历']}),
            '销售数据':pd.DataFrame([['S1','保值','区间A','P1','年龄组甲','女','信誉','E1',100,1,-5],
                                    ['S2','增值','区间A','P1','年龄组乙','男','服务','E1',300,5,20],
                                    ['S1','保值','区间B','P2','年龄组甲','女','信誉','E1',0,np.nan,0]],
                columns=['风险编号','购买目的','家庭年收入','品类编号','年龄','性别','选择本行的原因','学历编号','购买金额','期限','收益'])}


class MarketingTests(unittest.TestCase):
    def test_age_endpoints_and_underage_do_not_fall_into_oldest(self):
        ages=pd.Series([0,17,18,25,26,35,36,49,50,120])
        self.assertEqual(age_band(ages).tolist(),['18岁以下','18岁以下','18-25岁','18-25岁','26-35岁','26-35岁','36-49岁','36-49岁','50岁及以上','50岁及以上'])
        self.assertEqual(legacy_band(17),'50岁以上')

    def test_unknown_fractional_and_invalid_ages_rejected(self):
        for value in [None,np.nan,-1,121,25.5]:
            with self.assertRaises(ValueError):age_band(pd.Series([value]))

    def test_mutually_exclusive_counts_separate_customers_and_quantity(self):
        f=marketing_prepare(market());g=counts(f,'gender').set_index('gender')
        self.assertEqual(g.loc['Female','customers'],4);self.assertEqual(g.loc['Female','quantity'],11)
        self.assertEqual(g.customers.sum(),5);self.assertAlmostEqual(g.customer_share_in_scope.sum(),1)

    def test_target_intersection_does_not_include_men_or_younger_buyers(self):
        female,older,target,scopes=audiences(marketing_prepare(market()))
        self.assertEqual(len(female),4);self.assertEqual(len(older),3);self.assertEqual(set(target.customer_id),{'A','C'})
        self.assertEqual(scopes.customers.tolist(),[5,4,3,2]);self.assertEqual(scopes.iloc[-1].share_of_all_customers,.4)

    def test_duplicate_customer_requires_grain_review(self):
        raw=market();raw.loc[1,'客户ID']=' A '
        with self.assertRaises(ValueError):marketing_prepare(raw)

    def test_source_inputs_preserved_and_invalid_purchase_not_hidden(self):
        raw=market();before=raw.copy(deep=True);marketing_prepare(raw);pd.testing.assert_frame_equal(raw,before)
        for col,val in [('数量',0),('数量',1.5),('支付方式',None),('订单月份',13)]:
            bad=raw.copy();bad[col]=bad[col].astype('object');bad.loc[0,col]=val
            with self.assertRaises(ValueError):marketing_prepare(bad)

    def test_legacy_reference_text_and_wrong_row_are_exposed(self):
        self.assertEqual(legacy_band('标题'),'50岁以上')
        self.assertNotEqual(legacy_band(25),legacy_band(26))
        self.assertEqual(age_band(pd.Series([18])).iloc[0],'18-25岁')

    def test_empty_audience_counts_keep_unknown_shares(self):
        f=marketing_prepare(market());g=counts(f.iloc[:0],'payment')
        self.assertEqual(len(g),0);self.assertEqual(g.customers.sum(),0)


class BankTests(unittest.TestCase):
    def setUp(self):self.sheets=bank();self.f=bank_prepare(self.sheets)

    def test_target_full_month_and_time_progress_differ(self):
        p=progress(90000,100000,30,27)
        self.assertEqual(p['full_month_attainment'],.9);self.assertEqual(p['attainment_vs_time_prorated_target'],1)
        self.assertEqual(p['remaining_monthly_gap'],100);self.assertAlmostEqual(p['required_daily_amount_remaining'],100/3)

    def test_over_target_and_final_day_no_divide_by_zero(self):
        p=progress(110000,100000,31,31)
        self.assertEqual(p['remaining_monthly_gap'],0);self.assertIsNone(p['required_daily_amount_remaining'])
        p=progress(90000,100000,31,31);self.assertEqual(p['remaining_monthly_gap'],100)
        for target,day in [(0,1),(100000,0),(100000,32)]:
            with self.assertRaises(ValueError):progress(0,target,31,day)

    def test_source_business_text_drives_target_and_cutoff(self):
        description=Sheet('业务描述',{'B1':'销售目标为2500万。假设本月共31天，当前为本月29日。'}, {},{})
        parsed=business_context({'业务描述':description})
        self.assertEqual(parsed,{'monthly_target_cents':2500000000,'month_days':31,'elapsed_days':29})
        with self.assertRaises(ValueError):business_context({'业务描述':Sheet('业务描述',{'B1':'目标未知'},{},{})})

    def test_filter_keeps_whole_snapshot_denominator(self):
        chosen=select(self.f,{'risk_code':'S1'});g=aggregate(chosen,'category_code',int(self.f.amount_cents.sum()))
        self.assertEqual(len(chosen),2);self.assertAlmostEqual(g.share_of_selected_amount.sum(),1)
        self.assertAlmostEqual(g.share_of_whole_snapshot_amount.sum(),.25)
        p=progress(int(chosen.amount_cents.sum()),100000,30,15);self.assertEqual(p['monthly_target'],1000)

    def test_averages_are_record_means_and_term_has_observed_denominator(self):
        g=aggregate(self.f,['category_code','category'],int(self.f.amount_cents.sum())).set_index('category_code')
        self.assertEqual(g.loc['P1','records'],2);self.assertEqual(g.loc['P1','mean_purchase_per_record'],200)
        self.assertEqual(g.loc['P1','mean_term'],3);self.assertEqual(g.loc['P2','observed_terms'],0)
        self.assertTrue(pd.isna(g.loc['P2','mean_term']));self.assertEqual(len(g),2)

    def test_duplicate_dimensions_and_orphans_rejected(self):
        sheets=bank();sheets['风险偏好说明表']=pd.concat([sheets['风险偏好说明表'],sheets['风险偏好说明表'].iloc[[0]]])
        with self.assertRaises(ValueError):bank_prepare(sheets)
        sheets=bank();sheets['销售数据'].loc[0,'品类编号']='UNKNOWN'
        with self.assertRaises(ValueError):bank_prepare(sheets)

    def test_exact_duplicate_rows_are_preserved_without_transaction_id(self):
        sheets=bank();sheets['销售数据']=pd.concat([sheets['销售数据'],sheets['销售数据'].iloc[[0]]])
        f=bank_prepare(sheets);self.assertEqual(len(f),4);self.assertEqual(f.amount_cents.sum(),50000)

    def test_negative_yield_and_zero_purchase_preserved_source_unchanged(self):
        snapshots={key:value.copy(deep=True) for key,value in self.sheets.items()};f=bank_prepare(self.sheets)
        self.assertEqual(f.yield_cents.min(),-500);self.assertEqual(f.amount_cents.min(),0)
        for key,value in self.sheets.items():pd.testing.assert_frame_equal(value,snapshots[key])

    def test_empty_filter_and_independent_sql_means(self):
        chosen=select(self.f,{'category_code':'missing'});g=aggregate(chosen,'category_code',int(self.f.amount_cents.sum()))
        self.assertEqual(len(g),0);self.assertEqual(sql_checks(chosen),0);self.assertEqual(sql_checks(self.f),8)

    def test_saved_path_is_metadata_until_explicit_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'sample.pbix'
            state={'levels':[{'queryRefs':['销售数据.家庭年收入']},{'queryRefs':['销售数据.年龄']}],
                   'root':{'children':[{'isToggled':True,'identityValues':[{'Literal':{'Value':"'区间A'"}}],
                        'children':[{'isToggled':True,'identityValues':[{'Literal':{'Value':"'年龄组甲'"}}]}]}]}}
            layout={'sections':[{'visualContainers':[{'config':json.dumps({'singleVisual':{'visualType':'decompositionTreeVisual','expansionStates':[state]}})}]}]}
            with zipfile.ZipFile(p,'w') as z:z.writestr('Report/Layout',json.dumps(layout,ensure_ascii=False).encode('utf-16le'))
            path=saved_path(p);self.assertEqual(path,{'income':'区间A','age_band':'年龄组甲'})
            original=len(self.f);summary=path_summary(self.f,path)
            self.assertEqual(original,3);self.assertEqual(summary.records.tolist(),[3,2,1]);self.assertEqual(len(select(self.f,path)),1)

    def test_invalid_term_or_amount_not_silently_clipped(self):
        for column,value in [('期限',-1),('购买金额',-1),('收益',np.inf)]:
            sheets=bank();sheets['销售数据'][column]=sheets['销售数据'][column].astype(float);sheets['销售数据'].loc[0,column]=value
            with self.assertRaises(ValueError):bank_prepare(sheets)


if __name__=='__main__':unittest.main()
