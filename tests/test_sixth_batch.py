"""Business grain, spreadsheet boundaries and read-only source evidence."""
from pathlib import Path
import sys,unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.tabular_tools import many_to_one,money_minor,append_aligned
from bda_labs.excel_semantics import excel_round,approximate_lookup,exact_lookup,offset_address,workday,networkdays,tariff,frequency,subject_passes
from bda_labs.workbook_reference import Sheet
from bda_labs.data_models import prepare_mall,check_mall_formulas,mall_filter
from bda_labs.etl_tables import clean_orders,split_records,join_courses


class TableTests(unittest.TestCase):
    def test_dimension_join_preserves_repeated_fact_keys_and_amounts(self):
        fact=pd.DataFrame({'key':[1,1,2],'amount':[5,7,9]});before=fact.copy(deep=True)
        result=many_to_one(fact,pd.DataFrame({'key':[1,2],'label':['a','b']}),on='key')
        self.assertEqual(len(result),3);self.assertEqual(result.amount.sum(),21);pd.testing.assert_frame_equal(fact,before)

    def test_ambiguous_null_and_unmatched_keys_do_not_silently_merge(self):
        a=pd.DataFrame({'k':[1]})
        for b in [pd.DataFrame({'k':[1,1]}),pd.DataFrame({'k':[None]}),pd.DataFrame({'k':[2]})]:
            with self.assertRaises(ValueError):many_to_one(a,b,on='k')
        with self.assertRaises(ValueError):many_to_one(pd.DataFrame({'k':[None]}),pd.DataFrame({'k':[1]}),on='k')

    def test_decimal_parser_accepts_grouping_without_rounding_or_float_loss(self):
        np.testing.assert_array_equal(money_minor(['1,234.56','-0.01'],True),[123456,-1])
        self.assertEqual(money_minor(['90071992547409.91'])[0],9007199254740991)
        for value in ['1,23.45','1.234','NaN','',None,'1e3']:
            with self.assertRaises(ValueError):money_minor([value],True)

    def test_append_requires_explicit_mapping_and_rejects_name_collisions(self):
        a=pd.DataFrame({'store':['A1'],'sales':[200]});b=pd.DataFrame({'store':['A'],'amount':[100]})
        with self.assertRaises(ValueError):append_aligned([a,b])
        result=append_aligned([a,b],[{}, {'amount':'sales'}]);self.assertEqual(result.sales.sum(),300)
        self.assertEqual(result.store.tolist(),['A1','A'])
        with self.assertRaises(ValueError):append_aligned([pd.DataFrame({'amount':[1],'sales':[2]})],[{'amount':'sales'}])


class ExcelBoundaryTests(unittest.TestCase):
    def test_round_is_decimal_half_away_from_zero_including_negative_values(self):
        self.assertEqual(excel_round(1.25,1),1.3);self.assertEqual(excel_round(-1.25,1),-1.3)
        self.assertEqual(excel_round(125,-1),130);self.assertEqual(excel_round(21.3456,3),21.346)

    def test_lookup_lower_bounds_and_frequency_upper_bounds_differ_at_sixty(self):
        self.assertEqual(approximate_lookup([59.9,60,70,90],[0,60,70,90],['fail','pass','good','best']).tolist(),['fail','pass','good','best'])
        self.assertEqual(frequency([59.9,60,60.1],[60,70]).tolist(),[2,1,0])
        for bounds in [[0,60,60],[60,0,70]]:
            with self.assertRaises(ValueError):approximate_lookup([60],bounds,['a','b','c'])
        with self.assertRaises(ValueError):approximate_lookup([-1],[0],['a'])

    def test_exact_lookup_keeps_unmatched_distinct_from_real_zero_and_rejects_ambiguity(self):
        result=exact_lookup([1,2],[1],[0]);self.assertEqual(result.iloc[0],0);self.assertTrue(pd.isna(result.iloc[1]))
        with self.assertRaises(ValueError):exact_lookup([1],[1,1],['a','b'])
        with self.assertRaises(ValueError):exact_lookup([1],[1],[None])

    def test_holidays_endpoints_weekends_and_negative_workdays(self):
        holidays=['2017-10-01','2017-10-02','2017-10-03','2017-10-04','2017-10-05','2017-10-06','2017-10-07']
        self.assertEqual(str(workday('2017-09-30',10,holidays).date()),'2017-10-20')
        self.assertEqual(networkdays('2017-09-30','2017-10-20',holidays),10)
        self.assertEqual(networkdays('2024-01-08','2024-01-08'),1)
        self.assertEqual(str(workday('2024-01-08',-1).date()),'2024-01-05')
        self.assertEqual(networkdays('2024-01-08','2024-01-05'),-2)

    def test_whole_tier_and_progressive_tariffs_preserve_boundaries(self):
        self.assertEqual(tariff(120,[120,176],[2.07,4.07,6.07],'whole_tier'),248.40)
        self.assertEqual(tariff(121,[120,176],[2.07,4.07,6.07],'progressive'),252.47)
        self.assertEqual(tariff(121,[120,176],[2.07,4.07,6.07],'whole_tier'),492.47)
        self.assertEqual(tariff(0,[],[3.27],'progressive'),0)
        with self.assertRaises(ValueError):tariff(-1,[120],[2,3],'progressive')

    def test_offset_handles_negative_offsets_and_physical_sheet_bounds(self):
        self.assertEqual(offset_address('K18',-7,-1,7,2),'J11:K17')
        self.assertEqual(offset_address('A1',5,1,3,3),'B6:D8')
        with self.assertRaises(ValueError):offset_address('A1',-1,0)
        with self.assertRaises(ValueError):offset_address('XFD1',0,1)

    def test_three_failing_subjects_cannot_pass_due_to_a_text_evaluation_column(self):
        all_pass,any_pass=subject_passes([[10,20,30],[59,60,0],[60,60,60]])
        np.testing.assert_array_equal(all_pass,[False,False,True]);np.testing.assert_array_equal(any_pass,[False,True,True])
        with self.assertRaises(ValueError):subject_passes([[50,50,'未通过']])


