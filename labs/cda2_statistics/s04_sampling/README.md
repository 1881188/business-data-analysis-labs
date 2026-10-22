# S04 三种抽样设计

问题：从客户总体选取可重复样本，理解固定样本量、每层样本量和抽样比例的区别。

从仓库根目录运行：

```powershell
python run_labs.py --lab S04
```

[入口](main.py)调用[sampling.py](../../../src/bda_labs/sampling.py)。sample_size验证k并向上取整；get_sample接受simple_random、stratified、systematic，用行位置不放回抽取；main运行6种教材设计，检查客户唯一性、各层分配和计数，输出地区构成及N_h/n_h设计权重。

全部5个非空代码单元均有迁移对照。修正字符串身份比较、逐层容量检查与系统抽样可能不足的问题；系统抽样改为随机起点加N/n间隔。源程序未设种子，只核对缓存计数，不宣称客户名单一致。分层样本估计总体需要相应权重。

见[逐单元格迁移对照](../../../docs/results/S04/notebook-map.md)。

见[结果报告](../../../docs/results/S04/report.md)。输入版本在config/datasets.json，客户明细和行级中间产物只留在本地outputs/S04。
