"""Cloneable date, calendar and strictly historical time-series transformers."""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin, clone

from bda_labs.common import context
from bda_labs.advanced_common import complete, bars


class CalendarFeatures(TransformerMixin, BaseEstimator):
    def __init__(self, time_col='timestamp', period_dict=None, season_dict=None, public_vacations=None):
        self.time_col=time_col; self.period_dict=period_dict
        self.season_dict=season_dict; self.public_vacations=public_vacations

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        data=X.copy(); t=pd.to_datetime(data[self.time_col],errors='raise')
        data[self.time_col]=t
        for name,attr in [('year','year'),('mth','month'),('day','day'),('hour','hour'),
                          ('minute','minute'),('second','second'),('week','dayofweek'),('day_of_year','dayofyear')]:
            data[name]=getattr(t.dt,attr)
        data['week_of_year']=t.dt.isocalendar().week.astype(int)
        data['minute_of_day']=t.dt.hour*60+t.dt.minute
        for name,attr in [('is_leap_year','is_leap_year'),('is_mth_start','is_month_start'),
                          ('is_mth_end','is_month_end'),('is_quarter_start','is_quarter_start'),
                          ('is_quarter_end','is_quarter_end'),('is_year_start','is_year_start'),('is_year_end','is_year_end')]:
            data[name]=getattr(t.dt,attr)
        data['is_weekend']=t.dt.dayofweek>=5
        data['is_working']=(t.dt.hour>=8)&(t.dt.hour<22)
        if self.period_dict is not None: data['period']=t.dt.hour.map(self.period_dict)
        if self.season_dict is not None: data['season']=t.dt.month.map(self.season_dict)
        if self.public_vacations is not None: data['is_public_holiday']=t.dt.strftime('%Y%m%d').isin(self.public_vacations)
        return data


class HistoricalFeatures(TransformerMixin, BaseEstimator):
    """Each row may use only values in previous rows of the same entity.

    Input must already be chronologically sorted; a separate transform call has
    no implicit training history. Concatenate permitted past context explicitly.
    """
    def __init__(self, cols=None, group_col=None):
        self.cols=cols; self.group_col=group_col

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        data=X.copy()
        groups=[(None,data)] if self.group_col is None else data.groupby(self.group_col,sort=False,dropna=False)
        result=[]
        for _,part in groups:
            part=part.copy()
            for col in self.cols or []:
                s=part[col].astype(float)
                for lag in range(1,4): part[f'{col}-{lag}day']=s.shift(lag)
                past=s.shift(1)
                part[col+'_last_3_day_mean']=past.rolling(3,min_periods=3).mean()
                part[col+'_last_2_mins']=s.shift(1)-s.shift(2)
                for lag in (1,2):
                    part[f'{col}_lag_{lag}_corr']=past.expanding(min_periods=3).corr(past.shift(lag))
            result.append(part)
        return pd.concat(result).reindex(X.index)


def main(lab='F09', argv=None):
    ctx=context(lab,argv)
    sample=pd.DataFrame({'timestamp':['2023-01-01 10:00:00','2023-02-01 15:30:00'],'col1':[10,20]})
    calendar=CalendarFeatures(period_dict={0:'off-peak',6:'peak',12:'off-peak',18:'peak'},
                              season_dict={1:'winter',2:'winter'},public_vacations=['20230101'])
    calendar=clone(calendar).fit(sample)
    transformed=calendar.transform(sample)
    history=pd.DataFrame({'timestamp':pd.date_range('2024-01-01',periods=12),'col1':[1,4,2,8,3,7,9,6,10,5,11,12]})
    engineered=clone(HistoricalFeatures(cols=['col1'])).fit_transform(history)
    changed=history.copy();changed.loc[8:,'col1']=100000
    prefix=HistoricalFeatures(cols=['col1']).transform(changed)
    pd.testing.assert_frame_equal(engineered.iloc[:8],prefix.iloc[:8])
    if not np.isclose(engineered.loc[3,'col1-3day'],history.loc[0,'col1']): raise AssertionError('Lag shifted incorrectly')
    records=[{'section':'calendar_example','item':c,'value':str(transformed[c].tolist())} for c in transformed if c!='timestamp']
    records += [{'section':'history_example','item':c,'nonmissing':int(engineered[c].notna().sum())} for c in engineered if c!='timestamp']
    bars(ctx,['lag 1','lag 2','lag 3','past 3 mean'],[int(engineered[c].notna().sum()) for c in ['col1-1day','col1-2day','col1-3day','col1_last_3_day_mean']],
         '历史特征的可用观测数（合成样例）','rows')
    complete(ctx,lab,records,{'sample_rows':len(sample),'synthetic_validation_rows':len(history),
                            'future_perturbation_checked':True,'clone_checked':True},
             notes='修复源示例不同 lag 均调用 shift(1) 及全序列自相关泄露未来信息。历史特征按输入行先后计算，调用者必须先按实体和时间排序；不自动跨 transform 调用拼接历史。日期示例和扩展时序均为合成数据。存储格式与性能建议仅解释适用条件，不声称执行源注释中未实现的基准。')
