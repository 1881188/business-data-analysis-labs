# M25 · 流程挖掘pm4py

从事件日志提取流程关系频次和环节耗时。

使用标准库 XML 解析 XES，验证导出回读及事件计数；按原始 trace 内事件顺序统计直接跟随图。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab M25 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`m25_notebook`、`m25_input1`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_process.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/M25/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/M25/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
