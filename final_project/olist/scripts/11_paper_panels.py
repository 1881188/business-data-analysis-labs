"""Redraw the 15 verified chart views as eight readable paper figure groups."""
from pathlib import Path
import os, json, hashlib, warnings
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'outputs/.matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,ticker
from matplotlib.patches import Rectangle
from matplotlib.text import Text
import pandas as pd
import numpy as np
from chart_styles import gradient_bars, layered_ring, smooth_monthly

OUT=ROOT/'outputs/paper_panels'
TABLES=ROOT/'outputs/tables'
BG,WHITE,MUTED,BLUE,PINK,TEAL,GOLD='#1B2043','#F1F3FA','#C4CADE','#008CCC','#EE4776','#10B9BC','#F9C64A'
CAT={'health_beauty':'美妆健康','watches_gifts':'手表礼品','bed_bath_table':'床品卫浴','sports_leisure':'运动休闲','computers_accessories':'电脑配件','furniture_decor':'家具装饰'}
GROUPS=[
 {'id':1,'title':'销售趋势与同期变化','original_figures':[6,7],'templates':['11','13'],'layout':'two rows'},
 {'id':2,'title':'主要收货州销售规模及平均线','original_figures':[1,2],'templates':['01','02'],'layout':'two columns'},
 {'id':3,'title':'主要收货州同期金额与增幅','original_figures':[4,5,10],'templates':['06','08','26'],'layout':'one wide panel above two columns'},
 {'id':4,'title':'主要商品类别金额与份额','original_figures':[3,8],'templates':['03','19'],'layout':'two columns'},
 {'id':5,'title':'ABC类别贡献与累计分布','original_figures':[9,11],'templates':['20'],'layout':'two rows'},
 {'id':6,'title':'手表与礼品独立测试回测','original_figures':[12],'templates':[],'layout':'full width'},
 {'id':7,'title':'手表与礼品历史预测及预测区间','original_figures':[13],'templates':[],'layout':'full width'},
 {'id':8,'title':'配送体验与客户评价','original_figures':[14,15],'templates':[],'layout':'two columns'},
]

def read(name): return pd.read_csv(TABLES/name)

def new(height):
    return plt.figure(figsize=(9,height),dpi=240,facecolor=BG)

def axis(fig,rect,title,horizontal=False):
    ax=fig.add_axes(rect,facecolor=BG)
    ax.set_title(title,loc='left',color=WHITE,fontsize=15,pad=17)
    ax.spines[['left','right','top']].set_visible(False)
    ax.spines['bottom'].set_color('#77819D')
    ax.tick_params(colors=MUTED,labelsize=13,length=0,pad=5)
    ax.grid(axis='x' if horizontal else 'y',color=MUTED,alpha=.20,ls=':',zorder=0)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(4))
    return ax

def finish(fig,n,notes):
    fig.text(.075,.025,notes,color=MUTED,fontsize=12,va='bottom',linespacing=1.5)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always');fig.canvas.draw()
        assert not [x for x in w if 'Glyph' in str(x.message)],w
    renderer=fig.canvas.get_renderer()
    outside=[]
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text().strip():continue
        b=t.get_window_extent(renderer)
        if b.x0< -2 or b.y0< -2 or b.x1>fig.bbox.width+2 or b.y1>fig.bbox.height+2:outside.append(t.get_text())
    assert not outside,(n,outside)
    path=OUT/f'paper{n:02d}.png'
    fig.savefig(path,dpi=240,facecolor=BG)
    g=GROUPS[n-1];g.update(filename=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),text_bounds='passed')
    plt.close(fig)
    print(path.name,flush=True)

def bar_values(ax,values,color=BLUE):
    bars=gradient_bars(ax,values,width=.50)
    for b,v in zip(bars,values):ax.text(b.get_x()+b.get_width()/2,v+max(values)*.03,f'{v:.1f}',ha='center',color=WHITE,fontsize=12)
    ax.set_ylim(0,max(values)*1.27)

