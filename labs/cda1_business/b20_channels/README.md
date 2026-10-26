# B20 银行申请渠道贡献分解

```powershell
python run_labs.py --lab B20
```

[计算模块](../../../src/bda_labs/channel_attribution.py) · [结果与参考纠错](../../../docs/results/B20/report.md)

一行一个申请编号。以月份和渠道计数，增量/净变化、增量/上月总量分开命名；渠道迁移、申请增长与转化并非同一指标。参考副本核对但不重复计数，错误总计和贡献符号保留诊断。渠道贡献是加法分解，不证明数字化或路径改造的因果效果。
