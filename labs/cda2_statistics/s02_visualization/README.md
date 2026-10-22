# S02 Python数据可视化

问题：把价格、类别占比、分布和二元关系转成合适图形，说明真实配套数据与模拟数据的区别。

从仓库根目录运行：

```powershell
python run_labs.py --lab S02
```

[入口](main.py)调用[visualization.py](../../../src/bda_labs/visualization.py)。prepare_stock检查日期/OHLC关系并按时间排序；demonstration_data用局部RandomState保留源Notebook种子随机流；main按教学顺序生成13幅PNG，核对投票份额与直方图计数守恒。

全部22个非空代码单元均有迁移对照。旧seaborn图形采用matplotlib/scipy实现同类图，KDE直方图统一使用概率密度纵轴。随机热图不是相关矩阵，模拟投票不是调研结论。无图形界面也能运行。

见[逐单元格迁移对照](../../../docs/results/S02/notebook-map.md)。

见[结果报告](../../../docs/results/S02/report.md)。输入版本在config/datasets.json，客户明细和行级中间产物只留在本地outputs/S02。
