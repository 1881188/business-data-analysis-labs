"""Separate descriptive decomposition from chronological, training-only forecasts."""
import json
import numpy as np
import pandas as pd
from scipy.stats import t as student_t
from statsmodels.tsa.seasonal import seasonal_decompose
from .common import context,finish,plotting,save_table,compare_numeric
from .closure_tools import chart_caches
from .pbix_audit import visual_audit
from .workbook_reference import read_cached_book,coverage_table


def regular_series(dates,values,freq):
    d=pd.DatetimeIndex(pd.to_datetime(dates,errors='raise'));v=pd.to_numeric(pd.Series(values),errors='raise').to_numpy(dtype=float)
    if d.isna().any() or d.has_duplicates or not d.is_monotonic_increasing or not np.isfinite(v).all():raise ValueError('Expected finite observations on unique sorted dates')
    expected=pd.date_range(d[0],periods=len(d),freq=freq)
    if not d.equals(expected):raise ValueError('Missing or irregular calendar periods require review, not automatic interpolation')
    return pd.Series(v,index=d,name='observed')


def design(indices,period):
    indices=np.asarray(indices);season=(indices%period).astype(int)
    return np.column_stack([np.ones(len(indices)),indices,*[(season==i).astype(float) for i in range(1,period)]])


def predict(train,horizon,period,log=False):
    values=np.asarray(train,dtype=float)
    if period<2 or len(values)<2*period or horizon<1 or not np.isfinite(values).all() or (log and np.any(values<=0)):raise ValueError('Forecast requires two complete cycles and finite values; logs need positive values')
    y=np.log(values) if log else values;X=design(np.arange(len(y)),period);future=design(np.arange(len(y),len(y)+horizon),period)
    beta,_,rank,_=np.linalg.lstsq(X,y,rcond=None)
    if rank!=X.shape[1] or len(y)<=rank:raise ValueError('Insufficient independent training periods')
    fitted=X@beta;residual=y-fitted;variance=float(residual@residual/(len(y)-rank))
    center=future@beta;sd=np.sqrt(np.maximum(0,variance*(1+np.einsum('ij,jk,ik->i',future,np.linalg.pinv(X.T@X),future))))
    distance=student_t.ppf(.975,len(y)-rank)*sd
    if log:
        point=np.exp(center);lower=np.exp(center-distance);upper=np.exp(center+distance)
    else:point=center;lower=center-distance;upper=center+distance
    return pd.DataFrame({'prediction':point,'lower_95_model':lower,'upper_95_model':upper})


def seasonal_naive(train,horizon,period):
    train=np.asarray(train,dtype=float)
    if len(train)<period or horizon<1:raise ValueError('A full seasonal cycle is required')
    return np.resize(train[-period:],horizon)


def error_metrics(actual,predicted,training,period):
    actual=np.asarray(actual);predicted=np.asarray(predicted);training=np.asarray(training)
    if not len(actual) or len(training)<=period or actual.shape!=predicted.shape or not np.isfinite(actual).all() or not np.isfinite(predicted).all() or not np.isfinite(training).all():raise ValueError('Aligned finite pairs and a seasonal training scale are required')
    errors=predicted-actual;scale=float(np.abs(training[period:]-training[:-period]).mean())
    return {'mae':float(np.abs(errors).mean()),'rmse':float(np.sqrt(np.mean(errors**2))),
            'mape':float(np.mean(np.abs(errors/actual))) if np.all(actual!=0) else None,
            'mase_seasonal':float(np.abs(errors).mean()/scale) if scale else None}


def evaluate(series,period,holdout):
    if holdout<1 or len(series)-holdout<2*period:raise ValueError('Holdout leaves too little training history')
    train=series.iloc[:-holdout];test=series.iloc[-holdout:];rows=[];predictions=[]
    for name in ['seasonal_naive','trend_seasonal','log_trend_seasonal']:
        if name=='seasonal_naive':p=pd.DataFrame({'prediction':seasonal_naive(train,holdout,period)})
        else:p=predict(train.to_numpy(),holdout,period,log=name.startswith('log'))
        metrics=error_metrics(test.to_numpy(),p.prediction.to_numpy(),train.to_numpy(),period)
        rows.append({'model':name,'train_end':str(train.index[-1].date()),'training_observations':len(train),'holdout_observations':holdout,**metrics})
        p['date']=test.index;p['actual']=test.to_numpy();p['model']=name;predictions.append(p)
    return pd.DataFrame(rows),pd.concat(predictions,ignore_index=True)


