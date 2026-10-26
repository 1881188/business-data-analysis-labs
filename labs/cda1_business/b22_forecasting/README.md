# B22 效应分解与预测

```powershell
python run_labs.py --lab B22
```

[计算模块](../../../src/bda_labs/effect_forecasting.py) · [分解、回测和预测结果](../../../docs/results/B22/report.md)

AIR按月、两份信用卡序列按日分别建模。居中分解只解释历史，回测模型仅以前段训练；季节朴素与原尺度/log趋势季节模型比较，未来预测另用全历史重拟合。WPS保存预测不是未来真实值，原算法未知不猜参数。短样本、不同单位和条件预测区间的限制如实记录。
