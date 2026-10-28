"""XES log round trip and frequency/performance directly-follows graphs."""
from collections import defaultdict, Counter
import xml.etree.ElementTree as ET

import pandas as pd

from bda_labs.common import context, plotting
from bda_labs.advanced_common import specification, complete


def parse_xes(path):
    root=ET.parse(path).getroot()
    traces=[]
    for trace in root:
        if trace.tag.split('}')[-1]!='trace': continue
        events=[]
        for event in trace:
            if event.tag.split('}')[-1]!='event': continue
            attributes={p.attrib['key']:p.attrib.get('value') for p in event}
            events.append(attributes)
        traces.append(events)
    return root,traces


def main(lab='M25',argv=None):
    ctx=context(lab,argv)
    root,traces=parse_xes(ctx.source(specification(lab)['inputs'][0]))
    export=ctx.output/'log_private.xes'
    ET.ElementTree(root).write(export,encoding='utf-8',xml_declaration=True)
    _,restored=parse_xes(export)
    if restored!=traces:raise AssertionError('XES round trip changed events')
    frequencies=Counter();durations=defaultdict(list)
    for trace in traces:
        for a,b in zip(trace,trace[1:]):
            pair=(a['concept:name'],b['concept:name'])
            dt=(pd.Timestamp(b['time:timestamp'])-pd.Timestamp(a['time:timestamp'])).total_seconds()
            if dt<0:raise ValueError('Trace events are not chronological')
            frequencies[pair]+=1;durations[pair].append(dt)
    expected=sum(max(0,len(t)-1) for t in traces)
    if sum(frequencies.values())!=expected:raise AssertionError('DFG pair count differs')
    rows=[{'section':'directly_follows','item':a+' → '+b,'count':n,
           'mean_seconds':sum(durations[(a,b)])/n} for (a,b),n in sorted(frequencies.items())]
    plt=plotting();fig,axes=plt.subplots(1,2,figsize=(12,7))
    labels=[r['item'] for r in rows];positions=range(len(rows))
    axes[0].barh(positions,[r['count'] for r in rows]);axes[0].set_yticks(positions,labels,fontsize=8)
    axes[1].barh(positions,[r['mean_seconds']/3600 for r in rows]);axes[1].set_yticks(positions,labels,fontsize=8)
    axes[0].set(title='直接跟随频次',xlabel='transitions');axes[1].set(title='直接跟随平均耗时',xlabel='hours')
    fig.tight_layout();fig.savefig(ctx.output/'figure.png',dpi=150);plt.close(fig)
    complete(ctx,lab,rows,{'traces':len(traces),'events':sum(map(len,traces)),
                         'transitions':expected,'distinct_transitions':len(frequencies),'roundtrip_checked':True},
             notes='原 Notebook 只使用 pm4py 的 XES 读写、直接跟随频次和平均耗时；迁移用标准 XML 和显式统计重建这些功能，不声称实现 Petri 网或一致性检验。trace 内事件按源顺序保留，不把不同案例拼接。原日志、资源与单案事件留在本地，只发布活动对的聚合统计。')
