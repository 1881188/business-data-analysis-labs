"""Restricted LP-file translation into SciPy linear, integer and quadratic models."""
import re

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp, minimize

from bda_labs.common import context
from bda_labs.advanced_common import specification, complete, bars


def linear_terms(expression, names):
    expression = expression.strip()
    tokens = re.findall(r'([+-]?)\s*(\d+(?:\.\d*)?)?\s*([A-Za-z]\w*)', expression)
    remainder = re.sub(r'([+-]?)\s*(\d+(?:\.\d*)?)?\s*([A-Za-z]\w*)', '', expression)
    if remainder.strip():
        raise ValueError('Unsupported linear expression')
    vector = np.zeros(len(names))
    for sign, number, name in tokens:
        vector[names.index(name)] += (-1 if sign == '-' else 1) * (float(number) if number else 1.)
    return vector


def parse_linear_lp(text):
    """Reject unknown syntax; ignore the source's prose before Maximize."""
    match = re.search(r'(?ims)^\s*(Maximize|Minimize)\s*\n\s*obj:\s*(.*?)\nSubject To\s*\n(.*?)\nBounds\s*\n(.*?)(?:\nGenerals\s*\n(.*?))?\nEnd\s*$', text)
    if not match:
        raise ValueError('Unsupported LP structure')
    sense, objective, constraints, bounds, generals = match.groups()
    names = sorted(set(re.findall(r'\bx\d+\b', objective)), key=lambda n: int(n[1:]))
    if not names:
        raise ValueError('No supported decision variables')
    c = linear_terms(objective, names)
    matrix = []; lower = []; upper = []
    for row in constraints.strip().splitlines():
        m = re.fullmatch(r'\s*\w+:\s*(.*?)\s*(<=|>=|=)\s*([-+]?\d+(?:\.\d*)?)\s*', row)
        if not m: raise ValueError('Unsupported constraint')
        expression, operator, rhs = m.groups(); rhs = float(rhs)
        matrix.append(linear_terms(expression, names))
        lower.append(rhs if operator in {'>=','='} else -np.inf)
        upper.append(rhs if operator in {'<=','='} else np.inf)
    lb = np.zeros(len(names)); ub = np.full(len(names), np.inf)
    for row in bounds.strip().splitlines():
        m = re.fullmatch(r'\s*([-+]?\d+(?:\.\d*)?)\s*<=\s*(\w+)(?:\s*<=\s*([-+]?\d+(?:\.\d*)?))?\s*', row)
        if not m: raise ValueError('Unsupported bound')
        low, name, high = m.groups(); i = names.index(name)
        lb[i] = float(low); ub[i] = float(high) if high else np.inf
    integer_names = (generals or '').split()
    if set(integer_names) - set(names): raise ValueError('Unknown integer variable')
    integrality = np.array([int(n in integer_names) for n in names])
    return sense.lower(), names, c, np.asarray(matrix), np.array(lower), np.array(upper), lb, ub, integrality


