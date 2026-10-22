# S08 消费额方差分析

问题：比较教育/性别分组的观察消费额，并区分真实零、未观察响应及不可识别交互。

从仓库根目录运行：

```powershell
python run_labs.py --lab S08
```

[入口](main.py)调用[anova_expenses.py](../../../src/bda_labs/anova_expenses.py)。prepare_expenses建立观察样本和教材空白填0两套分支。fit_estimable先查设计矩阵满秩再拟合；fit_observed_models输出真正的单因素、加性及观察单元均值模型。robust_observed_interaction只检验可识别的交互对比，使用HC3协方差。

主分析70条，30条空白不填0。空组合使标准交互设计8列只有秩7；观察单元可检验2个增量自由度。数据提示方差不齐，经典交互p约0.042、HC3约0.207，不能只看一个阈值。25项教材兼容数值另行核对，主流程状态为运行通过。

全部非空代码单元见[迁移对照](../../../docs/results/S08/notebook-map.md)，完整解释见[结果报告](../../../docs/results/S08/report.md)。源文件通过相对路径和SHA-256识别，原始资料不改写。
