# 预测类实验结果速览

各表来自对应实验的聚合CSV，训练/测试范围、抽样和调参预算以报告为准。不同实验的样本不一定相同，不据此给算法跨数据集排名。AUC/AP越高通常越好，MAE/MSE越低越好；训练指标不是独立验证。

## M01 · 2.1线性回归

[完整报告](results/M01/report.md) · [聚合CSV](results/M01/metrics.csv)

| section | item | value |
|---|---|---|
| holdout_log_scale | ridge | 0.111605 |
| holdout_log_scale | lasso | 0.111917 |
| holdout_log_scale | elastic | 0.111918 |

## M02 · 2.2逻辑回归

[完整报告](results/M02/report.md) · [聚合CSV](results/M02/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| selected_logistic | test | 0.909091 | 0.933225 | 0.894737 |

## M12 · 3.1.1-3.1.2分类（反欺诈_DT_EnsembleMethods）

[完整报告](results/M12/report.md) · [聚合CSV](results/M12/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| decision_tree | test | 0.630202 | 0.261246 | 0.411765 |
| random_forest | test | 0.629968 | 0.261245 | 0.411765 |
| AdaBoost | test | 0.668367 | 0.261397 | 0.411765 |
| XGBoost | test | 0.629193 | 0.261243 | 0.411765 |
| LightGBM | test | 0.687969 | 0.263836 | 0 |
| XGB_early_stop | test | 0.44392 | 0.00223579 | 0 |

## M13 · 3.1.3-3.1.6分类（反欺诈_KNN_NB _SVM_MLP）

[完整报告](results/M13/report.md) · [聚合CSV](results/M13/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| KNN | test | 0.62963 | 0.261089 | 0.411765 |
| MultinomialNB | test | 0.643812 | 0.261286 | 0 |
| SVC | test | 0.6485 | 0.261304 | 0.411765 |
| MLP | test | 0.642072 | 0.26128 | 0.411765 |

## M14 · 1_XGBoost专题_课堂代码

[完整报告](results/M14/report.md) · [聚合CSV](results/M14/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| sklearn | test | 0.695295 | 0.636388 | 0.517124 |
| native_default | test | 0.700907 | 0.641123 | 0.459534 |
| native_parameters | test | 0.704741 | 0.644872 | 0.488713 |
| monotone | test | 0.703738 | 0.640631 | 0.477355 |
| interaction | test | 0.670711 | 0.581411 | 0.385861 |
| parallel_forest | test | 0.690615 | 0.620439 | 0.423947 |
| early_stop | test | 0.70231 | 0.64293 | 0.495434 |

## M15 · 2_LightGBM专题_课堂代码

[完整报告](results/M15/report.md) · [聚合CSV](results/M15/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| HistGB | test | 0.712143 | 0.65646 | 0.493651 |
| sklearn | test | 0.712048 | 0.656595 | 0.498882 |
| native | test | 0.712048 | 0.656595 | 0.498882 |
| early_stop | test | 0.707109 | 0.649955 | 0.487003 |
| monotone | test | 0.712214 | 0.655995 | 0.492891 |
| interaction | test | 0.526689 | 0.421694 | 0.0642715 |

## M17 · 3.2违规识别(IsolationForrest_LOF无监督)

[完整报告](results/M17/report.md) · [聚合CSV](results/M17/metrics.csv)

| section | item | AUC | AP |
|---|---|---|---|
| chronological_holdout | IsolationForest | 0.955358 | 0.0723534 |
| chronological_holdout | LOF | 0.966302 | 0.0798312 |

## M18 · 4.1.1销售数据预测(趋势分解法-不建议学习)

[完整报告](results/M18/report.md) · [聚合CSV](results/M18/metrics.csv)

| section | item | MAE |
|---|---|---|
| holdout | additive | 33.4356 |
| holdout | multiplicative | 21.414 |

## M19 · 4.1.2销售数据预测(SARIMA)

[完整报告](results/M19/report.md) · [聚合CSV](results/M19/metrics.csv)

最后12个月：SARIMA MAE=18.7513，季节朴素基线 MAE=66.6667。

## M20 · 4.1.3股价预测(LSTM)

[完整报告](results/M20/report.md) · [聚合CSV](results/M20/metrics.csv)

| section | item | MAE | naive_MAE |
|---|---|---|---|
| holdout | Open | 15.0864 | 14.8474 |
| holdout | Close | 18.9662 | 14.3854 |

本次留出中 Open、Close 的 LSTM 误差未优于前日值基线；完成迁移不等于证明复杂模型更好。

## M21 · ARIMA

[完整报告](results/M21/report.md) · [聚合CSV](results/M21/metrics.csv)

| section | item | MAE_holdout20 |
|---|---|---|
| AR1_a | diagnostics | 1.06374 |
| MA1_a | diagnostics | 1.35912 |
| ARMA_11_b | diagnostics | 2.04469 |
| ARIMA_110 | diagnostics | 4.22173 |

## M26 · 5.1 模型参数优化方法

[完整报告](results/M26/report.md) · [聚合CSV](results/M26/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| grid | test | 0.708043 | 0.646413 | 0.51317 |
| halving | test | 0.705129 | 0.644446 | 0.506523 |
| random | test | 0.707288 | 0.646328 | 0.50706 |
| TPE | test | 0.709495 | 0.650109 | 0.496293 |

## M27 · 5.2&3 pipeline_保险案例

[完整报告](results/M27/report.md) · [聚合CSV](results/M27/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| logistic | train | 0.662672 | 0.557343 | 0.441616 |
| logistic | test | 0.670525 | 0.565445 | 0.455606 |
| tree | test | 0.657283 | 0.539657 | 0.365669 |

## M29 · 类别不平衡专题_课堂代码

[完整报告](results/M29/report.md) · [聚合CSV](results/M29/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| holdout | baseline | 0.913195 | 0.563616 | 0.5 |
| holdout | SMOTE | 0.909687 | 0.543343 | 0.53468 |
| holdout | SMOTENC | 0.900374 | 0.53683 | 0.536825 |
| holdout | weighted | 0.909355 | 0.563388 | 0.540675 |
| holdout | max_delta_step | 0.903059 | 0.528893 | 0 |

## F02 · 第二章某银行贷款产品精准营销模型代码通过

[完整报告](results/F02/report.md) · [聚合CSV](results/F02/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| evaluation | test | 0.76622 | 0.112496 | 0 |

## F06 · 第5章贷前信用风险预测模型（A卡）代码通过

[完整报告](results/F06/report.md) · [聚合CSV](results/F06/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| WOE_logistic | test | 0.73772 | 0.21094 | 0.0390244 |

## F07 · 第6章贷中信用风险预测模型（B卡）代码通过

[完整报告](results/F07/report.md) · [聚合CSV](results/F07/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| WOE_logistic | test | 0.844546 | 0.678688 | 0.643312 |

排除观察期后的 47523 条第13期记录；建模不使用这些未来记录。

## F08 · 第8章申请反欺诈模型代码通过

[完整报告](results/F08/report.md) · [聚合CSV](results/F08/metrics.csv)

| section | item | AUC | AP | F1 |
|---|---|---|---|---|
| income_anomalies | test | 0.87571 | 0.138192 | 0 |
| with_network_GBDT | test | 0.871851 | 0.487137 | 0.592593 |
| network_LightGBM_GP | test | 0.874446 | 0.425524 | 0.285714 |

重复客户分组 3 组，留出客户交集 0；历史网络匹配比例 100.00%。基础表缺申请日期，快照逐次对齐仍无法核验。
