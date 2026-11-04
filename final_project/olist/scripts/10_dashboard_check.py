"""Data reconciliation and actual Dash HTTP callback checks, without a browser."""
from pathlib import Path
import sys
import csv
import json
import io
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dashboard.app import app,DATA,update
from dashboard.data import START,END

ROOT=Path(__file__).resolve().parents[1]


def main():
    checks={}
    full=DATA.select()
    assert full['metrics']['orders']==89860
    assert full['metrics']['revenue_cents']==1234245049
    assert full['metrics']['logistics_orders']==89852
    checks['full_scope_reconciliation']='passed'
    sp=DATA.select(states=['SP'])
    assert sp['metrics']['revenue_cents']==466785342
    assert sp['metrics']['orders']==37242
    checks['state_filter_reconciliation']='passed'
    year=DATA.select('2018-01-01',END)
    assert year['metrics']['revenue_cents']==637954848
    checks['date_filter_reconciliation']='passed'
    health=DATA.select(categories=['health_beauty'])
    assert health['metrics']['revenue_cents']==111016649
    assert health['metrics']['orders']==7845
    checks['category_filter_reconciliation']='passed'
    crossed=DATA.select('2018-01-01','2018-03-31',['SP'],['health_beauty','watches_gifts'])
    assert not crossed['orders']['order_id'].duplicated().any()
    assert (crossed['orders']['selected_cents']<=crossed['orders']['merchandise_value_cents']).all()
    partial=crossed['orders'].loc[crossed['orders']['selected_cents']<crossed['orders']['merchandise_value_cents']]
    assert len(partial)>0,'Exercise real mixed-category baskets'
    # Verify selected-item money directly against raw items and raw product/category maps.
    with (ROOT/'data/raw/product_category_name_translation.csv').open(encoding='utf-8-sig',newline='') as f:
        translations={x['product_category_name']:x['product_category_name_english'] for x in csv.DictReader(f)}
    with (ROOT/'data/raw/olist_products_dataset.csv').open(encoding='utf-8-sig',newline='') as f:
        product_categories={x['product_id']:translations.get(x['product_category_name'],x['product_category_name'] or 'unknown_category') for x in csv.DictReader(f)}
    order_ids=set(crossed['orders']['order_id'])
    raw_amount=Decimal(0)
    with (ROOT/'data/raw/olist_order_items_dataset.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['order_id'] in order_ids and product_categories[row['product_id']] in ['health_beauty','watches_gifts']:
                raw_amount+=Decimal(row['price'])
    assert int(raw_amount*100)==crossed['metrics']['revenue_cents']
    checks['crossed_filters_raw_decimal_reconciliation']='passed'
    checks['mixed_category_orders_without_double_counting']={'result':'passed','exercised_partial_baskets':len(partial)}
    empty=DATA.select('2017-01-01','2017-01-01',['AC'],['health_beauty'])
    assert empty['metrics']['orders']==0 and empty['metrics']['late_rate'] is None
    checks['empty_selection']='passed'
    client=app.server.test_client()
    assert client.get('/').status_code==200
    layout=client.get('/_dash-layout')
    assert layout.status_code==200 and b'kpi-row' in layout.data
    assert client.get('/assets/style.css').status_code==200
    mainkey=next(k for k in app.callback_map if 'kpi-row.children' in k)
    outputs=[{'id':o.component_id,'property':o.component_property} for o in app.callback_map[mainkey]['output']]
    def request(start,end,states,categories):
        response=client.post('/_dash-update-component',json={
            'output':mainkey,'outputs':outputs,'changedPropIds':['state-filter.value'],
            'inputs':[{'id':'date-filter','property':'start_date','value':start},
                      {'id':'date-filter','property':'end_date','value':end},
                      {'id':'state-filter','property':'value','value':states},
                      {'id':'category-filter','property':'value','value':categories}],
            'state':[]})
        assert response.status_code==200,response.data.decode()[:1000]
        return response.get_json()['response']
    response=request(START,END,['SP'],[])
    assert 'SP' in response['filter-summary']['children']
    assert response['kpi-row']['children'][0]['props']['children'][1]['props']['children']=='466.79'
    assert all(response[g]['figure']['data'] for g in ['monthly-chart','category-chart','state-chart','delivery-chart'])
    response=request('2017-01-01','2017-01-01',['AC'],['health_beauty'])
    assert response['kpi-row']['children'][1]['props']['children'][1]['props']['children']=='0'
    assert all(response[g]['figure']['layout']['annotations'] for g in ['monthly-chart','category-chart','state-chart','delivery-chart'])
    checks['dash_http_callbacks_full_and_empty']='passed'
    export_key='download-orders.data'
    exported=client.post('/_dash-update-component',json={'output':export_key,'outputs':{'id':'download-orders','property':'data'},
        'changedPropIds':['export-button.n_clicks'],'inputs':[{'id':'export-button','property':'n_clicks','value':1}],
        'state':[{'id':'date-filter','property':'start_date','value':START},{'id':'date-filter','property':'end_date','value':END},
                 {'id':'state-filter','property':'value','value':['SP']},{'id':'category-filter','property':'value','value':['health_beauty']}]})
    assert exported.status_code==200
    content=exported.get_json()['response']['download-orders']['data']['content']
    assert content.startswith('\ufeff')
    exported_rows=list(csv.DictReader(io.StringIO(content.lstrip('\ufeff'))))
    expected=DATA.select(states=['SP'],categories=['health_beauty'])
    assert len(exported_rows)==expected['metrics']['orders']
    assert sum(Decimal(x['所选商品金额_BRL']) for x in exported_rows)*100==expected['metrics']['revenue_cents']
    checks['filtered_csv_download_http_and_money']='passed'
    resetkey=next(k for k in app.callback_map if 'date-filter.start_date' in k)
    reset=client.post('/_dash-update-component',json={'output':resetkey,
        'outputs':[{'id':o.component_id,'property':o.component_property} for o in app.callback_map[resetkey]['output']],
        'changedPropIds':['reset-filters.n_clicks'],'inputs':[{'id':'reset-filters','property':'n_clicks','value':1}],'state':[]})
    assert reset.status_code==200
    reset_data=reset.get_json()['response']
    assert reset_data['state-filter']['value']==[] and reset_data['category-filter']['value']==[]
    assert reset_data['date-filter']['start_date']==START and reset_data['date-filter']['end_date']==END
    checks['reset_callback']='passed'
    checks['browser_manual_interactions']='pending'
    path=ROOT/'outputs/tables/dashboard_verification.json'
    path.write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
