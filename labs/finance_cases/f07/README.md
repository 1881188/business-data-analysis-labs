# F07 · 第6章贷中信用风险预测模型（B卡）代码通过

理解Vintage、A卡或B卡的业务口径与风险建模流程。

离线重建SQL备份、账户观察窗口、分箱WOE和评分卡；核查关联与成熟账龄。只发布聚合统计，不发布客户行或数据库连接信息。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab F07 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`f07_notebook`、`f07_input1`、`f07_input2`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_finance.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/F07/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/F07/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
