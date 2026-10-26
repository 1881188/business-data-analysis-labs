# B14 人力资源分析

按日期事件重建任职区间，区分来源总人数、期内曾任职、入职、离职和期末在职，不把源快照状态当历史状态。

```powershell
python run_labs.py --lab B14
python labs/cda1_business/b14_hr/main.py --start-date 2022-01-01 --end-date 2022-06-30 --output-root outputs/filtered
```

默认起点读取PBIX保存的日期切片器，终点为源最后入/离职事件；不使用TODAY，不外推事件边界之后。可选`--department`。采用[入职日,离职日)，离职日不计日末在职；同日入离职两项事件均保留。人天用独立日枚举核对，月份期初/期末连续。

查看[实现](../../../src/bda_labs/hr_workforce.py)和[结果及日期口径](../../../docs/results/B14/report.md)。公开仅聚合；员工姓名、工号、生日和任期明细只保存在本地`outputs/B14/employees_private.csv`。Power BI隐藏DAX和年龄分组未解码，Python规则明示，不宣称全部源度量逐值对账。
