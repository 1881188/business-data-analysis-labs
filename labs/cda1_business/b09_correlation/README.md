# B09 相关分析与线性趋势

问题：教材给出x/y观测，分析线性与单调关系，并复算Excel散点图的线性趋势。

从仓库根目录运行：

```powershell
python run_labs.py --lab B09
```

[入口](main.py)调用[correlation.py](../../../src/bda_labs/correlation.py)。calculate检查有限、完整且非常量的成对数据，用linregress计算斜率、截距和Pearson，另外给出两种秩相关。main读取Excel原始/参考表，解析参考图中的舍入标签，按显示精度核对并输出图和聚合指标。

参考范围只有图中3项舍入系数；不能把样本内R²或相关系数解释成因果或样本外预测能力。来源没有单位字典，不自行补写业务含义。行级拟合结果只留本地。

见[结果报告](../../../docs/results/B09/report.md)。输入版本在config/datasets.json，客户明细和行级中间产物只留在本地outputs/B09。
