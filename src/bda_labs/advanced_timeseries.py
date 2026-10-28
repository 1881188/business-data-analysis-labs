"""Chronological Prophet, SARIMA/ARIMA and two-output stacked-LSTM examples."""
from itertools import product
import importlib.metadata
import os
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import MinMaxScaler
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import adfuller,acf,pacf
from statsmodels.stats.stattools import durbin_watson
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.seasonal import seasonal_decompose
from threadpoolctl import threadpool_limits

from bda_labs.common import context, plotting
from bda_labs.advanced_common import read_csv, specification, complete, bars


def windows(values, steps=60):
    values=np.asarray(values,dtype=float)
    if values.ndim!=2 or steps<1 or len(values)<=steps or not np.isfinite(values).all():
        raise ValueError('Finite 2D series longer than the positive lookback required')
    return np.stack([values[i-steps:i] for i in range(steps,len(values))]),values[steps:].copy()


def arima_search(series, seasonal=False):
    results=[];best=None
    for order in product(range(2),repeat=3):
        seasons=list(product(range(2),repeat=3)) if seasonal else [(0,0,0)]
        for season in seasons:
            try:
                with warnings.catch_warnings(record=True) as caught:
                    model=(SARIMAX(series,order=order,seasonal_order=(*season,12),
                                   enforce_stationarity=True,enforce_invertibility=True).fit(disp=False,maxiter=200)
                           if seasonal else ARIMA(series,order=order).fit())
                converged=bool(model.mle_retvals.get('converged',True))
                results.append({'section':'search','item':str(order),'season':str(season),'AIC':float(model.aic),
                                'converged':converged,'warnings':len(caught)})
                if converged and np.isfinite(model.aic) and (best is None or model.aic<best.aic):best=model
            except (ValueError,np.linalg.LinAlgError) as error:
                results.append({'section':'search','item':str(order),'season':str(season),'error_type':type(error).__name__})
    if best is None:raise RuntimeError('No converged ARIMA candidate')
    return best,results


