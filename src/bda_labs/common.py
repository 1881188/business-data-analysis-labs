"""Portable paths, source integrity and explicit experiment outputs."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Context:
    data_root: Path
    output: Path
    sources: dict = field(default_factory=dict)

    def source(self, key: str) -> Path:
        registry = json.loads((ROOT / "config" / "datasets.json").read_text(encoding="utf-8"))
        record = registry[key]
        path = self.data_root / record["path"]
        if not path.is_file():
            raise FileNotFoundError(f"Missing source {key}: {path}. See data/README.md and --data-root.")
        actual = sha256(path)
        if actual != record["sha256"]:
            raise ValueError(f"Source checksum differs for {key}. Review the dataset version before changing its manifest.")
        self.sources[key]=record.copy()
        return path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def context(lab_id: str, argv=None) -> Context:
    parser = argparse.ArgumentParser(description=f"Run {lab_id}; original course materials remain read-only.")
    parser.add_argument("--data-root", type=Path, help="Directory containing the four textbook folders")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    args = parser.parse_args(argv)
    data_root = args.data_root
    if data_root is None and os.environ.get("BDA_DATA_ROOT"):
        data_root = Path(os.environ["BDA_DATA_ROOT"])
    config = ROOT / "config" / "datasets.local.json"
    if data_root is None and config.exists():
        data_root = Path(json.loads(config.read_text(encoding="utf-8"))["data_root"])
    if data_root is None:
        # Convenient checkout layout for this course; --data-root works anywhere.
        data_root = ROOT.parent / "a商业数据分析平时作业"
    if not data_root.is_dir():
        raise FileNotFoundError("Course materials directory not found. Supply --data-root or BDA_DATA_ROOT; see data/README.md.")
    output = args.output_root.resolve() / lab_id
    output.mkdir(parents=True, exist_ok=True)
    return Context(data_root.resolve(), output)


def write_json(path: Path, value) -> None:
    def encode(obj):
        if isinstance(obj, np.generic): return obj.item()
        if isinstance(obj, (Path, pd.Timestamp)): return str(obj)
        raise TypeError(type(obj).__name__)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=encode, allow_nan=False) + "\n", encoding="utf-8")


def save_table(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def runtime_info() -> dict:
    names = ["numpy", "pandas", "scipy", "statsmodels", "scikit-learn", "matplotlib", "openpyxl"]
    return {"python": platform.python_version(), "platform": platform.system(),
            "packages": {p: importlib.metadata.version(p) for p in names}}


def plotting():
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "outputs" / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt, font_manager
    font = os.environ.get("BDA_CHINESE_FONT")
    if not font:
        candidate = Path("C:/Windows/Fonts/msyh.ttc")
        if candidate.is_file(): font = str(candidate)
    if font:
        font_manager.fontManager.addfont(font)
        family = font_manager.FontProperties(fname=font).get_name()
        plt.rcParams["font.family"] = family
    else:
        plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                         "axes.unicode_minus": False, "font.size": 11, "figure.facecolor": "white",
                         "axes.titleweight": "bold", "savefig.facecolor": "white"})
    return plt


def finish(ctx: Context, summary: dict, report: str) -> None:
    summary["runtime"] = runtime_info()
    modules={"B05":"rfm","S01":"cleaning","S11":"churn"}
    entries={"B05":"labs/cda1_business/b05_rfm/main.py","S01":"labs/cda2_statistics/s01_cleaning/main.py","S11":"labs/cda2_statistics/s11_churn/main.py"}
    paths=["src/bda_labs/common.py",f"src/bda_labs/{modules[ctx.output.name]}.py",entries[ctx.output.name]]
    summary["implementation_sha256"]={p:sha256(ROOT/p) for p in paths}
    summary["source_files"]=ctx.sources
    summary["verified_at_utc"]=datetime.now(timezone.utc).isoformat()
    write_json(ctx.output / "summary.json", summary)
    (ctx.output / "report.md").write_text(report.rstrip() + "\n", encoding="utf-8")
    print(f"{ctx.output.name}: completed; results in {ctx.output}")