def main(lab, argv=None):
    ctx = context(lab, argv)
    text = ctx.source(specification(lab)['inputs'][0]).read_text(encoding='utf-8-sig')
    notes = ''
    if lab == 'M24':
        # Parse the exact quadratic grammar used by qp1.lp, with no eval.
        match = re.search(r'obj:\s*\[([\d.]+) a\^2 \+ ([\d.]+)?\s*b\^2 \+ a \* b\] /2 \+ a \+ b', text)
        if not match or not re.search(r'r1:\s*a \+ b = 1', text) or not all(f'0 <= {v}' in text for v in ['a','b']):
            raise ValueError('QP differs from the supported source expression')
        q = np.array([[float(match[1]), .5], [.5, float(match[2] or 1)]])
        c = np.ones(2)
        if np.linalg.eigvalsh(q).min() <= 0: raise ValueError('QP must be strictly convex')
        result = minimize(lambda x: .5*x@q@x+c@x, [.5,.5], jac=lambda x:q@x+c,
                          method='SLSQP', bounds=Bounds([0,0],[np.inf,np.inf]),
                          constraints=[LinearConstraint([[1,1]], [1],[1])], options={'ftol':1e-12})
        if not result.success: raise RuntimeError(result.message)
        # Solve the equality-constrained KKT system independently. For this
        # source its solution is interior, so the nonnegative bounds are inactive.
        kkt = np.block([[q, np.ones((2,1))],[np.ones((1,2)),np.zeros((1,1))]])
        exact = np.linalg.solve(kkt, np.r_[-c, 1])
        if (exact[:2] < 0).any() or not np.allclose(result.x, exact[:2], atol=1e-8):
            raise AssertionError('QP solution disagrees with independent KKT system')
        names=['a','b']; objective=float(result.fun)
        residual=float(abs(result.x.sum()-1)); x=result.x
        details={'solver':'scipy-SLSQP', 'objective':objective, 'constraint_residual':residual, 'independent_KKT_checked':True}
        notes='二次括号整体除以 2，交叉项对应 Hessian 的非对角元 0.5；同时求解独立 KKT 方程验证全局最优。'
    else:
        sense,names,c,a,lo,hi,lb,ub,integers=parse_linear_lp(text)
        direction=-1 if sense=='maximize' else 1
        if lab == 'M22':
            result=linprog(direction*c, A_ub=a, b_ub=hi, bounds=list(zip(lb,ub)), method='highs')
        else:
            result=milp(direction*c, integrality=integers, bounds=Bounds(lb,ub), constraints=LinearConstraint(a,lo,hi))
        if not result.success: raise RuntimeError(result.message)
        x=result.x; objective=float(c@x)
        residual=float(max(np.max(np.maximum(lo-a@x,0)),np.max(np.maximum(a@x-hi,0)),
                           np.max(np.maximum(lb-x,0)),np.max(np.maximum(x-ub,0))))
        if residual>1e-7 or np.any(abs(x[integers==1]-np.rint(x[integers==1]))>1e-7):
            raise AssertionError('Optimization solution violates source constraints')
        details={'solver':'scipy-HiGHS','objective':objective,'constraint_residual':residual,
                 'variables':len(names),'constraints':len(a),'integer_variables':int(integers.sum())}
        if lab == 'M23':
            all_binary=milp(direction*c,integrality=np.ones(len(c)),bounds=Bounds(lb,ub),constraints=LinearConstraint(a,lo,hi))
            if not all_binary.success: raise RuntimeError(all_binary.message)
            details['all_binary_comparison_objective']=float(c@all_binary.x)
            details['missing_integer_declarations']=[n for n,i in zip(names,integers) if not i]
            notes='教材 campaign.lp 漏写 x19 的 Generals 声明：主结果按文件保留该变量连续；另求所有变量整数的教学意图版本，并比较目标值。不擅自隐藏原模型差异。'
        else:
            # All 2D feasible boundary intersections form an independent LP check.
            planes=np.vstack([a, -np.eye(len(c))]); rhs=np.r_[hi,-lb]
            candidates=[]
            from itertools import combinations
            for i,j in combinations(range(len(planes)),2):
                pair=planes[[i,j]]
                if abs(np.linalg.det(pair))<1e-12: continue
                point=np.linalg.solve(pair,rhs[[i,j]])
                if np.all(planes@point<=rhs+1e-8): candidates.append(float(c@point))
            if not np.isclose(objective,max(candidates),atol=1e-8): raise AssertionError('LP vertex check differs')
            details['independent_vertex_check']=True
    rows=[{'section':'decision','item':n,'value':float(v)} for n,v in zip(names,x)]
    rows.append({'section':'objective','item':'optimal','value':objective})
    bars(ctx,names,x,'资源配置最优解','decision value')
    complete(ctx,lab,rows,details,notes=notes)
