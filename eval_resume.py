"""
eval_resume.py — W3 D3：嵌套结构版的评测

读 batch_extract.py 的产出，和人工标注的 gold 逐字段比对，算出：
    · 标量字段准确率（name/phone/email/city/years_experience）
    · 列表字段：skills（集合 P/R/F1）、education / projects（条目 P/R/F1 + 子字段准确率）
    · 整体完全正确率（一条里所有字段都对才算对）
    · 错误清单，并区分"模型错"和"口径错"两类

用法：
    python eval_resume.py                                   # 默认 v2
    python eval_resume.py --out eval/out_v2.jsonl --gold eval/samples_v2.jsonl
"""

import os
import re
import sys
import json
import argparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCALARS = ["name", "phone", "email", "city", "years_experience"]
FIELDS = ["name", "phone", "email", "city", "education",
          "skills", "years_experience", "projects"]

# 条目配对用哪些字段做"主键"。education 不能用 school 单字段——
# r09、r36 都是同一所学校读了两段，只用 school 会把两条挤成一条。
OBJ_SPECS = {
    "education": {"keys": ("school", "degree"),
                  "subkeys": ("school", "major", "degree", "graduation_year")},
    "projects": {"keys": ("name",),
                 "subkeys": ("name", "tech")},   # summary 是自由文本，不参与打分
}

_PUNCT = re.compile(r"[\s\-_·,，。.、（）：:｜|/\\()\[\]【】]")


def norm(s):
    return _PUNCT.sub("", str(s)).lower()


def is_null(v):
    return v is None or v == "" or v == []


def match_scalar(gold, pred):
    if is_null(gold) and is_null(pred):
        return True, ""
    if is_null(gold) and not is_null(pred):
        return False, f"应留空却填了「{pred}」"
    if is_null(pred) and not is_null(gold):
        return False, f"漏抽（应为「{gold}」）"
    g, p = norm(gold), norm(pred)
    if g == p or g in p or p in g:
        return True, ""
    return False, f"应为「{gold}」，实际「{pred}」"


def match_years(gold, pred):
    if gold is None and pred is None:
        return True, ""
    if gold is None:
        return False, f"应留空却填了 {pred}"
    if pred is None:
        return False, f"漏抽（应为 {gold}）"
    try:
        return abs(float(pred) - float(gold)) < 0.01, f"应为 {gold}，实际 {pred}"
    except (TypeError, ValueError):
        return False, f"应为 {gold}，实际 {pred}（非数字）"


def match_set(gold, pred):
    """集合比对，返回 (是否完全一致, P, R, F1)"""
    g = {norm(x) for x in (gold or []) if str(x).strip()}
    p = {norm(x) for x in (pred or []) if str(x).strip()}
    if not g and not p:
        return True, 1.0, 1.0, 1.0
    if not g or not p:
        return False, 0.0, 0.0, 0.0
    tp = len(g & p)
    prec, rec = tp / len(p), tp / len(g)
    f1 = 0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    return g == p, prec, rec, f1


def obj_key(obj, keys):
    return "|".join(norm(obj.get(k) or "") for k in keys)


