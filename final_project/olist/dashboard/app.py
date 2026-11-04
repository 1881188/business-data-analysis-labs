"""Run: python dashboard/app.py --port 8050. Local-only by default."""
from pathlib import Path
import sys
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dash import Dash,html,dcc,Input,Output,State
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go
from dashboard.data import DashboardData,START,END,CATEGORY_NAMES,STATE_NAMES

DATA=DashboardData()
BG,PANEL,TEXT,MUTED,BLUE,PINK,GOLD='#10152C','#1B2340','#EEF3FF','#9BAACB','#23B9E6','#F06C96','#E8C66B'
app=Dash(__name__,assets_folder=str(Path(__file__).parent/'assets'),title='Olist · 销售与履约分析',update_title='正在更新…')
server=app.server


def graph_empty(message='当前筛选没有数据'):
    fig=go.Figure()
    fig.add_annotation(text=message,x=.5,y=.5,xref='paper',yref='paper',showarrow=False,font={'color':MUTED,'size':14})
    return themed(fig,empty=True)


def themed(fig,empty=False):
    fig.update_layout(template=None,paper_bgcolor=PANEL,plot_bgcolor=PANEL,
      font={'family':'Microsoft YaHei, sans-serif','color':MUTED,'size':11},
      margin={'l':45,'r':20,'t':15,'b':42},height=270,
      hoverlabel={'bgcolor':'#293755','font_color':TEXT},
      legend={'orientation':'h','y':1.13,'font_size':10},
      xaxis={'gridcolor':'#2D3855','zeroline':False},yaxis={'gridcolor':'#2D3855','zeroline':False})
    if empty:
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
    return fig


def figures(result):
    if not result['metrics']['orders']:
        return [graph_empty() for _ in range(4)]
    monthly=result['monthly']
    trend=themed(go.Figure(go.Scatter(x=monthly['month'],y=monthly['cents']/1000000,mode='lines+markers',
        line={'color':BLUE,'width':2.5},marker={'size':5},fill='tozeroy',fillcolor='rgba(35,185,230,.08)',
        hovertemplate='%{x}<br>商品金额 %{y:,.2f} 万 BRL<extra></extra>')))
    trend.update_yaxes(title_text='万 BRL',title_font_size=10)
    trend.update_xaxes(nticks=7)
    cats=result['categories'].head(8).iloc[::-1]
    names=[CATEGORY_NAMES.get(x,x.replace('_',' ')) for x in cats['category_display']]
    structure=themed(go.Figure(go.Bar(x=cats['cents']/1000000,y=names,orientation='h',
        marker_color=BLUE,customdata=cats['category_display'],
        hovertemplate='%{y}<br>%{x:,.2f} 万 BRL<extra></extra>')))
    structure.update_layout(margin={'l':135,'r':20,'t':15,'b':42})
    structure.update_xaxes(title_text='万 BRL',title_font_size=10)
    regions=result['states'].head(8)
    regional=themed(go.Figure(go.Bar(x=regions['customer_state'],y=regions['cents']/1000000,
        marker_color=PINK,hovertemplate='收货州 %{x}<br>%{y:,.2f} 万 BRL<extra></extra>')))
    regional.update_yaxes(title_text='万 BRL',title_font_size=10)
    ratings=result['ratings']
    if ratings.empty:
        delivery=graph_empty('当前筛选没有有效配送评价')
    else:
        labels=['逾期签收' if bool(x) else '按期签收' for x in ratings['late_delivery_flag']]
        extra=list(zip(ratings['orders'],ratings['low_rate']))
        delivery=themed(go.Figure(go.Bar(x=labels,y=ratings['score'],marker_color=[PINK if bool(x) else BLUE for x in ratings['late_delivery_flag']],
            text=[f'{v:.2f}' for v in ratings['score']],textposition='outside',textfont={'color':TEXT},
            customdata=extra,hovertemplate='%{x}<br>平均评分 %{y:.2f}<br>订单 %{customdata[0]:,}<br>低评分占比 %{customdata[1]:.1%}<extra></extra>')))
        delivery.update_yaxes(range=[0,5.35],title_text='平均评分 / 5分',title_font_size=10)
    return trend,structure,regional,delivery


def card(label,value,detail,accent='blue'):
    return html.Div([html.Div(label,className='metric-label'),html.Div(value,className='metric-value'),html.Div(detail,className='metric-detail')],className='metric '+accent)