class ModelTests(unittest.TestCase):
    def test_fact_price_and_same_row_amount_survive_a_different_dimension_price(self):
        date=pd.Timestamp('2018-01-01')
        fact=pd.DataFrame({'订单日期':[date],'商铺城市':['A市'],'产品编号':['a001'],'品牌名称':['品牌A'],
                           '产品类别':['家电'],'产品名称':['商品A'],'销售数量':[2],' 销售单价':[3],'销售额':[7]})
        tables={'产品销售数据表':fact,'产品信息表':pd.DataFrame({'产品编号':['A001'],'品牌名称':['品牌A'],'产品类别':['家电'],
                    '产品名称':['商品A'],'采购单价':[1],'销售单价':[4]}),
                '品牌':pd.DataFrame({'品牌名称':['品牌A'],'品牌编号':['A']}),'类别':pd.DataFrame({'产品类别':['家电'],'类别编号':['001']}),
                '商铺城市':pd.DataFrame({'商铺城市':['A市'],'城市编码':['1']}),'日期表':pd.DataFrame({'日期':[date],'年度':[2018],'月':[1]})}
        before=fact.copy(deep=True);result,audit=prepare_mall(tables)
        self.assertEqual(result.sales_minor.iloc[0],600);self.assertEqual(result.销售单价.iloc[0],3)
        self.assertEqual(audit['fact_dimension_price_differences'],1);self.assertEqual(audit['row_business_mismatches'],1)
        self.assertEqual(audit['source_cached_sales_minor'],700);pd.testing.assert_frame_equal(fact,before)

    def test_formula_cache_consistency_does_not_prove_the_business_row_is_correct(self):
        sheet=Sheet('demo',{'G2':2,'H2':3,'G3':5,'H3':7,'I2':35},{'I2':'=G3*H3'}, {})
        issues,audit=check_mall_formulas(sheet)
        self.assertEqual(audit['source_formula_cache_mismatches'],0);self.assertEqual(audit['wrong_row_references'],1)
        self.assertEqual(issues.intended_row_formula.iloc[0],'=G2*H2')
        with self.assertRaises(ValueError):check_mall_formulas(Sheet('bad',{}, {'I2':'=__import__("os")'}, {}))

    def test_filter_does_not_mutate_source_and_an_absent_period_is_empty(self):
        frame=pd.DataFrame({'年度':[2018,2019],'月':[1,2],'amount':[1,2]});before=frame.copy(deep=True)
        self.assertEqual(len(mall_filter(frame,2018,1)),1);self.assertTrue(mall_filter(frame,2020).empty)
        with self.assertRaises(ValueError):mall_filter(frame,month=13)
        pd.testing.assert_frame_equal(frame,before)


class ETLTests(unittest.TestCase):
    def test_split_bridge_has_no_additive_measures_and_mixed_units_remain_separate(self):
        raw=pd.DataFrame({'订单号':['A,B,C','D,E,F'],'收货地址':['福建省厦门市湖里区','四川省成都市成华区'],
                          '商品名称':['水','本子'],'数量':['8件','10本'],'客户姓名':['PeterPark','TonyStark']})
        columns,bridge=split_records(raw)
        self.assertEqual(len(columns),2);self.assertEqual(len(bridge),6)
        self.assertEqual(set(bridge),{'source_record','order_id'});self.assertEqual(columns.unit.tolist(),['件','本'])
        with self.assertRaises(ValueError):split_records(raw.assign(订单号=['A,A','D,E']))

    def test_cleaning_keeps_real_zero_and_duplicate_order_lines_and_records_excel_errors(self):
        raw=pd.DataFrame({'订单号':['A','A',None],'order_date':[pd.Timestamp('2022-05-01')]*2+[None],
                          'year':[2022,2022,None],'month':[5,5,None],'day':[1,1,None],
                          '实付金额':['0','2.50',None],'下单数量':['0','1',None],
                          '商品id':['#N/A',123,None],'ip地址':['#N/A','青岛市',None]})
        before=raw.copy(deep=True);result,audit,errors=clean_orders(raw)
        self.assertEqual(len(result),2);self.assertEqual(audit['genuine_zero_paid_details'],1)
        self.assertEqual(audit['excel_error_cells'],2);self.assertEqual(audit['duplicate_order_ids'],1)
        self.assertEqual(result.paid_minor.sum(),250);self.assertEqual(len(errors),2);pd.testing.assert_frame_equal(raw,before)

    def test_course_join_counts_enrollments_and_unique_students_separately(self):
        students=pd.DataFrame({'学号':[1,2],'系别':['a','b']});courses=pd.DataFrame({'课程号':['x','y'],'课程名':['X','Y']})
        records=pd.DataFrame({'学号':[1,1],'课程号':['x','y'],'成绩':[59,60]})
        _,summary,audit=join_courses(students,courses,records)
        self.assertEqual(audit['enrollment_records'],2);self.assertEqual(audit['enrolled_students'],1)
        self.assertEqual(audit['students_without_enrollments'],1);self.assertEqual(summary.passes.sum(),1)
        with self.assertRaises(ValueError):join_courses(students,courses,records.assign(课程号=['x','missing']))


if __name__=='__main__':unittest.main()
