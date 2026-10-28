# M01 · 2.1线性回归

理解客户金额、客户响应或贷款营销的回归与样本外评分。

保留源模型、诊断及选择方法，修复指标口径与清洗不一致；模型选择和预处理只拟合训练范围，个人评分不公开。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab M01 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`m01_notebook`、`m01_input1`、`m01_input2`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_regression.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/M01/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/M01/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
