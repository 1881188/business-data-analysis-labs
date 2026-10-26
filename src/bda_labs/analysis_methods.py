"""Six descriptive analysis methods, using the workbook's saved teaching snapshots."""
import re
import numpy as np
import pandas as pd
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path
from .common import context, finish, plotting, save_table, compare_numeric
from .workbook_reference import read_cached_book, coverage_table
from .pbix_audit import visual_audit, AGGREGATION_SOURCE


RANGES = {
    'trend': [('annual', 'B3:C13', ['year', 'orders']),
              ('weekly', 'B19:E29', ['week', 'hours', 'saved_mean', 'warning']),
              ('monthly', 'B36:D47', ['month', 'orders', 'saved_growth'])],
    'comparison': [('products', 'B3:C13', ['product', 'orders']),
                   ('long_names', 'B19:C29', ['product', 'orders']),
                   ('radar', 'B39:C44', ['dimension', 'score'])],
    'composition': [('mix', 'B5:C8', ['product', 'sales']),
                    ('year_mix', 'B18:E22', ['year', 'product_1', 'product_2', 'product_3']),
                    ('area_mix', 'B30:E34', ['year', 'product_1', 'product_2', 'product_3'])],
    'distribution': [('traffic', 'B3:C50', ['time', 'traffic']),
                     ('illustration', 'B54:C59', ['saved_label', 'saved_value']),
                     ('ages', 'K3:L340', ['user_id', 'age']),
                     ('prices', 'T2:U339', ['user_id', 'price'])],
    'relationship': [('campaigns', 'B4:D8', ['campaign', 'ordered', 'not_ordered']),
                     ('loyalty', 'B16:D18', ['loyalty', 'satisfied', 'not_satisfied']),
                     ('spend', 'L2:O99', ['user_id', 'campaign_1', 'campaign_2', 'campaign_3']),
                     ('cost_return', 'Y2:Z59', ['return', 'cost'])],
    'flow': [('edges', 'B2:D16', ['source', 'target', 'flow'])]
}


