"""Shared, testable filter/aggregation logic. Monetary computations use cents."""
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
START,END='2017-01-01','2018-07-31'
CATEGORY_NAMES={'health_beauty':'美妆健康','watches_gifts':'手表与礼品','bed_bath_table':'床品卫浴',
 'sports_leisure':'运动休闲','computers_accessories':'电脑配件','furniture_decor':'家具装饰',
 'cool_stuff':'创意商品','housewares':'家居用品','auto':'汽车用品','garden_tools':'园艺工具',
 'unknown_category':'类别缺失'}
STATE_NAMES={'SP':'圣保罗州','RJ':'里约热内卢州','MG':'米纳斯吉拉斯州','RS':'南里奥格兰德州',
 'PR':'巴拉那州','SC':'圣卡塔琳娜州','BA':'巴伊亚州','DF':'联邦区'}


class DashboardData:
    def __init__(self):
        order_cols=['order_id','customer_unique_id','order_purchase_timestamp','customer_state',
                    'merchandise_value_cents','delivery_days','logistics_eligible',
                    'late_delivery_flag','review_eligible','review_score','sales_eligible']
        item_cols=['order_id','order_item_id','category_display','price_cents','sales_eligible']
        self.orders=pd.read_csv(ROOT/'data/clean/orders_fact.csv',usecols=order_cols)
        self.orders=self.orders.loc[self.orders['sales_eligible']].copy()
        self.orders['purchase']=pd.to_datetime(self.orders['order_purchase_timestamp'])
        self.orders['merchandise_value_cents']=self.orders['merchandise_value_cents'].astype('int64')
        self.items=pd.read_csv(ROOT/'data/clean/order_items_fact.csv',usecols=item_cols)
        self.items=self.items.loc[self.items['sales_eligible']].copy()
        self.items['price_cents']=self.items['price_cents'].astype('int64')
        if self.orders['order_id'].duplicated().any():
            raise ValueError('Order grain must be unique')
        if int(self.orders['merchandise_value_cents'].sum())!=int(self.items['price_cents'].sum()):
            raise ValueError('Order/item money mismatch')
        self.states=sorted(self.orders['customer_state'].unique())
        totals=self.items.groupby('category_display')['price_cents'].sum().sort_values(ascending=False)
        self.categories=list(totals.index)

    def select(self,start=START,end=END,states=None,categories=None):
        begin=pd.Timestamp(start or START).normalize()
        finish=pd.Timestamp(end or END).normalize()+pd.Timedelta(days=1)
        mask=self.orders['purchase'].ge(begin)&self.orders['purchase'].lt(finish)
        if states:
            mask &= self.orders['customer_state'].isin(states)
        orders=self.orders.loc[mask].copy()
        items=self.items.loc[self.items['order_id'].isin(orders['order_id'])].copy()
        if categories:
            items=items.loc[items['category_display'].isin(categories)].copy()
        grouped=items.groupby('order_id').agg(selected_cents=('price_cents','sum'),selected_items=('order_item_id','size'))
        orders=orders.merge(grouped,on='order_id',how='inner',validate='one_to_one')
        if int(orders['selected_cents'].sum())!=int(items['price_cents'].sum()):
            raise ValueError('Filtered revenue mismatch')
        logistics=orders.loc[orders['logistics_eligible']]
        reviews=orders.loc[orders['review_eligible']]
        monthly=orders.assign(month=orders['purchase'].dt.to_period('M').astype(str)).groupby('month').agg(
            cents=('selected_cents','sum'),orders=('order_id','size')).reset_index()
        cats=items.groupby('category_display').agg(cents=('price_cents','sum'),items=('order_item_id','size')).reset_index().sort_values('cents',ascending=False)
        regions=orders.groupby('customer_state').agg(cents=('selected_cents','sum'),orders=('order_id','size')).reset_index().sort_values('cents',ascending=False)
        ratings=reviews.assign(low=reviews['review_score'].le(2)).groupby('late_delivery_flag').agg(
            orders=('order_id','size'),score=('review_score','mean'),low_rate=('low','mean')).reset_index()
        total=int(orders['selected_cents'].sum())
        metrics={'revenue_cents':total,'orders':len(orders),'items':len(items),
                 'customers':int(orders['customer_unique_id'].nunique()),
                 'aov_brl':total/100/len(orders) if len(orders) else None,
                 'late_rate':float(logistics['late_delivery_flag'].mean()) if len(logistics) else None,
                 'logistics_orders':len(logistics),'review_orders':len(reviews),
                 'mean_score':float(reviews['review_score'].mean()) if len(reviews) else None}
        return {'orders':orders,'items':items,'monthly':monthly,'categories':cats,'states':regions,
                'ratings':ratings,'metrics':metrics,'category_filtered':bool(categories)}

    @staticmethod
    def export_view(result):
        orders=result['orders'].copy().sort_values(['purchase','order_id'],ascending=[False,True])
        orders['selected_amount_brl']=orders['selected_cents']/100
        orders['whole_order_brl']=orders['merchandise_value_cents']/100
        columns=['order_id','order_purchase_timestamp','customer_state','selected_amount_brl',
                 'whole_order_brl','selected_items','delivery_days','late_delivery_flag','review_score']
        return orders[columns].rename(columns={'order_id':'订单ID','order_purchase_timestamp':'购买时间',
          'customer_state':'收货州','selected_amount_brl':'所选商品金额_BRL','whole_order_brl':'整单商品金额_BRL',
          'selected_items':'所选商品件数','delivery_days':'配送天数','late_delivery_flag':'是否逾期','review_score':'评分'})
