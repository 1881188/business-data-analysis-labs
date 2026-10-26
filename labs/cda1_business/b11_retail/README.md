# B11 基础零售销售看板

从零售订单表重建销售看板：实际支付、订单数、销售数量、每单平均支付，以及日期、类别、城市和本地商品下钻表。支付按行汇总，不再乘数量；分母使用同一筛选范围内的唯一订单。

```powershell
python run_labs.py --lab B11
python labs/cda1_business/b11_retail/main.py --start-date 2022-04-01 --end-date 2022-04-07 --city 广州市 --output-root outputs/filtered
```

`--start-date`、`--end-date`、`--city`、`--category`支持筛选；结束日包含全天。无匹配时每单平均支付保留未知。过滤运行建议使用独立输出目录，以保留默认全量结果。

计算实现在[retail_dashboard.py](../../../src/bda_labs/retail_dashboard.py)。查看[结果报告](../../../docs/results/B11/report.md)、[静态看板](../../../docs/results/B11/retail_dashboard.png)和[离线交互看板](../../../docs/results/B11/dashboard.html)。HTML下载后可离线打开，日期、城市、类别筛选同步更新全部卡片与表格；GitHub预览不执行脚本。

Power BI两页9个容器均有迁移去向。订单卡片按保存的Function=5非空计数解释，另计算去重计数，不被过时的Min查询标签误导。没有地理坐标，用城市条形图表达；原类别图标题误写为城市，已按字段更正。原模型数值没有独立对账参考，状态为运行通过。
