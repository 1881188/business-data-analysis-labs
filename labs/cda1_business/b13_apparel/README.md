# B13 服装零售经营分析

实现订单/明细星型模型、经营指标及同星期日变化、店铺与员工月目标、首次观察购买同期群。

```powershell
python run_labs.py --lab B13
```

按[数据准备说明](../../../data/README.md)提供本地教材。`--as-of YYYY-MM-DD`仅改变同日与7天前的比较日期，月目标和同期群仍用完整输入。默认采用输入最后交易日。

本案例源说明限制原资料及案例内容传播：仓库发布新增代码、方法说明和完全合成演示；真实结果、截图、订单及会员信息均留在本地`outputs/B13/`。本地`local_report.md`查看真实结果，`private_summary.json`查看核对及异常；公开合成图不会替代教材真实运行。

查看[实现](../../../src/bda_labs/apparel_analysis.py)、[方法报告及合成图](../../../docs/results/B13/report.md)和[模型说明](model.md)。
