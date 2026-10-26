"""Explicit table grain, exact joins and decimal amounts for introductory migrations."""
from decimal import Decimal,InvalidOperation
import re
import numpy as np
import pandas as pd


def unique_key(frame,key):
    columns=[key] if isinstance(key,str) else list(key)
    if frame[columns].isna().any().any() or frame.duplicated(columns).any():
        raise ValueError(f'Expected a unique nonmissing key: {columns}')


def many_to_one(left,right,on,how='left',require_match=True):
    """Reject null/ambiguous keys instead of silently dropping facts or multiplying them."""
    if how not in ('left','inner'):raise ValueError('This helper supports left or inner joins')
    columns=[on] if isinstance(on,str) else list(on)
    unique_key(right,columns)
    if left[columns].isna().any().any():raise ValueError('Missing fact join key must be resolved explicitly')
    joined=left.merge(right,on=columns,how='left',validate='many_to_one',indicator='_joined',sort=False)
    if require_match and joined._joined.ne('both').any():raise ValueError(f'Unmatched fact key: {columns}')
    if how=='inner':joined=joined.loc[joined._joined.eq('both')]
    return joined.drop(columns='_joined')


def money_minor(values,grouped=False):
    """Parse finite decimal amounts with at most two fractional digits; never silently round."""
    pattern=r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?' if grouped else r'[+-]?\d+(?:\.\d{1,2})?'
    output=[]
    for raw in values:
        text=str(raw).strip()
        if not re.fullmatch(pattern,text):raise ValueError(f'Invalid two-decimal amount: {text[:40]}')
        try:amount=Decimal(text.replace(',',''))*100
        except InvalidOperation as exc:raise ValueError('Invalid decimal amount') from exc
        if not Decimal(np.iinfo(np.int64).min)<=amount<=Decimal(np.iinfo(np.int64).max):raise ValueError('Amount exceeds integer range')
        output.append(int(amount))
    return np.asarray(output,dtype=np.int64)


def append_aligned(frames,renames=None):
    if not frames:raise ValueError('At least one input table is required')
    renames=renames or [{} for _ in frames]
    if len(renames)!=len(frames):raise ValueError('A field mapping is required for every table')
    normalized=[];expected=None
    for frame,mapping in zip(frames,renames):
        clean=frame.rename(columns=mapping).copy()
        if clean.columns.duplicated().any():raise ValueError('Field mapping creates ambiguous duplicate names')
        if expected is None:expected=list(clean.columns)
        if set(clean.columns)!=set(expected):raise ValueError('Different schemas require an explicit field mapping')
        normalized.append(clean[expected])
    return pd.concat(normalized,ignore_index=True)
