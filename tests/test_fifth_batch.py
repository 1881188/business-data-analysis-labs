"""Response provenance, fold isolation, identifier exclusion and Ward geometry."""
from pathlib import Path
import sys,unittest
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from scipy.spatial.distance import pdist
from scipy.cluster.hierarchy import cut_tree
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bda_labs.linear_expenses import prepare,cross_validate,NUMERIC,EDUCATION
from bda_labs.bank_segments import channel_features,rotate_channels,cluster,CHANNELS
from bda_labs.city_hierarchy import ward_scores


def credit(n=100):
    rng=np.random.default_rng(63)
    data=pd.DataFrame({'id':np.arange(n),'Acc':1,'edad2':0,'gender':np.where(np.arange(n)%2,'Male','Female'),
                       'Age':rng.integers(20,60,n),'Income':rng.uniform(2,20,n),'Ownrent':rng.integers(0,2,n),
                       'Selfempl':rng.integers(0,2,n),'dist_home_val':rng.uniform(10,100,n),
                       'dist_avg_income':rng.uniform(2,10,n),'edu_class':np.resize(EDUCATION,n)})
    data['avg_exp']=np.exp(4+.03*data.Age+.02*data.Income+rng.normal(0,.15,n))
    return data


class RegressionTests(unittest.TestCase):
    def test_missing_response_is_excluded_and_source_is_unchanged(self):
        raw=credit();raw.loc[0,'avg_exp']=np.nan;raw.loc[0,'Age']=999;raw.loc[0,'edu_class']=None
        before=raw.copy(deep=True);primary,audit=prepare(raw);legacy,_=prepare(raw,True)
        self.assertEqual(len(primary),99);self.assertNotIn(0,primary.index);self.assertEqual(audit['excluded_rows'],1)
        self.assertEqual(len(legacy),100);self.assertEqual(legacy.loc[0,'avg_exp'],raw.avg_exp.mean())
        pd.testing.assert_frame_equal(raw,before)

    def test_invalid_age_and_missing_education_without_response_imputation(self):
        raw=credit();raw.loc[1,'Age']=999;raw.loc[2,'edu_class']=None
        primary,audit=prepare(raw);self.assertEqual(len(primary),98);self.assertEqual(audit['missing_response'],0)
        np.testing.assert_array_equal(primary.avg_exp,raw.loc[primary.index,'avg_exp'])

    def test_zero_target_duplicate_ids_and_unknown_categories_fail(self):
        for col,value in [('avg_exp',0),('id',1),('edu_class','unknown')]:
            raw=credit();raw.loc[0,col]=value
            with self.assertRaises(ValueError):prepare(raw)

    def test_changing_a_validation_folds_responses_cannot_change_its_predictions(self):
        frame,_=prepare(credit());_,first,_,_=cross_validate(frame)
        _,test=next(KFold(5,shuffle=True,random_state=20261023).split(frame))
        changed=frame.copy();changed.iloc[test,changed.columns.get_loc('avg_exp')]*=2
        changed['ln_avg_exp']=np.log(changed.avg_exp)
        _,second,_,_=cross_validate(changed)
        columns=[c for c in first if c not in ['source_index','fold','observed']]
        np.testing.assert_allclose(first.loc[test,columns],second.loc[test,columns],rtol=0,atol=1e-10)

    def test_cross_validation_has_one_prediction_per_record_on_the_original_scale(self):
        frame,_=prepare(credit());metrics,private,smearing,support=cross_validate(frame)
        self.assertEqual(private.source_index.nunique(),len(frame));self.assertEqual(len(metrics),6)
        np.testing.assert_allclose(metrics.mae_yuan,[abs(private.observed-private[name]).mean() for name in metrics.model])
        self.assertTrue(all(r['training_smearing']>=1-1e-12 for r in smearing))
        self.assertEqual(sum(r['validation_records_in_education_absent_from_training'] for r in support),0)


class BankTests(unittest.TestCase):
    def bank(self):
        rng=np.random.default_rng(42);shared=rng.poisson(10,180)
        x=pd.DataFrame({'CNT_TBM':rng.poisson(8,180),'CNT_ATM':shared+rng.poisson(2,180),
                        'CNT_POS':shared+rng.poisson(2,180),'CNT_CSC':rng.poisson(6,180)})
        return x.assign(ID=np.arange(len(x)),CNT_TOT=x.sum(axis=1))

    def test_id_and_redundant_total_never_enter_features(self):
        raw=self.bank();a=channel_features(raw);raw.ID+=100000
        b=channel_features(raw);pd.testing.assert_frame_equal(a,b);self.assertEqual(list(a),CHANNELS)

    def test_broken_total_duplicate_id_and_negative_counts_are_rejected(self):
        for col,value in [('CNT_TOT',-1),('ID',1),('CNT_TBM',-1)]:
            raw=self.bank();raw.loc[0,col]=value
            with self.assertRaises(ValueError):channel_features(raw)

    def test_three_direction_rotation_preserves_retained_euclidean_geometry(self):
        z,_,pc,w,scores=rotate_channels(channel_features(self.bank()))
        np.testing.assert_allclose(w.T@w,np.eye(3),atol=1e-10)
        np.testing.assert_allclose(pdist(scores),pdist(z@pc.components_.T),atol=1e-10)
        self.assertAlmostEqual(np.var(scores,axis=0,ddof=1).sum(),pc.explained_variance_.sum(),places=10)

    def test_kmeans_fixed_seed_and_canonical_centers_are_reproducible(self):
        rng=np.random.default_rng(7);x=np.vstack([rng.normal(loc=i*7,scale=.1,size=(20,3)) for i in range(3)])
        a,c,_,_=cluster(x);b,d,_,_=cluster(x)
        np.testing.assert_array_equal(a,b);np.testing.assert_allclose(c,d)
        self.assertTrue(np.all(np.diff(c[:,0])>0));self.assertEqual(len(np.unique(a)),3)

    def test_degenerate_or_nonfinite_scores_are_rejected(self):
        for x in [np.zeros((10,3)),np.full((10,3),np.nan),np.ones((10,4))]:
            with self.assertRaises(ValueError):cluster(x)


class WardTests(unittest.TestCase):
    def points(self):return np.array([[0.,0.],[.1,.2],[3.,2.],[3.4,2.8],[9.,-1.]])

    def test_square_distance_matrix_is_not_accepted_as_observations(self):
        with self.assertRaises(ValueError):ward_scores(np.eye(5))

    def test_rotation_and_translation_preserve_merge_nodes_and_heights(self):
        x=self.points();r=np.array([[.6,-.8],[.8,.6]])
        d,a=ward_scores(x);e,b=ward_scores(x@r+np.array([4.,-2.]))
        np.testing.assert_allclose(d,e,atol=1e-12);np.testing.assert_allclose(a,b,atol=1e-12)

    def test_scaling_changes_height_but_preserves_the_partition(self):
        _,a=ward_scores(self.points());_,b=ward_scores(self.points()*10)
        np.testing.assert_array_equal(a[:,[0,1,3]],b[:,[0,1,3]])
        np.testing.assert_allclose(a[:,2]*10,b[:,2]);np.testing.assert_array_equal(cut_tree(a,n_clusters=3),cut_tree(b,n_clusters=3))
        self.assertEqual(a[-1,3],5)


if __name__=='__main__':unittest.main()
