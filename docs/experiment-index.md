# 实验索引

目前79个编号入口已运行，其中14个完成指定参考核对（B04, B05, B06, B07, B08, B09, B16, B17, B18, B20, S03, S05, S06, S07）。F04是F05的重复检查点，共享实现，不计额外业务案例。一级为22个规划实施单元；二级13/13、三级29/29、金融15/16份Notebook来源已运行（金融含这份重复来源）。F01缺少原输入，仍待补资料。核对范围与差异见各报告，不计算跨口径的混合完成率。

素材覆盖：572份文件，58份Notebook、9份已有Python辅助文件、65份Excel；插件和阅读资料不按独立实验验收。所有来源见[source-map.csv](source-map.csv)。


## 1《CDA 一级认证教材：商业数据分析》

| ID | 实验/来源名称 | 状态 | 实现与结果 |
|---|---|---|---|
| B01 | 关系与维度数据模型 | 运行通过 | [代码](../labs/cda1_business/b01_models/main.py) · [报告](results/B01/report.md) |
| B02 | Excel与WPS函数、查找与透视 | 运行通过 | [代码](../labs/cda1_business/b02_functions/main.py) · [报告](results/B02/report.md) |
| B03 | ETL清洗、拆分与合并 | 运行通过 | [代码](../labs/cda1_business/b03_etl/main.py) · [报告](results/B03/report.md) |
| B04 | 波士顿矩阵 | 参考核对通过 | [代码](../labs/cda1_business/b04_bcg/main.py) · [报告](results/B04/report.md) |
| B05 | RFM客户价值分层 | 参考核对通过 | [代码](../labs/cda1_business/b05_rfm/main.py) · [报告](results/B05/report.md) |
| B06 | 用户忠诚度模型 | 参考核对通过 | [代码](../labs/cda1_business/b06_loyalty/main.py) · [报告](results/B06/report.md) |
| B07 | 同期群日留存 | 参考核对通过 | [代码](../labs/cda1_business/b07_cohort/main.py) · [报告](results/B07/report.md) |
| B08 | 转化漏斗 | 参考核对通过 | [代码](../labs/cda1_business/b08_funnel/main.py) · [报告](results/B08/report.md) |
| B09 | 相关分析 | 参考核对通过 | [代码](../labs/cda1_business/b09_correlation/main.py) · [报告](results/B09/report.md) |
| B10 | 六类分析方法 | 运行通过 | [代码](../labs/cda1_business/b10_methods/main.py) · [报告](results/B10/report.md) |
| B11 | 基础零售销售看板 | 运行通过 | [代码](../labs/cda1_business/b11_retail/main.py) · [报告](results/B11/report.md) |
| B12 | 分省销售分析 | 运行通过 | [代码](../labs/cda1_business/b12_province/main.py) · [报告](results/B12/report.md) |
| B13 | 服装零售经营分析 | 运行通过 | [代码](../labs/cda1_business/b13_apparel/main.py) · [报告](results/B13/report.md) |
| B14 | 人力资源分析 | 运行通过 | [代码](../labs/cda1_business/b14_hr/main.py) · [报告](results/B14/report.md) |
| B15 | 学生考试多表分析 | 运行通过 | [代码](../labs/cda1_business/b15_exams/main.py) · [报告](results/B15/report.md) |
| B16 | 收入趋势分析 | 参考核对通过 | [代码](../labs/cda1_business/b16_income/main.py) · [报告](results/B16/report.md) |
| B17 | 财务费用分解 | 参考核对通过 | [代码](../labs/cda1_business/b17_expenses/main.py) · [报告](results/B17/report.md) |
| B18 | 电商精准营销 | 参考核对通过 | [代码](../labs/cda1_business/b18_marketing/main.py) · [报告](results/B18/report.md) |
| B19 | 银行产品业务看板 | 运行通过 | [代码](../labs/cda1_business/b19_bank_products/main.py) · [报告](results/B19/report.md) |
| B20 | 银行申请渠道归因 | 参考核对通过 | [代码](../labs/cda1_business/b20_channels/main.py) · [报告](results/B20/report.md) |
| B21 | SQL与客户画像 | 运行通过 | [代码](../labs/cda1_business/b21_profiles/main.py) · [报告](results/B21/report.md) |
| B22 | 效应分解与预测 | 运行通过 | [代码](../labs/cda1_business/b22_forecasting/main.py) · [报告](results/B22/report.md) |

## 2《CDA 二级认证教材：量化策略分析》

