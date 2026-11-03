"""
batch_extract.py — W3 D2：批量抽取（并发 + 断点续跑 + 失败隔离）

把 extractor.py 的单条抽取包装成能跑 1000 份的生产版本。

用法：
    python batch_extract.py                                  # 默认抽 eval/samples.jsonl
    python batch_extract.py --in eval/samples.jsonl --out eval/out.jsonl --workers 6
    python batch_extract.py --force                          # 忽略已完成记录，全部重跑

产出：
    out.jsonl     每行一条结果：{"id":..., "schema_version":..., "data":..., "issues":[...]}
    failed.jsonl  失败的单独隔离，不阻塞主流程
"""

import os
import sys
import json
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from extractor import extract, make_client
from preflight import preflight
from cost_tracker import CostMeter, fmt_yuan

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCHEMA_VERSION = "v2.1"          # schema 改了就要升版本，否则新旧数据混在一起没法用
# v2.0：education / projects 改为数组（嵌套结构）。和 v1.1 的产出不可混读。
# v2.1：skills 口径改为"具体技术名词"（剔除学科/方法/角色词）；新增输入预检与姓名角色校验。
#       结构没变，但 gold 语义变了，所以同样要升版本 —— 版本号管的是"口径"，不只是"结构"。

_write_lock = threading.Lock()


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  [警告] {path} 有一行不是合法 JSON，已跳过")
    return rows


def write_jsonl(path, row):
    """追加一行。用追加而不是整体重写，跑到一半崩了前面的不会白干。"""
    with _write_lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_done_ids(out_path, force=False):
    if force or not os.path.exists(out_path):
        return set()
    return {r["id"] for r in read_jsonl(out_path) if "id" in r}


def run_one(item, client, meter, no_hints=False):
    """一次抽取。注意：异常不能往外抛，否则会吃掉整批。"""
    t0 = time.time()
    pre = preflight(item["text"])
    if no_hints:
        # A/B 对照用：照常跑预检、照常记 flags，只是不把 hints 写进 prompt。
        # 这样两组之间只差"那几句提示"，其他变量（schema、校验器、gold）完全相同。
        pre = {**pre, "hints": []}
    try:
        data, issues = extract(client, item["text"], meter=meter, pre=pre)
    except Exception as exc:
        return {"id": item["id"], "error": f"{type(exc).__name__}: {exc}"}
    return {
        "id": item["id"],
        "schema_version": SCHEMA_VERSION,
        "data": data,
        "issues": issues,
        "pre_flags": pre["flags"],       # 存下来，评测时可以按"有没有触发预检"分组看
        "elapsed": round(time.time() - t0, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="eval/samples_v3.jsonl")
    ap.add_argument("--out", dest="out", default="eval/out_v3.jsonl")
    ap.add_argument("--failed", dest="failed", default="eval/failed_v3.jsonl")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-hints", action="store_true", help="A/B 对照：不注入预检提示")
    args = ap.parse_args()

    if not os.getenv("API_KEY"):
        print("未读取到 API_KEY")
        return

    samples = read_jsonl(args.inp)
    if not samples:
        print(f"{args.inp} 里没有数据")
        return

    done = load_done_ids(args.out, args.force)
    todo = [s for s in samples if s["id"] not in done]
    print(f"总计 {len(samples)} 条 ｜ 已完成 {len(done)} ｜ 本次待处理 {len(todo)}")
    if not todo:
        print("全部已完成，无需重跑（要重跑加 --force）")
        return

    client = make_client()
    meter = CostMeter()
    ok = fail = 0
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, it, client, meter, args.no_hints): it for it in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            if "error" in row:
                write_jsonl(args.failed, row)
                print(f"  [{i}/{len(todo)}] {row['id']} ✗ {row['error'][:70]}")
                fail += 1
            else:
                write_jsonl(args.out, row)
                bad = f" ｜校验问题 {len(row['issues'])} 条" if row["issues"] else ""
                print(f"  [{i}/{len(todo)}] {row['id']} ✓ {row['elapsed']}s{bad}")
                ok += 1

    elapsed = time.time() - t_start
    print("\n" + "-" * 60)
    print(f"成功 {ok} ｜失败 {fail} ｜总耗时 {elapsed:.1f}s ｜"
          f"平均 {elapsed / max(len(todo), 1):.2f}s/条")
    meter.report()
    if fail:
        print(f"  失败记录见 {args.failed}，修好后直接重跑本命令即可（已完成的会跳过）")


if __name__ == "__main__":
    main()
