# 数据来源与字段

主数据为[Olist在Kaggle发布的巴西电商公开数据](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)，2026年10月19日通过Kaggle官方下载端点获取，没有网页抓取。许可为CC BY-NC-SA 4.0，来源校验清单见[raw/source_manifest.json](raw/source_manifest.json)。版本号未独立核实，以ZIP和9份CSV的SHA-256标识本次副本。

原始99,441笔订单、112,650条商品明细。分析采用2017-01-01至2018-07-31的89,860笔合格已交付订单，没有抽样，也未用AI或Faker补充交易。

原始ZIP、CSV及清洗明细不上传GitHub。`python run_all.py`从官方端点下载并生成；官方端点若要求登录，可在官方数据页下载ZIP并保存为`data/raw/brazilian-ecommerce.zip`后重试。

| 表 | 粒度与主要字段 | 关联 |
|---|---|---|
| orders | 每订单一行；order_id、customer_id、状态和购买/签收/预计日期 | 订单主键；customer_id关联customers |
| order_items | 每订单商品行；order_id、order_item_id、product_id、price、freight_value | 联合主键；product_id关联products |
| customers | 每订单客户标识一行；customer_id、customer_unique_id、customer_state | 唯一客户标识用于跨订单去重 |
| products与类别翻译 | 商品ID、葡语类别及英文类别名 | 多对一关联；缺失类别保留unknown_category |
| payments | 每订单支付序号一行；金额与方式 | 先汇总到订单再关联，避免多对多放大 |
| reviews | 每条评价；订单ID、1—5分、创建与答复日期 | 同单优先保留最新答复；另作最早评价敏感性核对 |

邮编级地理位置和卖家表随原始ZIP完整保留，但本分析不使用精细地理位置。日期统一解析；商品金额换算整数分后汇总，BRL为巴西雷亚尔。
