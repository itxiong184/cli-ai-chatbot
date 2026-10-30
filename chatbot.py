"""
chatbot.py — W2 D6：命令行聊天机器人（第一版）

把前面几天学的东西拼成一个真东西：
    D2 流式输出   → 一个字一个字往外冒，不用干等
    D3 多轮对话   → 历史全量重发，assistant 回复要存回去
    D4 异常重试   → 错误分类 + 指数退避；已经开始打印就不重试
    D5 成本核算   → 每轮记账，随时 /cost 看花了多少

用法：
    python chatbot.py          # 正常聊天
    python chatbot.py --demo   # 只问一句就退出（用来验证接口通不通，不花几分钱）
    python chatbot.py --selftest  # 只测本地逻辑，不发网络请求

命令：
    /help     看命令
    /clear    清空对话历史（system 保留）
    /cost     看账本
    /history  看当前历史有多少条
    /save     手动存档（每轮成功其实会自动存）
    /load     读取上次的存档
    /quit     退出

依赖：pip install openai python-dotenv
前提：同目录有 .env（API_KEY / BASE_URL），且有 cost_tracker.py 和 robust_call.py
"""

import os
import sys
import json
import time
import random
from datetime import datetime

from openai import OpenAI
from dotenv import load_dotenv

# 复用前面两天的成果，不重复造轮子
from robust_call import classify_error
from cost_tracker import CostMeter, fmt_yuan, is_peak

# Windows 控制台默认可能不是 UTF-8，打印中文/符号会崩，先兜一下
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()

MODEL = os.getenv("MODEL") or "deepseek-chat"
HISTORY_FILE = "chat_history.json"

# 上下文裁剪：最多保留最近 8 轮（1 轮 = 用户 1 条 + AI 1 条）
MAX_KEEP_TURNS = 8

SYSTEM_PROMPT = (
    "你是一个简洁的中文技术助手。"
    "回答尽量控制在 150 字以内，只有在必要时才给代码，代码要能直接运行。"
    "不确定的事情直接说不确定，不要编造。"
)


# ============================================================
# 1. 流式调用：今天唯一的新东西
# ============================================================

def make_client():
    return OpenAI(
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL") or "https://api.deepseek.com",
    )


def stream_once(client, messages, on_piece=None, temperature=0.7, timeout=60):
    """
    发一次流式请求，边收边打印。

    返回 (完整文本, usage, finish_reason)
    出错就直接抛异常，由外面的 ask() 决定要不要重试。
    """
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        # 关键：流式默认不返回 usage，必须显式要，否则你不知道花了多少 token
        stream_options={"include_usage": True},
        temperature=temperature,
        timeout=timeout,
    )

    parts = []
    usage = None
    finish_reason = None

    for chunk in resp:
        # 注意：最后一个 chunk 只带 usage，它的 choices 是空列表！
        # 所以必须先取 usage，再判断 choices 是否为空，顺序反了会 IndexError。
        if getattr(chunk, "usage", None):
            usage = chunk.usage

        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        if choice.finish_reason:
            finish_reason = choice.finish_reason

        piece = choice.delta.content if choice.delta else None
        if piece:
            parts.append(piece)
            if on_piece:
                on_piece(piece)

    return "".join(parts), usage, finish_reason


class EstUsage:
    """兜底用：服务端没返回 usage 时，用字符数估算一个"""

    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens
        self.prompt_cache_hit_tokens = 0
        self.prompt_cache_miss_tokens = prompt_tokens


def estimate_usage(messages, reply_text):
    """中文大约 1 字符 ≈ 0.6 token，英文约 0.3；这里统一按 0.6 粗估"""
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    return EstUsage(int(prompt_chars * 0.6), int(len(reply_text) * 0.6))