def growth(values):
    values = pd.Series(values, dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Order counts must be finite and nonnegative')
    prior = values.shift()
    return (values - prior).div(prior.where(prior.ne(0)))


def distribution(values):
    x = np.asarray(values, dtype=float)
    if x.size == 0 or not np.isfinite(x).all():
        raise ValueError('A complete finite sample is required')
    q0, q1, q2, q3, q4 = np.quantile(x, [0, .25, .5, .75, 1], method='linear')
    iqr = q3 - q1
    return {'mean': float(x.mean()), 'min': float(q0), 'q1': float(q1), 'median': float(q2),
            'q3': float(q3), 'max': float(q4), 'iqr': float(iqr),
            'upper_fence': float(q3 + 1.5 * iqr), 'lower_fence': float(q1 - 1.5 * iqr),
            'outliers': int(((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr)).sum())}


def flow_balance(edges):
    e = edges.copy()
    if e[['source', 'target', 'flow']].isna().any().any():
        raise ValueError('Flow edges require source, target and weight')
    e['flow'] = pd.to_numeric(e.flow, errors='raise')
    if not np.isfinite(e.flow).all() or (e.flow < 0).any():
        raise ValueError('Flow weights must be finite and nonnegative')
    incoming = e.groupby('target').flow.sum().rename('incoming')
    outgoing = e.groupby('source').flow.sum().rename('outgoing')
    nodes = pd.concat([incoming, outgoing], axis=1).fillna(0).rename_axis('node').reset_index()
    nodes['outgoing_minus_incoming'] = nodes.outgoing - nodes.incoming
    nodes['internal'] = nodes.node.isin(e.source) & nodes.node.isin(e.target)
    nodes['unexplained_gain'] = nodes.internal & nodes.outgoing.gt(nodes.incoming)
    return e, nodes


def extract(book, kind):
    sheet = next(iter(book.values()))
    frames = {name: pd.DataFrame(sheet.matrix(address), columns=columns)
              for name, address, columns in RANGES[kind]}
    if any(f.isna().any().any() for name, f in frames.items() if name != 'monthly'):
        raise ValueError(f'Unexpected blank within {kind} exercise ranges')
    return frames


def check_formulas(books):
    """Recompute 60 deterministic cells; range-check 778 saved random draws."""
    checks = []
    for key, book in books.items():
        for s in book.values():
            for address, formula in s.formulas.items():
                expected = s.get(address)
                random = re.fullmatch(r'=RANDBETWEEN\((\d+),(\d+)\)', formula)
                if random:
                    lo, hi = map(int, random.groups())
                    if not isinstance(expected, (int, float)) or expected != int(expected) or not lo <= expected <= hi:
                        raise AssertionError(f'Invalid random snapshot: {key}/{address}')
                    checks.append({'source': key, 'cell': address, 'check': 'saved_random_in_bounds',
                                   'absolute_difference': None})
                    continue
                if formula == '=AVERAGE($C$19:$C$29)':
                    actual = np.mean([s.get(f'C{r}') for r in range(19, 30)])
                elif re.fullmatch(r'=\(C\d+-C\d+\)/C\d+', formula):
                    r = int(re.search(r'\d+', address).group())
                    actual = growth([s.get(f'C{r-1}'), s.get(f'C{r}')]).iloc[1]
                elif address.startswith('W') and key.startswith('methods_distribution'):
                    d = distribution([s.get(f'U{r}') for r in range(2, 340)])
                    actual = d[['mean', 'min', 'q1', 'median', 'q3', 'max', 'iqr', 'upper_fence'][int(address[1:])-1]]
                else:
                    raise ValueError(f'Unmapped formula: {key}/{address}: {formula}')
                compare_numeric([actual], [expected], f'{key}/{address}')
                checks.append({'source': key, 'cell': address, 'check': 'recalculated',
                               'absolute_difference': abs(float(actual) - expected)})
    return pd.DataFrame(checks)


def draw_flows(edges, nodes, path, plt):
    # Preserve every edge. Node height=max(in,out); gaps therefore remain visible.
    names = list(dict.fromkeys([*edges.source, *edges.target]))
    levels = {n: 0 for n in names if n not in set(edges.target)}
    for _ in names:
        for row in edges.itertuples():
            if row.source in levels:
                levels[row.target] = max(levels.get(row.target, 0), levels[row.source] + 1)
    if len(levels) != len(names) or max(levels.values()) >= len(names):
        raise ValueError('This teaching flow renderer requires an acyclic graph')
    stats = nodes.set_index('node')
    positions = {}; scale = 1 / 3500
    for level in sorted(set(levels.values())):
        y = 0.
        for n in names:
            if levels[n] != level: continue
            height = max(stats.loc[n, 'incoming'], stats.loc[n, 'outgoing']) * scale
            positions[n] = (float(level), y, height)
            y += height + .13
    fig, ax = plt.subplots(figsize=(14, 7), layout='constrained')
    used_in = dict.fromkeys(names, 0.); used_out = used_in.copy()
    colors = plt.get_cmap('tab20')
    for i, row in enumerate(edges.itertuples()):
        sx, sy, _ = positions[row.source]; tx, ty, _ = positions[row.target]
        h = row.flow * scale; y1 = sy + used_out[row.source]; y2 = ty + used_in[row.target]
        x1, x2 = sx + .05, tx - .05
        verts = [(x1, y1), (x1+.4, y1), (x2-.4, y2), (x2, y2),
                 (x2, y2+h), (x2-.4, y2+h), (x1+.4, y1+h), (x1, y1+h), (x1,y1)]
        codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.LINETO,
                 Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts,codes), facecolor=colors(i % 20), alpha=.52, edgecolor='none'))
        t=.35 if i%2 else .65
        smooth=3*t*t-2*t*t*t
        ax.text(x1+(x2-x1)*t, y1+(y2-y1)*smooth+h/2, str(int(row.flow)), fontsize=8, ha='center')
        used_out[row.source] += h; used_in[row.target] += h
    for n, (x,y,h) in positions.items():
        ax.add_patch(Rectangle((x-.05,y),.1,h,color='#35566b'))
        ax.text(x,y+h+.02,n,ha='center',fontsize=9)
    ax.set(xlim=(-.35,max(levels.values())+.5), ylim=(-.05,max(y+h for x,y,h in positions.values())+.17),
           title='页面流向：保留原始边权，节点高度取入流与出流的较大值')
    ax.axis('off'); fig.savefig(path,dpi=150); plt.close(fig)


