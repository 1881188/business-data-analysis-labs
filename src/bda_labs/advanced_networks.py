"""Graph semantics, safe traversal, PageRank and aggregate community analysis."""
from collections import deque
import importlib.metadata

import networkx as nx
import numpy as np
import pandas as pd

from bda_labs.common import context, plotting
from bda_labs.advanced_common import read_csv, specification, complete, bars


def search_path(adjacency, start, end, *, depth_first=False):
    if start not in adjacency or end not in adjacency:
        raise ValueError('Unknown graph vertex')
    if start == end:
        return [start]
    if depth_first:
        # Iterators reproduce recursive adjacency order without a recursion limit.
        stack = [(start, iter(adjacency[start]))]
        previous = {start: None}
        while stack:
            node, neighbours = stack[-1]
            nxt = next(neighbours, None)
            if nxt is None:
                stack.pop(); continue
            if nxt in previous:
                continue
            previous[nxt] = node
            if nxt == end:
                break
            stack.append((nxt, iter(adjacency[nxt])))
    else:
        previous = {start: None}; queue = deque([start])
        while queue and end not in previous:
            node = queue.popleft()
            for nxt in adjacency[node]:
                if nxt not in previous:
                    previous[nxt] = node; queue.append(nxt)
    if end not in previous:
        return None
    path = [end]
    while path[-1] != start:
        path.append(previous[path[-1]])
    return path[::-1]


def pagerank_matrix(adjacency, damping=.85, tolerance=1e-12, max_iter=10000):
    a = np.asarray(adjacency, dtype=float)
    if a.ndim != 2 or a.shape[0] != a.shape[1] or not len(a) or not np.isfinite(a).all() or (a < 0).any():
        raise ValueError('A finite nonnegative square adjacency matrix is required')
    if not 0 < damping <= 1:
        raise ValueError('Invalid damping')
    n = len(a); degree = a.sum(axis=1)
    transition = np.divide(a, degree[:, None], out=np.full_like(a, 1 / n), where=degree[:, None] != 0).T
    rank = np.full(n, 1 / n)
    for iteration in range(max_iter):
        updated = damping * transition @ rank + (1 - damping) / n
        if np.linalg.norm(updated - rank, ord=1) < tolerance:
            if not np.isclose(updated.sum(), 1):
                raise AssertionError('PageRank probability mass lost')
            return updated, iteration + 1
        rank = updated
    raise RuntimeError('PageRank did not converge')


def community_records(graph):
    # The teaching notebook's attribute is "Weight", whereas python-louvain
    # defaults to lowercase "weight": its community objective is unweighted.
    groups = nx.community.louvain_communities(graph, weight=None, seed=42)
    groups = sorted(groups, key=lambda x: (-len(x), min(map(str, x))))
    records = [{'section': 'community', 'item': i, 'value': len(nodes),
                'internal_edges': graph.subgraph(nodes).number_of_edges()}
               for i, nodes in enumerate(groups)]
    modularity = nx.community.modularity(graph, groups, weight=None) if graph.number_of_edges() else 0.
    return groups, records, float(modularity)