def ask(client, messages, max_retry=2, base_delay=1.0):
    """
    带重试的流式提问。

    和 D4 的 call_with_retry 有个致命区别：
    流式一旦开始打印，用户屏幕上已经有半截话了，重试也无法撤回。
    所以：没打印过 → 可以重试；打印过 → 只报错，不重试。
    """
    for attempt in range(max_retry + 1):
        state = {"printed": False}

        def on_piece(p):
            state["printed"] = True
            print(p, end="", flush=True)

        try:
            reply, usage, finish = stream_once(client, messages, on_piece=on_piece)
            print()  # 补一个换行，别让提示符粘在回答后面
            if usage is None:
                usage = estimate_usage(messages, reply)
                print("  （服务端未返回 usage，以下为按字符估算值）")
            return reply, usage, finish

        except Exception as exc:
            kind = classify_error(exc)
            code = getattr(exc, "status_code", "-")

            if state["printed"]:
                print(f"\n  [输出中断] {type(exc).__name__}(status={code})")
                print("  已经显示的内容无法撤回，本轮不计入历史。")
                return None, None, None

            if kind == "retry" and attempt < max_retry:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.4), 8.0)
                print(f"  [重试] {type(exc).__name__}(status={code}) "
                      f"→ {delay:.1f}s 后重来（{attempt + 1}/{max_retry}）")
                time.sleep(delay)
                continue

            reason = {"fatal": "不可重试", "retry": "重试次数用完"}.get(kind, "未知错误")
            print(f"  [失败] {type(exc).__name__}(status={code}) | {reason}")
            print(f"  原始信息：{str(exc)[:160]}")
            return None, None, None

    return None, None, None


# ============================================================
# 2. 上下文裁剪：D5 学到的降本手段，这里是落地
# ============================================================

def trim_history(messages, max_turns=MAX_KEEP_TURNS):
    """
    保留 system + 最近 max_turns 轮。

    规则：
      - system 永远保留（它定义了 AI 的人格和约束）
      - 从后往前数，保留最近的若干条
      - 裁剪时保证不会把 assistant 的回答和它的提问切开
    返回 (新列表, 被裁掉的条数)
    """
    system = [m for m in messages if m["role"] == "system"]
    dialog = [m for m in messages if m["role"] != "system"]

    limit = max_turns * 2                 # 每轮 2 条
    if len(dialog) <= limit:
        return messages, 0

    kept = dialog[-limit:]
    # 如果第一条是 assistant，说明把提问切掉了，往后再让一条
    if kept and kept[0]["role"] == "assistant":
        kept = kept[1:]

    new_messages = system + kept
    return new_messages, len(messages) - len(new_messages)


# ============================================================
# 3. 存档
# ============================================================

def save_history(messages, path=HISTORY_FILE):
    data = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "messages": messages,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_history(path=HISTORY_FILE):
    if not os.path.exists(path):
        print(f"  没找到存档文件 {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"  存档文件损坏，读不出来：{path}")
        return None
    except OSError as exc:
        print(f"  读文件失败：{exc}")
        return None

    msgs = data.get("messages")
    if not isinstance(msgs, list) or not msgs:
        print("  存档里没有有效对话")
        return None

    print(f"  已载入 {len(msgs)} 条消息（存于 {data.get('saved_at', '未知时间')}）")
    return msgs


# ============================================================
# 4. 界面
# ============================================================

def print_banner(meter):
    now = datetime.now()
    print("=" * 62)
    print("  命令行聊天机器人 v0.1 ｜ W2 D6")
    print(f"  模型 {MODEL} ｜ {now.strftime('%m-%d %H:%M')} "
          f"｜ 当前{'高峰' if is_peak() else '空闲'}时段")
    print("  /help 看命令，/quit 退出")
    print("=" * 62)
    print(f"  累计：{meter.calls} 次调用，{fmt_yuan(meter.total_cost)}")


def handle_command(cmd, messages, meter):
    """
    返回 (messages, 是否退出)
    """
    if cmd in ("/quit", "/exit", "/q"):
        return messages, True

    if cmd == "/help":
        print("  /clear 清空历史   /cost 看账本   /history 看历史条数")
        print("  /save 存档        /load 读档     /quit 退出")

    elif cmd == "/clear":
        messages = [m for m in messages if m["role"] == "system"]
        print("  历史已清空（system 保留，账本不清零）")

    elif cmd == "/cost":
        meter.report(daily_calls=500)

    elif cmd == "/history":
        print(f"  当前 {len(messages)} 条消息（含 system 1 条）")

    elif cmd == "/save":
        save_history(messages)
        print(f"  已存到 {HISTORY_FILE}")

    elif cmd == "/load":
        loaded = load_history()
        if loaded:
            messages = loaded

    else:
        print(f"  未知命令：{cmd}（/help 看看有哪些）")

    return messages, False


# ============================================================
# 5. 主循环
# ============================================================

def run_chat():
    if not os.getenv("API_KEY"):
        print("未读取到 API_KEY，请检查同目录的 .env")
        return

    client = make_client()
    meter = CostMeter()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print_banner(meter)

    while True:
        try:
            text = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not text:
            continue

        if text.startswith("/"):
            messages, quit_now = handle_command(text, messages, meter)
            if quit_now:
                save_history(messages)
                meter.report(daily_calls=500)
                print(f"  自动存档到 {HISTORY_FILE}，再见。")
                break
            continue

        # 1) 先把用户这句话入历史
        messages.append({"role": "user", "content": text})

        # 2) 超长就裁掉最老的（省钱，D5 第六节那张表）
        messages, dropped = trim_history(messages)
        if dropped:
            print(f"  （上下文超了，裁掉最老 {dropped} 条）")

        # 3) 发请求
        print("AI: ", end="", flush=True)
        t0 = time.time()
        reply, usage, finish = ask(client, messages)
        cost = None

        if reply is None:
            # 失败：把这句用户消息撤回，保持历史干净（D4 的 rollback）
            messages.pop()
            print("  （本轮失败，历史未更新）")
            continue

        # 4) 成功才入历史 + 记账
        messages.append({"role": "assistant", "content": reply})
        cost = meter.add(usage)
        elapsed = time.time() - t0

        print(f"  [{elapsed:.1f}s | finish={finish} | 本轮 {fmt_yuan(cost)} "
              f"| 累计 {fmt_yuan(meter.total_cost)} | 历史 {len(messages)} 条]")

        # 5) 每轮自动存档，崩了也不丢
        try:
            save_history(messages)
        except OSError as exc:
            print(f"  （存档失败：{exc}）")

    return meter


def demo():
    """非交互式跑一句，用来验证接口通不通"""
    client = make_client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "用一句话说明什么是流式输出。"}]
    meter = CostMeter()
    print("AI: ", end="", flush=True)
    reply, usage, finish = ask(client, messages)
    if reply is None:
        print("调用失败，检查 .env 里的 API_KEY / BASE_URL")
        return
    cost = meter.add(usage)
    print(f"  [finish={finish} | 本轮 {fmt_yuan(cost)} | 输出 {len(reply)} 字]")


