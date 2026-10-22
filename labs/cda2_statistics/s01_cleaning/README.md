# S01 数据整合和清洗

来源：CDA二级第4章《数据整合和数据清洗》Notebook。覆盖12个教学小节：文件读写、行列操作、查询、横向连接、纵向合并、排序、分组、透视、赋值、重复值、缺失值与噪声值处理。

```powershell
python labs/cda2_statistics/s01_cleaning/main.py --data-root "教材资料目录"
```

计算在[src/bda_labs/cleaning.py](../../../src/bda_labs/cleaning.py)，报告见[结果与解释](../../../docs/results/S01/report.md)。

输入：原sample.csv和data/big.csv。其余小表及随机样本来自教学演示，不代表真实客户。脚本把交互展示改为45份有编号的演示产物，检查分块读取一致、连接键与金额守恒，不覆盖教材write.csv。

盖帽、填补和按键去重是待选业务规则，实际项目需要另外说明原因；用于建模时只从训练数据学习参数。