def kpis(result):
    m=result['metrics']
    chosen=result['category_filtered']
    revenue=f"{m['revenue_cents']/1000000:,.2f}"
    aov='—' if m['aov_brl'] is None else f"{m['aov_brl']:,.2f}"
    late='—' if m['late_rate'] is None else f"{m['late_rate']:.2%}"
    return [card('所选商品金额' if chosen else '商品销售金额',revenue,'万 BRL · 不含运费'),
            card('涉及订单数',f"{m['orders']:,}",f"{m['customers']:,} 位客户 · 订单去重"),
            card('订单平均选品金额' if chosen else '客单价',aov,'BRL / 涉及订单','pink'),
            card('配送逾期率',late,f"有效配送 {m['logistics_orders']:,} 单",'gold')]


def table(result):
    view=DATA.export_view(result).head(30)
    if view.empty:
        return html.Div('当前筛选没有订单，请调整日期、州或品类。',className='empty-state')
    def display(col,value):
        if str(value)=='nan' or str(value)=='<NA>':
            return '—'
        if col=='订单ID':
            return html.Span(str(value)[:12]+'…',title=str(value))
        if col.endswith('_BRL') or col=='配送天数':
            return f'{float(value):,.2f}'
        if col=='评分':
            return f'{float(value):.0f}'
        if col=='是否逾期':
            return '逾期' if bool(value) else '按期'
        return str(value)
    columns=list(view.columns)
    names={'所选商品金额_BRL':'所选金额 BRL','整单商品金额_BRL':'整单金额 BRL'}
    return html.Div(html.Table([
        html.Thead(html.Tr([html.Th(names.get(c,c)) for c in columns])),
        html.Tbody([html.Tr([html.Td(display(c,row[c])) for c in columns]) for _,row in view.iterrows()])
    ]),className='table-scroll')


def panel(title,subtitle,graph_id,figure,anchor=None):
    return html.Section([html.Div([html.H2(title),html.P(subtitle)],className='panel-heading'),
                         dcc.Graph(id=graph_id,figure=figure,responsive=True,
                                   style={'height':'270px','minHeight':'270px','minWidth':0},
                                   config={'displayModeBar':False,'responsive':True})],
                         className='panel',id=anchor or graph_id+'-panel')


initial=DATA.select()
initial_figures=figures(initial)
app.layout=html.Div([
    html.Aside([
        html.Div([html.Span('O',className='brand-mark'),html.Div([html.Strong('olist'),html.Small('商业数据分析')])],className='brand'),
        html.Div('分析视角',className='sidebar-label'),
        html.Nav([html.A('01  经营总览',href='#top',className='active'),html.A('02  销售与商品',href='#trend'),html.A('03  配送体验',href='#delivery'),html.A('04  订单明细',href='#orders')]),
        html.Div('联动筛选',className='sidebar-label filter-label'),
        html.Label('购买日期'),
        dcc.DatePickerRange(id='date-filter',start_date=START,end_date=END,min_date_allowed=START,max_date_allowed=END,
           display_format='YYYY-MM-DD',first_day_of_week=1,minimum_nights=0,number_of_months_shown=1,
           start_date_placeholder_text='开始日期',end_date_placeholder_text='结束日期',with_portal=True),
        html.Label('收货州'),
        dcc.Dropdown(id='state-filter',options=[{'label':f'{s} · {STATE_NAMES.get(s,"州代码")}','value':s} for s in DATA.states],
                     value=[],multi=True,placeholder='全部州 · 可多选',className='filter-dropdown'),
        html.Label('商品类别'),
        dcc.Dropdown(id='category-filter',options=[{'label':f'{CATEGORY_NAMES.get(c,c)}'+(f' · {c}' if c in CATEGORY_NAMES else ''),'value':c} for c in DATA.categories],
                     value=[],multi=True,placeholder='全部品类 · 可搜索',className='filter-dropdown'),
        html.Button('重置全部筛选',id='reset-filters',n_clicks=0,className='reset-button'),
        html.Div([html.Strong('历史样本'),html.P('2017.01 — 2018.07'),html.Small('Olist 官方数据 · 全 Python 实现')],className='source-note')
    ],className='sidebar',id='dashboard-sidebar'),
    html.Div(id='sidebar-resizer',className='sidebar-resizer',role='separator',tabIndex=0,
             title='拖动调整宽度；双击恢复；左右方向键微调',
             **{'aria-label':'调整侧边栏宽度','aria-orientation':'vertical',
                'aria-controls':'dashboard-sidebar','aria-valuemin':240,'aria-valuemax':440,'aria-valuenow':280}),
    html.Main([
        html.Header([html.Div([html.Div('经营分析 / OLIST BRAZIL',className='eyebrow'),html.H1('销售与履约总览'),
                              html.P('从商品贡献到配送体验，查看同一筛选范围下的经营表现。')]),
                     html.Span('历史数据 · 非实时',className='status-badge')],className='page-header',id='top'),
        html.Div('2017-01-01 — 2018-07-31  ·  全部州  ·  全部品类',id='filter-summary',className='filter-summary'),
        dcc.Loading(html.Div(id='kpi-row',children=kpis(initial),className='kpi-grid'),type='dot',color=BLUE),
        html.Div(id='scope-note',className='scope-note'),
        html.Div([
            panel('月度销售趋势','筛选日期可能包含不完整月份，请结合时间范围比较。','monthly-chart',initial_figures[0],'trend'),
            panel('商品类别贡献','展示所选商品金额前8类；完整数据可在下方导出。','category-chart',initial_figures[1]),
            panel('收货州销售分布','按客户收货地址归属，展示金额前8个州。','state-chart',initial_figures[2]),
            panel('配送体验与评分','评分差异描述关联，不代表已识别因果关系。','delivery-chart',initial_figures[3],'delivery'),
        ],className='chart-grid'),
        html.Section([
            html.Div([html.Div([html.H2('订单明细'),html.P(id='table-note')]),html.Button('导出当前筛选 CSV',id='export-button',n_clicks=0,className='export-button')],className='table-heading'),
            dcc.Loading(html.Div(id='order-table',children=table(initial)),type='dot',color=BLUE),dcc.Download(id='download-orders'),
        ],className='panel order-panel',id='orders'),
        html.Details([html.Summary('查看指标口径与数据来源'),html.Div([
            html.P('销售样本为2017年1月至2018年7月购买、最终已交付且通过金额检查的订单。商品金额不含运费，不代表利润。'),
            html.P('品类筛选后，金额仅合计所选商品；涉及订单去重。配送和评分仍是这些订单的整单结果，不能归因于所选商品本身。'),
            html.P('逾期：签收自然日晚于预计自然日。分母为有效配送订单；平均评分仅使用同时有有效配送和评价的订单。'),
            html.P('同单多评论取最新答复；评价可能先于签收。结果不代表实时经营、因果效应或整个巴西市场。'),
            html.A('数据来源：Olist / Kaggle',href='https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce',target='_blank',rel='noopener noreferrer'),
            html.P('数据许可：CC BY-NC-SA 4.0。个人课程分析，保留来源与授权说明。'),
        ],className='method-content')],className='method-panel'),
        html.Footer('Olist 电商销售与履约分析  /  个人课程项目  /  Dash + Plotly',className='page-footer'),
    ],className='main-content',id='dashboard-main')
],className='app-shell')


