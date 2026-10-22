"""S01: all 12 teaching sections from the data integration/cleaning notebook."""
from __future__ import annotations
import numpy as np
import pandas as pd

from .common import context, finish, plotting, save_table, write_json


def cap(series: pd.Series, lower=.01, upper=.99) -> pd.Series:
    """Winsorize using supplied data; for a predictive pipeline fit bounds on training only."""
    if not 0 <= lower < upper <= 1: raise ValueError("Require 0 <= lower < upper <= 1")
    lo, hi = series.quantile([lower, upper])
    return series.clip(lower=lo, upper=hi)


def merge_tables(left: pd.DataFrame, right: pd.DataFrame, how="left"):
    # Pedagogical example has unique IDs on both sides; reject accidental multiplication.
    return left.merge(right, how=how, on="id", validate="one_to_one", indicator=True)


def main(argv=None):
    ctx = context("S01", argv)
    artifacts, sections = [], []

    def keep(section, name, obj):
        if section not in sections: sections.append(section)
        if isinstance(obj, pd.Series): obj = obj.to_frame()
        if isinstance(obj, pd.DataFrame):
            frame = obj.copy()
            if isinstance(frame.columns, pd.MultiIndex): frame.columns = ["__".join(map(str, x)) for x in frame.columns]
            frame = frame.reset_index()
            save_table(frame, ctx.output / f"{name}.csv")
        else:
            write_json(ctx.output / f"{name}.json", obj)
        artifacts.append({"section":section, "name":name})

    # 1.1.1 Read, select, chunk, sentinel NA, encoding and isolated write-back.
    sample_path = ctx.source("cleaning_sample")
    initial = pd.read_csv(sample_path)
    keep("1.1.1读取数据", "01_read", initial)
    keep(sections[-1], "02_read_selection", pd.read_csv(sample_path, usecols=["id", "name"], nrows=2))
    chunks = list(pd.read_csv(ctx.source("cleaning_big"), chunksize=900))
    combined = pd.concat(chunks, ignore_index=True)
    whole = pd.read_csv(ctx.source("cleaning_big"))
    pd.testing.assert_frame_equal(combined, whole)
    keep(sections[-1], "03_chunk_shapes", {"chunks":[list(c.shape) for c in chunks], "combined_shape":list(combined.shape), "equals_full_read":True})
    sentinel = pd.read_csv(sample_path, na_values="99999", encoding="utf-8")
    keep(sections[-1], "04_sentinel_missing", sentinel)
    save_table(sentinel, ctx.output / "write.csv")

    # 1.2.1 Column/row selection and derivation, with the original random sequence.
    rng = np.random.RandomState(0)
    frame = pd.DataFrame(rng.randn(4,5), columns=list("abcde"))
    keep("1.2.1行列操作", "05_select_column", frame[["a"]])
    pd.testing.assert_series_equal(frame["a"], frame.iloc[:,0])
    pd.testing.assert_frame_equal(frame.loc[:1,:"b"], frame.iloc[:2,:2])
    frame["new_col"] = frame.a-frame.b
    keep(sections[-1], "06_derived", frame.assign(new_col2=frame.a-frame.b,new_col3=frame.a+frame.b))
    keep(sections[-1], "07_drop_columns", frame.drop(columns=["a","b"]))

    marks = pd.DataFrame({"group":[1,1,1,2,1,2], "name":["Bob","Lindy","Mark","Miki","Sully","Rose"],"score":[98,78,87,77,65,67]})
    filters = {"over_70":marks.score>70, "over_70_group_1":(marks.score>70)&(marks.group==1),
        "not_group_1":marks.group!=1, "group_1_or_2":marks.group.isin([1,2]),
        "between_70_80":marks.score.between(70,80,inclusive="both"),
        "names":marks.name.isin(["Bob","Lindy"]), "regex":marks.name.str.contains("[M]+")}
    for name, mask in filters.items(): keep("1.2.2条件查询",f"08_filter_{name}",marks.loc[mask])
    keep("1.2.2条件查询", "09_query", marks.query("score > 90"))

    left = pd.DataFrame({"col1":["a","b","c"],"id":[1,2,3]})
    right = pd.DataFrame({"col2":["d","e"],"id":[4,3]})
    for how in ["inner","left","right","outer"]: keep("1.2.3横向连接",f"10_merge_{how}",merge_tables(left,right,how))
    left_index = pd.DataFrame({"id1":[1,2,3],"col1":["a","b","c"]}, index=[1,2,3])
    right_index = pd.DataFrame({"id2":[1,2,3],"col2":["aa","bb","cc"]}, index=[1,3,2])
    joined = left_index.join(right_index,validate="one_to_one")
    pd.testing.assert_frame_equal(joined,pd.concat([left_index,right_index],axis=1))
    keep("1.2.3横向连接","11_index_alignment",joined)

    a = pd.DataFrame({"id":[1,1,1,2,3,4,6],"col":["a","a","b","c","v","e","q"]})
    b = pd.DataFrame({"id":[1,2,3,3,5],"col":["x","y","z","v","w"]})
    stacked = pd.concat([a,b],ignore_index=True)
    keep("1.2.4纵向合并","12_concat",stacked)
    keep(sections[-1],"13_concat_deduplicate",stacked.drop_duplicates())
    keep(sections[-1],"14_mismatched_columns",pd.concat([a,a.rename(columns={"col":"new_col"})],ignore_index=True).drop_duplicates())

    sorting=marks.assign(score=[98,78,87,77,77,np.nan])
    keep("1.2.5排序","15_sort_score",sorting.sort_values("score",ascending=False,na_position="last"))
    keep(sections[-1],"16_sort_group_score",sorting.sort_values(["group","score"]))
    school=pd.DataFrame({"name":marks.name,"class":[1,1,1,2,1,2],"grade":[1,1,1,2,2,2],"chinese":[88,78,86,56,77,54],"math":[98,78,87,77,77,np.nan]})
    keep("1.2.6分组汇总","17_grade_max",school.groupby("grade")[["math"]].max())
    keep(sections[-1],"18_grade_class_mean",school.groupby(["grade","class"])[["math"]].mean())
    keep(sections[-1],"19_grade_mean",school.groupby("grade")[["math","chinese"]].mean())
    keep(sections[-1],"20_class_aggregate",school.groupby("class")["math"].agg(["mean","min","max"]))
    nested=school.groupby(["grade","class"])[["math","chinese"]].agg(["min","max"])
    keep(sections[-1],"21_multiindex",nested)
    keep(sections[-1],"22_multiindex_selection",{"grade_2_class_2_math_min":float(nested.loc[(2,2),("math","min")])})

    money=pd.DataFrame({"Monetary":[3608,420,1894,3503,4567],"cust_id":[10001,10001,10002,10002,10003],"type":["Normal","Special_offer","Normal","Special_offer","Special_offer"]})
    keep("1.2.7拆分列","23_pivot_default_mean",money.pivot_table(index="cust_id",columns="type",values="Monetary"))
    pivot=money.pivot_table(index="cust_id",columns="type",values="Monetary",aggfunc="sum",fill_value=0)
    if pivot.to_numpy().sum()!=money.Monetary.sum(): raise AssertionError("Pivot amount conservation failed")
    keep(sections[-1],"24_pivot_sum",pivot)

    assigned=marks.assign(score=[99,78,999,77,77,np.nan])
    keep("1.2.8赋值与条件赋值","25_sentinel_replace",assigned.replace({"score":{999:np.nan},"name":{"Bob":np.nan}}))
    keep(sections[-1],"26_condition_assign",assigned.assign(class_n=assigned.group.map({1:"class1",2:"class2"})))
    duplicated=pd.DataFrame({"group":[1,1,1,2,1,2],"id":[1,1,1,3,4,5],"name":["Bob","Bob","Mark","Miki","Sully","Rose"],"score":[99,99,87,77,77,np.nan]})
    keep("1.3.1重复值处理","27_duplicate_rows",duplicated.loc[duplicated.duplicated()])
    keep(sections[-1],"28_full_row_dedup",duplicated.drop_duplicates())
    keep(sections[-1],"29_key_dedup",duplicated.drop_duplicates("id"))
    missing=pd.DataFrame({"group":[1,1,np.nan,2,1,np.nan],"id":[1,1,1,3,4,np.nan],"name":["Bob","Bob","Mark","Miki","Sully",np.nan],"score":[99,np.nan,87,77,77,np.nan]})
    keep("1.3.2缺失值处理","30_missing_rate",missing.isna().mean())
    keep(sections[-1],"31_fill_mean",missing.score.fillna(missing.score.mean()))
    keep(sections[-1],"32_fill_median",missing.score.fillna(missing.score.median()))
    keep(sections[-1],"33_missing_indicator",missing.score.isna().astype(int))

    # Previous notebook random draws precede this section; preserve that same generator state.
    normal=pd.Series(rng.randn(1000),name="normal")
    bounded=cap(normal)
    keep("1.3.3噪声值处理","34_capped",pd.DataFrame({"original":normal,"capped":bounded}))
    bins=pd.Series(np.random.RandomState(0).randn(10),name="normal")
    keep(sections[-1],"35_equal_width_bins",pd.DataFrame({"normal":bins,"five_bins":pd.cut(bins,5,labels=[1,2,3,4,5]),"two_bins":pd.cut(bins,2,labels=["bad","good"])}))
    keep(sections[-1],"36_quantile_bins",pd.cut(bins,bins.quantile([0,.5,1]),labels=["bad","good"],include_lowest=True))
    write_json(ctx.output/"artifact_index.json",artifacts)
    plt=plotting()
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout="constrained")
    axes[0].hist(normal,bins=50,color="#6b8ba4",alpha=.9)
    axes[0].set(title="原始教学样本",xlabel="标准正态随机值",ylabel="频数")
    axes[1].hist(bounded,bins=50,color="#087f8c",alpha=.9)
    axes[1].set(title="1% / 99% 分位数盖帽后",xlabel="处理后值",ylabel="频数")
    fig.suptitle("异常值盖帽：尾部被压到边界，不能视为自动纠错",fontsize=16,color="#17364d")
    fig.savefig(ctx.output/"cleaning_cap.png",dpi=150)
    plt.close(fig)
    summary={"lab_id":"S01","status":"run_verified","sections":sections,"section_count":len(sections),
        "sample_rows":len(initial),"chunk_rows":len(combined),"chunk_sizes":[len(c) for c in chunks],
        "chunk_full_read_equal":True,"artifact_count":len(artifacts),"join_rows":{how:len(merge_tables(left,right,how)) for how in ["inner","left","right","outer"]},
        "full_row_dedup_rows":len(duplicated.drop_duplicates()),"key_dedup_rows":len(duplicated.drop_duplicates("id")),
        "cap_changed_count":int((normal!=bounded).sum()),"original_notebook_code_cells":94}
    report=f"""# S01 数据整合与清洗

## 实现范围

对应二级教材第4章Notebook的12个教学小节、94个代码单元。按小节重构为独立脚本，保留读取、行列操作、查询、连接、合并、排序、分组、透视、赋值、重复值、缺失和噪声处理。每个中间演示保存表格，产物索引见本地artifact_index.json。

## 实测结果

- sample.csv为{len(initial)}行、{len(initial.columns)}列。原始文件只读，写回演示改存实验输出目录。
- big.csv为{len(combined):,}行，按900行分成{len(chunks)}块，拼接结果与整表读取逐项一致。
- 示例inner/left/right/outer连接分别为1/3/2/4行；按索引对齐与按业务键连接分别演示。
- 重复值示例全行去重后5行，按id保留首行后4行；后者会丢掉同id不同属性，不能无条件应用到业务表。
- 金额透视表汇总前后总金额一致；默认均值与显式求和分别保存。
- 盖帽修改{int((normal!=bounded).sum())}个随机教学样本值，边界为样本的1%和99%分位数。

![异常值处理演示](cleaning_cap.png)

## 代码含义与迁移调整

Notebook的裸表达式原本由交互环境展示，迁移后显式保存CSV/JSON。`loc`标签范围与`iloc`位置范围有不同端点规则，脚本对等价示例进行比对。横向连接增加键唯一性验证，避免意外多对多膨胀。缺失、异常、重复处理都保留原始对象，演示不会覆盖教材数据。

## 业务限制

随机数和表中人物是教材教学演示，不是实际客户分析。均值填补和分位数盖帽是待选规则，不能自动证明值错误。用于预测时，应只在训练数据拟合填补统计量与边界，再应用到验证/测试数据。本实验验证了教学流程和关键守恒关系，未声称逐单元比对Notebook缓存输出。
"""
    finish(ctx,summary,report)


if __name__=="__main__": main()