| ID | 实验/来源名称 | 状态 | 实现与结果 |
|---|---|---|---|
| S01 | 第4章  数据整合和数据清洗 | 运行通过 | [代码](../labs/cda2_statistics/s01_cleaning/main.py) · [报告](results/S01/report.md) |
| S02 | 第5章 python数据可视化 | 运行通过 | [代码](../labs/cda2_statistics/s02_visualization/main.py) · [报告](results/S02/report.md) |
| S03 | 第5章 描述性统计分析与绘图 | 参考核对通过 | [代码](../labs/cda2_statistics/s03_descriptive/main.py) · [报告](results/S03/report.md) |
| S04 | 抽样 | 运行通过 | [代码](../labs/cda2_statistics/s04_sampling/main.py) · [报告](results/S04/report.md) |
| S05 | 数据预处理 | 参考核对通过 | [代码](../labs/cda2_statistics/s05_preprocessing/main.py) · [报告](results/S05/report.md) |
| S06 | 在 Python 中实现主成分分析 | 参考核对通过 | [代码](../labs/cda2_statistics/s06_pca/main.py) · [报告](results/S06/report.md) |
| S07 | 在 Python 中实现因子分析 | 参考核对通过 | [代码](../labs/cda2_statistics/s07_factors/main.py) · [报告](results/S07/report.md) |
| S08 | 方差分析 | 运行通过 | [代码](../labs/cda2_statistics/s08_anova/main.py) · [报告](results/S08/report.md) |
| S09 | 列联表分析 | 运行通过 | [代码](../labs/cda2_statistics/s09_contingency/main.py) · [报告](results/S09/report.md) |
| S10 | 线性回归 | 运行通过 | [代码](../labs/cda2_statistics/s10_regression/main.py) · [报告](results/S10/report.md) |
| S11 | 逻辑回归 | 运行通过 | [代码](../labs/cda2_statistics/s11_churn/main.py) · [报告](results/S11/report.md) |
| S12 | Kmeans 的应用 - 用户细分 | 运行通过 | [代码](../labs/cda2_statistics/s12_kmeans/main.py) · [报告](results/S12/report.md) |
| S13 | hc_city10 | 运行通过 | [代码](../labs/cda2_statistics/s13_hierarchy/main.py) · [报告](results/S13/report.md) |

## 3《CDA 三级认证教材：敏捷数据挖掘》

| ID | 实验/来源名称 | 状态 | 实现与结果 |
|---|---|---|---|
| M01 | 2.1线性回归 | 运行通过 | [代码](../labs/cda3_mining/m01/main.py) · [报告](results/M01/report.md) |
| M02 | 2.2逻辑回归 | 运行通过 | [代码](../labs/cda3_mining/m02/main.py) · [报告](results/M02/report.md) |
| M03 | 2.3.1-2.3.2.主成分_因子分析_层次聚类(经济发展数据) | 运行通过 | [代码](../labs/cda3_mining/m03/main.py) · [报告](results/M03/report.md) |
| M04 | 2.3.1主成分分析(Loan_aplya打分) | 运行通过 | [代码](../labs/cda3_mining/m04/main.py) · [报告](results/M04/report.md) |
| M05 | 2.3.3变量聚类 | 运行通过 | [代码](../labs/cda3_mining/m05/main.py) · [报告](results/M05/report.md) |
| M06 | 2.3.4层次聚类(经济发展数据) | 运行通过 | [代码](../labs/cda3_mining/m06/main.py) · [报告](results/M06/report.md) |
| M07 | 2.3.5Kmeans聚类用户细分 | 运行通过 | [代码](../labs/cda3_mining/m07/main.py) · [报告](results/M07/report.md) |
| M08 | 2.4.1.关联规则（银行产品交叉销售分析） | 运行通过 | [代码](../labs/cda3_mining/m08/main.py) · [报告](results/M08/report.md) |
| M09 | 2.4.2.序列模式（银行产品交叉销售分析） | 运行通过 | [代码](../labs/cda3_mining/m09/main.py) · [报告](results/M09/report.md) |
| M10 | 上课版-银行产品交叉销售分析-mlxtendApriori copy | 运行通过 | [代码](../labs/cda3_mining/m10/main.py) · [报告](results/M10/report.md) |
| M11 | 课后答案版-银行产品交叉销售分析-mlxtendApriori | 运行通过 | [代码](../labs/cda3_mining/m11/main.py) · [报告](results/M11/report.md) |
| M12 | 3.1.1-3.1.2分类（反欺诈_DT_EnsembleMethods） | 运行通过 | [代码](../labs/cda3_mining/m12/main.py) · [报告](results/M12/report.md) |
| M13 | 3.1.3-3.1.6分类（反欺诈_KNN_NB _SVM_MLP） | 运行通过 | [代码](../labs/cda3_mining/m13/main.py) · [报告](results/M13/report.md) |
| M14 | 1_XGBoost专题_课堂代码 | 运行通过 | [代码](../labs/cda3_mining/m14/main.py) · [报告](results/M14/report.md) |
| M15 | 2_LightGBM专题_课堂代码 | 运行通过 | [代码](../labs/cda3_mining/m15/main.py) · [报告](results/M15/report.md) |
| M16 | 3_模型解释性专题_课堂代码 | 运行通过 | [代码](../labs/cda3_mining/m16/main.py) · [报告](results/M16/report.md) |
| M17 | 3.2违规识别(IsolationForrest_LOF无监督) | 运行通过 | [代码](../labs/cda3_mining/m17/main.py) · [报告](results/M17/report.md) |
| M18 | 4.1.1销售数据预测(趋势分解法-不建议学习) | 运行通过 | [代码](../labs/cda3_mining/m18/main.py) · [报告](results/M18/report.md) |
| M19 | 4.1.2销售数据预测(SARIMA) | 运行通过 | [代码](../labs/cda3_mining/m19/main.py) · [报告](results/M19/report.md) |
| M20 | 4.1.3股价预测(LSTM) | 运行通过 | [代码](../labs/cda3_mining/m20/main.py) · [报告](results/M20/report.md) |
| M21 | ARIMA | 运行通过 | [代码](../labs/cda3_mining/m21/main.py) · [报告](results/M21/report.md) |
| M22 | 4.2.1线性规划 | 运行通过 | [代码](../labs/cda3_mining/m22/main.py) · [报告](results/M22/report.md) |
| M23 | 4.2.2整数规划 | 运行通过 | [代码](../labs/cda3_mining/m23/main.py) · [报告](results/M23/report.md) |
| M24 | 4.2.3二次规划 | 运行通过 | [代码](../labs/cda3_mining/m24/main.py) · [报告](results/M24/report.md) |
| M25 | 流程挖掘pm4py | 运行通过 | [代码](../labs/cda3_mining/m25/main.py) · [报告](results/M25/report.md) |
| M26 | 5.1 模型参数优化方法 | 运行通过 | [代码](../labs/cda3_mining/m26/main.py) · [报告](results/M26/report.md) |
| M27 | 5.2&3 pipeline_保险案例 | 运行通过 | [代码](../labs/cda3_mining/m27/main.py) · [报告](results/M27/report.md) |
| M28 | Feature-engineering | 运行通过 | [代码](../labs/cda3_mining/m28/main.py) · [报告](results/M28/report.md) |
| M29 | 类别不平衡专题_课堂代码 | 运行通过 | [代码](../labs/cda3_mining/m29/main.py) · [报告](results/M29/report.md) |