def figures(f, out, plt):
    fig, ax = plt.subplots(1,3,figsize=(16,5),layout='constrained')
    annual, weekly, monthly = (f[n] for n in ['annual','weekly','monthly'])
    ax[0].bar(annual.year,annual.orders,color='#087f8c');ax[0].set(title='2014—2024：实际11个年份',ylabel='订单量（个）')
    ax[1].plot(range(1,12),weekly.hours,marker='o',label='处理时长')
    ax[1].axhline(weekly.hours.mean(),color='#d67b28',label='11周等权均值')
    ax[1].plot(range(1,12),weekly.warning,'--',label='教材预警值');ax[1].set(title='每周平均处理时长',xlabel='周',ylabel='小时');ax[1].legend(fontsize=8)
    ax[2].bar(monthly.month,monthly.orders,color='#087f8c');ax[2].set(title='月订单量与环比',xlabel='月',ylabel='订单量（个）')
    twin=ax[2].twinx();twin.plot(monthly.month,monthly.growth*100,color='#d67b28',marker='o');twin.set_ylabel('环比（%）')
    fig.savefig(out/'trend.png',dpi=150);plt.close(fig)
    fig=plt.figure(figsize=(16,6),layout='constrained');axs=[fig.add_subplot(131),fig.add_subplot(132),fig.add_subplot(133,projection='polar')]
    axs[0].bar(f['products']['product'],f['products'].orders,color='#087f8c');axs[0].tick_params(axis='x',rotation=55,labelsize=8);axs[0].set(title='不同产品订单量',ylabel='订单量（个）')
    ranked=f['long_names'].sort_values('orders');axs[1].barh(ranked['product'],ranked.orders,color='#087f8c');axs[1].tick_params(axis='y',labelsize=8);axs[1].set(title='长名称类别按数量排序',xlabel='订单量（个）')
    radar=f['radar'];angles=np.linspace(0,2*np.pi,len(radar),endpoint=False);a=np.r_[angles,angles[0]];v=np.r_[radar.score,radar.score.iloc[0]]
    axs[2].plot(a,v,color='#087f8c');axs[2].fill(a,v,alpha=.2);axs[2].set_xticks(angles,radar.dimension);axs[2].set_ylim(0,100);axs[2].set_title('教材六维分数（未经效度验证）')
    fig.savefig(out/'comparison.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(1,3,figsize=(15,5),layout='constrained');mix=f['mix'];ax[0].pie(mix.sales,labels=mix['product'],autopct='%.1f%%',pctdistance=.78,wedgeprops={'width':.45});ax[0].set_title('产品销量构成')
    for j,name in enumerate(['year_mix','area_mix'],1):
        data=f[name];values=data.iloc[:,1:].to_numpy(dtype=float);labels=['产品1','产品2','产品3']
        if j==1:
            bottom=np.zeros(len(data))
            for k in range(3):ax[j].bar(data.year,values[:,k],bottom=bottom,label=labels[k]);bottom+=values[:,k]
        else:ax[j].stackplot(data.year,*values.T,labels=labels)
        ax[j].set(title='年度销量堆积' if j==1 else '另一组数据的面积构成',ylabel='销量（源表未注明单位）');ax[j].set_xticks(data.year);ax[j].legend(fontsize=8)
    fig.savefig(out/'composition.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(1,4,figsize=(18,4.7),layout='constrained')
    ax[0].plot(f['traffic'].time,f['traffic'].traffic,color='#087f8c');ax[0].tick_params(axis='x',rotation=45,labelsize=8);ax[0].set(title='48个半小时时点的客流示例',ylabel='源表客流值（非整数）')
    ax[1].hist(f['ages'].age,bins=list(range(10,101,10)),color='#087f8c',edgecolor='white');ax[1].set(title='年龄分布：每10岁一组',xlabel='年龄（岁）',ylabel='人数')
    ax[2].boxplot(f['prices'].price,showmeans=True);ax[2].set(title='客单价分布',ylabel='源表未注明货币单位');ax[2].set_xticks([1],['338个保存观测'])
    ax[3].bar(range(1,7),f['illustration'].saved_value,color='#879eab');ax[3].set(title='原表另附6个示意值',xlabel='原始行顺序（标签重复）',ylabel='未核实的非整数“下单人数”')
    fig.savefig(out/'distribution.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for axis,name,c1,c2 in [(ax[0,0],'campaigns','ordered','not_ordered'),(ax[0,1],'loyalty','satisfied','not_satisfied')]:
        data=f[name];x=data.iloc[:,0];den=data[c1]+data[c2];labels=['下单','未下单'] if name=='campaigns' else ['满意','不满意'];axis.bar(x,data[c1]/den*100,label=labels[0]);axis.bar(x,data[c2]/den*100,bottom=data[c1]/den*100,label=labels[1]);axis.set(ylabel='组内比例（%）',title='营销活动下单构成' if name=='campaigns' else '忠诚度与满意度构成');axis.legend(fontsize=8)
    ax[1,0].boxplot(f['spend'].iloc[:,1:].to_numpy(),tick_labels=['活动1','活动2','活动3']);ax[1,0].set(title='三类活动销售额分布',ylabel='源表未注明货币单位')
    xy=f['cost_return'];ax[1,1].scatter(xy.cost,xy['return'],alpha=.7,color='#087f8c');ax[1,1].set(title='58对投入成本与产出收益',xlabel='投入成本（单位未注明）',ylabel='产出收益（单位未注明）')
    fig.savefig(out/'relationship.png',dpi=150);plt.close(fig)


def main(argv=None):
    ctx=context('B10',argv);books={};frames={};mapping={};snapshots=[]
    for kind in RANGES:
        for version in (['raw'] if kind=='flow' else ['raw','reference']):
            key=f'methods_{kind}_{version}';book=read_cached_book(ctx.source(key));books[key]=book
            extracted=extract(book,kind)
            for s in book.values():
                mapping[(key,s.name)]='；'.join(f'{name}: {address}' for name,address,_ in RANGES[kind]) if s==next(iter(book.values())) else '空工作表，未虚构实验'
            if version=='raw':frames.update(extracted)
        if kind!='flow':
            a=next(iter(books[f'methods_{kind}_raw'].values()));b=next(iter(books[f'methods_{kind}_reference'].values()))
            for address,value in a.values.items():
                if isinstance(value,(int,float)):
                    other=b.get(address)
                    snapshots.append({'kind':kind,'cell':address,'raw':value,'reference':other,
                                      'same':value==other,'random_formula':address in a.formulas and a.formulas[address].startswith('=RANDBETWEEN')})
    checks=check_formulas(books)
    coverage=coverage_table(books,mapping,ctx.output/'workbook-map.md')
    frames['monthly']['growth']=growth(frames['monthly'].orders)
    frames['mix']['share']=frames['mix'].sales/frames['mix'].sales.sum()
    edges,nodes=flow_balance(frames['edges'])
    stats=distribution(frames['prices'].price)
    for name,data in frames.items():save_table(data,ctx.output/f'{name}.csv')
    save_table(nodes,ctx.output/'flow_balance.csv');save_table(checks,ctx.output/'formula_checks.csv')
    snap=pd.DataFrame(snapshots);save_table(snap,ctx.output/'snapshot_comparison.csv')
    snapshot_summary=snap.assign(different=~snap.same).groupby('kind',as_index=False).agg(
        compared_cells=('cell','size'),different_cells=('different','sum'),random_formula_cells=('random_formula','sum'))
    save_table(snapshot_summary,ctx.output/'snapshot_summary.csv')
    save_table(pd.DataFrame([stats]),ctx.output/'price_statistics.csv')
    summaries=[]
    for name in ['campaigns','loyalty']:
        data=frames[name]
        for r in data.itertuples(index=False,name=None):summaries.append({'exercise':name,'group':r[0],'first_count':r[1],'second_count':r[2],'first_share':r[1]/(r[1]+r[2])})
    save_table(pd.DataFrame(summaries),ctx.output/'categorical_relationships.csv')
    save_table(frames['spend'].iloc[:,1:].describe().reset_index(names='statistic'),ctx.output/'campaign_statistics.csv')
    counts,bins=np.histogram(frames['ages'].age,bins=list(range(10,101,10)))
    if counts.sum()!=len(frames['ages']):raise AssertionError('Age histogram dropped observations')
    save_table(pd.DataFrame({'left':bins[:-1],'right':bins[1:],'count':counts}),ctx.output/'age_histogram.csv')
    visual_maps=[]
    destinations=['annual（逐年一行，Avg与保存订单量相同；不按queryRef名称计数）','weekly（11周等权均值，非总工单加权）','monthly（按月份排序，重新计算环比）',
                  'products','long_names','radar','mix（饼图与环形图表达同一构成）','mix（环形图）','year_mix（堆积柱图）','year_mix（PBIX引用与Excel另附area_mix不同，均保留）',
                  'prices（Excel客单价；PBIX产品类别/订单量不是同一来源，不声称数值复现）','ages（直接对逐人年龄计数，原生直方图）']
    tail=['cost_return','campaigns（按组内人数求比例）','spend（Excel活动销售额；PBIX渠道/流量来源不同，不声称数值复现）','edges（边权全部保留，指出不守恒）']
    for key in ['methods_pbix08','methods_pbix09']:
        dest=destinations+(['ages（重复直方图方案，保留相同Python结果）'] if key.endswith('09') else [])+tail
        visual_maps.append(visual_audit(ctx.source(key),dest))
    visuals=pd.concat(visual_maps,ignore_index=True);save_table(visuals,ctx.output/'pbix_visual_map.csv')
    plt=plotting();figures(frames,ctx.output,plt);draw_flows(edges,nodes,ctx.output/'flows.png',plt)
    weekly=frames['weekly'];unbalanced=nodes[nodes.unexplained_gain]
    report=f'''# B10 六类分析方法

## 教学范围与来源

完成6份原始工作簿中的18组数据区域，以及5份参考工作簿的快照与公式检查；13张工作表均有去向，其中桑吉图的Sheet2、Sheet3为空。详见[工作表对照](workbook-map.md)。参考文件把“分布”和“构成”的3/4编号交换，按内容配对。

这些是描述分析练习。带RANDBETWEEN的保存值作为固定教材快照读取，本次不重新抽样，也不当作真实经营观测。原表与参考表共比较{len(snap)}个数字单元，{int((~snap.same).sum())}个不相同；差异包括随机值及其依赖均值、环比，不把不同快照强行对齐。

共覆盖{len(checks)}个保存公式：{int(checks.check.eq('recalculated').sum())}个均值、环比与分位数公式独立重算符合各自缓存；{int(checks.check.eq('saved_random_in_bounds').sum())}个随机公式仅检查整数及上下界，没有逐值复现随机序列。snapshot_summary.csv按题汇总差异，formula_checks.csv记录公式坐标和检查类型；包含逐格输入值的snapshot_comparison.csv仅留本地。

## 趋势与对比

原标题写“近10年”，实际为2014—2024共11年。周均处理时长为{weekly.hours.mean():.6f}小时，最长{weekly.hours.max():.0f}小时，比等权均值多{weekly.hours.max()-weekly.hours.mean():.6f}小时。每周工单数未给出，不能解释成全部工单的加权均值。环比为本月/上月−1，首月未知；上月为0时保留未知，不填0。月序与week1—week11按数值顺序，避免按量排序或字典序。

![趋势](trend.png)

产品比较保留11类；长名称用水平条形图；雷达图六维I/E/S/N/T/P按原表顺序保留，不额外推断人格或营销标签。

![对比](comparison.png)

## 构成与分布

产品构成为各产品销量/同表总销量。两组年度构成是不同随机快照，堆积柱图与面积图分别使用各自区域，不混用。量与比例不在同一轴上混画。

![构成](composition.png)

年龄与客单价各338条，未因两列数值相似就假设为独立采样或合并。客单价均值{stats['mean']:.6f}，Q1={stats['q1']:.2f}、Q3={stats['q3']:.2f}，IQR={stats['iqr']:.2f}，上界{stats['upper_fence']:.3f}；采用与QUARTILE.INC相同的线性分位数。箱线图标记{stats['outliers']}个界外值，保留观测，不自动删异常。原表货币单位未知。

客流是48个半小时时点的非整数值。B54:C59另有6条“年龄/下单人数”示意，年龄标签重复且人数为小数，单列展示，不把它冒充338人年龄分组统计；实际直方图直接从逐人年龄计算，左闭右开、最后一组含右端点。

![分布](distribution.png)

## 关系与流向

下单/未下单、满意/不满意按各组总数算比例。三次活动销售额使用98条保存行；原ID有跳号，未补造客户。成本收益有58对观测，只作散点关系，不推断因果、利润率或营销增量。

![关系](relationship.png)

桑基图保留15条边。首页出流2700；博客页面入流250、出流270，多出20，来源未解释，不能把全图当作同一批用户的严格守恒漏斗。其他节点的净减少也没有事件时间或退出字段支持，不直接称为流失。flow_balance.csv列出全部节点。本图按max(入流,出流)绘制节点，保留差额，不补造来源。

![页面流向](flows.png)

## Power BI 对照边界

两份PBIX的33个视觉容器逐项登记在pbix_visual_map.csv（08版16个、09版17个）。queryRef的CountNonNull字样可能是旧名称：年度图的Function=1实际为Avg，长名称图Function=0为Sum；按保存配置解释。聚合枚举见[微软表达式说明]({AGGREGATION_SOURCE})。

PBIX中的产品类别/订单量箱线图和渠道/流量箱线图未提供同结构的独立Excel表，分别用本节Excel的客单价、活动销售额完成相应方法教学，并明确标记来源差异。二进制DataModel未解码；因此本实验状态为运行通过，只对报告所列Excel快照与60项确定性公式作核对，不宣称PBIX全部数值或第三方插件像素复现。
'''
    finish(ctx,{'lab_id':'B10','status':'execution_verified','workbook_coverage':coverage,
                'exercise_ranges':18,'source_formula_cells':len(checks),'formula_cells_covered':len(checks),
                'formula_checks':{'recalculated':int(checks.check.eq('recalculated').sum()),'saved_random_bounds':int(checks.check.eq('saved_random_in_bounds').sum())},
                'snapshot_cells':len(snap),'snapshot_differences':int((~snap.same).sum()),
                'pbix_visuals':len(visuals),'price_statistics':stats,'flow_inconsistencies':unbalanced.to_dict('records')},report)


if __name__=='__main__':main()