def main():
    OUT.mkdir(exist_ok=True)
    fp=os.environ.get('OLIST_CHINESE_FONT','C:/Windows/Fonts/msyh.ttc')
    font_manager.fontManager.addfont(fp)
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=fp).get_name(),'axes.unicode_minus':False,'font.size':14})
    monthly=read('analysis_monthly_sales.csv')
    state=read('analysis_state_sales.csv').head(6)
    categories=read('analysis_category_abc.csv')
    abc=read('analysis_abc_summary.csv').set_index('abc_class')
    states=state.customer_state.tolist()
    vals=state.revenue_brl.to_numpy()/10000
    left=state.jan_jul_2017_brl.to_numpy()/10000
    right=state.jan_jul_2018_brl.to_numpy()/10000
    growth=state.jan_jul_yoy.to_numpy()

    fig=new(6.8)
    ax=axis(fig,[.09,.61,.84,.28],'(a) 月度销售趋势  模板11')
    v=monthly.revenue_brl.to_numpy()/10000;x=np.arange(len(v));peak=int(np.argmax(v))
    smooth_monthly(ax,x,v,PINK,lw=2.5)
    ax.scatter([peak],[v[peak]],color=PINK,s=35)
    ax.vlines(peak,0,v[peak],color=PINK,ls=':',lw=1)
    ax.annotate(f'峰值 {v[peak]:.2f}万',(peak,v[peak]),xytext=(-6,12),textcoords='offset points',ha='right',color=WHITE,fontsize=13)
    ax.set_xticks([0,3,6,9,12,15,18],['2017-01','04','07','10','2018-01','04','07'])
    ax.set_ylim(0,118);ax.set_ylabel('万 BRL',color=MUTED,fontsize=13)
    ax=axis(fig,[.09,.18,.84,.27],'(b) 两年1—7月同期对比  模板13')
    for year,color in [('2017',PINK),('2018',BLUE)]:
        sub=monthly[monthly.purchase_month.str.startswith(year)].head(7)
        ax.plot(range(1,8),sub.revenue_brl/10000,'o-',color=color,lw=2.4,label=year+'年')
    ax.set_xticks(range(1,8),[f'{i}月' for i in range(1,8)]);ax.set_ylim(0,120)
    ax.set_ylabel('万 BRL',color=MUTED,fontsize=13)
    ax.legend(frameon=False,labelcolor=WHITE,fontsize=13,ncol=2,loc='upper left')
    finish(fig,1,'来源：Olist；2017.01—2018.07已交付订单，商品金额不含运费。\n同比金额+161.59%，订单数+160.78%，客单价+0.31%；平滑线为显示插值。')

    fig=new(4.8)
    mean=read('analysis_state_sales.csv').revenue_brl.mean()/10000
    for j,title in enumerate(['(a) 主要州金额  模板01','(b) 金额与全国州均值  模板02']):
        ax=axis(fig,[.075+j*.49,.25,.405,.56],title)
        bar_values(ax,vals);ax.set_xticks(range(6),states);ax.set_ylabel('万 BRL',color=MUTED,fontsize=13)
        if j:
            ax.axhline(mean,color=GOLD,lw=1.6)
            ax.text(.98,.91,f'州均值 {mean:.2f}万',ha='right',transform=ax.transAxes,color=GOLD,fontsize=12)
    finish(fig,2,'来源：Olist；2017.01—2018.07已交付订单；展示金额前6州。\nSP为圣保罗州；平均线按全部27个州级地区计算，非前6州均值。')

    fig=new(8.3)
    ax=axis(fig,[.13,.62,.77,.25],'(a) 两年同期金额  模板06')
    y=np.arange(6)
    ax.barh(y,-left,color=BLUE,height=.53,label='2017年');ax.barh(y,right,color=PINK,height=.53,label='2018年')
    ax.set_yticks(y,states);ax.invert_yaxis();limit=max(right)*1.25
    ax.set_xlim(-limit,limit);ax.set_ylim(5.7,-1.0);ax.grid(False)
    ax.set_xticks(np.linspace(-max(right),max(right),5))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v,p:f'{abs(v):.0f}'))
    ax.set_xlabel('两侧比例相同  单位：万 BRL',color=MUTED,fontsize=12)
    for i,(a,b) in enumerate(zip(left,right)):
        ax.text(-a-5,i,f'{a:.1f}',ha='right',va='center',color=WHITE,fontsize=12)
        ax.text(b+5,i,f'{b:.1f}',ha='left',va='center',color=WHITE,fontsize=12)
    ax.legend(frameon=False,labelcolor=WHITE,fontsize=12,ncol=2,loc='lower right',bbox_to_anchor=(1,1.01))
    ax=axis(fig,[.075,.18,.395,.27],'(b) 金额与同比标注  模板08')
    ax.set_axis_off()
    for i,(s,v,g) in enumerate(zip(states,right,growth)):
        width=v/max(right)*.57
        ax.barh(i,width,color=BLUE,height=.55)
        ax.add_patch(Rectangle((.64,i-.275),.28,.55,color='#A84667'))
        ax.text(-.02,i,s,color=MUTED,ha='right',va='center',fontsize=12)
        ax.text(.60,i,f'{v:.1f}',color=WHITE,va='center',ha='right',fontsize=11)
        ax.text(.78,i,f'+{g:.1%}',ha='center',color=WHITE,va='center',fontsize=12)
    ax.set_xlim(-.04,.95);ax.set_ylim(5.7,-.8)
    ax=axis(fig,[.57,.18,.37,.27],'(c) 金额与同比徽标  模板26')
    ax.bar(range(6),right,color=PINK,width=.47,zorder=3)
    ax.set_xticks(range(6),states);ax.set_ylim(0,max(right)*1.7)
    ax.set_ylabel('万 BRL',color=MUTED,fontsize=12)
    for i,(v,g) in enumerate(zip(right,growth)):
        ax.text(i,v+max(right)*.035,f'{v:.0f}',ha='center',color=WHITE,fontsize=11)
        ax.scatter(i,max(right)*1.45,s=1050*g/max(growth),color=BLUE,zorder=4)
        ax.text(i,max(right)*1.45,f'{g:.0%}',ha='center',va='center',color=WHITE,fontsize=10,zorder=5)
    finish(fig,3,'来源：Olist；均比较2017与2018年1—7月已交付商品金额。\n(b)金额单位为万BRL；等宽粉框只标注同比，(c)徽标为同比，均不与金额相加。')

    fig=new(5.4)
    top=categories.head(6);v=top.revenue_brl.to_numpy()/10000
    ax=axis(fig,[.08,.30,.40,.50],'(a) 主要品类金额  模板03')
    gradient_bars(ax,v,width=.24,rounded=True)
    ax.set_xticks(range(6),[CAT.get(c,c)[:2]+'\n'+CAT.get(c,c)[2:] for c in top.category_display],fontsize=12)
    ax.set_ylim(0,max(v)*1.26);ax.set_ylabel('万 BRL',color=MUTED,fontsize=13)
    ax.set_xlim(-.65,5.6)
    for i,value in enumerate(v):ax.text(i,value+max(v)*.05,f'{value:.1f}',ha='center',color=WHITE,fontsize=12)
    ax=axis(fig,[.56,.37,.36,.42],'(b) 主要品类份额  模板19')
    first=categories.head(5);values=list(first.revenue_cents)+[int(categories.revenue_cents.sum()-first.revenue_cents.sum())]
    labels=[CAT.get(c,c) for c in first.category_display]+['其他（含缺失）']
    wedges,_=ax.pie(values,colors=[PINK,GOLD,TEAL,BLUE,'#7664E1','#454A77'],startangle=90,counterclock=False,wedgeprops={'edgecolor':BG,'linewidth':1})
    ax.set_axis_off()
    ax.legend(wedges,[f'{s} {v/sum(values):.1%}' for s,v in zip(labels,values)],loc='upper center',bbox_to_anchor=(.5,.07),ncol=2,frameon=False,labelcolor=WHITE,fontsize=12,columnspacing=.7,handlelength=.9)
    finish(fig,4,'来源：Olist；2017.01—2018.07已交付商品金额；(a)前6品类，(b)前5品类。\n前5品类合计贡献39.83%；饼图分母含全部品类及类别缺失金额。')

    fig=new(7.1)
    ax=axis(fig,[.13,.60,.75,.27],'(a) ABC组别金额贡献  模板20')
    groups=['A','B','C','U'];values=[int(abc.loc[g,'revenue_cents']) for g in groups]
    wedges=layered_ring(ax,values,[BLUE,PINK,TEAL,GOLD])
    ax.text(0,.07,'79.85%',ha='center',color=WHITE,fontsize=17)
    ax.text(0,-.27,'A类金额贡献',ha='center',color=MUTED,fontsize=10)
    ax.legend(wedges,[f'{g}类  {int(abc.loc[g,"categories"])}类  {v/sum(values):.2%}' for g,v in zip(groups,values)],loc='center left',bbox_to_anchor=(1.05,.5),frameon=False,labelcolor=WHITE,fontsize=13)
    ax.set_xlim(-1.9,3.2);ax.set_axis_off()
    ax=axis(fig,[.10,.20,.77,.25],'(b) 已知类别帕累托分布')
    known=categories[categories.abc_class.ne('U')].reset_index(drop=True);x=np.arange(1,len(known)+1)
    ax.bar(x,known.revenue_brl/10000,color=known.abc_class.map({'A':BLUE,'B':PINK,'C':TEAL}),width=.85,zorder=3)
    ax.set_xticks([1,17,33,50,73]);ax.set_xlim(0,74);ax.set_ylabel('万 BRL',color=MUTED,fontsize=12)
    ax.set_xlabel('品类按金额降序排列',color=MUTED,fontsize=12)
    second=ax.twinx();second.plot(x,known.cumulative_share_known*100,color=GOLD,lw=2)
    second.set_ylim(0,107);second.set_yticks([0,50,80,95]);second.tick_params(colors=GOLD,labelsize=12,length=0)
    second.yaxis.set_major_formatter(ticker.PercentFormatter())
    for s in second.spines.values():s.set_visible(False)
    for p in [80,95]:second.axhline(p,color=GOLD,alpha=.45,ls=':',lw=1)
    ax.axvline(17.5,color=WHITE,ls='--',lw=1)
    finish(fig,5,'来源：Olist；已交付商品金额；(a)分母为全部金额，U为类别缺失。\n(a)角度表份额，径向层级仅作样式；(b)排除U类，阈值80%/95%。')

    hold=read('forecast_july_holdout.csv');fig=new(4.9)
    ax=axis(fig,[.09,.28,.84,.53],'2018年7月独立测试回测')
    for col,color,label,ls in [('actual_brl',BLUE,'实际下单金额','-'),('sarima_brl',PINK,'SARIMA','-'),('weekday_4week_mean_brl',GOLD,'近4周同星期均值','--')]:
        ax.plot(range(len(hold)),hold[col]/1000,color=color,lw=2,label=label,ls=ls)
    ax.set_xticks([0,7,14,21,30],['7月1日','8日','15日','22日','31日']);ax.set_ylim(0,hold.actual_brl.max()/1000*1.3)
    ax.set_ylabel('千 BRL',color=MUTED,fontsize=13)
    ax.legend(frameon=False,labelcolor=WHITE,fontsize=12,ncol=3,loc='upper left')
    finish(fig,6,'来源：Olist；下单商品金额，含最终取消等状态，区别于已交付销售口径。\nSARIMA RMSE为1367.55 BRL；强基线1390.83 BRL，仅改善1.67%。')

    daily=read('forecast_daily_series.csv').tail(45);future=read('forecast_august_simulation.csv');fig=new(4.9)
    ax=axis(fig,[.09,.28,.84,.53],'截至2018年7月末的随后14天历史预测')
    ax.plot(range(45),daily.ordered_value_brl/1000,color=BLUE,lw=2,label='历史下单金额')
    x=np.arange(45,59);ax.plot(x,future.forecast_brl/1000,color=PINK,lw=2,label='SARIMA预测')
    ax.fill_between(x,future.lower95_brl/1000,future.upper95_brl/1000,color=BLUE,alpha=.28,label='95%预测区间')
    ax.axvline(44.5,color=MUTED,ls='--',lw=1);ax.set_xticks([0,14,30,44,58],['6月17日','7月1日','17日','31日','8月14日'])
    ax.set_ylabel('千 BRL',color=MUTED,fontsize=13);ax.set_ylim(0,max(daily.ordered_value_brl.max(),future.upper95_brl.max())/1000*1.3)
    ax.legend(frameon=False,labelcolor=WHITE,fontsize=12,ncol=3,loc='upper left')
    finish(fig,7,'来源：Olist；下单商品金额含最终取消等状态；演示2018年历史预测。\n95%区间下界截为0，未含参数不确定性，不能直接作为补货数量。')

    review=read('analysis_delivery_review.csv');fig=new(5.0)
    ax=axis(fig,[.12,.31,.34,.48],'(a) 平均评分',True)
    for i,row in review.iterrows():
        ax.barh(1-i,row.mean_score,color=[BLUE,PINK][i],height=.38,zorder=3)
        ax.text(row.mean_score+.1,1-i,f'{row.mean_score:.2f}',va='center',color=WHITE,fontsize=14)
    ax.set_yticks([1,0],['按期签收','逾期签收']);ax.set_xlim(0,5.3);ax.set_ylim(-.7,1.7)
    ax.set_xlabel('满分5分',color=MUTED,fontsize=12)
    ax=axis(fig,[.62,.31,.32,.48],'(b) 1—2分低评分比例',True)
    for i,row in review.iterrows():
        p=row.low_score_rate*100;low=row.low_score_ci95_lower*100;up=row.low_score_ci95_upper*100
        ax.errorbar(p,1-i,xerr=[[p-low],[up-p]],fmt='o',color=[BLUE,PINK][i],ms=9,lw=2,capsize=5)
        ax.text(p+3,1-i,f'{p:.2f}%',va='center',color=WHITE,fontsize=13)
    ax.set_yticks([1,0],['按期签收','逾期签收']);ax.set_xlim(0,95);ax.set_ylim(-.7,1.7)
    ax.xaxis.set_major_formatter(ticker.PercentFormatter());ax.set_xlabel('误差线：Wilson 95%区间',color=MUTED,fontsize=12)
    finish(fig,8,'来源：Olist；有效配送和评价订单；按期83,237单，逾期5,993单。\n两组差异为描述性关联；评价可能先于签收，不能据此解释因果。')
    assert sorted(i for g in GROUPS for i in g['original_figures'])==list(range(1,16))
    (OUT/'panel_manifest.json').write_text(json.dumps(GROUPS,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
