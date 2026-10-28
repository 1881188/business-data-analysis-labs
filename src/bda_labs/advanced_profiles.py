"""PCA, sparse variable selection and multidimensional customer segmentation."""
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import linkage, cut_tree
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA, SparsePCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler, QuantileTransformer
from sklearn.tree import DecisionTreeClassifier, export_text
from statsmodels.multivariate.factor_rotation import rotate_factors
from threadpoolctl import threadpool_limits

from bda_labs.advanced_common import read_csv, specification, complete, bars
from bda_labs.common import context, plotting
from bda_labs.dimension_reduction import standardized_pca, principal_rotation


def rotated_basis(values, k):
    z = StandardScaler().fit_transform(values)
    pca = PCA(n_components=k, svd_solver='full').fit(z)
    basis, _ = rotate_factors(pca.components_.T, 'varimax', max_tries=10000)
    signs = np.where(basis[np.argmax(abs(basis), axis=0), np.arange(k)] < 0, -1, 1)
    basis *= signs
    if not np.allclose(basis.T @ basis, np.eye(k), atol=1e-9):
        raise AssertionError('Rotated eigenvectors lost orthonormality')
    return basis, pca


def sparse_selection(frame, k=2):
    """Select representatives by within/between squared-correlation ratio.

    The original helper reuses a global alpha and corrupts its correlation list.
    Here every feature is assigned to its strongest sparse component, then the
    smallest (1-R_within²)/(1-R_other²) representative is retained per component.
    """
    z = StandardScaler().fit_transform(frame)
    search = []
    chosen = None
    for alpha in np.arange(.1, 10, .2):
        model = SparsePCA(n_components=k, alpha=alpha, random_state=42).fit(z)
        counts = np.count_nonzero(model.components_, axis=0)
        valid = bool(np.all(counts == 1))
        search.append({'section': 'alpha_search', 'item': round(float(alpha), 3),
                       'nonzero': int(counts.sum()), 'disjoint_complete': valid})
        if valid:
            chosen = model
            break
    if chosen is None:
        raise ValueError('No alpha yields a complete disjoint variable grouping')
    scores = chosen.transform(z)
    correlations = np.corrcoef(z.T, scores.T)[:z.shape[1], z.shape[1]:] ** 2
    if not np.isfinite(correlations).all():
        raise ValueError('Undefined variable-component correlation')
    cluster = np.argmax(correlations, axis=1)
    reps = []
    for j in range(k):
        candidates = np.flatnonzero(cluster == j)
        if not len(candidates):
            raise ValueError('Empty variable cluster')
        ratios = (1 - correlations[candidates, j]) / np.maximum(
            1 - np.max(np.delete(correlations[candidates], j, axis=1), axis=1), 1e-15)
        idx = candidates[np.argmin(ratios)]
        reps.append(frame.columns[idx])
        search.append({'section': 'representative', 'item': frame.columns[idx],
                       'component': j + 1, 'value': float(min(ratios))})
    return reps, search


def run_small(ctx, lab, frame):
    features = frame.loc[:, 'X1':].astype(float)
    records = []
    if lab == 'M04':
        z, _, pca, scores = standardized_pca(features, 5)
        for i, (value, ratio) in enumerate(zip(pca.explained_variance_, pca.explained_variance_ratio_), 1):
            records.append({'section': 'PCA', 'item': f'PC{i}', 'eigenvalue': value, 'value': ratio})
        if not np.allclose(scores[:, 0], z @ pca.components_[0]):
            raise AssertionError('PCA scoring identity failed')
        one = PCA(n_components=1, svd_solver='full').fit(z)
        if not np.allclose(abs(one.transform(z)[:, 0]), abs(scores[:, 0])):
            raise AssertionError('One-component refit differs from the first component')
        bars(ctx, [r['item'] for r in records], [r['value'] for r in records], '贷款申请：主成分解释方差')
        return records, {'rows': len(frame), 'retained_components': 5, 'score_identity_checked': True}
    if lab == 'M05':
        reps, records = sparse_selection(features)
        bars(ctx, reps, [1] * len(reps), '稀疏主成分代表变量')
        return records, {'rows': len(frame), 'selected_features': reps,
                         'source_helper_bugs_corrected': ['global_best_alpha', 'correlation_list_mutation']}
    z, _, pca, weights, scores, rotation, norm = principal_rotation(features)
    tree = linkage(scores, method='ward', metric='euclidean')
    labels = cut_tree(tree, n_clusters=2).ravel()
    for i, ratio in enumerate(pca.explained_variance_ratio_, 1):
        records.append({'section': 'PCA', 'item': f'PC{i}', 'value': ratio})
    for i, name in enumerate(features.columns):
        records.append({'section': 'rotated_eigenvectors', 'item': name,
                        'factor1': weights[i, 0], 'factor2': weights[i, 1]})
    centers = features.groupby(labels).mean()
    for label, row in centers.iterrows():
        for name, value in row.items():
            records.append({'section': 'cluster_mean', 'item': name, 'cluster': int(label), 'value': value})
    if lab == 'M03':
        for alpha in [.5, *np.arange(.1, 1, .05), .65]:
            spca = SparsePCA(n_components=2, alpha=alpha, random_state=42).fit(z)
            records.append({'section': 'SparsePCA', 'item': round(float(alpha), 3),
                            'value': int(np.count_nonzero(spca.components_))})
        sparse_scores = spca.transform(z)
        if not np.isfinite(sparse_scores).all():
            raise AssertionError('Sparse scores are not finite')
    plt = plotting()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))
    from scipy.cluster.hierarchy import dendrogram
    axes[0].scatter(scores[:, 0], scores[:, 1], c=labels, cmap='viridis')
    axes[0].set(title='城市因子空间与分群', xlabel='factor 1', ylabel='factor 2')
    dendrogram(tree, ax=axes[1], no_labels=True)
    axes[1].set(title='Ward 层次聚类', ylabel='distance')
    fig.tight_layout(); fig.savefig(ctx.output / 'figure.png', dpi=150); plt.close(fig)
    return records, {'rows': len(frame), 'cluster_counts': pd.Series(labels).value_counts().sort_index().tolist(),
                     'rotation_gradient_norm': norm, 'retained_variance_ratio': float(pca.explained_variance_ratio_.sum())}


