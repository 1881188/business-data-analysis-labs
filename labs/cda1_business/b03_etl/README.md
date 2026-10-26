# B03 ETL清洗、拆列与合并

问题：区分全空白行、错误与真实零，理解拆列与追加对统计粒度的影响。

在仓库根目录运行：

```powershell
python run_labs.py --lab B03
```

[独立入口](main.py)调用[etl_tables.py](../../../src/bda_labs/etl_tables.py)。clean_orders从读取缓存时保留Excel错误，再记录源行号；split_records保持2行原数量，另建不带可加度量的6行订单桥；join_courses用选课事实与唯一维表关联，append_aligned要求显式字段映射。

11张工作表含2张空表。保留27条明细和4条真实零支付，7个错误单元格有单独记录。源ip地址实际不是IP，未猜测替换。季度金额映射后1212，直接追加漏计406；8件和10本不能因拆订单重复三倍。

结果、教材差异与边界见[实验报告](../../../docs/results/B03/report.md)。原始工作簿、CSV和PBIX只读；客户、学生、手机号及订单级数据仅留本地outputs。公开内容按允许列表发布。
