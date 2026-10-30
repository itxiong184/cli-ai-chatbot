"""
robust_call.py — W2 D4：异常与重试（完整可运行版）

用法：
    python robust_call.py          # 依次跑 4 个实验（默认）
    python robust_call.py normal   # 只跑正常调用
    python robust_call.py badkey   # Key 错误 → 应立即失败，不重试
    python robust_call.py badmodel # 模型名错误 → 应立即失败，不重试
    python robust_call.py badurl   # 域名错误/断网 → 应重试 1s/2s/4s
    python robust_call.py chat     # 多轮对话（已接入重试）

依赖：pip install openai python-dotenv
前提：同目录有 .env，内容为 API_KEY=... 和 BASE_URL=...
"""

import os
import sys
import time
import random

import openai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL = "deepseek-chat"
BASE_URL = os.getenv("BASE_URL") or "https://api.deepseek.com"
API_KEY = os.getenv("API_KEY")


# ============================================================
# 1. 错误分类：今天的核心
# ============================================================

# 可重试：临时性故障，等一会儿可能就好了
RETRYABLE_TYPES = (
    openai.APITimeoutError,        # 超时
    openai.APIConnectionError,     # 连不上（断网、域名错、DNS 失败）
    openai.RateLimitError,         # 429 限流
    openai.InternalServerError,    # 5xx 服务端故障
)

# 不可重试：你自己的问题，重试 100 次也一样
FATAL_TYPES = (
    openai.AuthenticationError,    # 401 Key 错
    openai.PermissionDeniedError,  # 403 无权限
    openai.BadRequestError,        # 400 参数错（含模型名错、上下文超长）
    openai.NotFoundError,          # 404 地址/资源不存在
)

RETRYABLE_CODES = {408, 409, 429, 500, 502, 503, 504}


def classify_error(exc):
    """
    把异常归类，返回 "retry" / "fatal" / "unknown"

    判断顺序有讲究：先按 SDK 异常类型判断，再退回状态码，最后看异常名。
    """
    # 第一层：SDK 的异常类型（最可靠）
    if isinstance(exc, RETRYABLE_TYPES):
        return "retry"
    if isinstance(exc, FATAL_TYPES):
        return "fatal"

    # 第二层：按 HTTP 状态码（兼容未被 SDK 包装的异常）
    code = getattr(exc, "status_code", None)
    if code in RETRYABLE_CODES:
        return "retry"
    if code is not None:
        return "fatal"

    # 第三层：Python 自带网络异常
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "retry"

    return "unknown"


# ============================================================
# 2. 带指数退避 + 抖动的重试调用
# ============================================================

def make_client(api_key=None, base_url=None):
    """创建一个 client；实验里可以传错的 key / 错的地址来模拟故障"""
    return OpenAI(
        api_key=api_key or API_KEY,
        base_url=base_url or BASE_URL,
    )


def call_with_retry(
    messages,
    model=MODEL,
    max_retry=3,
    base_delay=1.0,
    max_delay=8.0,
    timeout=30,
    temperature=0.3,
    client=None,
    tag="调用",
):
    """
    返回 (reply_text, usage)；彻底失败时返回 (None, None)

    重试策略：指数退避 + 随机抖动
        第 1 次失败 → 等 1s 左右
        第 2 次失败 → 等 2s 左右
        第 3 次失败 → 等 4s 左右
        （每次翻倍，加随机抖动避免所有请求同时冲同一时刻）
    """
    client = client or make_client()

    for attempt in range(max_retry + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                timeout=timeout,          # 必须显式设置，别用默认的超长值
            )
            if attempt > 0:
                print(f"  [{tag}] 第 {attempt + 1} 次尝试成功")
            return resp.choices[0].message.content, resp.usage

        except Exception as exc:
            kind = classify_error(exc)
            code = getattr(exc, "status_code", "-")

            # 还能再试一次
            if kind == "retry" and attempt < max_retry:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.4), max_delay)
                print(f"  [{tag}] 可重试错误 {type(exc).__name__}(status={code}) "
                      f"→ 等待 {delay:.1f}s 后重试（{attempt + 1}/{max_retry}）")
                time.sleep(delay)
                continue

            # 不再重试：要么是致命错误，要么次数用完了
            reason = "不可重试" if kind == "fatal" else ("重试次数用完" if kind == "retry" else "未知错误，保守失败")
            print(f"  [{tag}] 放弃：{type(exc).__name__}(status={code}) | {reason}")
            print(f"  [{tag}] 原始信息：{str(exc)[:150]}")
            return None, None

    return None, None


