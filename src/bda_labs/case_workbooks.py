"""Explicit case-table contracts and saved Excel reference checks; no formula eval."""
from decimal import Decimal,InvalidOperation
import re
import zipfile
from xml.etree import ElementTree as ET
import numpy as np
import pandas as pd
from .common import compare_numeric


def money_cents(values,allow_negative=True):
    result=[]
    for value in values:
        try:number=Decimal(str(value))
        except InvalidOperation as exc:raise ValueError('Expected an observed monetary amount') from exc
        if not number.is_finite() or number*100!=(number*100).to_integral_value():raise ValueError('Amounts require finite values with at most two decimal places')
        if not allow_negative and number<0:raise ValueError('Negative sales require a separately reviewed returns policy')
        result.append(int(number*100))
    return pd.Series(result,index=values.index,dtype='int64')


def calendar_period(year,month):
    y=pd.to_numeric(year,errors='raise')
    m=pd.to_numeric(month.astype('string').str.strip().str.replace(r'月$','',regex=True),errors='raise')
    if y.isna().any() or m.isna().any() or not y.between(1000,9998).all() or not m.between(1,12).all() or y.mod(1).ne(0).any() or m.mod(1).ne(0).any():raise ValueError('Expected integer year and month in calendar range')
    return pd.Series(pd.PeriodIndex(y.astype(int).astype(str)+'-'+m.astype(int).astype(str),freq='M'),index=year.index)


def ratio(numerator,denominator):
    """Preserve missing and zero-denominator results as NaN, including 0/0."""
    a,b=np.broadcast_arrays(np.asarray(numerator,dtype=float),np.asarray(denominator,dtype=float))
    out=np.full(a.shape,np.nan,dtype=float)
    return np.divide(a,b,out=out,where=np.isfinite(a)&np.isfinite(b)&(b!=0))


def check_cell(records,sheet,address,actual,scope,formula=None):
    if formula is not None and sheet.formulas.get(address)!=formula:raise AssertionError(f'Review changed source formula at {address}')
    saved=sheet.get(address)
    if saved is None:
        if not pd.isna(actual):raise AssertionError(f'Unexpected value for absent cache {address}')
    else:compare_numeric([actual],[saved],f'{scope}/{address}')
    records.append({'scope':scope,'cell':address,'saved':saved,'python':actual,
                    'formula':sheet.formulas.get(address),'numeric_compared':saved is not None,'matched':True})


def chart_audit(path,destinations,values):
    ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    rows=[];points=0
    with zipfile.ZipFile(path) as z:
        names=sorted([n for n in z.namelist() if re.fullmatch(r'xl/charts/chart\d+\.xml',n)],key=lambda n:int(re.search(r'chart(\d+)',n).group(1)))
        if len(names)!=len(destinations) or len(values)!=len(names):raise AssertionError('Every source chart requires an explicit destination')
        for name,destination,expected in zip(names,destinations,values):
            root=ET.fromstring(z.read(name));series=root.findall('.//c:ser',ns)
            if len(series)!=1:raise AssertionError('Review multi-series chart before migrating')
            s=series[0];cat=s.find('c:cat',ns);val=s.find('c:val',ns)
            categories=[x.text for x in cat.findall('.//c:pt/c:v',ns)]
            numbers=[float(x.text) for x in val.findall('.//c:pt/c:v',ns)]
            compare_numeric(numbers,expected,name);points+=len(numbers)
            rows.append({'chart':name,'title':''.join(x.text or '' for x in root.findall('.//c:title//a:t',ns)),
                         'category_reference':';'.join(x.text for x in cat.findall('.//c:f',ns)),
                         'value_reference':';'.join(x.text for x in val.findall('.//c:f',ns)),
                         'cached_categories':len(categories),'cached_values':len(numbers),
                         'category_value_length_equal':len(categories)==len(numbers),
                         'numeric_cache_matched':True,'python_destination':destination})
    return pd.DataFrame(rows),points