def decompose(series,period,log=False):
    values=np.log(series) if log else series
    if log and series.le(0).any():raise ValueError('Log decomposition requires positive observations')
    result=seasonal_decompose(values,period=period,model='additive',extrapolate_trend=0)
    f=pd.DataFrame({'date':series.index,'observed_scale':values.to_numpy(),'trend':result.trend.to_numpy(),'seasonal':result.seasonal.to_numpy(),'residual':result.resid.to_numpy()})
    complete=f.dropna();compare_numeric(complete.trend+complete.seasonal+complete.residual,complete.observed_scale,'Decomposition reconstruction')
    return f


def main(argv=None):
    ctx=context('B22',argv);keys=['air_csv','air_excel','air_wps','credit_holiday','credit_no_holiday','credit_wps','decomposition_pbix']
    paths={key:ctx.source(key) for key in keys};books={key:read_cached_book(paths[key]) for key in keys if key not in ['air_csv','decomposition_pbix']}
    raw=pd.read_csv(paths['air_csv']);air=regular_series(pd.to_datetime(raw.DATE,format='%m/%d/%Y'),raw.AIR,'MS')
    checks=[]
    def verified(name,actual,saved,tolerance=1e-9):
        result=compare_numeric(actual,saved,name,tolerance=tolerance);checks.append({'scope':name,'values_compared':result['values_compared'],'tolerance':tolerance,'matched':True})
    excel=pd.read_excel(paths['air_excel']);verified('AIR CSV versus Excel',air.to_numpy(),excel.AIR)
    verified('CSV rounded logarithms',np.log(air),raw.ln_AIR,1e-9)
    for col in ['F','I']:
        s=books['air_excel']['AirPassengers'];verified('Excel duplicate '+col,[s.get(f'{col}{r}') for r in range(2,146)],air if col=='F' else raw.ln_AIR)
    source_air=books['air_wps']['AirPassengers'];verified('WPS AIR input',[source_air.get(f'B{r}') for r in range(2,146)],air)
    from openpyxl.utils.datetime import from_excel
    verified('Excel serial dates',[pd.Timestamp(from_excel(source_air.get(f'A{r}'))).value for r in range(2,146)],air.index.asi8,tolerance=0)
    credit={}
    for key in ['credit_holiday','credit_no_holiday','credit_wps']:
        f=pd.read_excel(paths[key],sheet_name=0);credit[key]=regular_series(f.iloc[:,0],f.iloc[:,1],'D')
    verified('No-holiday versus WPS input',credit['credit_no_holiday'],credit['credit_wps'],1e-12)
    for key,sheet_name,history in [('air_wps','Sheet3',air),('credit_wps','Sheet2',credit['credit_no_holiday'])]:
        sheet=books[key][sheet_name];saved=[sheet.get(f'B{r}') for r in range(2,len(history)+2)]
        # Daily WPS display keeps two decimals; it is not an exact original input copy.
        if key=='credit_wps':
            if not np.all(np.abs(np.asarray(saved)-history.to_numpy())<=.0050000001):raise AssertionError('WPS historical display exceeds 0.01 rounding')
            checks.append({'scope':'WPS daily historical display (0.01 rounding)','values_compared':len(history),'tolerance':.0050000001,'matched':True})
        else:verified('WPS AIR historical display',saved,history)
    series={'air_monthly':air,'credit_with_holiday':credit['credit_holiday'],'credit_without_holiday':credit['credit_no_holiday']}
    metrics=[];holdouts=[];futures=[];components=[]
    for name,s in series.items():
        period=12 if name=='air_monthly' else 7;horizon=24 if name=='air_monthly' else 7
        score,p=evaluate(s,period,horizon);score['series']=name;p['series']=name;metrics.append(score);holdouts.append(p)
        # Fixed in advance: multiplicative-scale passenger seasonality, additive daily teaching series.
        future=predict(s.to_numpy(),horizon,period,log=name=='air_monthly');future['date']=pd.date_range(s.index[-1],periods=horizon+1,freq='MS' if name=='air_monthly' else 'D')[1:]
        future['series']=name;future['model']='log_trend_seasonal' if name=='air_monthly' else 'trend_seasonal';futures.append(future)
        comp=decompose(s,period,log=name=='air_monthly');comp['series']=name;comp['scale']='log' if name=='air_monthly' else 'original';components.append(comp)
    metrics=pd.concat(metrics,ignore_index=True);holdouts=pd.concat(holdouts,ignore_index=True);futures=pd.concat(futures,ignore_index=True);components=pd.concat(components,ignore_index=True)
    comparisons=[];charts=[]
    for key,sheet_name,series_name in [('air_wps','Sheet3','air_monthly'),('credit_wps','Sheet2','credit_without_holiday')]:
        sheet=books[key][sheet_name];current=futures[futures.series.eq(series_name)].set_index('date');rows=[]
        for address,value in sheet.values.items():
            if address.startswith('C') and address[1:].isdigit() and int(address[1:])>1:
                date=pd.Timestamp(sheet.get('A'+address[1:]));rows.append({'series':series_name,'date':date,'saved_wps_forecast':float(value),'python_forecast':current.loc[date,'prediction']})
        comparison=pd.DataFrame(rows);comparison['python_minus_wps']=comparison.python_forecast-comparison.saved_wps_forecast;comparisons.append(comparison)
        cache=chart_caches(paths[key],books[key],['历史与保存预测分列，稀疏点索引保持；未知WPS算法不冒充复现']);cache['source']=key;charts.append(cache)
    for name,data in [('forecast_metrics',metrics),('holdout_predictions',holdouts),('future_predictions',futures),('decomposition',components),('reference_checks',pd.DataFrame(checks)),('wps_forecast_comparison',pd.concat(comparisons,ignore_index=True)),('chart_map',pd.concat(charts,ignore_index=True))]:save_table(data,ctx.output/(name+'.csv'))
    visuals=visual_audit(paths['decomposition_pbix'],['原始AIR：月度12季节+24期未来；未重建PowerBI自动预测引擎','log AIR：按月取对数后加性分解；不先按年求对数合计再当月序列'])
    save_table(visuals,ctx.output/'pbix_visual_map.csv')
    descriptions={}
    for key,book in books.items():
        for sheet in book:
            descriptions[(key,sheet)]={'air_excel':'144个月AIR/ln及重复区域核对，原始与对数尺度分解',
                'air_wps':'144历史及24未来保存WPS快照；按稀疏缓存位置核查',
                'credit_wps':'31天输入和两位小数显示历史、7天保存预测，算法参数未给出',
                'credit_holiday':'31天原始金额序列独立建模；未提供节日标签/调整公式',
                'credit_no_holiday':'31天另一尺度的教材序列独立分析，不擅自当原始金额的可验证去节日结果'}[key]
    coverage=coverage_table(books,descriptions,ctx.output/'workbook-map.md')
    plt=plotting()
    def forecast_plot(name,filename):
        s=series[name];p=holdouts[holdouts.series.eq(name)];f=futures[futures.series.eq(name)]
        fig,ax=plt.subplots(2,1,figsize=(14,9),layout='constrained')
        ax[0].plot(s.index,s,label='历史观测');ax[0].plot(f.date,f.prediction,label='全历史拟合后的未来点预测');ax[0].fill_between(f.date,f.lower_95_model,f.upper_95_model,alpha=.2,label='模型条件近似95%区间');ax[0].set_title(name+'：未来无真实值，尚不能评价误差');ax[0].legend(fontsize=9)
        test=p[p.model.eq('seasonal_naive')];ax[1].plot(test.date,test.actual,color='black',label='留出真实值')
        for model,g in p.groupby('model'):ax[1].plot(g.date,g.prediction,label=model)
        ax[1].set_title('仅以前段训练，对最后24个月/7天做固定留出检验');ax[1].legend(fontsize=9)
        fig.savefig(ctx.output/filename,dpi=150);plt.close(fig)
    forecast_plot('air_monthly','air_forecasting.png');forecast_plot('credit_without_holiday','credit_forecasting.png')
    fig,ax=plt.subplots(3,3,figsize=(18,11),layout='constrained')
    for axes,(name,g) in zip(ax,components.groupby('series',sort=False)):
        axes[0].plot(g.date,g.observed_scale,label='观测');axes[0].plot(g.date,g.trend,label='居中趋势（描述用）');axes[0].set_title(name+' / '+g.scale.iloc[0]);axes[0].legend(fontsize=8)
        axes[1].plot(g.date,g.seasonal,color='#087f8c');axes[1].set_title('季节项（该序列自身尺度）')
        axes[2].plot(g.date,g.residual,color='#d95f45');axes[2].axhline(0,color='gray',lw=.8);axes[2].set_title('残差（边缘未知不填0）')
        for axis in axes:axis.tick_params(axis='x',rotation=25)
    fig.savefig(ctx.output/'effect_decomposition.png',dpi=150);plt.close(fig)
    metric_lines=['| 序列 | 方法 | 留出MAE | 留出RMSE |','|---|---|---:|---:|']
    for row in metrics.itertuples():metric_lines.append(f'| {row.series} | {row.model} | {row.mae:.4f} | {row.rmse:.4f} |')
    report=f'''# B22 效应分解与时间序列预测

## 三条序列分别处理

AirPassengers为1949—1960年144个月；信用卡“含节日”和“去除节日”各31天，日期均2013年3月，但数值尺度显著不同。未提供节日日期、单位换算或调整公式，不能从两个文件名推断逐值剔除关系，更不能相减作真实节日效应。两条信用卡序列分别分析，误差不跨量纲比较。

AIR的CSV、Excel原值、重复区域、WPS输入和历史快照核对；ln_AIR只保留9位小数，以1e−9核查。WPS信用卡输入与去节日原始表一致，显示历史两位小数按0.005绝对容差单独核查。没有原Excel公式，5份工作簿的{coverage['source_sheets']}张表都有去向；PBIX两页预测参数均登记，24期/12季节/95%等保存配置不等于模型算法公开。

## 分解与未来信息

![效应分解](effect_decomposition.png)

描述性分解对AIR取log后作12月加性分解，对两条日序列作7天加性分解，完整内点满足观测=趋势+季节+残差，边缘未知不填0。居中移动平均使用相邻未来观测，仅用于历史解释，不参与留出预测。log尺度的加法对应原尺度的乘法关系。

预测另用仅训练前段估计的线性趋势+季节哑变量回归。AIR预先指定log版本，日序列指定原尺度版本；另比较季节朴素、原尺度和log模型的留出表现，不按测试误差挑一个再宣称独立验证。只做固定一次时间切分：AIR前120月训练/后24月检验，日序列前24天训练/后7天检验。所有参数和残差方差都从训练段估计，未先全序列分解再切分。

![AIR预测](air_forecasting.png)

![信用卡预测](credit_forecasting.png)

forecast_metrics列MAE、RMSE、MAPE和训练段季节差分尺度MASE。真实值含0则MAPE未知，训练季节差分尺度0则MASE未知；不默默剔除零误差对。31天只有四周多，短样本误差不代表长期部署可靠性。

{chr(10).join(metric_lines)}

日“去节日”序列的预先指定趋势季节模型RMSE约2.0576，季节朴素约1.8898，复杂方法在该指标上没有改进；不隐去这一结果。各序列使用各自原单位比较，不把百万级原金额与约180的另一序列作绝对误差排名。

未来AIR24月及信用卡7天用全历史重拟合后生成，尚无真实值。log反变换exp给条件中位点预测，不冒称无偏均值。95%区间基于线性模型同方差独立残差假设的条件预测区间，未验证真实覆盖；不是PowerBI置信区间等价复刻。每日含节日序列的未来与回测也在CSV完整保留。

WPS保存的24+7个预测值单独与Python数值并列，差异只是不同未知算法输出差异，不能算预测误差。原SARIMA标签未给阶数/训练配置，不猜参数拟合答案。图缓存按原索引核查，历史144/31和未来24/7的空位置不当0。状态为运行通过，不宣称未知WPS/PowerBI预测引擎逐值重建。

```powershell
python run_labs.py --lab B22
```
'''
    finish(ctx,{'lab_id':'B22','status':'execution_verified','series_observations':{k:len(s) for k,s in series.items()},'fixed_holdout_models':len(metrics),
        'source_numeric_checks':int(pd.DataFrame(checks).values_compared.sum()),'wps_future_comparison_points':sum(len(x) for x in comparisons),
        'chart_numeric_checks':int(pd.concat(charts).cached_numeric_points.sum()),'decomposition_reconstruction_checks':3,'pbix_visuals':len(visuals),'workbook_coverage':coverage},report)


if __name__=='__main__':main()
