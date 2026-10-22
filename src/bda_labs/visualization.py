"""Thirteen static plot examples, preserving the notebook's data and teaching scope."""
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

from .common import context, finish, plotting, save_table
from .notebook_reference import read_notebook, write_coverage


def prepare_stock(raw):
    result = raw.copy(deep=True)
    result['日期'] = pd.to_datetime(result['日期'], errors='raise')
    prices = result[['收盘价','开盘价','最高价','最低价']]
    if result['日期'].isna().any() or result['日期'].duplicated().any() or not np.isfinite(prices.to_numpy()).all():
        raise ValueError('Stock dates must be distinct and prices complete and finite')
    if (prices.le(0).any().any() or (prices['最高价'] < prices.max(axis=1)).any()
            or (prices['最低价'] > prices.min(axis=1)).any()):
        raise ValueError('Stock prices violate positive OHLC ordering')
    return result.sort_values('日期', kind='stable').reset_index(drop=True)


def demonstration_data():
    # RandomState deliberately matches the source notebook's np.random.seed stream.
    votes = pd.DataFrame({'plan':['plan A','plan B','plan C','plan D','plan E'],
                          'votes':np.random.RandomState(1).randint(10,100,5)})
    normal = np.random.RandomState(1).normal(80,20,200).astype(int)
    rng = np.random.RandomState(1)
    scores = pd.DataFrame({'语文':rng.randint(60,150,10),'英语':rng.randint(40,150,10),'数学':rng.randint(20,150,10)})
    rain = pd.DataFrame({'产量':[2200,3300,4400,5500,5700,7300,8000],'降水量':[22,39,55,66,105,100,122]})
    bivariate = np.random.RandomState(0).multivariate_normal([0,1],[[1,.5],[.5,1]],200)
    heat = np.random.RandomState(0).uniform(-1,1,(7,7))
    return votes, normal, scores, rain, bivariate, heat


