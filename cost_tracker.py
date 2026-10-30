"""
cost_tracker.py — W2 D5：成本核算（完整可运行版）

用法：
    python cost_tracker.py            # 依次跑 3 个实验（会花几分钱）
    python cost_tracker.py cache      # 实验① 缓存命中：同样的长 prompt 发两次
    python cost_tracker.py length     # 实验② 输出长度：max_tokens 小 vs 大
    python cost_tracker.py multiturn  # 实验③ 多轮对话：成本为什么会变陡
    python cost_tracker.py selftest   # 只算假数据，不发网络请求，验证公式

依赖：pip install openai python-dotenv
前提：同目录有 .env，内容为 API_KEY=... 和 BASE_URL=...

价格来源：DeepSeek 官方价目表 https://api-docs.deepseek.com/zh-cn/quick_start/pricing
抓取日期：2026-10-28（官方明确写了"价格可能变动"，所以半年后要重查）
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# 你代码里一直用的模型名；价目表里对应的是 flash 这一档
MODEL = os.getenv("MODEL") or "deepseek-chat"


# ============================================================
# 1. 价目表：单位是「元 / 百万 tokens」
# ============================================================

PRICES = {
    # 模型名（价目表里的正式名）: {时段: {输入缓存命中, 输入缓存未命中, 输出}}
    "deepseek-flash": {
        "peak": {"hit": 0.04, "miss": 2.0, "out": 8.0},
        "idle": {"hit": 0.02, "miss": 1.0, "out": 4.0},
    },
    "deepseek-v4-pro": {
        "peak": {"hit": 0.30, "miss": 9.0, "out": 27.0},
        "idle": {"hit": 0.15, "miss": 4.5, "out": 13.5},
    },
}

# 旧模型名 → 价目表里的正式名（只是用来查价格，不影响真正发请求时的 model 参数）
PRICE_ALIAS = {
    "deepseek-chat": "deepseek-flash",
    "deepseek-flash": "deepseek-flash",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
}

BEIJING = timezone(timedelta(hours=8))


def is_peak(now=None):
    """
    高峰时段 = 北京时间 周一至周五 9:00-12:00、14:00-18:00（法定节假日除外）
    其余时段（含周末）都是空闲时段，价格是高峰的一半。
    """
    now = now or datetime.now(BEIJING)
    if now.weekday() >= 5:          # 5=周六 6=周日
        return False
    m = now.hour * 60 + now.minute
    return (9 * 60 <= m < 12 * 60) or (14 * 60 <= m < 18 * 60)


def unit_price(model=MODEL, peak=None):
    """取出当前生效的三个单价；查不到就退回 flash 的价"""
    key = PRICE_ALIAS.get(model, "deepseek-flash")
    if peak is None:
        peak = is_peak()
    return PRICES[key]["peak" if peak else "idle"]


# ============================================================
# 2. 从 usage 里把三类 token 抠出来
# ============================================================

def read_usage(usage):
    """
    返回 (prompt_tokens, cache_hit_tokens, completion_tokens)

    为什么这么绕：不同服务商、不同 SDK 版本，字段名不一样，还有可能不返回。
    真实工程里必须容错，不能假设字段一定存在。
    """
    if usage is None:
        return 0, 0, 0

    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0

    # DeepSeek 直接给这两个字段
    hit = getattr(usage, "prompt_cache_hit_tokens", None)

    # 兼容 OpenAI 风格：usage.prompt_tokens_details.cached_tokens
    if hit is None:
        details = getattr(usage, "prompt_tokens_details", None)
        hit = getattr(details, "cached_tokens", 0) if details else 0

    hit = hit or 0
    if hit > prompt_tokens:          # 防止上游数据异常导致负数
        hit = prompt_tokens
    return prompt_tokens, hit, completion_tokens


def calc_cost(prompt_tokens, cache_hit_tokens, completion_tokens, model=MODEL, peak=None):
    """
    核心公式（唯一需要背下来的一行）：
        费用 = 各类 token 数 / 1_000_000 * 该类单价
    返回 (总费用元, 明细字典)
    """
    p = unit_price(model, peak)
    miss = max(prompt_tokens - cache_hit_tokens, 0)

    cost_hit = cache_hit_tokens / 1_000_000 * p["hit"]
    cost_miss = miss / 1_000_000 * p["miss"]
    cost_out = completion_tokens / 1_000_000 * p["out"]

    detail = {
        "hit_tokens": cache_hit_tokens,
        "miss_tokens": miss,
        "out_tokens": completion_tokens,
        "cost_hit": cost_hit,
        "cost_miss": cost_miss,
        "cost_out": cost_out,
        "peak": peak if peak is not None else is_peak(),
        "model": PRICE_ALIAS.get(model, "deepseek-flash"),
    }
    return cost_hit + cost_miss + cost_out, detail


def fmt_yuan(x):
    """人民币金额：小于 1 分钱也显示出来，否则全是 0.0000 看不出差别"""
    if x >= 0.01:
        return f"{x:.4f} 元"
    return f"{x * 1000:.4f} 厘（{x:.8f} 元）"


def print_cost(tag, usage, model=MODEL, peak=None):
    pt, hit, ct = read_usage(usage)
    total, d = calc_cost(pt, hit, ct, model, peak)
    print(f"  [{tag}] 输入 {pt}（命中 {hit} / 未命中 {d['miss_tokens']}）"
          f" | 输出 {ct} | 费用 {fmt_yuan(total)}")
    return total, pt, hit, ct


# ============================================================
# 3. 会话累计器：真实项目里必须有这个东西
# ============================================================

class CostMeter:
    """一条对话的账本：累计 token、累计费用，并给出月成本预估"""

    def __init__(self, model=MODEL):
        self.model = model
        self.calls = 0
        self.prompt_tokens = 0
        self.hit_tokens = 0
        self.completion_tokens = 0
        self.total_cost = 0.0

    def add(self, usage, peak=None):
        pt, hit, ct = read_usage(usage)
        cost, _ = calc_cost(pt, hit, ct, self.model, peak)
        self.calls += 1
        self.prompt_tokens += pt
        self.hit_tokens += hit
        self.completion_tokens += ct
        self.total_cost += cost
        return cost

    def report(self, daily_calls=None):
        print("\n" + "-" * 58)
        print(f"  账本｜调用 {self.calls} 次")
        print(f"      输入 {self.prompt_tokens} tokens（其中缓存命中 {self.hit_tokens}）")
        print(f"      输出 {self.completion_tokens} tokens")
        print(f"      累计费用 {fmt_yuan(self.total_cost)}")
        if self.calls:
            avg = self.total_cost / self.calls
            print(f"      单次均价 {fmt_yuan(avg)}")
            if daily_calls:
                print(f"      按每天 {daily_calls} 次估算：日 {fmt_yuan(avg * daily_calls)}"
                      f" / 月 {avg * daily_calls * 30:.2f} 元")
        print("-" * 58)


# ============================================================
# 4. 三个实验
# ============================================================

def make_client():
    return OpenAI(api_key=os.getenv("API_KEY"),
                  base_url=os.getenv("BASE_URL") or "https://api.deepseek.com")


def call_once(client, messages, max_tokens=None, temperature=0.3):
    kwargs = {"model": MODEL, "messages": messages,
              "temperature": temperature, "timeout": 30}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content, resp.usage


LONG_CONTEXT = "以下是一份内部技术规范，请记住它，后面我会提问。\n" + "\n".join(
    f"第 {i} 条：接口调用必须设置超时；失败必须按错误类型决定是否重试；"
    f"日志必须记录 trace_id；金额一律用整数分存储；所有外部依赖必须有降级方案。"
    for i in range(1, 41)
)


def exp_cache(client):
    """实验①：同一段长 prompt 发两次，第二次应该大量命中缓存 → 便宜几十倍"""
    print("\n" + "=" * 62)
    print("实验① 缓存命中：长 system prompt 发两次")
    print("=" * 62)
    print(f"  预热文本长度：{len(LONG_CONTEXT)} 字符")
    meter = CostMeter()
    for i in (1, 2):
        messages = [{"role": "system", "content": LONG_CONTEXT},
                    {"role": "user", "content": "用一句话总结这份规范的核心要求。"}]
        _, usage = call_once(client, messages, max_tokens=120)
        c = meter.add(usage)
        print_cost(f"第{i}次", usage)
    meter.report(daily_calls=200)
    print("  观察重点：第 2 次的『命中』应该明显大于 0，费用应大幅下降。")


def exp_length(client):
    """实验②：同样的输入，输出长度不同 → 费用差多少"""
    print("\n" + "=" * 62)
    print("实验② 输出长度对费用的影响")
    print("=" * 62)
    meter = CostMeter()
    q = [{"role": "user", "content": "介绍一下什么是向量数据库。"}]
    for mt in (50, 400):
        reply, usage = call_once(client, q, max_tokens=mt)
        print_cost(f"max_tokens={mt}", usage)
        meter.add(usage, peak=False)      # 这里顺便演示按空闲时段计价
    print(f"  （对照：空闲时段单价是高峰的一半，同一笔调用半夜跑省 50%）")


def exp_multiturn(client):
    """实验③：多轮对话里，输入 token 为什么会平方级增长"""
    print("\n" + "=" * 62)
    print("实验③ 多轮对话的成本曲线（全量重发 vs 滑动窗口）")
    print("=" * 62)
    questions = ["什么是 RAG？", "它和微调有什么区别？", "那成本上哪个高？", "举个小团队的例子。"]

    print("\n  【A】全量重发：历史越长，每次重发的输入越多")
    full = [{"role": "system", "content": "你是简洁的技术助手，每次回答不超过 60 字。"}]
    meter_a = CostMeter()
    for i, q in enumerate(questions, 1):
        full.append({"role": "user", "content": q})
        reply, usage = call_once(client, full, max_tokens=200)
        meter_a.add(usage)
        print_cost(f"第{i}轮 历史{len(full)}条", usage)
        full.append({"role": "assistant", "content": reply})
    meter_a.report()

    print("\n  【B】滑动窗口：只带 system + 最近 2 条历史")
    win = [{"role": "system", "content": "你是简洁的技术助手，每次回答不超过 60 字。"}]
    meter_b = CostMeter()
    for i, q in enumerate(questions, 1):
        win.append({"role": "user", "content": q})
        reply, usage = call_once(client, win, max_tokens=200)
        meter_b.add(usage)
        print_cost(f"第{i}轮 历史{len(win)}条", usage)
        win.append({"role": "assistant", "content": reply})
        if len(win) > 5:                 # system + 2 问 + 2 答
            win = [win[0]] + win[-4:]
    meter_b.report()

    if meter_a.total_cost > 0:
        print(f"\n  结论：本轮全量重发比滑动窗口贵 "
              f"{meter_a.total_cost / max(meter_b.total_cost, 1e-12):.1f} 倍")


def selftest():
    """不发网络请求，用假 usage 验证公式，顺便算几个真实场景"""
    print("=" * 62)
    print("公式自测（假数据，不花钱）")
    print("=" * 62)

    class FakeUsage:
        def __init__(self, p, c, h=0):
            self.prompt_tokens = p
            self.completion_tokens = c
            self.total_tokens = p + c
            self.prompt_cache_hit_tokens = h

    cases = [
        ("hello.py 那种小调用", 30, 24, 0),
        ("多轮对话第 5 轮（全量重发约 2000 输入）", 2000, 200, 0),
        ("2000 输入里命中 1500 缓存", 2000, 200, 1500),
        ("超长文档 3 万输入 + 1000 输出", 30000, 1000, 0),
    ]
    for name, p, c, h in cases:
        for peak in (True, False):
            total, d = calc_cost(p, h, c, "deepseek-flash", peak)
            when = "高峰" if peak else "空闲"
            print(f"\n  {name}｜{when}｜hit={h}")
            print(f"    未命中 {d['miss_tokens']} × {PRICES['deepseek-flash']['peak' if peak else 'idle']['miss']} 元/M"
                  f" = {d['cost_miss']:.6f} 元")
            print(f"    命中   {d['hit_tokens']} × {PRICES['deepseek-flash']['peak' if peak else 'idle']['hit']} 元/M"
                  f" = {d['cost_hit']:.6f} 元")
            print(f"    输出   {d['out_tokens']} × {PRICES['deepseek-flash']['peak' if peak else 'idle']['out']} 元/M"
                  f" = {d['cost_out']:.6f} 元")
            print(f"    合计 {fmt_yuan(total)}")

    print("\n" + "-" * 58)
    print("  边界检查：")
    # 1) usage 为 None
    print("  usage=None →", read_usage(None))
    # 2) 缓存命中数大于输入总数（上游脏数据）
    bad = FakeUsage(100, 10, 500)
    print("  命中数 500 > 输入 100 → 已截断为", read_usage(bad)[1])
    print("  对应费用（不应出现负数）→", fmt_yuan(calc_cost(*read_usage(bad))[0]))


# ============================================================
# 5. 入口
# ============================================================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "selftest":
        selftest()
        return

    if not os.getenv("API_KEY"):
        print("未读取到 API_KEY，请检查同目录的 .env 文件")
        return

    client = make_client()
    print(f"模型：{MODEL}｜当前时段：{'高峰' if is_peak() else '空闲'}"
          f"（{datetime.now(BEIJING).strftime('%Y-%m-%d %H:%M')} 北京时间）")

    t0 = time.time()
    if mode == "cache":
        exp_cache(client)
    elif mode == "length":
        exp_length(client)
    elif mode == "multiturn":
        exp_multiturn(client)
    else:
        exp_cache(client)
        exp_length(client)
        exp_multiturn(client)
    print(f"\n全部结束，总耗时 {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
