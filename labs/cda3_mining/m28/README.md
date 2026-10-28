# M28 · Feature-engineering

理解数据清洗、表示、降维和特征筛选的各类方法。

逐项重建源演示，增加编码、归一化和白化恒等式校验；这是样本内教学分析，不声称模型泛化。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab M28 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`m28_notebook`、`m28_input1`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_features.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/M28/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/M28/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