# ============================================================
# 3. 四个实验
# ============================================================

QUESTION = [{"role": "user", "content": "用一句话说明什么是重试。"}]


def _run(title, fn):
    print("\n" + "=" * 62)
    print(f"实验：{title}")
    print("=" * 62)
    t0 = time.time()
    fn()
    print(f"  ⏱ 本次实验总耗时：{time.time() - t0:.1f}s")


def exp_normal():
    reply, usage = call_with_retry(QUESTION, tag="正常")
    print(f"  回复：{reply}")
    print(f"  tokens：{usage.total_tokens if usage else '-'}")


def exp_bad_key():
    """Key 错 → 401 → AuthenticationError → 立即失败，不重试"""
    bad = make_client(api_key=(API_KEY or "sk-none") + "xxx")
    reply, _ = call_with_retry(QUESTION, client=bad, tag="坏Key")
    print(f"  结果：{reply}")


def exp_bad_model():
    """模型名错 → 400 → BadRequestError → 立即失败，不重试"""
    reply, _ = call_with_retry(QUESTION, model="gpt-999", tag="坏模型")
    print(f"  结果：{reply}")


def exp_bad_url():
    """域名错 → 连不上 → APIConnectionError → 重试 1s / 2s / 4s"""
    bad = make_client(base_url="https://api.deepseek-not-exist-12345.com")
    reply, _ = call_with_retry(QUESTION, client=bad, tag="坏地址")
    print(f"  结果：{reply}")


def exp_chat():
    """多轮对话 + 重试（D6-7 聊天机器人的雏形）"""
    messages = [{"role": "system", "content": "你是一个简洁的助手，回答不超过 40 字。"}]
    print("输入内容开始聊天，输入 q 退出")
    while True:
        text = input("你: ").strip()
        if text == "q":
            break
        if not text:
            continue

        messages.append({"role": "user", "content": text})
        reply, usage = call_with_retry(messages, tag="聊天")

        if reply is None:
            print("AI: [本次失败，历史未更新]")
            messages.pop()          # 失败就把这条用户消息撤回，保持历史干净
            continue

        print(f"AI: {reply}")
        messages.append({"role": "assistant", "content": reply})
        print(f"   [历史 {len(messages)} 条 | tokens {usage.total_tokens}]")


# ============================================================
# 4. 入口
# ============================================================

def main():
    if not API_KEY:
        print("未读取到 API_KEY，请检查同目录的 .env 文件")
        return

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "normal":
        _run("正常调用（应一次成功）", exp_normal)
    elif mode == "badkey":
        _run("Key 错误（应立即失败，不重试）", exp_bad_key)
    elif mode == "badmodel":
        _run("模型名错误（应立即失败，不重试）", exp_bad_model)
    elif mode == "badurl":
        _run("域名错误/断网（应重试 1s→2s→4s）", exp_bad_url)
    elif mode == "chat":
        exp_chat()
    else:
        _run("① 正常调用", exp_normal)
        _run("② Key 错误 → 预期：立即失败", exp_bad_key)
        _run("③ 模型名错误 → 预期：立即失败", exp_bad_model)
        _run("④ 域名错误 → 预期：重试 1s→2s→4s", exp_bad_url)
        print("\n全部实验结束。观察重点：②③ 总耗时约 1s（不等待），④ 总耗时约 8s（三次退避）。")


if __name__ == "__main__":
    main()
