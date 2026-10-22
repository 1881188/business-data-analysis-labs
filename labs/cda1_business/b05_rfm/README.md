# B05 RFM客户价值分层

来源：CDA一级第2章“分析的基础范式”RFM原始工作簿与参考答案。

业务问题：从近期消费、消费频次和累计金额识别不同客户群体，为后续运营实验提供分层。

```powershell
python labs/cda1_business/b05_rfm/main.py --data-root "教材资料目录"
```

计算在[src/bda_labs/rfm.py](../../../src/bda_labs/rfm.py)，报告见[结果与解释](../../../docs/results/B05/report.md)。

R使用固定分析日2019-08-03，F按不同流水号而非商品行计数，M使用全部明细金额。相同内容的商品行不盲目删除。八类标签和严格均值边界与教材一致。程序逐客户核对R/F/M、最后消费日及标签，差异时明确失败。

输入：`rfm_raw`、`rfm_reference`，准确路径和校验和见[清单](../../../config/datasets.json)。输出：本地客户表、分层聚合、参考差异、图、摘要与报告。客户明细不纳入公开仓库。
