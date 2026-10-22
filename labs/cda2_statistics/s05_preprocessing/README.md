# S05 收入零值与缺失审计

问题：按教材规则识别AvgIncome中的伪有效值，并量化对有效样本量和描述统计的影响。

从仓库根目录运行：

```powershell
python run_labs.py --lab S05
```

[入口](main.py)调用[preprocessing.py](../../../src/bda_labs/preprocessing.py)。clean_income复制输入，记录AvgIncome_was_zero，把收入0转为np.nan。main检查行数、缺失增量和非收入字段不变，核对原Notebook缓存，输出前后统计与缺失审计。

全部6个非空代码单元均有迁移对照。仅处理本案例明确声明的收入0；房屋价值0保留待核实，Age/ARPU原缺失不填补。24项缓存值包含重复房屋价值检查；清洗后收入没有describe参考输出，仅做本实现守恒检查。均值变化不能解释为收入增长。

见[逐单元格迁移对照](../../../docs/results/S05/notebook-map.md)。

见[结果报告](../../../docs/results/S05/report.md)。输入版本在config/datasets.json，客户明细和行级中间产物只留在本地outputs/S05。
