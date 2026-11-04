"""Independent result checks and a human-readable stage report."""
from pathlib import Path
import json
import csv
import math
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/tables'


def rows(name):
    with (OUT/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def main():
    analysis=json.loads((OUT/'analysis_summary.json').read_text(encoding='utf-8'))
    forecast=json.loads((OUT/'forecast_summary.json').read_text(encoding='utf-8'))
    monthly,categories=rows('analysis_monthly_sales.csv'),rows('analysis_category_abc.csv')
    cents=sum(int(Decimal(x['revenue_cents'])) for x in categories)
    assert cents==sum(int(Decimal(x['revenue_cents'])) for x in monthly)
    assert cents==int(Decimal(str(analysis['merchandise_value_brl']))*100)
    assert sum(int(x['orders']) for x in monthly)==analysis['sales_orders']
    shares=[Decimal(x['share_known']) for x in categories if x['abc_class']!='U']
    assert abs(sum(shares)-1)<Decimal('0.000000001')
    assert all(x['abc_class']=='U' for x in categories if x['category_display']=='unknown_category')
    holdout=rows('forecast_july_holdout.csv')
    assert len(holdout)==31 and holdout[0]['date']=='2018-07-01' and holdout[-1]['date']=='2018-07-31'
    for metric,col in zip(forecast['holdout_metrics'],['sarima_brl','seasonal_naive_brl','weekday_4week_mean_brl']):
        rmse=math.sqrt(sum((float(x['actual_brl'])-float(x[col]))**2 for x in holdout)/len(holdout))
        assert math.isclose(rmse,metric['rmse_brl'],rel_tol=1e-10)
    assert all(0<=float(x['lower95_brl'])<=float(x['sarima_brl'])<=float(x['upper95_brl']) for x in holdout)
    coverage=sum(float(x['lower95_brl'])<=float(x['actual_brl'])<=float(x['upper95_brl']) for x in holdout)/len(holdout)
    assert math.isclose(coverage,forecast['holdout_pi95_coverage'])
    metrics=forecast['holdout_metrics']
    comparisons=analysis['review_comparison']
    ontime=next(x for x in comparisons if not x['late_delivery_flag'])
    late=next(x for x in comparisons if x['late_delivery_flag'])
    adjusted=analysis['state_category_standardized_review_comparison']
    audit={'sales_totals_across_months_categories':'passed',
           'abc_known_share_and_unknown_category_handling':'passed',
           'independent_holdout_rmse_for_all_three_models':'passed',
           'holdout_date_count_and_pi_ordering':'passed',
           'independent_holdout_interval_coverage':'passed',
           'chart_visual_review':'manual review required; not inferred from script success'}
    (OUT/'analysis_verification.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=[
        '# Olist商业分析阶段结果', '',
        '本阶段已完成趋势与同比环比、商品ABC分类、配送与评价比较，以及一个品类的SARIMA回测与历史预测示范。图表最新清单见05_图表索引与解读.md，大屏开发与HTTP验证见06_交互大屏使用与验收.md；论文公开版见本目录；浏览器页面操作及视觉验收尚待完成，不能用HTTP检查代替。', '',
        '## 研究范围', '',
        '销售分析使用2017年1月至2018年7月购买、最终已交付并通过金额检查的89,860笔订单；商品金额不含运费，单位为巴西雷亚尔BRL，不能解释为利润。样本增长可能受到平台规模、样本覆盖或品类结构变化影响，不能外推为巴西电商整体增长。', '',
        '## 销售变化', '',
        f"2017年1—7月商品金额为{analysis['jan_jul_2017_revenue_brl']:,.2f} BRL，2018年同期为{analysis['jan_jul_2018_revenue_brl']:,.2f} BRL，同比增长{analysis['jan_jul_revenue_growth']:.2%}。订单数增长{analysis['jan_jul_order_growth']:.2%}，客单价增长{analysis['jan_jul_aov_growth']:.2%}，数量变化对金额增长的贡献更突出。",
        f"分析期内月度销售金额最高的是{analysis['peak_month']}，达到{analysis['peak_month_revenue_brl']:,.2f} BRL。尚未加入促销活动证据，不直接将峰值归因于某个营销活动。",
        f"客户收货州SP（圣保罗州）贡献{analysis['top_state_share']:.2%}商品金额。该指标按客户地址统计，不是卖家所在地，也不表示Olist在当地的市场份额。", '',
        '## 商品贡献与ABC', '',
        f"前5个商品类别贡献总商品金额的{analysis['top5_category_share_total']:.2%}。共有{analysis['known_categories']}个已知类别，按金额降序和累计80%/95%界限分组，A类{analysis['a_categories']}个，贡献总金额的{analysis['a_share_total']:.2%}。",
        f"缺失类别单列U类，占总金额{analysis['unknown_category_share_total']:.2%}；ABC阈值的分母仅使用已知类别金额，因此A类约占已知金额的80.96%，与占总金额79.85%是不同口径。",
        '跨阈值类别保留在更高优先级组，因此累计占比略超阈值。敏感性检查中，A界限改为75%、80%、85%时，A类别数分别为14、17、20，说明分组不是天然客观标签。',
        '建议优先关注主要贡献类别的服务稳定性与供给状况；数据缺少库存、成本和利润，暂不能给出具体补货量或盈利排序。类别内订单数跨类别会重复，不能把类别订单数直接求和当总订单数。', '',
        '## 配送与评价', '',
        f"有效配送样本中自然日逾期率为{analysis['late_rate']:.2%}。在既有配送日期又有评分的样本中：", '',
        '| 分组 | 订单数 | 平均评分（满分5） | 低评分比例（1—2分） |',
        '|---|---:|---:|---:|',
        f"| 按期签收 | {ontime['orders']:,} | {ontime['mean_score']:.2f} | {ontime['low_score_rate']:.2%} |",
        f"| 逾期签收 | {late['orders']:,} | {late['mean_score']:.2f} | {late['low_score_rate']:.2%} |", '',
        f"按客户州和订单金额最大的主要品类分层，只保留两组各至少20单的{adjusted['common_strata']}个共同分层，覆盖{adjusted['covered_orders']:,}单；用各层合并样本比例作共同权重后，按期与逾期平均评分分别为{adjusted['on_time_mean_score']:.2f}和{adjusted['late_mean_score']:.2f}，差异仍在。",
        '将多评论订单改取最早一条评价，结果基本一致。该比较依然存在未控制的价格、卖家、地区服务和评价选择偏差，并且部分评价可能在签收前提交，因此仅报告关联，不能声称证明配送逾期导致差评。',
        '可据此建议优先排查主要贡献品类及逾期较多地区的承诺时效与履约异常，并用后续试点验证服务改进是否有效。', '',
        '## 预测实验', '',
        '选择手表与礼品（watches_gifts）。仅依据2017年1月至2018年5月的金额排序和非零日期覆盖率选择品类，没有用6月验证或7月测试表现挑品类。训练516天，6月验证30天选模型，7月31天作为独立测试。',
        '预测目标为每日下单商品金额：正价格明细，包含后来取消等所有最终状态。采用这个口径避免用最终是否交付来筛选购买当时的需求；它与前文已交付销售金额不同。没有记录的日期补0表示数据内未观察到交易，不等于现实中没有需求。',
        '比较4个低阶候选，周周期7天。验证期RMSE最小的模型为SARIMA(0,1,1)×(0,1,1,7)，模型拟合均收敛，最终模型参数和摘要保存在outputs/sarima_model_summary.txt。', '',
        '| 方法 | 7月RMSE（BRL） | MAE（BRL） | WAPE |',
        '|---|---:|---:|---:|',
    ]
    names={'SARIMA':'SARIMA','seasonal_naive':'重复上一周','weekday_4week_mean':'近4周同星期均值'}
    for m in metrics:
        lines.append(f"| {names[m['model']]} | {m['rmse_brl']:,.2f} | {m['mae_brl']:,.2f} | {m['wape']:.2%} |")
    lines += ['',f"相对更强的4周均值基线，SARIMA的RMSE仅降低{forecast['rmse_improvement_vs_best_baseline']:.2%}，未检验统计显著性。WAPE仍为{metrics[0]['wape']:.2%}，预测存在明显不确定性，不建议直接作为自动补货依据。",
        f"95%模型预测区间在测试月覆盖{coverage:.2%}的实际值（30/31天）；样本仅一个月，不能据此声称区间长期校准良好。区间基于模型高斯观测分布，下界截为0，不包含参数估计不确定性。",
        '用截至2018年7月31日的数据重新拟合，给出2018年8月1—14日的历史预测演示。这不是2026年的未来经营预测。已发布数据不是逐时点历史快照，本实验不构成严格的生产环境验证。',
        '方法参考： https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html 及 https://www.statsmodels.org/stable/examples/notebooks/generated/statespace_forecasting.html 。', '',
        '## 图表与下一步', '',
        'fig01_主要州销售金额分布.png参考用户提供的模板01，深蓝背景、蓝色柱形、结论式副标题、数值与单位标注，1920×1080像素，160dpi。已检查中文显示、标签和边距。',
        '完整图表清单和逐图解读见05_图表索引与解读.md。大屏已实现筛选联动并通过HTTP回调检查，但浏览器视觉验收和截图尚未完成。图表需要逐张检查，不把成功运行脚本等同于画面合格。', '',
        '## 验证与复现', '',
        '本阶段独立核对月份、品类和订单金额总计；ABC已知类别份额与缺失类别处理；用Python标准库重新计算三种预测方法的测试RMSE、区间覆盖率及日期数。检查全部通过。',
        'python run_all.py从数据获取开始运行；已有清洗数据时可用python run_all.py --from-stage 4重跑本阶段。', '',
        '结果表位于outputs/tables；这份阶段报告不是最终课程论文。', '',
    ]
    (ROOT/'docs/04_商业分析阶段结果.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
