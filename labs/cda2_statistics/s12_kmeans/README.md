# S12 银行客户渠道分群

问题：以四种渠道计数建立描述性群像，理解标准化、旋转、分位数转换与聚类。

在仓库根目录运行：

```powershell
python run_labs.py --lab S12
```

[独立入口](main.py)调用[bank_segments.py](../../../src/bda_labs/bank_segments.py)。channel_features验证唯一ID和总数守恒，返回四渠道；rotate_channels保留3维单位方向。cluster显式固定种子与n_init，按中心排序标签。解释树只使用四渠道，排除ID与派生总数。

10万条客户记录，39项降维及偏度缓存值核对；原Kmeans未固定种子，不能逐客户核对旧分区。树在保留样本上的一致率只衡量它对既定聚类标签的拟合，不是业务真值准确率。

全部非空代码单元见[迁移对照](../../../docs/results/S12/notebook-map.md)，数据口径和结果解释见[报告](../../../docs/results/S12/report.md)。输入版本按SHA-256检查，教材原文件保持只读；客户明细只留本地outputs。
