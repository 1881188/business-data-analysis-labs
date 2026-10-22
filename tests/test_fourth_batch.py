"""Numerical conventions, estimability and valid hypothesis-test observations."""
from pathlib import Path
import sys,unittest
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.dimension_reduction import standardized_pca,principal_rotation
from bda_labs.statistical_reference import numpy_tokens,check_printed,indexed_table_tokens
from bda_labs.anova_expenses import prepare_expenses,fit_observed_models,robust_observed_interaction
from bda_labs.contingency import analyze_table


class DimensionReductionTests(unittest.TestCase):
    def data(self):
        rng=np.random.default_rng(7)
        latent=rng.normal(size=(80,2))
        return pd.DataFrame(latent@np.array([[3.,2.,.4,.2],[.3,.6,2.,1.]])+rng.normal(scale=.1,size=(80,4)))

    def test_whitening_uses_sample_covariance_and_scaling_uses_population(self):
        z,_,_,scores=standardized_pca(self.data(),2,whiten=True)
        np.testing.assert_allclose(z.var(axis=0,ddof=0),1,atol=1e-12)
        np.testing.assert_allclose(np.cov(scores,rowvar=False),np.eye(2),atol=1e-12)
        np.testing.assert_allclose(scores.var(axis=0,ddof=0),79/80,atol=1e-12)

    def test_feature_unit_changes_do_not_change_standardized_pca_or_input(self):
        raw=self.data();original=raw.copy(deep=True)
        _,_,a,sa=standardized_pca(raw,2)
        changed=raw.copy();changed[0]*=1000
        _,_,b,sb=standardized_pca(changed,2)
        np.testing.assert_allclose(a.explained_variance_ratio_,b.explained_variance_ratio_,atol=1e-12)
        np.testing.assert_allclose(sa,sb,atol=1e-11)
        pd.testing.assert_frame_equal(raw,original)

    def test_constant_incomplete_and_zero_variance_whitening_rejected(self):
        for bad in [pd.DataFrame([[1,1],[2,1],[3,1]]),pd.DataFrame([[1,2],[2,np.nan],[3,4]])]:
            with self.assertRaises(ValueError):standardized_pca(bad)
        with self.assertRaises(ValueError):
            standardized_pca(pd.DataFrame({'a':[1,2,3,4],'b':[2,4,6,8]}),2,whiten=True)

    def test_rotation_preserves_projector_and_total_variance_but_not_score_independence(self):
        _,_,model,weights,scores,rotation,gradient=principal_rotation(self.data())
        np.testing.assert_allclose(weights.T@weights,np.eye(2),atol=1e-10)
        np.testing.assert_allclose(weights@weights.T,model.components_.T@model.components_,atol=1e-10)
        self.assertAlmostEqual(np.var(scores,axis=0,ddof=1).sum(),model.explained_variance_.sum(),places=10)
        self.assertGreater(abs(np.corrcoef(scores,rowvar=False)[0,1]),.01)
        self.assertLess(gradient,1e-7)

    def test_component_count_and_rank_limits_are_explicit(self):
        for n in [0,True,5,1.5]:
            with self.assertRaises(ValueError):standardized_pca(self.data(),n)
        with self.assertRaises(ValueError):
            principal_rotation(pd.DataFrame({'a':[1,2,3,4],'b':[2,4,6,8]}))


class ReferenceParsingTests(unittest.TestCase):
    def test_small_scientific_pvalue_is_checked_at_its_printed_scale(self):
        check_printed(2.691e-26,'2.69e-26')
        with self.assertRaises(AssertionError):check_printed(1e-15,'2.69e-26')
        with self.assertRaises(AssertionError):check_printed(2.70e-26,'2.69e-26')

    def test_truncated_array_requires_explicit_partial_coverage(self):
        with self.assertRaises(ValueError):numpy_tokens('array([[1,2], ...,[3,4]])')
        self.assertEqual(numpy_tokens('array([[1,2], ...,[3,4]])',True),['1','2','3','4'])
        for text in ['[1+1]','[float("nan")]','[__import__("os")]']:
            with self.assertRaises(ValueError):numpy_tokens(text)

    def test_printed_table_requires_all_expected_row_labels(self):
        self.assertEqual(indexed_table_tokens('  0  1\n0  .1 .2\n1 .3 .4',2,2),['.1','.2','.3','.4'])
        with self.assertRaises(ValueError):indexed_table_tokens('0 .1 .2\n2 .3 .4',2,2)


