"""Sales, category ABC and delivery/review descriptive analysis."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'tables'


def save(df, name):
    df.to_csv(OUT / name, index=False, encoding='utf-8-sig')


def abc_labels(shares, a=.80, b=.95):
    # The category crossing a boundary remains in the higher-priority class.
    previous = shares.cumsum().shift(fill_value=0)
    return np.where(previous < a, 'A', np.where(previous < b, 'B', 'C'))


def review_groups(df, score='review_score'):
    tmp = df.assign(low_score=df[score].le(2))
    result = tmp.groupby('late_delivery_flag').agg(
        orders=('order_id', 'size'), mean_score=(score, 'mean'),
        low_score_orders=('low_score', 'sum'), low_score_rate=('low_score', 'mean'))
    # Wilson 95% intervals for descriptive low-score proportions.
    n, p = result['orders'], result['low_score_rate']
    center = (p + 1.96**2 / (2*n)) / (1 + 1.96**2/n)
    half = 1.96*np.sqrt(p*(1-p)/n + 1.96**2/(4*n*n)) / (1+1.96**2/n)
    result['low_score_ci95_lower'], result['low_score_ci95_upper'] = center-half, center+half
    return result.reset_index()


def main():
    all_orders = pd.read_csv(ROOT / 'data/clean/orders_fact.csv', dtype={'customer_zip_code_prefix': str})
    all_items = pd.read_csv(ROOT / 'data/clean/order_items_fact.csv', dtype={'seller_zip_code_prefix': str})
    orders = all_orders.loc[all_orders['sales_eligible']].copy()
    items = all_items.loc[all_items['sales_eligible']].copy()
    orders['purchase'] = pd.to_datetime(orders['order_purchase_timestamp'])
    monthly = orders.groupby('purchase_month').agg(
        orders=('order_id', 'size'), customers=('customer_unique_id', 'nunique'),
        revenue_cents=('merchandise_value_cents', 'sum'), freight_cents=('freight_value_cents', 'sum'))
    monthly['revenue_brl'] = monthly['revenue_cents']/100
    monthly['avg_order_value_brl'] = monthly['revenue_brl']/monthly['orders']
    monthly['revenue_mom'] = monthly['revenue_brl'].pct_change(fill_method=None)
    monthly['revenue_yoy'] = monthly['revenue_brl'].pct_change(12, fill_method=None)
    monthly['revenue_ma3_brl'] = monthly['revenue_brl'].rolling(3, min_periods=3).mean()
    save(monthly.reset_index(), 'analysis_monthly_sales.csv')
    orders['year'] = orders['purchase'].dt.year
    comparable = orders.loc[orders['purchase'].dt.month.le(7)]
    year = comparable.groupby('year').agg(orders=('order_id', 'size'), revenue_cents=('merchandise_value_cents', 'sum'))
    year['revenue_brl'] = year['revenue_cents']/100
    year['avg_order_value_brl'] = year['revenue_brl']/year['orders']
    save(year.reset_index(), 'analysis_jan_jul_comparison.csv')
    states = orders.groupby('customer_state').agg(orders=('order_id', 'size'), revenue_cents=('merchandise_value_cents', 'sum'))
    states['revenue_brl'] = states['revenue_cents']/100
    states['share'] = states['revenue_cents']/states['revenue_cents'].sum()
    state_year = comparable.pivot_table(index='customer_state', columns='year', values='merchandise_value_cents', aggfunc='sum')
    states['jan_jul_2017_brl'] = state_year[2017]/100
    states['jan_jul_2018_brl'] = state_year[2018]/100
    states['jan_jul_yoy'] = states['jan_jul_2018_brl']/states['jan_jul_2017_brl'].replace(0, np.nan)-1
    states = states.sort_values('revenue_cents', ascending=False)
    save(states.reset_index(), 'analysis_state_sales.csv')
    categories = items.groupby('category_display').agg(
        revenue_cents=('price_cents', 'sum'), items=('order_item_id', 'size'), orders=('order_id', 'nunique'))
    categories = categories.sort_values(['revenue_cents', 'category_display'], ascending=[False, True]).reset_index()
    total_cents = int(categories['revenue_cents'].sum())
    if total_cents != int(orders['merchandise_value_cents'].sum()):
        raise ValueError('Category and order revenue totals differ')
    categories['revenue_brl'] = categories['revenue_cents']/100
    categories['share_total'] = categories['revenue_cents']/total_cents
    known = categories.loc[categories['category_display'].ne('unknown_category')].copy()
    known['share_known'] = known['revenue_cents']/known['revenue_cents'].sum()
    known['cumulative_share_known'] = known['share_known'].cumsum()
    known['abc_class'] = abc_labels(known['share_known'])
    categories = categories.merge(known[['category_display','share_known','cumulative_share_known','abc_class']], on='category_display', how='left', validate='one_to_one')
    categories['abc_class'] = categories['abc_class'].fillna('U')
    save(categories, 'analysis_category_abc.csv')
    abc = categories.groupby('abc_class').agg(categories=('category_display', 'size'), revenue_cents=('revenue_cents', 'sum'))
    abc['share_total'] = abc['revenue_cents']/total_cents
    save(abc.reset_index(), 'analysis_abc_summary.csv')
    sensitivity = []
    for a,b in [(.75,.90),(.80,.95),(.85,.97)]:
        temp = known.assign(abc=abc_labels(known['share_known'], a,b))
        row = {'a_threshold':a, 'b_threshold':b}
        for group in ['A','B','C']:
            subset = temp.loc[temp['abc'].eq(group)]
            row[group+'_categories'] = len(subset)
            row[group+'_share_known'] = float(subset['share_known'].sum())
        sensitivity.append(row)
    save(pd.DataFrame(sensitivity), 'analysis_abc_sensitivity.csv')
    logistics = orders.loc[orders['logistics_eligible']].copy()
    reviews = logistics.loc[logistics['review_eligible']].copy()
    groups = review_groups(reviews)
    save(groups, 'analysis_delivery_review.csv')
    state_delivery = logistics.groupby('customer_state').agg(
        eligible_orders=('order_id', 'size'), late_orders=('late_delivery_flag', 'sum'),
        median_delivery_days=('delivery_days', 'median'))
    state_delivery['late_rate'] = state_delivery['late_orders']/state_delivery['eligible_orders']
    save(state_delivery.reset_index(), 'analysis_state_delivery.csv')
    # Control descriptive comparisons for state and primary product category.
    contribution = items.groupby(['order_id','category_display'])['price_cents'].sum().reset_index()
    dominant = contribution.sort_values(['order_id','price_cents','category_display'], ascending=[True,False,True]).drop_duplicates('order_id')
    review_detail = reviews.merge(dominant[['order_id','category_display']], on='order_id', how='left', validate='one_to_one')
    review_detail['low_score'] = review_detail['review_score'].le(2)
    strata = review_detail.groupby(['customer_state','category_display','late_delivery_flag']).agg(
        n=('order_id','size'), mean_score=('review_score','mean'), low_rate=('low_score','mean'))
    flat = strata.unstack('late_delivery_flag').dropna()
    eligible_strata = flat.loc[(flat['n'][True]>=20) & (flat['n'][False]>=20)].copy()
    weights = eligible_strata['n'].sum(axis=1)
    weights /= weights.sum()
    adjusted = {'common_strata':len(eligible_strata), 'min_orders_per_group_per_stratum':20,
                'covered_orders':int(eligible_strata['n'].sum().sum()),
                'on_time_mean_score':float((eligible_strata['mean_score'][False]*weights).sum()),
                'late_mean_score':float((eligible_strata['mean_score'][True]*weights).sum()),
                'on_time_low_rate':float((eligible_strata['low_rate'][False]*weights).sum()),
                'late_low_rate':float((eligible_strata['low_rate'][True]*weights).sum())}
    strata.reset_index().to_csv(OUT/'analysis_delivery_review_strata.csv', index=False, encoding='utf-8-sig')
    # Review selection sensitivity: earliest instead of latest answered review.
    raw_reviews = pd.read_csv(ROOT/'data/raw/olist_order_reviews_dataset.csv')
    raw_reviews['_row'] = np.arange(len(raw_reviews))
    first = raw_reviews.sort_values(['review_answer_timestamp','review_creation_date','review_id','_row'], na_position='first', kind='stable').drop_duplicates('order_id', keep='first')
    first_join = reviews.drop(columns='review_score').merge(first[['order_id','review_score']], on='order_id', validate='one_to_one')
    save(review_groups(first_join), 'analysis_delivery_review_earliest_sensitivity.csv')
    # Forecast category chosen before validation/test, on Jan 2017--May 2018 only.
    dates = pd.to_datetime(all_items['order_purchase_timestamp'])
    training_items = all_items.loc[dates.ge('2017-01-01') & dates.lt('2018-06-01') & all_items['price_cents'].gt(0)
                                   & all_items['category_display'].ne('unknown_category')]
    candidate = training_items.groupby('category_display').agg(revenue_cents=('price_cents','sum'), items=('order_item_id','size')).sort_values('revenue_cents', ascending=False)
    calendar = pd.date_range('2017-01-01','2018-07-31',freq='D')
    choices = []
    for category in candidate.head(10).index:
        ci = all_items.loc[all_items['category_display'].eq(category)].copy()
        ci['date'] = pd.to_datetime(ci['order_purchase_timestamp']).dt.normalize()
        ci = ci.loc[ci['price_cents'].gt(0)]
        series = ci.groupby('date')['price_cents'].sum().reindex(calendar,fill_value=0)/100
        tr = series.loc[:'2018-05-31']
        choices.append({'category':category,'selection_train_revenue_brl':float(tr.sum()),
                        'training_days':len(tr),'training_nonzero_rate':float(tr.gt(0).mean())})
    save(pd.DataFrame(choices), 'forecast_category_candidates.csv')
    selected = next(x['category'] for x in choices if x['training_nonzero_rate']>=.90)
    fi = all_items.loc[all_items['category_display'].eq(selected) & all_items['price_cents'].gt(0)].copy()
    fi['date'] = pd.to_datetime(fi['order_purchase_timestamp']).dt.normalize()
    daily = fi.groupby('date')['price_cents'].sum().reindex(calendar,fill_value=0).rename('ordered_value_cents').to_frame()
    daily['ordered_value_brl'] = daily['ordered_value_cents']/100
    daily.index.name = 'date'
    save(daily.reset_index(), 'forecast_daily_series.csv')
    summary = {
        'period':'2017-01-01 to 2018-07-31', 'sales_orders':len(orders),
        'merchandise_value_brl':total_cents/100,
        'jan_jul_2017_revenue_brl':float(year.loc[2017,'revenue_brl']),
        'jan_jul_2018_revenue_brl':float(year.loc[2018,'revenue_brl']),
        'jan_jul_revenue_growth':float(year.loc[2018,'revenue_brl']/year.loc[2017,'revenue_brl']-1),
        'jan_jul_order_growth':float(year.loc[2018,'orders']/year.loc[2017,'orders']-1),
        'jan_jul_aov_growth':float(year.loc[2018,'avg_order_value_brl']/year.loc[2017,'avg_order_value_brl']-1),
        'peak_month':str(monthly['revenue_brl'].idxmax()),
        'peak_month_revenue_brl':float(monthly['revenue_brl'].max()),
        'top_state':str(states.index[0]), 'top_state_share':float(states.iloc[0]['share']),
        'top5_category_share_total':float(categories.head(5)['share_total'].sum()),
        'known_categories':len(known), 'a_categories':int(abc.loc['A','categories']),
        'a_share_total':float(abc.loc['A','share_total']),
        'unknown_category_share_total':float(categories.loc[categories['abc_class'].eq('U'),'share_total'].sum()),
        'late_rate':float(logistics['late_delivery_flag'].mean()),
        'review_comparison':groups.to_dict(orient='records'),
        'state_category_standardized_review_comparison':adjusted,
        'forecast_category':selected,
        'forecast_metric':'Ordered merchandise value BRL; all final statuses, positive item prices; differs from delivered sales scope',
    }
    (OUT/'analysis_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
