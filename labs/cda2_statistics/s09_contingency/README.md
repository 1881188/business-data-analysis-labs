# S09 列联表检验

问题：比较bankruptcy_ind与bad_ind的样本关联，理解展示合计、真实观测与检验自由度。

从仓库根目录运行：

```powershell
python run_labs.py --lab S09
```

[入口](main.py)调用[contingency.py](../../../src/bda_labs/contingency.py)。main对217条缺失单独记账，采用5628条完整记录。analyze_table拒绝All合计、非整数伪频数和空边际，输出未校正Pearson、Yates、Fisher与Cramér V。展示表和检验表分开保存。

含合计的错误旧流程只在INVALID诊断分支保留，并核对30个源缓存数值。正确2×2 Pearson自由度为1，p约0.088；旧3×3错误自由度4、p约0.572。weight定义未提供，未加权样本比例不当作总体坏账概率。

全部非空代码单元见[迁移对照](../../../docs/results/S09/notebook-map.md)，完整解释见[结果报告](../../../docs/results/S09/report.md)。源文件通过相对路径和SHA-256识别，原始资料不改写。
