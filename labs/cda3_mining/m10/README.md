# M10 · 上课版-银行产品交叉销售分析-mlxtendApriori copy

用银行产品篮子和订单先后关系发现交叉销售模式。

独立实现精确 Apriori 与完整有序项集模式增长，替换旧包和辅助脚本。以客户数作为支持度分母，不把订单内共现误记为先后。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab M10 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`m10_notebook`、`m10_input1`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_rules.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/M10/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/M10/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
