# S06 电信主成分分析

问题：用四种业务使用量作描述性降维，理解标准化、主成分方向与白化后的得分。

从仓库根目录运行：

```powershell
python run_labs.py --lab S06
```

[入口](main.py)调用[pca_telecom.py](../../../src/bda_labs/pca_telecom.py)。main显式选择cnt_call/cnt_msg/cnt_wei/cnt_web，ID不入模。共享standardized_pca先用ddof=0标准化，再用完整SVD估计样本主成分；保持源whiten=True，检查全部得分的样本协方差为单位矩阵。

28项缓存数值核对包含源显示前后三行的12个得分。中间594行原缓存省略，不能声称全量对账。代码另独立检查所有得分。主成分方向和白化系数分列，客户级得分只留本地。

全部非空代码单元见[迁移对照](../../../docs/results/S06/notebook-map.md)，完整解释见[结果报告](../../../docs/results/S06/report.md)。源文件通过相对路径和SHA-256识别，原始资料不改写。
