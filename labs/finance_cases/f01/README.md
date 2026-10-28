# F01 · 待补原始输入的辅助实验

源 test.ipynb 需要 data12261.csv，当前材料没有该文件。[入口](main.py)已整理为Python，但未纳入已运行清单。

```powershell
python labs/finance_cases/f01/main.py --input "原data12261.csv的路径"
```

该入口会核查原字段，按训练数据确定清洗边界、标准化与RFE，保存本地试运行摘要；不会自动发布或改变验收状态。输入取得后先登记哈希并审核，不能用其他CSV或合成数据冒充原始实验。