def match_obj_list(gold, pred, spec):
    """
    列表型字段的比对。返回 (整组是否全对, P, R, F1, 子字段命中数, 子字段总数, 错误列表)

    逻辑：先按主键把两边的条目配对（像 SQL 的 join），再逐个比子字段。
    漏了条目 = 召回不足，多了条目 = 精确率不足，配上了但字段错 = 子字段错。
    """
    errors = []
    g = [i for i in (gold or []) if isinstance(i, dict)]
    p = [i for i in (pred or []) if isinstance(i, dict)]

    gmap = {obj_key(i, spec["keys"]): i for i in g}
    pmap = {obj_key(i, spec["keys"]): i for i in p}

    matched = set(gmap) & set(pmap)
    missing = set(gmap) - set(pmap)
    extra = set(pmap) - set(gmap)

    tp = len(matched)
    prec = tp / len(pmap) if pmap else (1.0 if not gmap else 0.0)
    rec = tp / len(gmap) if gmap else (1.0 if not pmap else 0.0)
    f1 = 0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)

    sub_ok = sub_total = 0
    for k in matched:
        gi, pi = gmap[k], pmap[k]
        for sk in spec["subkeys"]:
            sub_total += 1
            gv, pv = gi.get(sk), pi.get(sk)
            if isinstance(gv, list) or isinstance(pv, list):
                ok, _, _, _ = match_set(gv, pv)
            else:
                ok, why = match_scalar(gv, pv)
                if not ok:
                    errors.append(f"条目「{k}」的 {sk}：{why}")
            sub_ok += ok
    for k in missing:
        errors.append(f"漏条目「{k}」")
    for k in extra:
        errors.append(f"多条目「{k}」")

    exact = not missing and not extra and sub_ok == sub_total
    return exact, prec, rec, f1, sub_ok, sub_total, errors


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/out_v2.jsonl")
    ap.add_argument("--gold", default="eval/samples_v2.jsonl")
    ap.add_argument("--report", default="eval/report_v2.md")
    args = ap.parse_args()

    if not os.path.exists(args.out):
        print(f"找不到 {args.out}，先跑 batch_extract.py")
        return

    golds = {r["id"]: r["gold"] for r in load_jsonl(args.gold)}
    results = [r for r in load_jsonl(args.out) if r.get("data")]
    print(f"参与评测：{len(results)} 条（gold 共 {len(golds)} 条）"
          f"｜schema {results[0].get('schema_version', '-') if results else '-'}\n")

    stat = {f: {"ok": 0, "total": 0} for f in FIELDS}
    prf = {f: [] for f in ("skills", "education", "projects")}
    sub = {f: {"ok": 0, "total": 0} for f in ("education", "projects")}
    errors, perfect, attr_blocked = [], 0, 0

    for r in results:
        rid, data = r["id"], r["data"]
        gold = golds.get(rid)
        if not gold:
            continue
        if any("可能不属于" in i for i in r.get("issues") or []):
            attr_blocked += 1
        row_ok = True

        for f in FIELDS:
            gv, pv = gold.get(f), data.get(f)

            if f == "skills":
                exact, prec, rec, f1 = match_set(gv, pv)
                prf[f].append((prec, rec, f1))
                ok, why = exact, ("" if exact else f"应为 {gv}，实际 {pv}")
            elif f in OBJ_SPECS:
                ok, prec, rec, f1, so, st, errs = match_obj_list(gv, pv, OBJ_SPECS[f])
                prf[f].append((prec, rec, f1))
                sub[f]["ok"] += so
                sub[f]["total"] += st
                why = "；".join(errs)
                errors.extend((rid, f, e) for e in errs)
            elif f == "years_experience":
                ok, why = match_years(gv, pv)
            else:
                ok, why = match_scalar(gv, pv)

            stat[f]["total"] += 1
            if ok:
                stat[f]["ok"] += 1
            else:
                row_ok = False
                if f not in OBJ_SPECS:
                    errors.append((rid, f, why))

        if row_ok:
            perfect += 1

    # ---------------- 输出 ----------------
    lines = ["# 抽取器评测报告（schema v2.0 · 嵌套结构）\n",
             f"- 样本数：{len(results)}",
             f"- schema 版本：{results[0].get('schema_version', '未知') if results else '-'}",
             f"- 完全正确（8 字段全对）：{perfect}/{len(results)} "
             f"= **{perfect / max(len(results), 1) * 100:.1f}%**",
             f"- 被归属检测（上下文含联系人/家属等）拦下的记录：{attr_blocked} 条\n",
             "| 字段 | 类型 | 准确率 | 错误数 |", "|---|---|---|---|"]

    TYPE = {"education": "对象数组", "projects": "对象数组", "skills": "字符串数组"}
    print("字段级准确率")
    print("-" * 54)
    print(f"{'字段':<18}{'类型':<10}{'准确率':>10}{'错误':>6}")
    order = sorted(FIELDS, key=lambda f: stat[f]["ok"] / max(stat[f]["total"], 1))
    for f in order:
        s = stat[f]
        acc = s["ok"] / max(s["total"], 1)
        t = TYPE.get(f, "标量")
        print(f"{f:<18}{t:<10}{acc * 100:>9.1f}%{s['total'] - s['ok']:>6}")
        lines.append(f"| {f} | {t} | {acc * 100:.1f}% | {s['total'] - s['ok']} |")

    for f in ("skills", "education", "projects"):
        if prf[f]:
            p = sum(x[0] for x in prf[f]) / len(prf[f])
            rc = sum(x[1] for x in prf[f]) / len(prf[f])
            f1 = sum(x[2] for x in prf[f]) / len(prf[f])
            label = {"skills": "技能集合", "education": "学历条目", "projects": "项目条目"}[f]
            line = f"{label}：P={p * 100:.1f}%  R={rc * 100:.1f}%  F1={f1 * 100:.1f}%"
            if sub.get(f, {}).get("total"):
                line += f" ｜子字段 {sub[f]['ok']}/{sub[f]['total']} = {sub[f]['ok'] / sub[f]['total'] * 100:.1f}%"
            print(line)
            lines.append(f"\n**{label}**：精确率 {p * 100:.1f}% ｜ 召回率 {rc * 100:.1f}% ｜ "
                         f"F1 {f1 * 100:.1f}%")

    macro = sum(stat[f]["ok"] / max(stat[f]["total"], 1) for f in FIELDS) / len(FIELDS)
    print(f"\n字段平均准确率（macro）：{macro * 100:.1f}%")
    print(f"完全正确率：{perfect}/{len(results)} = {perfect / max(len(results), 1) * 100:.1f}%")
    print(f"归属检测命中：{attr_blocked} 条")

    print("\n" + "-" * 54)
    print(f"错误明细（共 {len(errors)} 处）")
    for rid, f, why in errors[:30]:
        print(f"  {rid}  {f:<12} {why}")
    if len(errors) > 30:
        print(f"  …… 还有 {len(errors) - 30} 处")

    lines.append(f"\n- 字段平均准确率（macro）：**{macro * 100:.1f}%**\n")
    lines.append(f"## 错误明细（{len(errors)} 处）\n")
    for rid, f, why in errors:
        lines.append(f"- `{rid}` **{f}**：{why}")

    with open(args.report, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
    print(f"\n报告已写入 {args.report}")


if __name__ == "__main__":
    main()