def run_segmentation(ctx, frame):
    frame = frame.copy()
    fill = ['interested_travel', 'computer_owner', 'HH_adults_num']
    frame[fill] = frame[fill].fillna({c: frame[c].mode().iloc[0] for c in fill})
    frame['HH_has_children'] = frame['HH_has_children'].map({'N': 0, 'Y': 1}).fillna(0)
    frame['interested_reading'] = frame['interested_reading'].replace('.', '0').astype(int)
    categories = ['interested_travel', 'computer_owner', 'marital', 'interested_golf',
                  'interested_gambling', 'HH_has_children', 'interested_reading']
    sample = frame[categories].sample(min(3000, len(frame)), random_state=12345)
    records = [{'section': 'chi_square', 'item': a + '/' + b,
                'value': stats.chi2_contingency(pd.crosstab(sample[a], sample[b]))[1]}
               for a, b in combinations(categories, 2)]
    frame['interested_reading'] = (frame['interested_reading'] > 1.5).astype(int)
    interest = ['interested_travel', 'computer_owner', 'interested_golf', 'interested_gambling', 'interested_reading']
    frame['interest'] = frame[interest].sum(axis=1) / len(interest)
    continuous = ['age', 'home_value', 'risk_score', 'interested_sport', 'HH_dieting',
                  'auto_member', 'HH_grandparent', 'HH_head_age', 'loan_ratio']
    ordered = ['marital', 'interest', 'HH_adults_num']
    values = frame[continuous + ordered].astype(float)
    if values.isna().any().any():
        raise ValueError('Unexpected missing segmentation features')
    transformed = values.copy()
    transformed[continuous] = QuantileTransformer(n_quantiles=100, output_distribution='normal',
                                                random_state=42).fit_transform(values[continuous])
    transformed[ordered] = StandardScaler().fit_transform(values[ordered])
    groups = {'household': (['age', 'marital', 'HH_adults_num', 'home_value', 'risk_score',
                            'HH_grandparent', 'HH_head_age', 'loan_ratio'], 4, 3),
              'hobby': (['HH_dieting', 'auto_member', 'interest', 'interested_sport'], 3, 2)}
    assignments = {}
    tree_texts = []
    for dimension, (cols, factors, chosen_k) in groups.items():
        basis, pca = rotated_basis(transformed[cols], factors)
        # Preserve the notebook's explicit score formula (unscaled transformed
        # variables times the rotated eigenvectors), then standardize the scores.
        scores = StandardScaler().fit_transform(transformed[cols].to_numpy() @ basis)
        for i, value in enumerate(pca.explained_variance_ratio_, 1):
            records.append({'section': dimension + '_PCA', 'item': i, 'value': value})
        for i, col in enumerate(cols):
            for j in range(factors):
                records.append({'section': dimension + '_rotation', 'item': col,
                                'component': j + 1, 'value': basis[i, j]})
        chosen = None
        for k in range(2, 12):
            model = KMeans(n_clusters=k, n_init=5, random_state=42).fit(scores)
            sil = silhouette_score(scores, model.labels_, sample_size=min(2000, len(scores)), random_state=42)
            records.append({'section': dimension + '_search', 'item': k, 'value': sil, 'SSD': model.inertia_})
            if k == chosen_k:
                chosen = model
        assignments[dimension] = chosen.labels_
        interpretation = DecisionTreeClassifier(random_state=42).fit(frame[cols], chosen.labels_)
        tree_texts.append(f'### {dimension}\n\n```text\n{export_text(interpretation, feature_names=cols, max_depth=2)}\n```')
    cross = pd.crosstab(assignments['household'], assignments['hobby'])
    for h in cross.index:
        for b in cross.columns:
            mask = (assignments['household'] == h) & (assignments['hobby'] == b)
            records.append({'section': 'cross_segments', 'item': f'{h}/{b}', 'value': int(mask.sum())})
            for col, value in frame.loc[mask, continuous + ordered].mean().items():
                records.append({'section': 'segment_profile', 'item': col, 'cluster': f'{h}/{b}', 'value': value})
    bars(ctx, [f'{h}/{b}' for h in cross.index for b in cross.columns], cross.to_numpy().ravel(), '家庭 × 爱好：交叉客群人数', 'customers')
    return records, {'rows': len(frame), 'cross_segment_total': int(cross.to_numpy().sum()),
                     'seed': 42, 'chosen_clusters': {'household': 3, 'hobby': 2}}, '\n\n'.join(tree_texts)


def main(lab, argv=None):
    ctx = context(lab, argv)
    frame = read_csv(ctx, specification(lab)['inputs'][0], skipinitialspace=True)
    with threadpool_limits(limits=1):
        if lab in {'M07', 'F03'}:
            records, details, notes = run_segmentation(ctx, frame)
        else:
            records, details = run_small(ctx, lab, frame)
            notes = '主成分符号、旋转因子顺序与聚类编号不构成业务等级。代表变量法修复教材辅助脚本的状态与索引错误。'
    complete(ctx, lab, records, details, notes=notes)
