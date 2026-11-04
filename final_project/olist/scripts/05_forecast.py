"""Chronological SARIMA experiment with untouched July holdout and baselines."""
from pathlib import Path
import json
import warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/tables'
MODELS = [((1,0,0),(1,0,0,7),'c'), ((1,1,0),(1,0,0,7),'n'),
          ((0,1,1),(0,1,1,7),'n'), ((1,0,1),(1,0,0,7),'c')]


def fit(y, order, seasonal, trend):
    with warnings.catch_warnings(record=True) as notes:
        warnings.simplefilter('always')
        model = SARIMAX(y/1000, order=order, seasonal_order=seasonal, trend=trend,
                        enforce_stationarity=True, enforce_invertibility=True)
        fitted = model.fit(disp=False, maxiter=150)
    return fitted, sorted(set(str(x.message) for x in notes))


def prediction(fitted, steps):
    pred = fitted.get_forecast(steps=steps)
    intervals = pred.conf_int(alpha=.05)*1000
    point = np.maximum(np.asarray(pred.predicted_mean)*1000, 0)
    lower = np.maximum(intervals.iloc[:,0].to_numpy(), 0)
    upper = np.maximum(intervals.iloc[:,1].to_numpy(), 0)
    return point, lower, upper


def metrics(actual, predicted):
    a,p = np.asarray(actual), np.asarray(predicted)
    return {'rmse_brl':float(np.sqrt(np.mean((a-p)**2))),
            'mae_brl':float(np.mean(np.abs(a-p))),
            'wape':float(np.sum(np.abs(a-p))/np.sum(a)) if np.sum(a)>0 else None}


def baseline(train, n, weeks=1):
    weekday_pattern = np.array(train.iloc[-7*weeks:]).reshape(weeks,7).mean(axis=0)
    return np.tile(weekday_pattern, int(np.ceil(n/7)))[:n]


def main():
    df = pd.read_csv(OUT/'forecast_daily_series.csv',parse_dates=['date']).set_index('date')
    y = df['ordered_value_brl'].asfreq('D')
    if y.isna().any() or (y<0).any():
        raise ValueError('Forecast series has invalid values')
    train, validation, test = y.loc[:'2018-05-31'],y.loc['2018-06-01':'2018-06-30'],y.loc['2018-07-01':]
    candidates = []
    for i,(order,seasonal,trend) in enumerate(MODELS):
        fitted, notes = fit(train,order,seasonal,trend)
        point,lo,hi = prediction(fitted,len(validation))
        result = {'candidate':i, 'order':str(order),'seasonal_order':str(seasonal), 'trend':trend,
                  'converged':bool(fitted.mle_retvals.get('converged',False)),
                  'aic':float(fitted.aic), 'warnings':' | '.join(notes), **metrics(validation,point)}
        candidates.append(result)
        print(json.dumps(result),flush=True)
    pd.DataFrame(candidates).to_csv(OUT/'forecast_validation_candidates.csv',index=False,encoding='utf-8-sig')
    viable = [x for x in candidates if x['converged'] and np.isfinite(x['rmse_brl'])]
    if not viable:
        raise RuntimeError('No SARIMA candidate converged; revise the model before using results.')
    chosen = min(viable,key=lambda x:x['rmse_brl'])
    order,seasonal,trend = MODELS[chosen['candidate']]
    pretest = y.loc[:'2018-06-30']
    fitted, notes = fit(pretest,order,seasonal,trend)
    if not fitted.mle_retvals.get('converged',False):
        raise RuntimeError('Selected model did not converge on pretest training data')
    point,lo,hi = prediction(fitted,len(test))
    holdout = pd.DataFrame({'date':test.index,'actual_brl':test.values, 'sarima_brl':point,
                            'lower95_brl':lo,'upper95_brl':hi,
                            'seasonal_naive_brl':baseline(pretest,len(test)),
                            'weekday_4week_mean_brl':baseline(pretest,len(test),4)})
    holdout.to_csv(OUT/'forecast_july_holdout.csv',index=False,encoding='utf-8-sig')
    scores=[]
    for name,col in [('SARIMA','sarima_brl'),('seasonal_naive','seasonal_naive_brl'),('weekday_4week_mean','weekday_4week_mean_brl')]:
        scores.append({'model':name, **metrics(test,holdout[col])})
    coverage = float(((test.values>=lo)&(test.values<=hi)).mean())
    pd.DataFrame(scores).to_csv(OUT/'forecast_holdout_metrics.csv',index=False,encoding='utf-8-sig')
    full,full_notes = fit(y,order,seasonal,trend)
    if not full.mle_retvals.get('converged',False):
        raise RuntimeError('Final model did not converge')
    p,l,u=prediction(full,14)
    future=pd.DataFrame({'date':pd.date_range('2018-08-01',periods=14),
                         'forecast_brl':p,'lower95_brl':l,'upper95_brl':u})
    future.to_csv(OUT/'forecast_august_simulation.csv',index=False,encoding='utf-8-sig')
    best_baseline = min(x['rmse_brl'] for x in scores if x['model']!='SARIMA')
    summary = {
        'category':json.loads((OUT/'analysis_summary.json').read_text(encoding='utf-8'))['forecast_category'],
        'target':'Daily ordered merchandise value BRL, positive-price items, all final order statuses',
        'category_selection':'Revenue ranking and >=90% nonzero days using data before 2018-06-01 only',
        'training_start':str(train.index.min().date()), 'training_end':str(train.index.max().date()),
        'validation_period':'2018-06-01 to 2018-06-30', 'untouched_test_period':'2018-07-01 to 2018-07-31',
        'selected_model':chosen, 'holdout_metrics':scores,
        'holdout_pi95_coverage':coverage,
        'rmse_improvement_vs_best_baseline':float(1-scores[0]['rmse_brl']/best_baseline),
        'warnings':notes+full_notes,
        'forecast_period':'2018-08-01 to 2018-08-14, historical simulation, not a prediction for 2026',
        'interval_method':'Model-based Gaussian observation prediction interval, lower bound clipped at 0; no parameter uncertainty',
        'limitations':[
            'Not a point-in-time database snapshot; retrospective exercise on published transactions.',
            'Ordered-value target includes later cancellations and differs from delivered-sales figures.',
            'Zero on dates with no recorded category item means zero observed transactions, not proof of no demand.',
            'Historical prices and one held-out month cannot establish future commercial performance.',
            'No promotion, holiday, inventory or external covariates; WAPE complements RMSE, MAPE omitted because of zero/low days.',
        ],
    }
    (OUT/'forecast_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'outputs'/'sarima_model_summary.txt').write_text(str(full.summary()),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
