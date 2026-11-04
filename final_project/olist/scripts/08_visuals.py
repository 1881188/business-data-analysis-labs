"""Ten textbook-style templates, six model charts and delivery evidence.

All charts use previously reconciled analysis tables. No Excel/BI images.
"""
from pathlib import Path
import os
import json
import warnings
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'outputs/.matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,ticker
from matplotlib.patches import Rectangle
from matplotlib.text import Text
import numpy as np
import pandas as pd
from chart_styles import gradient_bars, layered_ring, smooth_monthly
from PIL import Image,ImageOps,ImageDraw

TABLES=ROOT/'outputs/tables'
FIGURES=ROOT/'outputs/figures'
BG,WHITE,MUTED,BLUE,PINK,TEAL,GOLD='#1B2043','#F1F3FA','#A9B0CB','#008CCC','#EE4776','#10B9BC','#F9C64A'
PALETTE=[PINK,GOLD,TEAL,BLUE,'#6658DC','#8C5DC4']
STATE={'SP':'圣保罗州','RJ':'里约热内卢州','MG':'米纳斯吉拉斯州','RS':'南里奥格兰德州','PR':'巴拉那州','SC':'圣卡塔琳娜州'}
CATEGORY={'health_beauty':'美妆健康','watches_gifts':'手表与礼品','bed_bath_table':'床品卫浴',
          'sports_leisure':'运动休闲','computers_accessories':'电脑配件','furniture_decor':'家具装饰','cool_stuff':'创意商品'}
INDEX=[]
BOUNDS=[]


def read(name):
    return pd.read_csv(TABLES/name)


def setup():
    font_path=os.environ.get('OLIST_CHINESE_FONT','C:/Windows/Fonts/msyh.ttc')
    if not Path(font_path).is_file():
        raise RuntimeError('Provide a Chinese font path via OLIST_CHINESE_FONT')
    font_manager.fontManager.addfont(font_path)
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font_path).get_name(),
                         'axes.unicode_minus':False,'font.size':11,'figure.max_open_warning':10})
    FIGURES.mkdir(parents=True,exist_ok=True)


def base(title,subtitle,unit=None,footer=None):
    fig=plt.figure(figsize=(12,6.75),dpi=160,facecolor=BG)
    ax=fig.add_axes([.105,.22,.83,.51],facecolor=BG)
    fig.text(.10,.88,title,color=WHITE,fontsize=22,weight='bold')
    fig.text(.10,.81,subtitle,color=WHITE,fontsize=12)
    fig.text(.10,.085,footer or '注：Olist官方数据；2017.01—2018.07，已交付订单，商品金额不含运费。',color=MUTED,fontsize=9)
    if unit:
        ax.text(-.06,1.02,unit,transform=ax.transAxes,color=MUTED,fontsize=10)
    style(ax)
    return fig,ax


def style(ax,horizontal=False):
    ax.spines[['left','right','top']].set_visible(False)
    ax.spines['bottom'].set_color('#6A7393')
    ax.tick_params(axis='both',colors=MUTED,length=0,pad=9,labelsize=10)
    ax.grid(axis='x' if horizontal else 'y',color='#667092',linestyle=(0,(2,3)),linewidth=.6,alpha=.35,zorder=0)
    if not horizontal:
        ax.yaxis.set_major_locator(ticker.MaxNLocator(4))


def legend(ax,**kwargs):
    return ax.legend(frameon=False,labelcolor=MUTED,fontsize=10,**kwargs)


def save(fig,number,name,template,method,conclusion,source,scope):
    filename=f'fig{number:02d}_{name}.png'
    fig.text(.10,.048,f"{('样式参考教材模板'+template) if template else '业务分析图'}；Python生成。{scope}",color=MUTED,fontsize=9)
    with warnings.catch_warnings(record=True) as found:
        warnings.simplefilter('always')
        fig.canvas.draw()
        glyph=[str(w.message) for w in found if 'Glyph' in str(w.message)]
        if glyph:
            raise RuntimeError(f'Missing font glyphs: {glyph[:3]}')
    renderer=fig.canvas.get_renderer()
    outside=[]
    for t in fig.findobj(Text):
        if not t.get_visible() or not t.get_text().strip():
            continue
        bb=t.get_window_extent(renderer=renderer)
        if bb.x0 < -2 or bb.y0 < -2 or bb.x1 > fig.bbox.width+2 or bb.y1>fig.bbox.height+2:
            outside.append(t.get_text())
    BOUNDS.append({'file':filename,'text_outside_canvas':outside})
    if outside:
        raise RuntimeError(f'Text outside canvas in {filename}: {outside}')
    fig.savefig(FIGURES/filename,dpi=160,facecolor=BG)
    plt.close(fig)
    INDEX.append({'figure':f'fig{number:02d}','filename':filename,'template':template or '新增业务图',
                  'method':method,'conclusion':conclusion,'source_table':source,'scope':scope})
    print(filename,flush=True)


