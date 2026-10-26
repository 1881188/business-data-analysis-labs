# B12 分省销售分析

识别订单头、商品明细和维表的粒度，回答不同省份、月份和商品类别的销售与利润问题。

```powershell
python run_labs.py --lab B12
python labs/cda1_business/b12_province/main.py --year 2020 --month 8 --output-root outputs/filtered
```

支持year、month、province、category参数。商品类别变化后，订单数按可见明细的订单ID去重计算；类别之间的订单数可能重叠。缺失雇员记录保留，不丢订单或金额。商品名重复时以商品ID区分。

保存的Power BI年份切片器与折线局部筛选范围不同，明确列为两份诊断；默认报告分析全量输入。查看[计算代码](../../../src/bda_labs/province_sales.py)、[报告](../../../docs/results/B12/report.md)和[模型说明](model.md)。
