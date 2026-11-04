"""Create order/item facts with explicit flags; never modify raw CSVs.

Reporting period is a provisional, conservative choice: 2017-01-01 to
2018-08-01 exclusive. August 2018 has an observed delivered-order cutoff
on August 29; early 2016 is sparse. The full data are retained alongside flags.
"""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
CLEAN = ROOT / 'data' / 'clean'
OUT = ROOT / 'outputs' / 'tables'
DOCS = ROOT / 'docs'
START, END = pd.Timestamp('2017-01-01'), pd.Timestamp('2018-08-01')


def load(name):
    return pd.read_csv(RAW / f'olist_{name}_dataset.csv', dtype=str)


def unique(df, key):
    if df[key].isna().any().any() or df.duplicated(key).any():
        raise ValueError(f'Invalid unique key: {key}')


def main():
    CLEAN.mkdir(parents=True, exist_ok=True)
    orders, customers, items = load('orders'), load('customers'), load('order_items')
    products, sellers = load('products'), load('sellers')
    payments, reviews = load('order_payments'), load('order_reviews')
    translation = pd.read_csv(RAW / 'product_category_name_translation.csv', dtype=str)
    for df, key in [(orders, ['order_id']), (customers, ['customer_id']),
                    (items, ['order_id', 'order_item_id']), (products, ['product_id']),
                    (sellers, ['seller_id']), (payments, ['order_id', 'payment_sequential']),
                    (translation, ['product_category_name'])]:
        unique(df, key)
    for col in orders.columns:
        if col.endswith(('_timestamp', '_date')):
            orders[col] = pd.to_datetime(orders[col], errors='raise')
    for col in ['review_creation_date', 'review_answer_timestamp']:
        reviews[col] = pd.to_datetime(reviews[col], errors='raise')
    reviews['review_score'] = pd.to_numeric(reviews['review_score'], errors='raise')
    if not reviews['review_score'].between(1, 5).all():
        raise ValueError('Review score outside 1..5')
    items['shipping_limit_date'] = pd.to_datetime(items['shipping_limit_date'], errors='raise')
    for df, cols in [(items, ['price', 'freight_value']), (payments, ['payment_value'])]:
        for col in cols:
            n = pd.to_numeric(df[col], errors='raise')
            # BRL cents avoid floating-point summation drift and retain raw numbers.
            cents = (n * 100).round()
            if ((n * 100 - cents).abs() > 1e-6).any():
                raise ValueError('Unexpected monetary precision')
            df[col] = n
            df[col + '_cents'] = cents.astype('Int64')
    unique_item_count = len(items)
    items['nonpositive_price_flag'] = items['price'].le(0) | items['price'].isna()
    items['negative_freight_flag'] = items['freight_value'].lt(0) | items['freight_value'].isna()
    item_agg = items.groupby('order_id').agg(
        merchandise_value_cents=('price_cents', 'sum'),
        freight_value_cents=('freight_value_cents', 'sum'),
        item_count=('order_item_id', 'size'),
        item_amount_issue_flag=('nonpositive_price_flag', 'max'),
        freight_issue_flag=('negative_freight_flag', 'max'))
    pay_agg = payments.groupby('order_id').agg(payment_value_cents=('payment_value_cents', 'sum'),
                                                            payment_record_count=('order_id', 'size'))
    # Keep the latest answered review for descriptive analysis; retain counts/ranges.
    reviews['_source_row'] = range(len(reviews))
    counts = reviews.groupby('order_id').agg(review_record_count=('review_id', 'size'),
                                            review_score_min=('review_score', 'min'),
                                            review_score_max=('review_score', 'max'))
    latest = reviews.sort_values(['review_answer_timestamp', 'review_creation_date', 'review_id', '_source_row'],
                                na_position='first', kind='stable').drop_duplicates('order_id', keep='last')
    latest = latest[['order_id', 'review_score', 'review_answer_timestamp']].merge(
        counts, on='order_id', validate='one_to_one')
    fact = orders.merge(customers, on='customer_id', validate='one_to_one', how='left', indicator=True)
    if not fact['_merge'].eq('both').all():
        raise ValueError('Unmatched customer')
    fact = fact.drop(columns='_merge')
    for agg in [item_agg, pay_agg, latest.set_index('order_id')]:
        fact = fact.merge(agg, on='order_id', how='left', validate='one_to_one')
    if len(fact) != len(orders):
        raise ValueError('Order grain changed')
    for col in ['merchandise_value', 'freight_value', 'payment_value']:
        fact[col] = fact[col + '_cents'] / 100
    fact['payment_difference_cents'] = fact['payment_value_cents'] - fact['merchandise_value_cents'] - fact['freight_value_cents']
    fact['payment_mismatch_flag'] = fact['payment_difference_cents'].abs().gt(5).astype('boolean')
    fact['missing_items_flag'] = fact['item_count'].isna()
    fact['missing_payment_flag'] = fact['payment_record_count'].isna()
    fact['in_analysis_period'] = fact['order_purchase_timestamp'].ge(START) & fact['order_purchase_timestamp'].lt(END)
    fact['sales_eligible'] = (fact['order_status'].eq('delivered') & fact['in_analysis_period']
                              & ~fact['missing_items_flag'] & fact['merchandise_value'].gt(0)
                              & ~fact['item_amount_issue_flag'].fillna(True)
                              & ~fact['freight_issue_flag'].fillna(True))
    fact['delivery_days'] = (fact['order_delivered_customer_date'] - fact['order_purchase_timestamp']).dt.total_seconds() / 86400
    fact['delay_days_calendar'] = (fact['order_delivered_customer_date'].dt.normalize()
                                  - fact['order_estimated_delivery_date'].dt.normalize()).dt.days
    fact['missing_delivery_date_flag'] = fact['order_delivered_customer_date'].isna()
    fact['negative_delivery_days_flag'] = fact['delivery_days'].lt(0)
    fact['logistics_eligible'] = (fact['sales_eligible'] & fact['delivery_days'].notna()
                                 & fact['delay_days_calendar'].notna() & ~fact['negative_delivery_days_flag'])
    fact['late_delivery_flag'] = fact['delay_days_calendar'].gt(0).astype('boolean')
    fact.loc[fact['delay_days_calendar'].isna(), 'late_delivery_flag'] = pd.NA
    fact['review_eligible'] = fact['logistics_eligible'] & fact['review_score'].notna()
    fact['purchase_month'] = fact['order_purchase_timestamp'].dt.to_period('M').astype(str)
    products = products.merge(translation, on='product_category_name', how='left', validate='many_to_one')
    products['category_missing_flag'] = products['product_category_name'].isna()
    products['category_translation_missing_flag'] = products['product_category_name'].notna() & products['product_category_name_english'].isna()
    products['category_display'] = products['product_category_name_english'].fillna(products['product_category_name']).fillna('unknown_category')
    enriched = items.merge(products, on='product_id', how='left', validate='many_to_one', indicator=True)
    if not enriched['_merge'].eq('both').all():
        raise ValueError('Unmatched product')
    enriched = enriched.drop(columns='_merge').merge(sellers, on='seller_id', how='left', validate='many_to_one', indicator=True)
    if not enriched['_merge'].eq('both').all():
        raise ValueError('Unmatched seller')
    enriched = enriched.drop(columns='_merge')
    enriched = enriched.merge(fact[['order_id', 'order_purchase_timestamp', 'purchase_month', 'order_status',
                                    'customer_state', 'sales_eligible']], on='order_id', how='left', validate='many_to_one')
    if len(enriched) != unique_item_count:
        raise ValueError('Item grain changed')
    sales = fact.loc[fact['sales_eligible']]
    eligible_items = enriched.loc[enriched['sales_eligible']]
    item_cents = int(eligible_items['price_cents'].sum())
    order_cents = int(sales['merchandise_value_cents'].sum())
    if item_cents != order_cents:
        raise ValueError('Order/item merchandise amounts do not reconcile')
    freq = sales.groupby('customer_unique_id')['order_id'].nunique()
    result = {
        'analysis_start_inclusive': str(START.date()), 'analysis_end_exclusive': str(END.date()),
        'raw_orders': len(orders), 'order_fact_rows': len(fact),
        'raw_items': unique_item_count, 'item_fact_rows': len(enriched),
        'sales_eligible_orders': len(sales), 'sales_eligible_items': len(eligible_items),
        'sales_eligible_customers': len(freq), 'sales_repeat_customers': int(freq.gt(1).sum()),
        'sales_repeat_customer_rate': float(freq.gt(1).mean()),
        'merchandise_value_brl': order_cents / 100,
        'freight_value_brl': int(sales['freight_value_cents'].sum()) / 100,
        'logistics_eligible_orders': int(fact['logistics_eligible'].sum()),
        'logistics_review_eligible_orders': int(fact['review_eligible'].sum()),
        'selected_period_delivered_missing_signature': int((fact['sales_eligible'] & fact['missing_delivery_date_flag']).sum()),
        'sales_payment_mismatch_orders': int(sales['payment_mismatch_flag'].sum()),
        'order_item_cents_reconciliation': 'passed',
        'raw_rows_dropped': 0, 'synthetic_rows': 0,
        'review_selection': 'latest answer timestamp, creation timestamp, review_id, original row; keep last',
    }
    fact.to_csv(CLEAN / 'orders_fact.csv', index=False, encoding='utf-8-sig')
    enriched.to_csv(CLEAN / 'order_items_fact.csv', index=False, encoding='utf-8-sig')
    (OUT / 'cleaning_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    docs = [
        '# Olist清洗口径与验证', '',
        '保留全量原始CSV；清洗表不丢弃订单或商品明细，用布尔标记控制分析样本。未生成任何模拟记录。', '',
        '## 暂定分析时期', '',
        '2017年1月1日至2018年7月31日，按购买时间归属。早期样本稀疏，2018年8月已交付订单的购买日期只到29日，因此保守排除该月及以后。这个选择不证明所选期间涵盖平台全部交易，仍受数据集覆盖限制。',
        '同比可比较2018年1—7月与2017年1—7月，不使用2018年全年与2017年全年作同比。RFM观察截止日暂定2018年8月1日；仅作为历史窗口描述，不作为对当时可见信息的预测评估。', '',
        '## 订单和商品粒度', '',
        'orders_fact.csv每行一个订单；order_items_fact.csv每行一个订单内商品序号。关联用validate检查基数。订单表内金额不能在商品明细连接后重复相加。商品和支付先按订单汇总，再加入订单表。',
        'customer_unique_id识别实际客户，customer_id仅用于连接订单。邮编前缀以文本保存前导零。原数据没有成本字段，因此不计算利润。', '',
        '## 质量处理规则', '',
        '- 关键主键缺失或重复会中止运行，不悄悄去重。地理表暂不进入分析表，其原始重复坐标记录保留。',
        '- 商品金额和运费分别计算，使用整数分校验金额；支付对账差异保留标记及例外表，不篡改支付额来配平。',
        '- 销售主体样本要求期间内、已交付、有商品明细、商品金额为正且无非正商品价格或负运费问题。未交付订单单独保留。',
        '- 签收缺失不虚构日期，不影响其可核实的销售金额；这类订单仅从配送指标中排除。配送时长小于0也排除。',
        '- 逾期按签收自然日晚于预计自然日定义，同一天内晚于午夜不算逾期。分母为具有有效签收、预计日期且配送时长非负的销售样本。',
        '- 同订单多评论选择最新答复记录；保留评论条数、最高和最低分。该规则反映观察结束时可见评价，不能作为购买时已知特征。',
        '- 商品类别缺失标为unknown_category；英文翻译缺失时保留葡语原类别，不删除原类别，也不编造翻译。中文展示名称在后续单独映射。',
        '- 高金额、长配送时间保留；异常极值需按业务检查，并在模型适用时做敏感性分析，不能默认删掉真实极端交易。', '',
        '## 本次验证结果', '',
    ]
    docs += [f'- {key}: {value}' for key, value in result.items()]
    docs += ['', '验证包括原始校验和、唯一主键、关联基数、订单及商品行数守恒，以及两张分析表的销售金额整数分对账。',
             '这些是数据质量检查，不表示商业模型、图表、大屏和论文已经完成。', '']
    (DOCS / '02_清洗口径与验证.md').write_text('\n'.join(docs), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
