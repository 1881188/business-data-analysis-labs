"""Explicit marginal response, including the two-point categorical-grid case."""
import numpy as np


def marginal_response(model,frame,column,grid):
    """Average P(y=1) after setting one feature to each grid value.

    This is the brute-force partial-dependence definition; it does not use the
    target labels or expose individual predictions. Correlated-feature caveats
    remain: the substitutions need not be realistic joint observations.
    """
    grid=np.asarray(grid)
    if column not in frame or not len(frame) or grid.ndim!=1 or not len(grid):
        raise ValueError('Nonempty feature frame and one-dimensional grid required')
    values=[]
    for value in grid:
        counterfactual=frame.copy();counterfactual[column]=value
        probability=np.asarray(model.predict_proba(counterfactual))
        if probability.shape!=(len(frame),2) or not np.isfinite(probability).all():
            raise ValueError('Binary finite probabilities required')
        values.append(float(probability[:,1].mean()))
    return np.asarray(values)
