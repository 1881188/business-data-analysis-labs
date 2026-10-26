# B02 函数、查找与透视

问题：把函数意图与边界迁移到Python，明确缓存、条件筛选、近似分档与引用语义。

在仓库根目录运行：

```powershell
python run_labs.py --lab B02
```

[独立入口](main.py)调用[spreadsheet_functions.py](../../../src/bda_labs/spreadsheet_functions.py)。excel_semantics处理十进制舍入、工作日、精确/近似查找、OFFSET和双收费口径；simple_examples只实现已核查标量演示，绝不eval原公式。CacheChecks要求每个保存公式都有去向；summarize_pivots读取实际济南筛选。

31张工作表、292个保存公式均有映射；363项缓存值一致，2个随机格不逐值比较。两个ROUND精度不同且缓存都正确；OR错引文字列在当前样本中恰好未造成结果差异。62条错误商品键先隔离，真实查询100条。条件格式与切片器以显式逻辑和图表迁移，未承诺原生UI效果。

结果、教材差异与边界见[实验报告](../../../docs/results/B02/report.md)。原始工作簿、CSV和PBIX只读；客户、学生、手机号及订单级数据仅留本地outputs。公开内容按允许列表发布。