def main(argv=None):
    ctx = context('S02', argv)
    nb = read_notebook(ctx.source('notebook_visualization'))
    raw = pd.read_excel(ctx.source('visualization_stock'))
    stock = prepare_stock(raw)
    votes, normal, scores, rain, data, heat = demonstration_data()
    votes['share'] = votes.votes/votes.votes.sum()
    bins = np.arange(30,131,10)
    counts, _ = np.histogram(normal,bins=bins)
    outside = int(((normal < bins[0]) | (normal > bins[-1])).sum())
    if counts.sum()+outside != len(normal) or not np.isclose(votes.share.sum(),1):
        raise AssertionError('Plot counts or shares did not reconcile')
    save_table(votes,ctx.output/'synthetic_votes.csv')
    save_table(stock,ctx.output/'stock_chronological_local.csv')
    plt = plotting()
    inventory = []

    def save(fig, name, topic, kind):
        fig.savefig(ctx.output/name,dpi=140)
        plt.close(fig)
        inventory.append({'file':name,'topic':topic,'data_kind':kind})

    def canvas(width=8,height=5):
        return plt.subplots(figsize=(width,height),layout='constrained')

    fig,ax = canvas(11,5)
    for name, marker in [('收盘价','o'),('开盘价','s'),('最高价','^'),('最低价','v')]:
        ax.plot(stock['日期'],stock[name],marker=marker,markersize=4,label=name)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.set(title='教材2017年价格序列（日期升序）',xlabel='2017年日期',ylabel='价格（原字段数值）')
    ax.legend(frameon=False,ncol=4)
    save(fig,'stock_lines.png','线图','textbook_input')

    fig,ax = canvas(7,6)
    ax.pie(votes.votes,labels=votes.plan,autopct='%.2f%%',colors=['#087f8c','#d67b28','#5b5fa6','#93a7b5','#d5b56b'],
           textprops={'fontsize':11})
    ax.set_title('模拟方案投票占比')
    save(fig,'vote_pie.png','饼图','seeded_synthetic')

    fig,ax = canvas()
    ax.bar(votes.plan,votes.votes,color='#087f8c',width=.6)
    ax.set(title='模拟方案投票人数',xlabel='方案',ylabel='人数')
    save(fig,'vote_bars.png','柱形图','seeded_synthetic')

    fig,ax = canvas()
    ordered = votes.sort_values('votes')
    ax.barh(ordered.plan,ordered.votes,color='#087f8c',height=.6)
    ax.set(title='模拟方案投票人数（按人数排序）',xlabel='人数',ylabel='方案')
    save(fig,'vote_horizontal.png','水平条形图','seeded_synthetic')

    fig,ax = canvas()
    ax.hist(normal,bins=bins,color='#087f8c',edgecolor='white')
    ax.set(title='正态模拟整数样本的直方图',xlabel='模拟值',ylabel='频数',xticks=bins)
    save(fig,'histogram.png','直方图','seeded_synthetic')

    fig,ax = canvas()
    ax.scatter(rain['降水量'],rain['产量'],color='#087f8c',s=60)
    ax.set(title='教材降水量与产量示意',xlabel='降水量（原示意单位）',ylabel='产量（原示意单位）')
    save(fig,'rainfall_scatter.png','散点图','textbook_illustration')

    fig,ax = canvas()
    ax.boxplot([scores[c] for c in scores],tick_labels=list(scores))
    ax.set(title='模拟学科分数箱线图',ylabel='模拟分数')
    save(fig,'subject_boxplot.png','箱线图','seeded_synthetic')

    fig,ax = canvas()
    ax.hist(normal,bins=bins,density=True,color='#087f8c',alpha=.55,edgecolor='white',label='密度直方图')
    grid = np.linspace(normal.min()-15,normal.max()+15,300)
    ax.plot(grid,gaussian_kde(normal)(grid),color='#d67b28',label='Scott带宽核密度')
    ax.set(title='模拟样本分布与核密度',xlabel='模拟值',ylabel='概率密度')
    ax.legend(frameon=False)
    save(fig,'histogram_kde.png','直方图与核密度','seeded_synthetic')

    gx = np.linspace(data[:,0].min()-.5,data[:,0].max()+.5,80)
    gy = np.linspace(data[:,1].min()-.5,data[:,1].max()+.5,80)
    xx,yy = np.meshgrid(gx,gy)
    zz = gaussian_kde(data.T)(np.vstack([xx.ravel(),yy.ravel()])).reshape(xx.shape)

    def joint(kde=False):
        fig = plt.figure(figsize=(7,7),layout='constrained')
        axes = fig.subplot_mosaic([['top','blank'],['main','right']],gridspec_kw={'width_ratios':[4,1],'height_ratios':[1,4]})
        axes['blank'].axis('off')
        if kde:
            axes['main'].contour(xx,yy,zz,levels=7,cmap='viridis')
        else:
            axes['main'].scatter(data[:,0],data[:,1],color='#087f8c',alpha=.6,s=15)
        axes['top'].hist(data[:,0],bins=15,color='#087f8c')
        axes['right'].hist(data[:,1],bins=15,orientation='horizontal',color='#087f8c')
        axes['top'].set(xlim=(gx[0],gx[-1]),ylabel='频数',xticks=[])
        axes['right'].set(ylim=(gy[0],gy[-1]),xlabel='频数',yticks=[])
        axes['main'].set(xlim=(gx[0],gx[-1]),ylim=(gy[0],gy[-1]),xlabel='x',ylabel='y')
        fig.suptitle('模拟二元核密度与边际分布' if kde else '模拟二元散点与边际分布')
        return fig

    save(joint(),'joint_scatter.png','二元散点与边际直方图','seeded_synthetic')
    fig,ax = canvas()
    ax.scatter(data[:,0],data[:,1],color='#087f8c',alpha=.65,s=22)
    ax.set(title='模拟二元关系图',xlabel='x',ylabel='y')
    save(fig,'relational_scatter.png','二元关系散点图','seeded_synthetic')
    save(joint(True),'joint_kde.png','二元核密度与边际直方图','seeded_synthetic')
    fig,ax = canvas()
    contours = ax.contourf(xx,yy,zz,levels=12,cmap='viridis')
    fig.colorbar(contours,ax=ax,label='估计概率密度')
    ax.set(title='模拟二维核密度分布',xlabel='x',ylabel='y')
    save(fig,'bivariate_kde.png','二维核密度图','seeded_synthetic')

    fig,ax = canvas(8,6)
    im = ax.imshow(heat,vmin=-1,vmax=1,cmap='RdBu_r')
    ax.set(xticks=range(7),xticklabels=list('ABCDEFG'),yticks=range(7),yticklabels=list('abcdefg'),
           title='独立均匀随机矩阵热图（非相关矩阵）')
    fig.colorbar(im,ax=ax,label='随机值')
    save(fig,'random_heatmap.png','随机矩阵热图','seeded_synthetic')

    coverage = write_coverage(nb,[([2,3,4],'价格线图与中文字体','prepare_stock，动态日期刻度，日期升序，无图形界面保存'),
        ([6,7],'模拟投票饼图','demonstration_data；局部RandomState(1)复用原随机流'),
        ([9,10],'柱形图与条形图','保留原顺序及按人数排序两个示例'),
        ([12,13],'模拟整数样本直方图','保持原30到130箱界，核对箱内外总量'),
        ([15,16],'降水量与产量散点','保留教材示意点，不附会为因果数据'),
        ([18,19],'学科分数箱线图','同一随机流依次生成三科分数，更新tick_labels参数'),
        ([21,22],'带核密度的直方图','以scipy KDE代替seaborn，统一使用概率密度单位'),
        ([24,25,26,27,28],'四种二元图','同一200点数据，散点/边际直方图/二维核密度'),
        ([30,31],'热图','保留7×7均匀随机矩阵，明确其不是相关矩阵')],ctx.output/'notebook-map.md')
    save_table(pd.DataFrame(inventory),ctx.output/'chart_inventory.csv')
    links = '\n\n'.join(f"### {i+1}. {r['topic']}\n\n![{r['topic']}]({r['file']})" for i,r in enumerate(inventory))
    report = f"""# S02 Python数据可视化

## 实现范围

重构原Notebook全部{coverage['mapped_code_cells']}个非空代码单元，生成13幅图：线图、饼图、柱形图、条形图、直方图、散点图、箱线图、直方图与KDE、4种二元图，以及热图。[逐单元格对照](notebook-map.md)记录每项迁移，chart_inventory.csv记录图形与数据性质。

价格文件有{len(stock)}个交易日，从{stock['日期'].min():%Y-%m-%d}到{stock['日期'].max():%Y-%m-%d}。原表倒序，现按真实日期升序排列，不再硬编码range(15)。OHLC数值未改写，检查最高/最低与开收盘关系。图中名称和数值均取原表，没有补写证券代码或把历史片段用于投资建议。

其他例子是固定种子的模拟数据或教材给出的示意点。使用局部RandomState复现原np.random.seed的随机流，不污染调用者的全局随机状态。投票总数{int(votes.votes.sum())}，占比和为1；直方图200个样本中箱内{int(counts.sum())}个、箱外{outside}个。模拟分数与正态样本只为绘图教学，不能当作真实调研结果。

## 依赖与解释

原seaborn图形改用本仓库已有的matplotlib和scipy.gaussian_kde实现，保留二元关系、边际分布和KDE教学目的，不宣称像素级复现。KDE采用Scott带宽，直方图与KDE共用概率密度纵轴；其形状受带宽影响。热图输入是独立随机数矩阵，既不对称也不要求对角线为1，不能误标为相关矩阵。

所有图保存为PNG并关闭图形对象，可从命令行无界面运行。股票原始行级数据只留本地，公开投票表为明确标注的合成数据。本实验状态为运行通过，没有独立的图像参考评分。

## 图形

{links}
"""
    finish(ctx,{'lab_id':'S02','status':'execution_verified','stock_rows':len(stock),
        'stock_start':stock['日期'].min(),'stock_end':stock['日期'].max(),'figures':inventory,
        'random_streams':{'votes_normal_scores':1,'bivariate_heat':0},'vote_total':int(votes.votes.sum()),
        'histogram_included':int(counts.sum()),'histogram_outside':outside,'notebook_coverage':coverage},report)


if __name__ == '__main__':
    main()