@app.callback(Output('kpi-row','children'),Output('monthly-chart','figure'),Output('category-chart','figure'),
              Output('state-chart','figure'),Output('delivery-chart','figure'),Output('order-table','children'),
              Output('filter-summary','children'),Output('scope-note','children'),Output('table-note','children'),
              Input('date-filter','start_date'),Input('date-filter','end_date'),Input('state-filter','value'),Input('category-filter','value'))
def update(start,end,states,categories):
    result=DATA.select(start,end,states,categories)
    charts=figures(result)
    state_text='全部州' if not states else '、'.join(states)
    cat_text='全部品类' if not categories else ('、'.join(CATEGORY_NAMES.get(c,c) for c in categories[:2])+('等' if len(categories)>2 else ''))
    scope='当前为全部品类：金额与订单均使用整单销售口径。'
    if categories:
        scope='当前已筛选品类：金额仅统计所选商品，订单去重；配送与评价反映涉及订单的整单体验。'
    return (kpis(result),*charts,table(result),f'{start or START} — {end or END}  ·  {state_text}  ·  {cat_text}',
            scope,f"共 {result['metrics']['orders']:,} 笔涉及订单，按购买时间倒序展示前30笔；导出包含全部筛选结果。")


@app.callback(Output('date-filter','start_date'),Output('date-filter','end_date'),Output('state-filter','value'),Output('category-filter','value'),
              Input('reset-filters','n_clicks'),prevent_initial_call=True)
def reset(n_clicks):
    return START,END,[],[]


@app.callback(Output('download-orders','data'),Input('export-button','n_clicks'),State('date-filter','start_date'),
              State('date-filter','end_date'),State('state-filter','value'),State('category-filter','value'),prevent_initial_call=True)
def export(n_clicks,start,end,states,categories):
    if not n_clicks:
        raise PreventUpdate
    result=DATA.select(start,end,states,categories)
    return dcc.send_string('\ufeff'+DATA.export_view(result).to_csv(index=False),filename='Olist_当前筛选订单.csv',type='text/csv;charset=utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8050)
    args=parser.parse_args()
    app.run(host='127.0.0.1',port=args.port,debug=False)
