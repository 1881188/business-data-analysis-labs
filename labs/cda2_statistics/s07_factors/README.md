# S07 地区主成分旋转

问题：将九项地区经济指标提取为两维，理解旋转如何改善方向的解释。

从仓库根目录运行：

```powershell
python run_labs.py --lab S07
```

[入口](main.py)调用[region_factors.py](../../../src/bda_labs/region_factors.py)。principal_rotation先提取两列单位特征向量，用statsmodels做varimax。检查旋转正交、投影子空间和总保留方差不变，再以Z乘方向矩阵算得分。main分别输出方向系数、变量得分相关及地区得分。

保持教材fa_kit的主成分提取语义，没有改换为最大似然共同因子模型。148项缓存值核对含全部18个旋转权重、20个地区得分。正交方向不保证得分不相关；原资料无明确年度与单位，不能当作当前地区排名。

全部非空代码单元见[迁移对照](../../../docs/results/S07/notebook-map.md)，完整解释见[结果报告](../../../docs/results/S07/report.md)。源文件通过相对路径和SHA-256识别，原始资料不改写。
