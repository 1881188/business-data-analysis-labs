# M29 · 类别不平衡专题_课堂代码

理解类别不平衡的采样策略及类别特征插值风险。

保留六种合成采样及真实数据的SMOTE/SMOTENC、权重和更新步长比较；训练集重采样，测试集维持原分布。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab M29 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`m29_notebook`、`m29_input1`。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_balance.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/M29/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/M29/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
