"""First Python chart sample, aligned with reference template 01."""
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'outputs'/'.matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,ticker
import pandas as pd


def main():
    font=Path(os.environ.get('OLIST_CHINESE_FONT','C:/Windows/Fonts/msyh.ttc'))
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    else:
        raise RuntimeError('Set an installed Chinese font before rendering the sample')
    plt.rcParams['axes.unicode_minus']=False
    df=pd.read_csv(ROOT/'outputs/tables/analysis_state_sales.csv').head(6)
    bg,white,muted,blue='#1B2043','#F1F3FA','#A9B0CB','#008CCC'
    fig=plt.figure(figsize=(12,6.75),dpi=160,facecolor=bg)
    ax=fig.add_axes([.105,.22,.83,.51],facecolor=bg)
    labels={'SP':'圣保罗州','RJ':'里约热内卢州','MG':'米纳斯吉拉斯州',
            'RS':'南里奥格兰德州','PR':'巴拉那州','SC':'圣卡塔琳娜州','BA':'巴伊亚州'}
    values=df['revenue_brl']/10000
    bars=ax.bar(range(len(df)),values,width=.38,color=blue,zorder=3)
    ax.set_xticks(range(len(df)),[labels.get(s,s)+'\n'+s for s in df['customer_state']],fontsize=10,color=muted)
    ax.set_ylim(0,values.max()*1.23)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(4))
    ax.tick_params(axis='both',colors=muted,length=0,pad=10,labelsize=10)
    ax.spines[['left','right','top']].set_visible(False)
    ax.spines['bottom'].set_color('#6A7393')
    ax.grid(axis='y',color='#667092',linestyle=(0,(2,3)),linewidth=.6,alpha=.35,zorder=0)
    for bar,value in zip(bars,values):
        ax.text(bar.get_x()+bar.get_width()/2,value+values.max()*.025,f'{value:,.1f}',ha='center',color=white,fontsize=11)
    fig.text(.10,.88,'主要州销售金额分布',color=white,fontsize=22,weight='bold')
    fig.text(.10,.81,f"圣保罗州销售金额最高，占分析样本的{df.iloc[0]['share']:.1%}",color=white,fontsize=12)
    ax.text(-.06,1.02,'单位：万 BRL',transform=ax.transAxes,color=muted,fontsize=10)
    fig.text(.10,.085,'注：Olist官方数据；2017.01—2018.07，已交付订单，按购买时间统计。',color=muted,fontsize=9)
    fig.text(.10,.048,'展示销售金额排名前6州；商品金额不含运费。样式参考教材模板01，Python生成。',color=muted,fontsize=9)
    out=ROOT/'outputs/figures'
    out.mkdir(parents=True,exist_ok=True)
    path=out/'fig01_主要州销售金额分布.png'
    fig.savefig(path,dpi=160,facecolor=bg)
    plt.close(fig)
    print(str(path))


if __name__=='__main__':
    main()
