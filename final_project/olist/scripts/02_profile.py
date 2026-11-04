"""Profile untouched CSVs and produce reproducible quality evidence, not cleaned data."""
from pathlib import Path
import json
import hashlib
from datetime import datetime, timezone
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
OUT = ROOT / 'outputs' / 'tables'
DOCS = ROOT / 'docs'
KEYS = {
    'customers': ['customer_id'], 'orders': ['order_id'],
    'order_items': ['order_id', 'order_item_id'],
    'order_payments': ['order_id', 'payment_sequential'],
    'products': ['product_id'], 'sellers': ['seller_id'],
    'product_category_name_translation': ['product_category_name'],
}


def save_csv(df, name):
    df.to_csv(OUT / name, index=False, encoding='utf-8-sig')


def table_name(path):
    return path.stem.removeprefix('olist_').removesuffix('_dataset')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    manifest = json.loads((RAW / 'source_manifest.json').read_text(encoding='utf-8'))
    tables, summary, fields, anomalies = {}, [], [], []
    for source in manifest['files']:
        path = RAW / source['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise RuntimeError(f'Raw source checksum mismatch: {path.name}')
        # Preserve identifiers, especially postal prefixes with leading zeros.
        df = pd.read_csv(path, dtype=str)
        name = table_name(path)
        key = KEYS.get(name)
        summary.append({
            'table': name, 'rows': len(df), 'columns': len(df.columns),
            'file_bytes': path.stat().st_size,
            'dataframe_bytes_deep': int(df.memory_usage(deep=True).sum()),
            'exact_duplicate_rows': int(df.duplicated().sum()),
            'expected_key': '+'.join(key) if key else 'not assumed unique',
            'duplicate_key_rows': int(df.duplicated(key).sum()) if key else None,
            'null_key_rows': int(df[key].isna().any(axis=1).sum()) if key else None,
        })
        for col in df.columns:
            fields.append({'table': name, 'field': col, 'rows': len(df),
                           'missing': int(df[col].isna().sum()),
                           'missing_rate': float(df[col].isna().mean()),
                           'distinct_non_null': int(df[col].nunique())})
            if col.endswith(('_timestamp', '_date')):
                parsed = pd.to_datetime(df[col], errors='coerce')
                anomalies.append({'table': name, 'field': col, 'check': 'nonblank_invalid_date',
                                  'count': int((df[col].notna() & parsed.isna()).sum())})
        if name != 'geolocation':
            tables[name] = df
        print(f'Profiled {name}: {len(df):,} rows', flush=True)

    save_csv(pd.DataFrame(summary), 'table_inventory.csv')
    save_csv(pd.DataFrame(fields), 'field_profile.csv')

    relations = []
    for child, field, parent, parent_field in [
        ('orders', 'customer_id', 'customers', 'customer_id'),
        ('order_items', 'order_id', 'orders', 'order_id'),
        ('order_items', 'product_id', 'products', 'product_id'),
        ('order_items', 'seller_id', 'sellers', 'seller_id'),
        ('order_payments', 'order_id', 'orders', 'order_id'),
        ('order_reviews', 'order_id', 'orders', 'order_id'),
        ('products', 'product_category_name', 'product_category_name_translation', 'product_category_name'),
    ]:
        s = tables[child][field]
        relations.append({'child': child, 'field': field, 'parent': parent,
                          'null_rows': int(s.isna().sum()),
                          'unmatched_non_null_rows': int((s.notna() & ~s.isin(tables[parent][parent_field])).sum())})
    save_csv(pd.DataFrame(relations), 'foreign_key_checks.csv')

    orders = tables['orders'].copy()
    for col in orders.columns:
        if col.endswith(('_timestamp', '_date')):
            orders[col] = pd.to_datetime(orders[col], errors='coerce')
    items = tables['order_items'].copy()
    payments = tables['order_payments'].copy()
    for df, name, cols in [(items, 'order_items', ['price', 'freight_value']),
                           (payments, 'order_payments', ['payment_value', 'payment_installments'])]:
        for col in cols:
            raw = df[col]
            df[col] = pd.to_numeric(raw, errors='coerce')
            anomalies.extend([
                {'table': name, 'field': col, 'check': 'nonblank_invalid_number',
                 'count': int((raw.notna() & df[col].isna()).sum())},
                {'table': name, 'field': col, 'check': 'negative', 'count': int(df[col].lt(0).sum())},
                {'table': name, 'field': col, 'check': 'zero', 'count': int(df[col].eq(0).sum())},
            ])
    save_csv(pd.DataFrame(anomalies), 'type_and_value_checks.csv')

    # Each money table is first aggregated to one row per order.
    item_totals = items.groupby('order_id').agg(
        merchandise_value=('price', 'sum'), freight_value=('freight_value', 'sum'),
        item_count=('order_item_id', 'size'))
    payment_totals = payments.groupby('order_id').agg(payment_value=('payment_value', 'sum'))
    comparison = item_totals.join(payment_totals, how='outer')
    comparison['difference'] = comparison['payment_value'] - comparison['merchandise_value'] - comparison['freight_value']
    compared = comparison.dropna(subset=['difference'])
    mismatch = compared.loc[compared['difference'].abs().gt(0.05)]
    save_csv(mismatch.reset_index(), 'payment_reconciliation_exceptions.csv')

    # Validated many-to-one / one-to-one merges prevent accidental row multiplication.
    fact = orders.merge(tables['customers'], on='customer_id', validate='one_to_one')
    fact = fact.merge(item_totals, on='order_id', how='left', validate='one_to_one')
    delivered = fact.loc[fact['order_status'].eq('delivered')].copy()
    delivered['actual_days'] = (delivered['order_delivered_customer_date'] - delivered['order_purchase_timestamp']).dt.total_seconds() / 86400
    delivered['delay_days'] = (delivered['order_delivered_customer_date'].dt.normalize() - delivered['order_estimated_delivery_date'].dt.normalize()).dt.days
    eligible = delivered.dropna(subset=['order_delivered_customer_date', 'order_estimated_delivery_date'])
    freq = delivered.groupby('customer_unique_id')['order_id'].nunique()
    rfm = {
        'scope': 'All raw orders with status delivered; before cleaning anomalous dates or period restriction',
        'customers': len(freq), 'repeat_customers': int(freq.gt(1).sum()),
        'repeat_customer_rate': float(freq.gt(1).mean()),
        'frequency_median': float(freq.median()), 'frequency_max': int(freq.max()),
    }
    save_csv(freq.value_counts().sort_index().rename_axis('delivered_order_count').reset_index(name='customers'),
             'customer_frequency_distribution.csv')
    fact['purchase_month'] = fact['order_purchase_timestamp'].dt.to_period('M').astype(str)
    monthly = fact.groupby('purchase_month').agg(orders=('order_id', 'size'),
                                                merchandise_value_all_statuses=('merchandise_value', 'sum'))
    monthly_delivered = fact.loc[fact['order_status'].eq('delivered')].groupby('purchase_month').agg(
        delivered_orders=('order_id', 'size'), delivered_merchandise_value=('merchandise_value', 'sum'))
    save_csv(monthly.join(monthly_delivered).reset_index(), 'monthly_coverage.csv')
    save_csv(orders['order_status'].value_counts().rename_axis('order_status').reset_index(name='orders'), 'order_status_counts.csv')

    reviews = tables['order_reviews']
    stats = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'raw_hash_checks': 'all passed', 'archive_bytes': manifest['archive_bytes'],
        'uncompressed_bytes': manifest['uncompressed_bytes'], 'file_count': len(summary),
        'order_count': len(orders), 'delivered_orders': len(delivered),
        'purchase_min': str(orders['order_purchase_timestamp'].min()),
        'purchase_max': str(orders['order_purchase_timestamp'].max()),
        'delivered_purchase_min': str(delivered['order_purchase_timestamp'].min()),
        'delivered_purchase_max': str(delivered['order_purchase_timestamp'].max()),
        'rfm_feasibility': rfm,
        'missing_customer_delivery_date_in_delivered': int(delivered['order_delivered_customer_date'].isna().sum()),
        'negative_actual_delivery_days': int(delivered['actual_days'].lt(0).sum()),
        'delivery_date_eligible_orders': len(eligible),
        'late_orders_calendar_day': int(eligible['delay_days'].gt(0).sum()),
        'late_rate_calendar_day': float(eligible['delay_days'].gt(0).mean()),
        'median_delivery_days': float(delivered['actual_days'].median()),
        'review_rows': len(reviews), 'review_duplicate_review_id_rows': int(reviews['review_id'].duplicated().sum()),
        'orders_with_multiple_review_rows': int(reviews.groupby('order_id').size().gt(1).sum()),
        'orders_with_multiple_items': int(items.groupby('order_id').size().gt(1).sum()),
        'orders_with_multiple_payment_rows': int(payments.groupby('order_id').size().gt(1).sum()),
        'orders_without_item_rows': int((~orders['order_id'].isin(items['order_id'])).sum()),
        'orders_without_payment_rows': int((~orders['order_id'].isin(payments['order_id'])).sum()),
        'money_comparison_orders': len(compared), 'money_difference_over_005_orders': len(mismatch),
        'money_max_absolute_difference': float(compared['difference'].abs().max()),
        'foreign_key_unmatched_non_null_rows_total': sum(x['unmatched_non_null_rows'] for x in relations),
    }
    (OUT / 'profile_summary.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [
        '# Olist数据初检报告', '',
        '本报告核对数据规模、质量和模型适用性，尚未进行正式清洗或得出经营结论。原始CSV保持不变。', '',
        '## 数据来源与规模', '',
        f"来源：{manifest['source_url']}；官方下载文件，无网页抓取。获取时间（UTC）：{manifest['downloaded_at_utc']}。",
        '授权：CC BY-NC-SA 4.0，发布成果时保留来源、非商业及相同方式共享要求。',
        f"压缩包 {manifest['archive_bytes']/1e6:.2f} MB；解压 {manifest['uncompressed_bytes']/1e6:.2f} MB（十进制）。9份CSV全部通过SHA-256复核，ZIP通过CRC检查。", '',
        '| 数据表 | 行数 | 字段数 | 文件MB | 完全重复行 |', '|---|---:|---:|---:|---:|',
    ]
    for row in summary:
        lines.append(f"| {row['table']} | {row['rows']:,} | {row['columns']} | {row['file_bytes']/1e6:.2f} | {row['exact_duplicate_rows']:,} |")
    lines += ['', '## 订单时间与样本口径', '',
        f"订单总数 {len(orders):,}；已交付订单 {len(delivered):,}。原始购买时间从 {stats['purchase_min']} 至 {stats['purchase_max']}。",
        f"已交付订单的购买时间从 {stats['delivered_purchase_min']} 至 {stats['delivered_purchase_max']}。",
        '检查monthly_coverage.csv后再锁定正式分析时间段。最早和最晚月份不能直接当完整月份做环比；同比仅比较双方均完整且覆盖口径一致的时期。', '',
        '## 多表关联与金额', '',
        f"订单多商品情况：{stats['orders_with_multiple_items']:,}单；多支付记录：{stats['orders_with_multiple_payment_rows']:,}单；多评论记录：{stats['orders_with_multiple_review_rows']:,}单。",
        f"review_id重复行 {stats['review_duplicate_review_id_rows']:,}，不能将review_id直接假定为唯一主键或直接去重。",
        f"可对账订单 {len(compared):,}；支付额与商品金额加运费差异超过0.05的订单 {len(mismatch):,}。逐单例外保存在payment_reconciliation_exceptions.csv，不能直接用支付额替换商品销售额。",
        f"无商品明细订单 {stats['orders_without_item_rows']:,}；无支付记录订单 {stats['orders_without_payment_rows']:,}。缺失不直接按0填补。",
        f"所检查外键的非空未匹配行合计 {stats['foreign_key_unmatched_non_null_rows_total']:,}，细节见foreign_key_checks.csv。",
        '正式分析先在各表内汇总到订单粒度，再做有基数校验的关联。商品金额=sum(price)，运费=sum(freight_value)，支付额=sum(payment_value)，金额单位为巴西雷亚尔BRL，不代表利润。', '',
        '## 客户分析适用性', '',
        f"在全部原始已交付订单中，独立客户 {len(freq):,}，至少购买两次的客户 {rfm['repeat_customers']:,}，占 {rfm['repeat_customer_rate']:.2%}；订单频次中位数 {rfm['frequency_median']:.0f}，最大值 {rfm['frequency_max']}。",
        '客户标识必须用customer_unique_id，customer_id是订单关联标识。该复购比例是数据观察窗口内的结果，不能外推为平台真实长期复购率。',
        'RFM可以计算，但F高度集中于1次，不能强制按四分位或声称存在均衡的八类客群。若使用，F优先考虑单次购买/重复购买的业务划分，并披露局限；同期群留存只做候选补充，不能预设它有明显差异。', '',
        '## 交付日期初检', '',
        f"已交付但缺少客户签收时间 {stats['missing_customer_delivery_date_in_delivered']:,}单；交付时间早于购买时间 {stats['negative_actual_delivery_days']:,}单。",
        f"签收与预计日期均有效的 {len(eligible):,}单中，按自然日比较的逾期订单 {stats['late_orders_calendar_day']:,}，占 {stats['late_rate_calendar_day']:.2%}。这是清洗前描述，不构成因果结论。",
        '物流与评价分析具备可用字段，可作为经营问题的候选重点。日期缺失、异常时间顺序及多评论选择规则需要在清洗阶段单独记录。', '',
        '## 下一步', '',
        '1. 确定订单粒度和商品粒度两份分析表，保留原始状态与质量标记。',
        '2. 核对各字段缺失的业务含义；统一日期类型；地理坐标表暂不加入主分析。',
        '3. 锁定完整且可比的分析时期；取消与不可用订单从销售主体分析中排除，另表披露。',
        '4. 暂定三种方法：趋势/同比环比、品类ABC、代表性日序列SARIMA；RFM暂不作为主线，配送与评价作为特色补充。预测须有回测、基线对照和95%区间。',
        '5. 形成10种模板与至少6张业务图的对应清单，再制作一张样图供检查。', '',
        '复现：python run_all.py。当前入口执行下载、初检与基础清洗；清洗见02_清洗口径与验证.md，模型、图表和大屏尚未实现。',
    ]
    (DOCS / '01_数据初检报告.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