def main(lab, argv=None):
    ctx = context(lab, argv)
    records = []; details = {'networkx_version': importlib.metadata.version('networkx')}
    notes = ''
    if lab == 'F10':
        edges = [('0','0',1),('0','1',1),('0','5',1),('0','5',2),('1','2',3),('1','4',5),
                 ('2','1',7),('2','4',6),('3','5',5),('4','8',4),('6','7',1),('7','8',2),('8','6',3),('8','3',5)]
        graphs = [nx.Graph(), nx.DiGraph()]
        for name, graph in zip(['undirected', 'directed'], graphs):
            graph.add_nodes_from(map(str, range(9))); graph.add_weighted_edges_from(edges)
            records += [{'section': name, 'item': str(n), 'value': int(d)} for n, d in graph.degree()]
        details.update({'undirected_edges': graphs[0].number_of_edges(), 'directed_edges': graphs[1].number_of_edges(),
                        'out_degree_1': int(graphs[1].out_degree('1')), 'self_loops': nx.number_of_selfloops(graphs[0])})
        bars(ctx, ['undirected edges', 'directed edges', 'out degree(1)'],
             [details['undirected_edges'], details['directed_edges'], details['out_degree_1']], '图的方向、重复边与自环')
        notes = '简单图重复边覆盖属性；反向边在无向图中合并，自环对无向度贡献 2。原图的九个演示节点为教材虚构编号。'
    elif lab == 'F11':
        graph = nx.Graph([(0,1),(0,3),(1,2),(1,4),(2,5),(3,4),(4,5),(4,6),(5,7),(6,7)])
        adjacency = {n: list(graph[n]) for n in graph}
        bfs = search_path(adjacency, 0, 7)
        dfs = search_path(adjacency, 0, 7, depth_first=True)
        if len(bfs) - 1 != nx.shortest_path_length(graph, 0, 7):
            raise AssertionError('BFS did not find a shortest path')
        records = [{'section': name, 'item': ' → '.join(map(str, path)), 'value': len(path) - 1}
                   for name, path in [('BFS', bfs), ('DFS', dfs)]]
        bars(ctx, ['BFS', 'DFS'], [len(bfs) - 1, len(dfs) - 1], '遍历路径长度', 'edges')
        details['bfs_shortest_path_checked'] = True
        notes = '修复源脚本不可达目标和起终点相同的路径重建；DFS 保持邻接表访问顺序。BFS 求无权最短路，DFS 仅保证可达路径。'
    elif lab == 'F12':
        directed = nx.DiGraph()
        directed.add_weighted_edges_from([(a,b,1) for a,b in [('1','2'),('1','6'),('1','7'),('2','3'),
            ('3','4'),('4','5'),('4','7'),('5','6'),('6','7'),('7','5')]])
        for n in directed:
            records.append({'section': 'directed_degree', 'item': n, 'in_degree': directed.in_degree(n),
                            'out_degree': directed.out_degree(n), 'value': directed.degree(n)})
        star = nx.star_graph(5)
        measures = {'degree': nx.degree_centrality(star), 'closeness': nx.closeness_centrality(star),
                    'betweenness': nx.betweenness_centrality(star), 'eigenvector': nx.eigenvector_centrality(star, tol=1e-12)}
        records += [{'section': name, 'item': n, 'value': value} for name, values in measures.items() for n, value in values.items()]
        if not np.isclose(measures['degree'][0], 1) or not np.isclose(measures['betweenness'][0], 1):
            raise AssertionError('Star centrality identity failed')
        bars(ctx, list(measures), [m[0] for m in measures.values()], '星形网络：中心节点的中心性')
        details['star_identity_checked'] = True
    elif lab == 'F13':
        transition = np.array([[0,.5,0,.5],[1/3,0,0,1/3],[1/3,.5,0,0],[1/3,0,1,0]])
        a = transition.T
        rng = np.random.default_rng(42)
        random_graph = (rng.random((10,10)) < .8).astype(float); np.fill_diagonal(random_graph, 0)
        for name, adj, damping in [('source_matrix', a, 1.), ('random_graph', random_graph, 1.), ('damped', random_graph, .85)]:
            rank, iterations = pagerank_matrix(adj, damping)
            graph = nx.from_numpy_array(adj, create_using=nx.DiGraph)
            ref = nx.pagerank(graph, alpha=damping, tol=1e-13, max_iter=10000)
            if not np.allclose(rank, [ref[i] for i in range(len(adj))], atol=1e-10):
                raise AssertionError('Matrix and NetworkX PageRank differ')
            records += [{'section': name, 'item': i, 'value': r} for i, r in enumerate(rank)]
        bars(ctx, [str(i) for i in range(4)], [r['value'] for r in records[:4]], 'PageRank：迭代收敛后的节点概率')
        details.update({'seed': 42, 'independent_pagerank_checked': True})
        notes = '修复源 MV_computer 每次用初始向量而没有累计迭代的错误。补充悬挂节点概率重分配、阻尼和未收敛报错；同时保留教材 alpha=1 的无阻尼实验。'
    else:
        data = read_csv(ctx, specification(lab)['inputs'][0])
        if lab == 'F16':
            source, target = '源客户号', '目标客户号'
        else:
            source, target = 'Source', 'Target'
        if data[[source, target]].isna().any().any():
            raise ValueError('Missing graph endpoint')
        # Do not publish customer identifiers, individual edges or graph layouts.
        directed = nx.from_pandas_edgelist(data, source, target, create_using=nx.DiGraph())
        graph = nx.from_pandas_edgelist(data, source, target)
        details.update({'input_rows': len(data), 'nodes': graph.number_of_nodes(), 'edges': graph.number_of_edges(),
                        'directed_edges': directed.number_of_edges(), 'self_loops': nx.number_of_selfloops(graph),
                        'connected_components': nx.number_connected_components(graph)})
        if lab == 'F14':
            degrees = pd.Series(dict(directed.degree())).value_counts().sort_index()
            records = [{'section': 'degree_distribution', 'item': int(k), 'value': int(v)} for k, v in degrees.items()]
            bars(ctx, list(map(str, degrees.index)), degrees.values, '网络度数分布（聚合）', 'nodes')
        else:
            groups, records, modularity = community_records(graph)
            details.update({'communities': len(groups), 'modularity_unweighted': modularity, 'seed': 42})
            bars(ctx, [str(i) for i in range(len(groups))], [len(g) for g in groups], '社区规模（不含节点标识）', 'nodes')
        notes = ('原 Notebook 用 python-louvain，迁移为 NetworkX 内置 Louvain，固定随机种子。'
                 '保留原简单无向图和默认无权社区目标；Weight 大写字段原本不会被默认 weight 参数使用。'
                 '不同实现的启发式分区允许不同，不宣称逐节点复现。图布局和节点明细留在本地；公开图仅展示规模或度分布。')
    complete(ctx, lab, records, details, notes=notes)