def selftest():
    """不发网络请求，只测本地逻辑"""
    print("=" * 62)
    print("本地逻辑自测（不发请求，不花钱）")
    print("=" * 62)

    # 1) 裁剪
    msgs = [{"role": "system", "content": "SYSTEM"}]
    for i in range(1, 21):
        msgs.append({"role": "user", "content": f"问题{i}"})
        msgs.append({"role": "assistant", "content": f"回答{i}"})
    print(f"\n  裁剪前：{len(msgs)} 条")
    trimmed, dropped = trim_history(msgs, max_turns=8)
    print(f"  裁剪后：{len(trimmed)} 条（丢掉 {dropped} 条）")
    print(f"  第一条是 system？{trimmed[0]['role'] == 'system'}")
    print(f"  第二条是 user？  {trimmed[1]['role'] == 'user'}")
    print(f"  保留的最后一条：{trimmed[-1]['content']}")

    # 2) 边界：只有 user 没有 assistant 时不能切错
    odd = [{"role": "system", "content": "S"}]
    for i in range(1, 12):
        odd.append({"role": "user", "content": f"u{i}"})
    t2, d2 = trim_history(odd, max_turns=3)
    print(f"\n  奇数条裁剪：{len(odd)} → {len(t2)} 条，首条角色 {t2[1]['role']}")

    # 3) 估算兜底
    est = estimate_usage([{"role": "user", "content": "一二三四五六七八九十"}], "回答" * 50)
    print(f"\n  估算兜底：prompt={est.prompt_tokens} completion={est.completion_tokens}")

    # 4) 存档往返
    save_history([{"role": "system", "content": "S"},
                  {"role": "user", "content": "存档测试：中文 & 符号 ✓"}], "_selftest.json")
    back = load_history("_selftest.json")
    print(f"  存档往返一致？{back[1]['content'] == '存档测试：中文 & 符号 ✓'}")
    os.remove("_selftest.json")

    # 5) 重试不会无限循环（假 client）
    class DeadClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise ConnectionError("模拟断网")

    t0 = time.time()
    r = ask(DeadClient(), [{"role": "user", "content": "hi"}], max_retry=1, base_delay=0.2)
    print(f"\n  假断网：返回值 {r[0]}，耗时 {time.time() - t0:.1f}s（应约 0.2s，只重试 1 次）")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--selftest":
        selftest()
    elif arg == "--demo":
        demo()
    else:
        run_chat()


if __name__ == "__main__":
    main()