def xlabel_states(ax,df):
    ax.set_xticks(np.arange(len(df)),[STATE.get(s,s)+'\n'+s for s in df['customer_state']])


def number_bars(ax,bars,values,headroom=.025):
    top=max(values)
    for bar,v in zip(bars,values):
        ax.text(bar.get_x()+bar.get_width()/2,v+top*headroom,f'{v:,.1f}',ha='center',color=WHITE,fontsize=11)
    ax.set_ylim(0,top*1.23)


def annotated_pie(ax,values,labels,colors,donut=False):
    ax.set_position([.26,.18,.48,.57])
    if donut:
        wedges=layered_ring(ax,values,colors)
    else:
        wedges,_=ax.pie(values,colors=colors,startangle=90,counterclock=False,
                        wedgeprops={'edgecolor':BG,'linewidth':1})
    ax.set_aspect('equal')
    ax.set_xlim(-1.75,1.75)
    ax.set_ylim(-1.36,1.36)
    groups={-1:[],1:[]}
    for wedge,label,value in zip(wedges,labels,values):
        angle=np.deg2rad((wedge.theta1+wedge.theta2)/2)
        radius=wedge.r
        x,y=radius*np.cos(angle),radius*np.sin(angle)
        groups[1 if x>=0 else -1].append((y,x,label,value))
    total=sum(values)
    if donut:
        # Tiny C/U sectors are labelled above the ring on opposite sides.
        # Fixed exterior routing avoids crossing clustered radial leaders.
        placements=[(1.48,-.10),(-1.48,.12),(-1.48,1.13),(1.48,1.13)]
        for i,(wedge,label,value) in enumerate(zip(wedges,labels,values)):
            angle=np.deg2rad((wedge.theta1+wedge.theta2)/2)
            x,y=wedge.r*np.cos(angle),wedge.r*np.sin(angle)
            tx,ty=placements[i]
            if i==0:
                points=[(x,y),(x*1.11,y*1.11),(1.33,ty),(1.42,ty)]
            elif i==1:
                points=[(x,y),(-1.21,y),(-1.33,ty),(-1.42,ty)]
            else:
                top=1.22 if i==2 else 1.33
                points=[(x,y),(x*1.10,top),(1.33 if tx>0 else -1.33,top),(1.42 if tx>0 else -1.42,ty)]
            ax.plot(*zip(*points),color='#65708F',lw=.8,clip_on=False)
            ax.text(tx,ty,f'{label}\n{value/total:.1%}',ha='left' if tx>0 else 'right',
                    va='center',color=WHITE,fontsize=10)
        ax.set_axis_off()
        return
    for side,entries in groups.items():
        entries.sort(reverse=True)
        if len(entries)>1:
            # Keep clustered small slices near their anchors instead of forcing
            # labels to the opposite hemisphere of the ring.
            center=float(np.mean([e[0] for e in entries]))
            span=.40*(len(entries)-1)
            levels=np.linspace(center+span/2,center-span/2,len(entries))
            if levels[0]>1.03:
                levels-=levels[0]-1.03
            if levels[-1]<-1.03:
                levels+=-1.03-levels[-1]
        else:
            levels=[0]
        for (y,x,label,value),level in zip(entries,levels):
            # Radial segment then an exterior elbow avoids crossing the pie/ring.
            ax.plot([x*.99,x*1.17,side*1.28,side*1.40],
                    [y*.99,y*1.17,level,level],color='#65708F',lw=.8,clip_on=False)
            ax.text(side*1.43,level,f'{label}\n{value/total:.1%}',
                    color=WHITE,fontsize=11,ha='left' if side>0 else 'right',va='center')
    ax.set_axis_off()


