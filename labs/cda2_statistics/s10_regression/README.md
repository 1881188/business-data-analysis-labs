# S10 信用卡消费线性回归

问题：用已观察消费额解释条件关联，比较原额、对数、二次项和交互项模型。

在仓库根目录运行：

```powershell
python run_labs.py --lab S10
```

[独立入口](main.py)调用[linear_expenses.py](../../../src/bda_labs/linear_expenses.py)。prepare将真实响应与教材填均值分支分开；formulas保留5个教学变体。cross_validate逐折拟合编码与标准化，对数回变换只用训练残差估计修正。

正式样本70条，不填6个缺失响应；5个教材兼容OLS的89项系数/统计量与8个VIF另行核对。70条的5折比较没有独立最终测试集；某折小学及以下类别在训练中缺失，回退基线的局限见报告。

全部非空代码单元见[迁移对照](../../../docs/results/S10/notebook-map.md)，数据口径和结果解释见[报告](../../../docs/results/S10/report.md)。输入版本按SHA-256检查，教材原文件保持只读；客户明细只留本地outputs。
