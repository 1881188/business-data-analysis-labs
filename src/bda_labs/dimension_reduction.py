"""Standardized PCA and principal-component rotation using installed numerical libraries."""
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from statsmodels.multivariate.factor_rotation import rotate_factors


def standardized_pca(frame, n_components=2, whiten=False):
    values = np.asarray(frame, dtype=float)
    if values.ndim != 2 or min(values.shape) < 2 or not np.isfinite(values).all():
        raise ValueError('PCA requires a finite matrix with at least two rows and columns')
    if isinstance(n_components,bool) or not isinstance(n_components,(int,np.integer)) or not 1 <= n_components <= min(values.shape):
        raise ValueError('Invalid number of retained components')
    if np.any(np.ptp(values,axis=0) == 0):
        raise ValueError('Constant features cannot be standardized for this experiment')
    scaler = StandardScaler()
    z = scaler.fit_transform(values)
    model = PCA(n_components=n_components,whiten=whiten,svd_solver='full').fit(z)
    if whiten and np.any(model.explained_variance_ <= np.finfo(float).eps*model.explained_variance_[0]*max(values.shape)):
        raise ValueError('Whitening requires nonzero retained variance')
    signs = np.where(model.components_[np.arange(n_components),np.argmax(abs(model.components_),axis=1)] < 0,-1,1)
    model.components_ *= signs[:,None]
    scores = model.transform(z)
    return z, scaler, model, scores


def principal_rotation(frame):
    z, scaler, model, _ = standardized_pca(frame,2)
    if model.explained_variance_[-1] <= np.finfo(float).eps*model.explained_variance_[0]*max(z.shape):
        raise ValueError('Two nonzero principal directions are required for this rotation')
    basis = model.components_.T
    weights, rotation = rotate_factors(basis,'varimax',tol=1e-10,max_tries=10000)
    signs = np.where(weights[np.argmax(abs(weights),axis=0),np.arange(2)] < 0,-1,1)
    weights *= signs
    rotation *= signs
    order = np.argsort(np.var(z@weights,axis=0,ddof=1))[::-1]
    weights, rotation = weights[:,order], rotation[:,order]
    scores = z@weights
    if not np.allclose(rotation.T@rotation,np.eye(2),atol=1e-10,rtol=0):
        raise AssertionError('Rotation is not orthogonal')
    if not np.allclose(basis@basis.T,weights@weights.T,atol=1e-10,rtol=0):
        raise AssertionError('Rotation changed the retained subspace')
    if not np.isclose(np.var(scores,axis=0,ddof=1).sum(),model.explained_variance_.sum(),rtol=1e-12):
        raise AssertionError('Rotation changed total retained variance')
    gradient = 4*(weights**3 - weights*np.mean(weights**2,axis=0))
    g = basis.T@gradient
    tangent = g-rotation@((rotation.T@g+g.T@rotation)/2)
    if np.linalg.norm(tangent) > 1e-7:
        raise AssertionError('Varimax did not reach a stationary solution')
    return z, scaler, model, weights, scores, rotation, float(np.linalg.norm(tangent))
