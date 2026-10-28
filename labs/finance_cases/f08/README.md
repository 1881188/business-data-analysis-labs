# F08 · 第8章申请反欺诈模型代码通过

结合收入一致性和申请时点的关系网络理解反欺诈建模。

重建按日关系特征、训练内异常特征和多模型搜索；已披露历史风险与申请者自身结果分离，所有个人关系与评分留在本地。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab F08 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`f08_notebook`、`f08_input1`、`f08_input2`、`f08_input3`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_financial_fraud.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/F08/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/F08/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
