# 工作表迁移对照

原工作簿只读；缓存是教材保存的快照，不等于本次重算。

| 来源键 | 工作表 | 教学内容与Python去向 |
|---|---|---|
| air_excel | AirPassengers | 144个月AIR/ln及重复区域核对，原始与对数尺度分解 |
| air_wps | AirPassengers | 144历史及24未来保存WPS快照；按稀疏缓存位置核查 |
| air_wps | Sheet3 | 144历史及24未来保存WPS快照；按稀疏缓存位置核查 |
| credit_holiday | pos | 31天原始金额序列独立建模；未提供节日标签/调整公式 |
| credit_no_holiday | Sheet1 | 31天另一尺度的教材序列独立分析，不擅自当原始金额的可验证去节日结果 |
| credit_wps | Sheet1 | 31天输入和两位小数显示历史、7天保存预测，算法参数未给出 |
| credit_wps | Sheet2 | 31天输入和两位小数显示历史、7天保存预测，算法参数未给出 |
