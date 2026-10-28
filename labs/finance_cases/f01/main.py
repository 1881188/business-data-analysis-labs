"""Pending source test.ipynb: requires the absent data12261.csv, never fake it."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
import numpy as np
import pandas as pd
from sklearn.feature_selection import RFE
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from bda_labs.advanced_regression import classification_metrics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True,help='Original missing data12261.csv; other datasets are not substitutes')
    parser.add_argument('--output',type=Path,default=Path('outputs/F01/pending_result.json'))
    args=parser.parse_args()
    if not args.input.is_file():raise FileNotFoundError('F01 remains pending: data12261.csv has not been supplied')
    data=pd.read_csv(args.input).fillna(0).drop(columns=['account_id','amount'])
    if 'y' not in data or set(data['y'].unique())!={0,1}:raise ValueError('Expected binary y and the original source schema')
    X=data.drop(columns='y').astype(float);y=data['y'].astype(int)
    train,test=train_test_split(np.arange(len(data)),test_size=.5,stratify=y,random_state=42)
    # Use training bounds; cap rather than removing difficult test observations.
    q1=X.iloc[train].quantile(.25);q3=X.iloc[train].quantile(.75);iqr=q3-q1
    clipped=X.clip(q1-1.5*iqr,q3+1.5*iqr,axis=1)
    model=make_pipeline(StandardScaler(),RFE(LogisticRegression(max_iter=3000),n_features_to_select=min(5,len(X.columns))),LogisticRegression(max_iter=3000))
    model.fit(clipped.iloc[train],y.iloc[train])
    report={'lab_id':'F01','status':'external_input_run_requires_review','source_sha256':hashlib.sha256(args.input.read_bytes()).hexdigest(),
            'train_rows':len(train),'test_rows':len(test),'seed':42,
            'test':classification_metrics(y.iloc[test],model.predict_proba(clipped.iloc[test])[:,1])}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('External-input run saved locally. Register and verify this source before publishing or marking F01 complete.')


if __name__=='__main__':main()