## 4《金融数据分析和数据挖掘案例实战》

| ID | 实验/来源名称 | 状态 | 实现与结果 |
|---|---|---|---|
| F01 | test | 待补资料 | 缺少 data12261.csv；待数据验证入口：[代码](../labs/finance_cases/f01/main.py) |
| F02 | 第二章某银行贷款产品精准营销模型代码通过 | 运行通过 | [代码](../labs/finance_cases/f02/main.py) · [报告](results/F02/report.md) |
| F03 | 第3章多维特征的客户细分代码通过 | 运行通过 | [代码](../labs/finance_cases/f03/main.py) · [报告](results/F03/report.md) |
| F04 | Vintage-checkpoint | 运行通过 | [代码](../labs/finance_cases/f04/main.py) · [报告](results/F04/report.md) |
| F05 | Vintage | 运行通过 | [代码](../labs/finance_cases/f05/main.py) · [报告](results/F05/report.md) |
| F06 | 第5章贷前信用风险预测模型（A卡）代码通过 | 运行通过 | [代码](../labs/finance_cases/f06/main.py) · [报告](results/F06/report.md) |
| F07 | 第6章贷中信用风险预测模型（B卡）代码通过 | 运行通过 | [代码](../labs/finance_cases/f07/main.py) · [报告](results/F07/report.md) |
| F08 | 第8章申请反欺诈模型代码通过 | 运行通过 | [代码](../labs/finance_cases/f08/main.py) · [报告](results/F08/report.md) |
| F09 | 第9章算法工程化代码通过 | 运行通过 | [代码](../labs/finance_cases/f09/main.py) · [报告](results/F09/report.md) |
| F10 | 02-社交网络-基本理论CODE | 运行通过 | [代码](../labs/finance_cases/f10/main.py) · [报告](results/F10/report.md) |
| F11 | 03-1-深度遍历和广度遍历 | 运行通过 | [代码](../labs/finance_cases/f11/main.py) · [报告](results/F11/report.md) |
| F12 | 03-2-社交网络-核心度量指标 | 运行通过 | [代码](../labs/finance_cases/f12/main.py) · [报告](results/F12/report.md) |
| F13 | 03-3-PageRank-Python实现 | 运行通过 | [代码](../labs/finance_cases/f13/main.py) · [报告](results/F13/report.md) |
| F14 | 04-社交网络算法-小案例 | 运行通过 | [代码](../labs/finance_cases/f14/main.py) · [报告](results/F14/report.md) |
| F15 | 04-社交网络算法-小案例_子网分割 | 运行通过 | [代码](../labs/finance_cases/f15/main.py) · [报告](results/F15/report.md) |
| F16 | 05-社交网络—银行交易圈实践-社区发现  | 运行通过 | [代码](../labs/finance_cases/f16/main.py) · [报告](results/F16/report.md) |
