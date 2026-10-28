# M14 · 1_XGBoost专题_课堂代码

理解模型、参数选择、解释与评估之间的关系。

保留各源主题的模型族和主要方法；实际搜索预算在报告公开。折内预处理、训练内验证及独立留出防止信息泄露；所有标签约定与抽样范围显式记录。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab M14 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`m14_notebook`、`m14_input1`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_supervised.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/M14/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/M14/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
