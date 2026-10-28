# M03 · 2.3.1-2.3.2.主成分_因子分析_层次聚类(经济发展数据)

理解变量压缩、经济特征与客户细分，形成可解释的聚合画像。

保留标准化、主成分/旋转方向、稀疏性或聚类的教学目标。固定随机种子；旋转单位特征向量以保持 fa_kit 语义；不发布客户逐行得分。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab M03 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`m03_notebook`、`m03_input1`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_profiles.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/M03/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/M03/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
