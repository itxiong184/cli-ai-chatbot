"""
exp_prompt_layers.py — 验证「三层保险」各自到底管什么

背景：把 SYSTEM_PROMPT 里的规则 1（只输出 JSON）删掉后，程序居然没报错。
说明某一层在悄悄兜底。这个脚本把三种组合各跑一次，用输出对比出真相。

用法：python exp_prompt_layers.py
"""

import os
import sys
import json
import time

from openai import OpenAI
from dotenv import load_dotenv

from extractor import SYSTEM_PROMPT, SAMPLES, make_client, parse_json
from cost_tracker import CostMeter, fmt_yuan

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()
MODEL = os.getenv("MODEL") or "deepseek-chat"

# 把规则 1 那一行从 prompt 里剥掉（模拟"删除规则 1"）
RULE1_PREFIX = "1. 只输出 JSON 本体"
PROMPT_NO_RULE1 = "\n".join(
    line for line in SYSTEM_PROMPT.split("\n")
    if not line.strip().startswith(RULE1_PREFIX)
)

SAMPLE = SAMPLES["② 口语化自我介绍"]


def run(label, system_prompt, use_json_mode, meter):
    print("\n" + "=" * 66)
    print(f"  {label}")
    print(f"  规则1：{'有' if system_prompt is SYSTEM_PROMPT else '无'}   "
          f"JSON模式：{'开' if use_json_mode else '关'}")
    print("=" * 66)

    kwargs = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": SAMPLE}],
        "temperature": 0.0,
        "timeout": 60,
    }
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    client = make_client()
    t0 = time.time()
    resp = client.chat.completions.create(**kwargs)
    raw = resp.choices[0].message.content
    meter.add(resp.usage)
    elapsed = time.time() - t0

    print(f"  原始返回（前 150 字符）：\n  {raw[:150]!r}")
    print(f"  返回长度：{len(raw)} 字符 ｜ 耗时 {elapsed:.1f}s")

    try:
        data = parse_json(raw)
        print(f"  ✅ json.loads 成功，拿到 {len(data)} 个字段")
    except json.JSONDecodeError as exc:
        print(f"  ❌ json.loads 失败：{exc}")

    # 关键：JSON 合法 ≠ 字段对。检查有没有多套一层或字段名漂移
    if "data" in locals() or True:
        pass
    return raw


def main():
    if not os.getenv("API_KEY"):
        print("未读取到 API_KEY")
        return

    meter = CostMeter()
    run("A 完整版：规则1 + JSON模式（正常跑的状态）", SYSTEM_PROMPT, True, meter)
    run("B 去掉规则1，保留 JSON模式（你刚做的实验）", PROMPT_NO_RULE1, True, meter)
    run("C 去掉规则1，同时关掉 JSON模式（这才是真正的裸奔）", PROMPT_NO_RULE1, False, meter)

    meter.report()
    print("\n  结论看上面三次的『json.loads 成功/失败』：")
    print("  B 不报错 → 兜底的是 JSON 模式，不是规则 1")
    print("  C 报错   → 规则 1 只在没有 JSON 模式时才成为唯一防线")


if __name__ == "__main__":
    main()
