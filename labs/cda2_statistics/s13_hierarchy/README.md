# S13 地区层次聚类

问题：从九指标提取两维旋转得分，理解欧氏压缩距离、Ward树与示例切树。

在仓库根目录运行：

```powershell
python run_labs.py --lab S13
```

[独立入口](main.py)调用[city_hierarchy.py](../../../src/bda_labs/city_hierarchy.py)。独立读取本章地区标签并核对提供的CSV。ward_scores只接受两列观察向量，再pdist和linkage；检查节点、成员数及高度单调。切树k=3/4为附加教学示例。

42项缓存按打印精度核对，18项方向权重另以3e-8绝对加相对容差核对；旋转保持保留空间距离，整树与参考CSV一致。第7章同名文件的地区标签顺序不同，不能复用其地区表。

全部非空代码单元见[迁移对照](../../../docs/results/S13/notebook-map.md)，数据口径和结果解释见[报告](../../../docs/results/S13/report.md)。输入版本按SHA-256检查，教材原文件保持只读；客户明细只留本地outputs。