class AnovaSampleTests(unittest.TestCase):
    def test_blank_is_not_genuine_zero_and_source_is_preserved(self):
        raw=pd.DataFrame({'avg_exp':[' ',0,'10',None],'edu_class':[0,0,1,1],'gender':[0,1,0,1]})
        original=raw.copy(deep=True)
        primary,audit=prepare_expenses(raw)
        legacy,_=prepare_expenses(raw,'textbook_zero')
        self.assertEqual(primary.avg_exp.tolist(),[0,10])
        self.assertEqual(len(legacy),3)
        self.assertEqual(audit['blank_expenses'],1)
        self.assertEqual(audit['excluded_rows'],2)
        pd.testing.assert_frame_equal(raw,original)

    def test_unrecognized_or_negative_response_is_not_silently_replaced(self):
        for response in ['unknown',-1,np.inf]:
            with self.assertRaises(ValueError):
                prepare_expenses(pd.DataFrame({'avg_exp':[response],'edu_class':[0],'gender':[0]}))

    def test_empty_factor_cell_is_identified_and_only_observable_interaction_is_tested(self):
        rows=[]
        for edu in range(4):
            for gender in range(2):
                if (edu,gender)==(0,1):continue
                for noise in [-1,0,1]:
                    rows.append({'avg_exp':100+20*edu+7*gender+noise,'edu_class':str(edu),'gender':str(gender)})
        models,comparison,audit=fit_observed_models(pd.DataFrame(rows))
        self.assertEqual(audit,{'full_interaction_columns':8,'full_interaction_rank':7,'unestimable_dimensions':1})
        self.assertEqual(int(comparison.iloc[1].df_diff),2)
        self.assertAlmostEqual(comparison.iloc[1]['Pr(>F)'],1,places=10)
        self.assertEqual(models['observed_cells'].model.exog.shape[1],7)
        robust=robust_observed_interaction(models['additive'],models['observed_cells'])
        self.assertEqual(robust['df_numerator'],2)
        self.assertEqual(robust['df_denominator'],14)
        self.assertAlmostEqual(robust['pvalue'],1,places=10)

    def test_confounded_factors_do_not_produce_interpretable_alias_coefficients(self):
        frame=pd.DataFrame({'avg_exp':[1,2,3,4,5,6],'edu_class':['a']*3+['b']*3,'gender':['0']*3+['1']*3})
        with self.assertRaises(ValueError):fit_observed_models(frame)


class ContingencyTests(unittest.TestCase):
    def test_known_pearson_statistic_degrees_and_yates_difference(self):
        result,expected=analyze_table([[10,20],[20,10]])
        np.testing.assert_allclose(expected,np.full((2,2),15))
        self.assertAlmostEqual(result['pearson_chi2'],20/3)
        self.assertEqual(result['dof'],1)
        self.assertAlmostEqual(result['cramers_v'],1/3)
        self.assertAlmostEqual(result['yates_chi2'],5.4)

    def test_total_rows_and_invalid_pseudocounts_are_rejected(self):
        table=pd.DataFrame([[10,20,30],[20,10,30],[30,30,60]],index=['N','Y','All'],columns=[0,1,'All'])
        with self.assertRaises(ValueError):analyze_table(table)
        for values in [[[1.,2.5],[3,4]],[[0,0],[1,2]],[[1,-1],[2,3]],[[1,2]],[[1,np.nan],[3,4]]]:
            with self.subTest(values=values),self.assertRaises(ValueError):analyze_table(values)


if __name__=='__main__':unittest.main()