def main():
    setup()
    state=read('analysis_state_sales.csv').head(6)
    category=read('analysis_category_abc.csv')
    monthly=read('analysis_monthly_sales.csv')
    abc=read('analysis_abc_summary.csv')
    summary=json.loads((TABLES/'analysis_summary.json').read_text(encoding='utf-8'))
    forecast=json.loads((TABLES/'forecast_summary.json').read_text(encoding='utf-8'))
    x=np.arange(6)
    vals=state['revenue_brl'].to_numpy()/10000
    fig,ax=base('主要州销售金额分布','圣保罗州销售金额最高，占分析样本的37.8%','单位：万 BRL')
    number_bars(ax,gradient_bars(ax,vals),vals)
    xlabel_states(ax,state)
    save(fig,1,'主要州销售金额分布','01','描述性比较','圣保罗州贡献总金额的37.8%。','analysis_state_sales.csv','展示金额排名前6州。')

    allstates=read('analysis_state_sales.csv')
    mean=allstates['revenue_brl'].mean()/10000
    fig,ax=base('主要州销售金额与全国州均值',f'展示前6州；全部{len(allstates)}个州级地区的平均金额为{mean:.1f}万 BRL','单位：万 BRL')
    bars=gradient_bars(ax,vals)
    number_bars(ax,bars,vals)
    xlabel_states(ax,state)
    ax.axhline(mean,color=GOLD,lw=1.2)
    ax.text(.98,.94,f'州均值 {mean:.1f}万',transform=ax.transAxes,ha='right',color=GOLD,fontsize=10)
    save(fig,2,'州销售金额与平均线','02','描述性比较','平均线分母为全部27个州级地区，不是所展示的前6州。','analysis_state_sales.csv','州均值为非加权平均。')

    top=category.head(6)
    v=top['revenue_brl'].to_numpy()/10000
    fig,ax=base('主要商品类别销售金额','美妆健康与手表礼品金额居前，类别排名按商品金额计算','单位：万 BRL')
    gradient_bars(ax,v,width=.24,rounded=True)
    ax.set_xticks(x,[CATEGORY.get(c,c) for c in top['category_display']])
    ax.set_ylim(0,max(v)*1.24)
    for i,value in enumerate(v):
        ax.text(i,value+max(v)*.06,f'{value:.1f}',ha='center',color=WHITE,fontsize=11,
                bbox={'boxstyle':'round,pad=.25','fc':'#24567B','ec':'none'})
    save(fig,3,'商品销售渐变圆角柱形图','03','描述性比较','美妆健康为样本期商品金额最高类别。','analysis_category_abc.csv','展示前6个类别。')

    left=state['jan_jul_2017_brl'].to_numpy()/10000
    right=state['jan_jul_2018_brl'].to_numpy()/10000
    fig,ax=base('主要州同期销售金额对比','比较2017与2018年1—7月，左右两侧使用相同数值比例',None,
                '注：Olist官方数据；两年均仅比较1—7月，已交付订单，金额不含运费。')
    ax.set_axis_off()
    y=np.arange(6)
    la=fig.add_axes([.11,.24,.32,.45],facecolor=BG)
    ra=fig.add_axes([.57,.24,.32,.45],facecolor=BG)
    limit=max(right)*1.13
    for a,data,color in [(la,left,BLUE),(ra,right,PINK)]:
        a.barh(y,data,color=color,height=.48)
        a.set_ylim(5.7,-.7)
        a.set_xlim(0,limit)
        a.set_axis_off()
        for i,value in enumerate(data):
            a.text(value+4,i,f'{value:.1f}',ha='right' if a is la else 'left',va='center',color=WHITE,fontsize=10)
    la.invert_xaxis()
    fig.text(.25,.72,'2017年',color=BLUE,ha='center',fontsize=12)
    fig.text(.73,.72,'2018年',color=PINK,ha='center',fontsize=12)
    for i,s in enumerate(state['customer_state']):
        display_y=ra.transData.transform((0,i))[1]/fig.bbox.height
        fig.text(.50,display_y,STATE.get(s,s)+' '+s,color=MUTED,fontsize=10,ha='center',va='center')
    save(fig,4,'主要州同期蝴蝶图','06','趋势与同比补充','所展示6州2018年同期金额均高于2017年。','analysis_state_sales.csv','左右共用比例；单位：万 BRL。')

    fig,ax=base('主要州销售金额及同比变化','蓝条表示2018年1—7月金额；粉色框单独标注同比增幅',None,
                '注：Olist官方数据；已交付订单，同比比较2018与2017年1—7月。')
    ax.set_position([.19,.23,.68,.48])
    ax.set_axis_off()
    normalized=right/right.max()*.76
    for i,(s,width,amount,growth) in enumerate(zip(state['customer_state'],normalized,right,state['jan_jul_yoy'])):
        ax.barh(i,width,color=BLUE,height=.55)
        ax.add_patch(Rectangle((.80,i-.275),.20,.55,color='#A84667'))
        ax.text(-.025,i,STATE.get(s,s)+' '+s,ha='right',va='center',color=MUTED,fontsize=10)
        ax.text(width/2,i,f'{amount:.1f}万',ha='center',va='center',color=WHITE,fontsize=10)
        ax.text(.90,i,f'+{growth:.1%}',ha='center',va='center',color=WHITE,fontsize=10)
    ax.set_xlim(0,1.08)
    ax.set_ylim(5.6,-.8)
    save(fig,5,'州销售金额与同比条形图','08','趋势与同比补充','粉色同比标注为独立指标，不与销售金额相加。','analysis_state_sales.csv','粉色框等宽，仅作标注；金额单位BRL。')

    v=monthly['revenue_brl'].to_numpy()/10000
    xx=np.arange(len(monthly))
    fig,ax=base('月度销售金额走势','2017年11月达到分析期峰值，随后月度金额有所波动','单位：万 BRL')
    smooth_monthly(ax,xx,v,PINK)
    peak=int(np.argmax(v))
    ax.plot(peak,v[peak],'o',color=PINK,ms=6)
    ax.vlines(peak,0,v[peak],color=PINK,ls=':',alpha=.5)
    ax.annotate(f'{v[peak]:.1f}',(peak,v[peak]),xytext=(0,12),textcoords='offset points',ha='center',color=WHITE,fontsize=11)
    ax.set_xticks(xx,[m[5:]+'月' for m in monthly['purchase_month']],fontsize=9)
    ax.set_xlim(-.5,18.5)
    ax.set_ylim(0,max(v)*1.16)
    for start,width,color,year in [(-.5,12,'#58BFD2','2017年'),(11.5,7,GOLD,'2018年')]:
        ax.add_patch(Rectangle((start,-.21),width,.07,transform=ax.get_xaxis_transform(),clip_on=False,color=color))
        ax.text(start+width/2,-.175,year,transform=ax.get_xaxis_transform(),color=BG,ha='center',va='center',fontsize=9)
    save(fig,6,'月度销售趋势','11','趋势1','2017年11月为样本期销售金额峰值；平滑曲线经过标记的原始月度值。','analysis_monthly_sales.csv','2018年仅含1—7月。')

    fig,ax=base('两年同期月度销售金额对比','2018年1—7月金额同比增长161.6%，客单价仅增长0.3%','单位：万 BRL',
                '注：Olist官方数据；已交付订单，两年均比较1—7月，金额不含运费。')
    for year,color in [('2017',PINK),('2018',BLUE)]:
        sub=monthly.loc[monthly['purchase_month'].str.startswith(year)].head(7)
        ax.plot(np.arange(1,8),sub['revenue_brl']/10000,'o-',color=color,lw=2,label=year+'年',ms=5)
    ax.set_xticks(range(1,8),[str(i)+'月' for i in range(1,8)])
    ax.set_ylim(0,115)
    legend(ax,loc='upper left',ncol=2)
    save(fig,7,'同期月度销售对比','13','趋势2','增长主要表现为订单数增加，而非客单价明显上涨。','analysis_monthly_sales.csv','同比为观察样本变化，不外推平台整体。')

    first=category.head(5)
    values=list(first['revenue_cents'])+[int(category['revenue_cents'].sum()-first['revenue_cents'].sum())]
    labels=[CATEGORY.get(c,c) for c in first['category_display']]+['其他类别']
    fig,ax=base('主要商品类别销售份额','前5个类别贡献39.8%，其余类别合并展示')
    annotated_pie(ax,values,labels,[PINK,GOLD,TEAL,BLUE,'#6859D9','#454A77'])
    save(fig,8,'商品类别销售份额','19','销售结构','前5类合计贡献39.8%；其他含缺失类别。','analysis_category_abc.csv','分母为全部分析商品金额。')

    fig,ax=base('ABC商品类别销售贡献','17个A类贡献总商品金额的79.9%，优先关注其服务稳定性')
    lookup=abc.set_index('abc_class')
    groups=['A','B','C','U']
    labels=[f"{g}类（{int(lookup.loc[g,'categories'])}类）" if g!='U' else '类别缺失' for g in groups]
    annotated_pie(ax,[lookup.loc[g,'revenue_cents'] for g in groups],labels,[BLUE,PINK,TEAL,GOLD],donut=True)
    ax.text(0,.10,'79.9%',ha='center',va='center',fontsize=25,color=WHITE)
    ax.text(0,-.22,'A类金额贡献',ha='center',color=MUTED,fontsize=11)
    save(fig,9,'ABC类别销售贡献','20','ABC1','ABC阈值以已知类别金额为分母；图中份额以全部金额为分母。','analysis_abc_summary.csv','累计界限80%/95%；角度表份额，径向层级仅作样式。')

    v=right
    fig,ax=base('主要州销售金额与同比增幅','2018年1—7月，圣保罗州金额与同比增幅均居所展示6州首位','单位：万 BRL',
                '注：Olist官方数据；已交付订单，同比比较2018与2017年1—7月。')
    ax.bar(x,v,width=.38,color=PINK,zorder=3)
    for i,(value,growth) in enumerate(zip(v,state['jan_jul_yoy'])):
        ax.text(i,value+max(v)*.025,f'{value:.1f}',ha='center',color=WHITE,fontsize=11)
        ax.scatter(i,max(v)*1.26,s=1100*growth/state['jan_jul_yoy'].max(),color=BLUE,zorder=4)
        ax.text(i,max(v)*1.26,f'{growth:.0%}',color=WHITE,ha='center',va='center',fontsize=10,zorder=5)
    ax.set_ylim(0,max(v)*1.44)
    xlabel_states(ax,state)
    save(fig,10,'州销售与同比徽标','26','趋势与同比补充','徽标代表各州同比增幅，柱高代表2018年同期金额。','analysis_state_sales.csv','仅展示分析期总金额排名前6州。')

    known=category.loc[category['abc_class'].ne('U')].reset_index(drop=True)
    fig,ax=base('商品类别帕累托分析','73个已知类别中，前17类累计贡献已知金额的81.0%','金额：万 BRL')
    xx=np.arange(1,len(known)+1)
    ax.bar(xx,known['revenue_brl']/10000,color=known['abc_class'].map({'A':BLUE,'B':PINK,'C':TEAL}),width=.8,zorder=3)
    ax.set_xticks([1,10,17,30,40,50,60,73])
    ax.set_xlabel('类别按销售金额从高到低排序',color=MUTED,fontsize=10,labelpad=8)
    ax.set_xlim(0,74)
    ax2=ax.twinx()
    ax2.plot(xx,known['cumulative_share_known']*100,color=GOLD,lw=1.8)
    ax2.set_ylim(0,110)
    ax2.tick_params(colors=MUTED,length=0)
    ax2.yaxis.set_major_formatter(ticker.PercentFormatter())
    for spine in ax2.spines.values():
        spine.set_visible(False)
    for pct in [80,95]:
        ax2.axhline(pct,color=GOLD,lw=.6,ls=':',alpha=.6)
    ax.axvline(17.5,color=MUTED,lw=.8,ls='--')
    fig.text(.59,.745,'A类 17类  /  B类 16类  /  C类 40类',color=WHITE,fontsize=10)
    save(fig,11,'品类帕累托分析',None,'ABC2','A类包含跨过80%阈值的类别，因此累计金额略超过80%。','analysis_category_abc.csv','排除类别缺失；右轴为已知类别累计占比。')

    hold=read('forecast_july_holdout.csv')
    fig,ax=base('手表与礼品日金额预测回测','7月独立测试：SARIMA比近4周同星期均值的RMSE低1.7%','单位：千 BRL',
                '注：Olist官方数据；2018年7月独立测试；下单金额含最终取消等状态，不含运费。')
    xx=np.arange(len(hold))
    for col,color,label,ls in [('actual_brl',BLUE,'实际下单金额','-'),('sarima_brl',PINK,'SARIMA预测','-'),('weekday_4week_mean_brl',GOLD,'近4周同星期均值','--')]:
        ax.plot(xx,hold[col]/1000,color=color,lw=1.7,label=label,ls=ls)
    ax.set_xticks([0,7,14,21,30],['7月1日','7月8日','7月15日','7月22日','7月31日'])
    ax.set_ylim(bottom=0,top=max(hold['actual_brl'].max(),hold['sarima_brl'].max())/1000*1.25)
    legend(ax,loc='upper left',ncol=3)
    save(fig,12,'SARIMA独立回测',None,'预测1','相对较强基线的优势只有1.7%，不能夸大模型能力。','forecast_july_holdout.csv','选择模型用6月验证集，7月未参与选型。')

    daily=read('forecast_daily_series.csv').tail(45)
    fut=read('forecast_august_simulation.csv')
    fig,ax=base('手表与礼品短期预测及95%区间','截至2018年7月31日拟合，演示随后14天的历史预测','单位：千 BRL',
                '注：Olist官方数据；下单金额含最终取消等状态，区别于已交付销售口径。')
    h=np.arange(len(daily))
    ff=np.arange(len(daily),len(daily)+len(fut))
    ax.plot(h,daily['ordered_value_brl']/1000,color=BLUE,lw=1.6,label='历史下单金额')
    ax.plot(ff,fut['forecast_brl']/1000,color=PINK,lw=2,label='SARIMA预测')
    ax.fill_between(ff,fut['lower95_brl']/1000,fut['upper95_brl']/1000,color=BLUE,alpha=.24,label='95%预测区间')
    ax.axvline(44.5,color=MUTED,lw=.8,ls='--')
    ax.set_xticks([0,14,30,44,58],['6月17日','7月1日','7月17日','7月31日','8月14日'])
    ax.set_ylim(0,max(daily['ordered_value_brl'].max(),fut['upper95_brl'].max())/1000*1.22)
    legend(ax,loc='upper left',ncol=3)
    save(fig,13,'SARIMA预测区间',None,'预测2','区间体现模型内不确定性，不能当作精确的补货指令。','forecast_daily_series.csv; forecast_august_simulation.csv','历史演示；区间下界截为0，未含参数不确定性。')

    review=read('analysis_delivery_review.csv')
    fig,ax=base('配送体验与客户评分','按期签收平均4.28分，逾期签收平均2.22分；仅表示关联',None,
                '注：Olist官方数据；2017.01—2018.07，有有效配送日期及评价的已交付销售订单。')
    means=review['mean_score'].to_numpy()
    ax.barh([1,0],means,height=.36,color=[BLUE,PINK])
    ax.set_yticks([1,0],['按期签收','逾期签收'])
    ax.set_xlim(0,5)
    ax.set_ylim(-.7,1.7)
    ax.set_xlabel('平均评分（满分5分）',color=MUTED,fontsize=10)
    ax.grid(False)
    ax.xaxis.grid(True,color='#667092',ls=':',alpha=.35)
    for yy,m,n in zip([1,0],means,review['orders']):
        ax.text(m+.08,yy,f'{m:.2f}分  /  {n:,}单',color=WHITE,va='center',fontsize=11)
    save(fig,14,'配送体验与评分',None,'配送评价补充','差异在州和主要品类分层后仍在，但不能视为因果。','analysis_delivery_review.csv','同单多评论取最新答复；评价可能先于签收。')

    fig,ax=base('逾期订单低评分比例更高','低评分定义为1—2分；点为比例，误差线为Wilson 95%区间',None,
                '注：Olist官方数据；有效配送和评价样本；按期83,237单，逾期5,993单。')
    p=review['low_score_rate'].to_numpy()*100
    lower=review['low_score_ci95_lower'].to_numpy()*100
    upper=review['low_score_ci95_upper'].to_numpy()*100
    for i,color in enumerate([BLUE,PINK]):
        ax.errorbar(p[i],1-i,xerr=[[p[i]-lower[i]],[upper[i]-p[i]]],fmt='o',color=color,ms=12,lw=2,capsize=6)
        ax.text(p[i]+3,1-i,f'{p[i]:.2f}%',color=WHITE,va='center',fontsize=12)
    ax.set_yticks([1,0],['按期签收','逾期签收'])
    ax.set_xlim(0,80)
    ax.set_ylim(-.7,1.7)
    ax.xaxis.set_major_formatter(ticker.PercentFormatter())
    ax.grid(False)
    ax.xaxis.grid(True,color='#667092',ls=':',alpha=.35)
    ax.set_xlabel('低评分订单比例',color=MUTED,fontsize=10)
    save(fig,15,'配送与低评分比例',None,'配送评价补充','逾期组低评分占比63.69%，按期组9.38%，并非因果效应估计。','analysis_delivery_review.csv','描述性比例区间，未进行随机实验。')

    pd.DataFrame(INDEX).to_csv(TABLES/'figure_index.csv',index=False,encoding='utf-8-sig')
    (TABLES/'figure_layout_checks.json').write_text(json.dumps(BOUNDS,ensure_ascii=False,indent=2),encoding='utf-8')
    # Contact sheets are QA aids, not additional charts for assignment counting.
    qa=ROOT/'outputs/qa'
    qa.mkdir(exist_ok=True)
    for page in range(3):
        selected=INDEX[page*6:(page+1)*6]
        sheet=Image.new('RGB',(1920,540*((len(selected)+1)//2)),BG)
        for j,item in enumerate(selected):
            with Image.open(FIGURES/item['filename']) as im:
                sheet.paste(im.convert('RGB').resize((960,540),Image.Resampling.LANCZOS),((j%2)*960,(j//2)*540))
        sheet.save(qa/f'contact_{page+1}.jpg',quality=94)
    lines=['# 图表索引与解读','','已生成15张独立图：10种教材模板、至少6张业务模型图（部分重合），以及2张配送评价补充图。模板总览用于定位参考类型，不重复计入独立图表数量。',
           '', '图片统一1920×1080像素、160dpi、中文字体、深蓝背景。模板编号对应两份第二章配套Excel工作簿的工作表；模板清单与正文位置见08_模板复现与章节对应.md。', '',
           'ABC两张图及趋势两张图使用已交付销售口径；预测两张图使用含后来取消的下单金额口径，在图脚明确标注。', '',
           '| 图号 | 模板 | 方法或用途 | 解读及口径 |','|---|---|---|---|']
    for item in INDEX:
        lines.append(f"| {item['figure']} | {item['template']} | {item['method']} | {item['conclusion']} {item['scope']} |")
    lines+=['','## 六张模型图对应关系','','- 趋势与同比环比：fig06、fig07。','- 品类ABC：fig09、fig11。','- SARIMA预测：fig12、fig13。',
             '', '## 模板复现说明', '',
             '01渐变柱形、02均值线柱形、03渐变圆角柱形、06蝴蝶、08数值百分比、11平滑折线、13对比折线、19圆饼、20分层圆环、26柱形圆，共10种。',
             '模板08中同比标注框等宽，不代表同比的数量尺度；蓝条长度单独编码金额，避免两种单位相加。模板11以PCHIP作显示插值并标记全部真实月度点，不增加观测；模板20的角度表示ABC金额份额，径向分层仅作样式。模板26的圆面积按正同比增幅缩放。',
             '', '## 论文图文整合', '', '全部15个分析视图在正文中组织为8组图，并在第5.2节增设10种模板总览。正文图1—图9与独立原图的对应关系见08_模板复现与章节对应.md；拼图不增加独立图计数。', '']
    (ROOT/'docs/05_图表索引与解读.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'figures':len(INDEX),'distinct_templates':len({x['template'] for x in INDEX if x['template']!='新增业务图'}),'text_bounds':'passed'},ensure_ascii=False))


if __name__=='__main__':
    main()
