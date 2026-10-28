# F13 · 03-3-PageRank-Python实现

理解关系网络、路径搜索、中心性或交易圈社区。

采用 NetworkX 图模型；自编算法与独立库或数学恒等式核对。社区模型采用无权目标和固定种子，客户关系明细不公开。

## 运行

从仓库根目录执行，先准备本地配套材料并安装高级依赖：

```powershell
python -m pip install -r requirements-advanced-lock.txt
python run_labs.py --lab F13 --data-root "你的四套教材资料父目录"
```

输入文件与校验哈希见 [datasets.json](../../../config/datasets.json)，涉及登记键：`f13_notebook`；本条以明确标注的教学样例构造输入。

## 实现与交付

[入口代码](main.py)调用[计算模块](../../../src/bda_labs/advanced_networks.py)。每个非空代码单元的去向见[迁移对照](../../../docs/results/F13/notebook-map.md)，聚合结果、解释和验证边界见[结果报告](../../../docs/results/F13/report.md)。

模型搜索预算、抽样与数据限制见[三级与金融迁移说明](../../../docs/advanced-migration.md)。原文件只读，个人预测、网络边与模型留在本地 outputs；公开产物由白名单发布。
