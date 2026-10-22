# 商业数据分析实验集

将四套教材中的 Excel、Power BI 案例迁移为 Python，把 Jupyter Notebook 整理为独立脚本，记录业务问题、指标口径、结果和解释。

当前完成 **7 个实验**。RFM和忠诚度已逐客户核对；波士顿矩阵、同期群、漏斗完成各自报告中列明的数值参考核对；数据清洗与客户流失已独立运行。其他材料按[实验索引](docs/experiment-index.md)继续推进，未完成项目不计入完成数。

![RFM客户分层](docs/results/B05/rfm_segments.png)

## 已完成实验

| ID | 实验与教材 | 代码说明 | 结果报告 | 验证状态 |
|---|---|---|---|---|
| B04 | 一级：波士顿矩阵 | [实验入口](labs/cda1_business/b04_bcg/README.md) | [结果与解释](docs/results/B04/report.md) | 14个品牌的份额/增长及两条阈值核对通过 |
| B05 | 一级：RFM客户价值分层 | [实验入口](labs/cda1_business/b05_rfm/README.md) | [结果与解释](docs/results/B05/report.md) | 7,178名客户的R/F/M、消费日期与标签全部对账一致 |
| B06 | 一级：用户忠诚度 | [实验入口](labs/cda1_business/b06_loyalty/README.md) | [结果与解释](docs/results/B06/report.md) | 990名会员标签一致；705名会员F/M及评分一致 |
| B07 | 一级：同期群日留存 | [实验入口](labs/cda1_business/b07_cohort/README.md) | [结果与解释](docs/results/B07/report.md) | 243个已观察单元核对，未到期不填零 |
| B08 | 一级：转化漏斗 | [实验入口](labs/cda1_business/b08_funnel/README.md) | [结果与解释](docs/results/B08/report.md) | 销售示例24项数值核对；另完成两组练习 |
| S01 | 二级：数据整合和清洗 | [实验入口](labs/cda2_statistics/s01_cleaning/README.md) | [结果与解释](docs/results/S01/report.md) | 12个小节，分块读取、关联、汇总等关键检查通过 |
| S11 | 二级：电信客户流失逻辑回归 | [实验入口](labs/cda2_statistics/s11_churn/README.md) | [结果与解释](docs/results/S11/report.md) | 主模型运行通过；教材未正则多元拟合不收敛，改动已说明 |

RFM样本中18.45%的重要价值客户贡献62.45%的销售额。流失实验使用1,039名独立测试客户，L2正则多元模型ROC AUC为0.9290。这些是教材样本上的结果，不代表实际营销干预效果。

## 运行

实测环境为 Windows、Python 3.13.0，依赖版本见[requirements.txt](requirements.txt)。原始教材配套数据不随仓库分发，先按[数据准备说明](data/README.md)准备四个教材目录。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_labs.py --lab all --data-root "你的教材配套资料目录"
```

也可以单独运行：

```powershell
python run_labs.py --lab B05
python run_labs.py --lab B04 B06 B07 B08
python run_labs.py --lab S01 S11
python -m unittest discover -s tests -v
python tools/check_project.py
```

数据位置支持`--data-root`、`BDA_DATA_ROOT`环境变量或不纳入Git的`config/datasets.local.json`。将本仓库与`a商业数据分析平时作业`并列放置时可自动找到资料。输出默认写入`outputs/<实验ID>/`，可用`--output-root`改变位置。

`--lab all`只运行当前已实现并登记的实验；失败会返回非零状态，未实现项目不会被静默算成完成。原始输入按SHA-256检查，不匹配的资料版本需要先审查。

## 四个教材板块

| 板块 | 整理范围 | 当前进度 |
|---|---|---|
| CDA 一级：商业数据分析 | 建议22个迁移单元，涵盖数据处理、RFM、留存、看板、归因与预测 | B04-B08已完成对应范围的参考核对 |
| CDA 二级：量化策略分析 | 13份Notebook及辅助代码 | S01、S11已运行 |
| CDA 三级：敏捷数据挖掘 | 29份Notebook及辅助算法 | 待逐项迁移 |
| 金融数据分析与挖掘案例 | 16份Notebook，含一份代码重复的Vintage检查点 | 待逐项迁移与补齐依赖 |

[source-map.csv](docs/source-map.csv)记录572份原材料的相对路径、哈希、类型和实现去向，插件与参考资料不按独立实验计数。[迁移说明](docs/migration-guide.md)记录首批关键修正。

## 目录

```text
labs/                  每个实验的独立入口与业务说明
src/bda_labs/           计算逻辑、路径与输出处理
config/                可移植的输入清单与配置示例
data/                  数据准备方法；原始数据不提交
docs/results/          可公开的聚合报告、图表和运行摘要
docs/source-map.csv    教材材料到实验的映射与真实状态
tests/                 使用合成数据的业务边界与流程检查
tools/                 文档构建、格式导出与项目检查
outputs/               本地运行产物，不纳入Git
```

已实现入口、计算模块及公开产物统一登记在[implemented_labs.json](config/implemented_labs.json)，避免各工具各维护一套名单。当前22项合成数据测试覆盖订单粒度、分位数边界、登录去重、未到期观察、零分母和模型训练分区等行为。

## 数据、许可与后续

本仓库新增代码使用[MIT许可](LICENSE)，教材、第三方代码和数据的权利范围另见[来源说明](THIRD_PARTY_NOTICES.md)。公开成果只保留聚合表和必要图表，客户级RFM、预测与分区记录留在本地输出。

GitHub公开仓库：[1881188/business-data-analysis-labs](https://github.com/1881188/business-data-analysis-labs)。检查运行见[GitHub Actions](https://github.com/1881188/business-data-analysis-labs/actions)，详细状态见[进度记录](docs/progress.md)。Gitee目标账号待补充。后续批次继续覆盖全部教材实验，首批样板不替代全量要求。