def main(lab,argv=None):
    ctx=context(lab,argv);data=read_csv(ctx,specification(lab)['inputs'][0])
    records=[];details={};notes=''
    with threadpool_limits(limits=1):
        if lab=='M18':
            from prophet import Prophet
            series=data.rename(columns={'DATE':'ds','AIR':'y'});series['ds']=pd.to_datetime(series['ds'])
            series=series.sort_values('ds').reset_index(drop=True)
            scores={}
            for mode in ['additive','multiplicative']:
                train=series.iloc[:-12]
                kwargs={'growth':'linear','seasonality_mode':mode,'interval_width':.95,
                        'weekly_seasonality':False,'daily_seasonality':False,'yearly_seasonality':'auto'}
                model=Prophet(**kwargs)
                if mode=='multiplicative':model.add_country_holidays('China')
                model.fit(train)
                predicted=model.predict(series.iloc[-12:][['ds']])
                mae=float(mean_absolute_error(series.iloc[-12:]['y'],predicted['yhat']));scores[mode]=mae
                records.append({'section':'holdout','item':mode,'MAE':mae,'rows':12})
                # Separate full-data refit for the source's 36-month projection.
                full=Prophet(**kwargs)
                if mode=='multiplicative':full.add_country_holidays('China')
                full.fit(series)
                future=full.make_future_dataframe(periods=36,freq='MS')
                forecast=full.predict(future)
                for _,r in forecast.tail(36).iterrows():
                    records.append({'section':'future_'+mode,'item':str(r['ds'].date()),'value':r['yhat'],
                                    'lower95':r['yhat_lower'],'upper95':r['yhat_upper'],
                                    'trend':r['trend'],'yearly':r.get('yearly',0.),'holidays':r.get('holidays',0.)})
                details[mode+'_changepoints']=len(full.changepoints)
            bars(ctx,list(scores),list(scores.values()),'Prophet：最后 12 个月留出 MAE','passengers')
            details.update({'rows':len(series),'forecast_months':36,'prophet_version':importlib.metadata.version('prophet')})
            notes='fbprophet 迁移到 Prophet，保留加法趋势与中国节假日乘法模型。月度数据不应过度解释日级节假日系数；36 月未来预测无真实标签，另留最后 12 月报告泛化误差。'
        elif lab=='M19':
            dates=pd.to_datetime(data['Year_Month'],format='%Y-%b')
            series=pd.Series(data['Number_of_Sold'].to_numpy(dtype=float),index=pd.DatetimeIndex(dates,freq='MS'))
            if (series<=0).any():raise ValueError('Multiplicative/log series requires positivity')
            decomposition=seasonal_decompose(series,model='multiplicative',period=12)
            records += [{'section':'decomposition','item':m,'value':float(decomposition.seasonal[decomposition.seasonal.index.month==m].mean())} for m in range(1,13)]
            train=np.log(series.iloc[:-12]);test=series.iloc[-12:]
            differenced=train.diff().dropna()
            av,pv=acf(differenced,nlags=30),pacf(differenced,nlags=30)
            records += [{'section':'log_difference_correlation','item':i,'ACF':float(av[i]),'PACF':float(pv[i])} for i in range(31)]
            best,search=arima_search(train,True);records+=search
            holdout=np.exp(best.get_forecast(steps=12).predicted_mean)
            details.update({'holdout_MAE':float(mean_absolute_error(test,holdout)),
                            'seasonal_naive_MAE':float(mean_absolute_error(test,series.iloc[-24:-12].values)),
                            'selected_order':list(best.model.order),'selected_seasonal_order':list(best.model.seasonal_order)})
            final=SARIMAX(np.log(series),order=best.model.order,seasonal_order=best.model.seasonal_order,
                          enforce_stationarity=True,enforce_invertibility=True).fit(disp=False,maxiter=300)
            if not final.mle_retvals.get('converged',True):raise RuntimeError('Final SARIMA did not converge')
            projection=final.get_forecast(steps=36);interval=np.exp(projection.conf_int(alpha=.05))
            for i,(date,value) in enumerate(np.exp(projection.predicted_mean).items()):
                records.append({'section':'future','item':str(date.date()),'value':value,
                                'lower95':interval.iloc[i,0],'upper95':interval.iloc[i,1]})
            diagnostic=acorr_ljungbox(best.resid,lags=[12],return_df=True)
            details['ljung_box_p_12']=float(diagnostic['lb_pvalue'].iloc[0])
            bars(ctx,['SARIMA','seasonal naive'],[details['holdout_MAE'],details['seasonal_naive_MAE']], '拖拉机销量：留出 MAE','units')
            notes='保留 64 组季节/非季节参数网格，只按训练段 AIC 选择收敛模型。修复原未来索引从最后观测月重复开始的问题。对数回变换为中位数预测；区间是模型假设下的预测区间。'
        elif lab=='M21':
            series_names=['AR1_a','MA1_a','ARMA_11_b','ARIMA_110'];orders=[(1,0,0),(0,0,1),(1,0,1),(1,1,0)]
            errors=[]
            for name,order in zip(series_names,orders):
                series=data[name].astype(float);model=ARIMA(series.iloc[:-20],order=order).fit()
                error=float(mean_absolute_error(series.iloc[-20:],model.forecast(20)));errors.append(error)
                full=ARIMA(series,order=order).fit()
                for domain,values in [('series',series),('residual',full.resid)]:
                    av,pv=acf(values,nlags=20),pacf(values,nlags=20)
                    records += [{'section':name+'_'+domain+'_correlation','item':i,'ACF':float(av[i]),'PACF':float(pv[i])} for i in range(21)]
                records.append({'section':name,'item':'diagnostics','MAE_holdout20':error,'AIC':full.aic,
                                'Durbin_Watson':float(durbin_watson(full.resid)),
                                'normality_p':float(stats.normaltest(full.resid).pvalue),
                                'ADF_p':float(adfuller(series)[1]),'diff1_ADF_p':float(adfuller(series.diff().dropna())[1]),
                                'Ljung_Box_p20':float(acorr_ljungbox(full.resid,lags=[20],return_df=True)['lb_pvalue'].iloc[0])})
                for i,value in enumerate(full.forecast(6),1):records.append({'section':name,'item':f'future{i}','value':value})
                if name in {'ARMA_11_b','ARIMA_110'}:
                    best,search=arima_search(series.iloc[:-20]);records += [{**r,'section':name+'_'+r['section']} for r in search]
            bars(ctx,series_names,errors,'模拟序列：预设 ARIMA 的留出 MAE','MAE')
            details['holdout_rows']=20
            notes='修复旧版 ARIMA 位置参数和未定义 param_seasonal 导致网格候选全部被异常捕获的问题。保留四种模拟过程、平稳性、残差诊断和未来预测；不再静默吞掉所有错误。'
        else:
            os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
            import tensorflow as tf
            tf.config.threading.set_inter_op_parallelism_threads(1)
            tf.config.threading.set_intra_op_parallelism_threads(1)
            tf.keras.utils.set_random_seed(42)
            tf.config.experimental.enable_op_determinism()
            dates=pd.to_datetime(data['Date'])
            if not dates.is_monotonic_increasing:raise ValueError('Stock rows must be chronological')
            values=data[['Open','Close']].to_numpy(dtype=float)
            cutoff=round(.8*len(values));validation=round(.9*cutoff)
            scaler=MinMaxScaler().fit(values[:validation])
            scaled=scaler.transform(values);X,y=windows(scaled,60)
            target_rows=np.arange(60,len(values))
            train_mask=target_rows<validation;valid_mask=(target_rows>=validation)&(target_rows<cutoff);test_mask=target_rows>=cutoff
            network=tf.keras.Sequential([tf.keras.layers.Input(shape=(60,2)),tf.keras.layers.LSTM(32,return_sequences=True),
                tf.keras.layers.LSTM(32),tf.keras.layers.Dropout(.2),tf.keras.layers.Dense(2)])
            network.compile(optimizer='adam',loss='mean_squared_error')
            # Explicit tf.data options avoid platform-specific large thread pools.
            options=tf.data.Options();options.threading.private_threadpool_size=1
            training=tf.data.Dataset.from_tensor_slices((X[train_mask],y[train_mask])).batch(16).with_options(options)
            valid=tf.data.Dataset.from_tensor_slices((X[valid_mask],y[valid_mask])).batch(16).with_options(options)
            history=network.fit(training,validation_data=valid,epochs=100,verbose=0)
            predictions=scaler.inverse_transform(network(X[test_mask],training=False).numpy())
            actual=values[target_rows[test_mask]];naive=values[target_rows[test_mask]-1]
            for i,name in enumerate(['Open','Close']):
                records.append({'section':'holdout','item':name,'MAE':float(mean_absolute_error(actual[:,i],predictions[:,i])),
                                'naive_MAE':float(mean_absolute_error(actual[:,i],naive[:,i]))})
            records += [{'section':'training','item':i+1,'loss':loss,'validation_loss':val} for i,(loss,val) in enumerate(zip(history.history['loss'],history.history['val_loss']))]
            bars(ctx,['Open LSTM','Open naive','Close LSTM','Close naive'],
                 [v for r in records[:2] for v in [r['MAE'],r['naive_MAE']]],'股价：相同目标日期上的留出 MAE','price')
            details.update({'tensorflow_version':tf.__version__,'seed':42,'epochs':100,'lookback':60,
                            'training_targets':int(train_mask.sum()),'validation_targets':int(valid_mask.sum()),'test_targets':int(test_mask.sum()),
                            'scaler_fit_end_exclusive':validation,'test_start':cutoff})
            notes='保留双层各 32 单元 LSTM、Dropout 0.2、双输出、Adam/MSE、100 epoch。独立训练内验证段替代原测试集验证；归一化仅拟合训练段。修复 Open 预测与 Close 真值混比和基线日期不齐；测试首日可以使用切分点前已观测历史，所有窗口严格早于目标日。'
    complete(ctx,lab,records,details,notes=notes)
