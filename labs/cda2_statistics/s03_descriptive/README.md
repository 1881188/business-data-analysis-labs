# S03 描述性统计与绘图

问题：描述price的典型水平和离散程度，比较AREA与price的线性、秩相关。

从仓库根目录运行：

```powershell
python run_labs.py --lab S03
```

[入口](main.py)调用[descriptive.py](../../../src/bda_labs/descriptive.py)。describe_price计算均值、中位数、ddof=1方差/标准差、线性插值分位数和三种相关。main读取原Notebook缓存，逐项比较显示精度，并用整数有理数公式独立复算price方差。

全部14个非空代码单元均有迁移对照。旧方差缓存末位存在细微差异，实际差值、独立复算和容差已公开。正态模拟现固定种子，不强行匹配旧随机数。12项缓存核对包含重复标准差检查，来源没有单位字典与采样时间。

见[逐单元格迁移对照](../../../docs/results/S03/notebook-map.md)。

见[结果报告](../../../docs/results/S03/report.md)。输入版本在config/datasets.json，客户明细和行级中间产物只留在本地outputs/S03。
