"""
extractor.py — W3 D1：简历信息抽取器 v0.1

把一段自由文本（简历片段 / 口语化自我介绍）抽取成固定结构的 JSON。

用法：
    python extractor.py            # 跑内置的 3 个样本
    python extractor.py --dry      # 只打印将要发送的 prompt，不调用 API（不花钱）
    python extractor.py --file a.txt   # 抽取你指定的文件
    python extractor.py --raw      # 同时打印模型返回的原始字符串（调试用）

依赖：openai python-dotenv；同目录需有 .env 和 cost_tracker.py
"""

import os
import re
import sys
import json
import time
from datetime import datetime

from openai import OpenAI
from dotenv import load_dotenv

from cost_tracker import CostMeter, fmt_yuan

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()

MODEL = os.getenv("MODEL") or "deepseek-chat"


# ============================================================
# 1. schema：先把"要什么"定死，再谈怎么问
# ============================================================

# 这是给模型看的说明书，也是给你自己看的合同。
# 字段名一旦定了，下游代码就依赖它，不能随便改。改了就要升 schema 版本号。
#
# v2.0 的结构性变化：education 和 projects 从"一个值"变成"一组值"。
# v1.1 那种扁平写法有个死穴——一个人有两段学历时，只能留一段，
# 另一段的信息在抽取阶段就永久丢失了，后面任何代码都补不回来。
SCHEMA_DOC = """{
  "name": string|null,               // 姓名
  "phone": string|null,              // 手机号，只保留数字，如 "13800138000"
  "email": string|null,              // 邮箱
  "city": string|null,               // 现居城市或工作所在城市；完全无法判断时为 null

  "education": [                     // 教育经历，按时间从早到晚排列，有几段写几段
    {
      "school": string,              // 学校全称
      "major": string|null,          // 专业
      "degree": "专科"|"本科"|"硕士"|"博士"|null,  // "大专""专升本"的本科段归为"本科"
      "graduation_year": string|null // 毕业年份四位数字；"2027 届""预计 2027 年毕业"都算 2027
    }
  ],

  "skills": string[],                // 全文出现的全部技术/工具关键词，含项目里提到的；
                                     // 原文措辞照抄，不合并同类、不补全缩写；与 tech 允许重复
  "years_experience": number|null,   // 全职工作年限；仅实习/兼职不计入，应届生为 null

  "projects": [                      // 项目经历；没有明确项目名称的一律不收
    {
      "name": string,                // 项目名称，照抄原文
      "tech": string[],              // 该项目用到的技术，原文措辞
      "summary": string|null         // 一句话客观描述，不超过 40 字，不加评价
    }
  ]
}"""

SYSTEM_PROMPT = f"""你是一个简历信息抽取引擎。你的唯一任务是从用户给出的文本中抽取字段，输出一个 JSON 对象。

硬性规则：
1. 只输出 JSON 本体。不要输出解释、前后缀、markdown 代码块标记。
2. 严格遵守下面的 schema：字段名、字段顺序、类型都不得改动，不得增删字段。
3. 文本中没有提到的字段，值必须是 null（数组字段用 []）。绝对不许猜测或编造。
4. 只做复制和归类，不做推理、总结、美化。原文写"了解 Python"，就写"了解 Python"，不许升级成"精通"。
5. 手机号只保留数字；年份用四位数字字符串；技能拆成独立关键词。
6. education 有几段写几段，不许只保留最高学历，也不许把两段合并成一条。
7. projects 只收有明确名称的项目；实习期间做的项目也算；没有名称的不收，不要自己起名。
8. skills 收全文中出现的所有技术/工具关键词，不限于"技能"那一段；和 tech 重复是允许的。

schema:
{SCHEMA_DOC}"""


# ============================================================
# 2. 三个样本：一个好例子不够，要能看见坏情况
# ============================================================

SAMPLES = {
    "① 标准简历片段": """熊阳阳
男 | 郑州 | 138 0013 8000 | xiong@example.com
郑州轻工业大学 网络工程（云计算方向） 本科 2023.09-2027.06
技能：Python、Linux、MySQL、Git、Docker
2026.07-2026.09 在某科技公司实习，做接口联调与日志排查，约 3 个月。
项目：命令行 AI 对话工具，用 Python + DeepSeek API 实现流式输出与 token 成本核算。""",

    "② 口语化自我介绍": """你好，我叫李明，家是河南南阳的，现在在郑州上学。
学校是河南工业大学，学的是计算机科学与技术，明年就毕业了。
平时写过一些 Python 脚本，也用过一点 Java，数据库会 MySQL。
电话就不留了吧，邮箱 liming2027@163.com 可以找到我。""",

    "③ 缺字段 + 干扰信息": """这是一份兼职招聘启事，联系人王女士，电话 13912345678。
应聘者张小满，2025 年从郑州大学毕业，专业是软件工程，本科学历。
她熟悉 JavaScript 和 Vue，做过两个小程序项目，但简历上没写期望薪资。
（备注：以上信息由第三方录入，可能存在误差）""",

    "④ 多段学历 + 多个项目": """周衡，男，苏州，18600001111，zhouheng@mail.com
教育经历：
2015.09-2018.06 苏州职业大学 计算机应用技术 专科
2018.09-2020.06 苏州科技大学 软件工程 本科
2020.09-2023.06 东南大学 软件工程 硕士
项目经历：
「企业知识库问答系统」负责检索模块，用 Python、LangChain、FAISS，把 3 万份文档做成可检索的知识库。
「订单对账平台」用 Java、Spring Boot、MySQL 做日终对账，把人工核对从 4 小时压到 20 分钟。
2023 年硕士毕业后在苏州一家公司做后端开发，至今 2 年。熟悉 Python、Java、MySQL、Redis。""",
}


# ============================================================
# 3. 调用：JSON 模式 + 解析 + 自动修复
# ============================================================

def make_client():
    return OpenAI(api_key=os.getenv("API_KEY"),
                  base_url=os.getenv("BASE_URL") or "https://api.deepseek.com")


def call_model(client, messages, temperature=0.0):
    """
    temperature=0.0：抽取任务要"确定性"，同样的输入尽量给同样的输出。
    这是抽取类任务和聊天类任务最大的参数差异。
    """
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,          # 抽取任务：0
        response_format={"type": "json_object"},   # 让服务端保证返回的是 JSON
        timeout=60,
    )
    return resp.choices[0].message.content, resp.usage


def parse_json(text):
    """模型偶尔会裹一层 ```json，兜一下再解析"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def extract(client, text, meter=None, max_fix=1, verbose=False):
    """
    抽取主流程：调用 → 解析 → 校验 → （可选）带错误信息让模型修一次

    返回 (data, issues)；彻底失败返回 (None, [错误说明])
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]

    for attempt in range(max_fix + 1):
        raw, usage = call_model(client, messages)
        if meter is not None:
            meter.add(usage)
        if verbose:
            print(f"\n  --- 模型原始返回（第 {attempt + 1} 次）---\n{raw}\n  ---")

        # ① 解析：这一步最容易崩
        try:
            data = parse_json(raw)
        except json.JSONDecodeError as exc:
            if attempt < max_fix:
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 f"上面的输出不是合法 JSON（错误：{exc}）。"
                                 f"请只输出修正后的 JSON 本体，不要任何解释或代码块标记。"})
                continue
            return None, [f"JSON 解析失败：{exc}"]

        # ② 校验：解析成功不等于内容正确
        issues = validate(data, text)
        if not issues:
            return data, []

        if attempt < max_fix:
            # 把校验错误回灌给模型，让它自己改（self-repair）
            # 注意措辞：不要写成"没有依据的就置 null"，那会让模型把正确的字段也一起清掉。
            # 校验规则是启发式的，一定有误报 —— 所以要把判断权交回给模型。
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                             "你输出的 JSON 通过了解析，但有以下问题：\n- "
                             + "\n- ".join(issues)
                             + "\n请逐条核对原文：确实错的才改；原文明确写了的信息必须保留，不要为了通过检查而清空字段。"
                               "\n修正后重新输出完整 JSON。"})
            continue

        return data, issues

    return None, ["超过最大修复次数"]


# ============================================================
# 4. 校验：程序侧的"验收标准"
# ============================================================

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
DEGREES = {"专科", "本科", "硕士", "博士"}

FIELDS = ["name", "phone", "email", "city", "education",
          "skills", "years_experience", "projects"]
EDU_FIELDS = ["school", "major", "degree", "graduation_year"]
PROJ_FIELDS = ["name", "tech", "summary"]

# 归属干扰词：这些词出现在值附近，说明这个值可能属于别人（HR、家属、推荐人…）
# 这是对"回溯校验"盲区的补丁 —— 值确实在原文里，但可能不属于候选人。
DISOWN_WORDS = ("联系人", "招聘", "人事", "HR", "hr", "客服", "咨询",
                "家属", "家长", "推荐人", "证明人", "紧急联系", "辅导员")


def _norm(s):
    """去掉空白和标点后比对，用于幻觉检测"""
    return re.sub(r"[\s\-_·,，。.、|]", "", str(s))


def _locate(text, value):
    """在原文里找这个值的位置。手机号可能带空格横杠，所以再试一次纯数字"""
    v = str(value)
    pos = text.find(v)
    if pos >= 0:
        return pos, len(v)
    digits = re.sub(r"\D", "", v)
    if digits and digits != v:
        pos = text.find(digits)
        if pos >= 0:
            return pos, len(digits)
    return -1, 0


SENT_BREAKS = "。！？；\n"


def _sentence_around(text, pos, length):
    """
    切出值所在的那一句，返回 (句子, 值在句内的相对位置)。
    为什么要按句切？因为"联系人"这种词可能在上一句，离得再近也不该算进来。
    """
    start = 0
    for ch in SENT_BREAKS:
        i = text.rfind(ch, 0, pos)
        if i >= 0:
            start = max(start, i + 1)
    end = len(text)
    for ch in SENT_BREAKS:
        i = text.find(ch, pos + length)
        if i >= 0:
            end = min(end, i)
    return text[start:end], pos - start


def check_attribution(data, text):
    """
    归属检测：值存在 ≠ 值是候选人的。

    r04 那个例子——HR 的电话确实在原文里，回溯校验必然通过，
    但那个号码属于赵女士，不属于陈晨。这里用"同句 + 距离"兜一下。

    第一版只取"前后 25 字"，结果把 r10（同一句里有"客服"这个职业词）
    和 r32（本人手机后面那句才是"紧急联系人"）全判成了干扰，
    自修复机制再把正确的电话改成 null —— 校验器的误报会直接污染数据。
    所以窗口必须收窄到"同一句话内、且词出现在值之前"。
    """
    issues = []
    for field in ("phone", "email"):
        val = data.get(field)
        if val in (None, ""):
            continue
        pos, length = _locate(text, val)
        if pos < 0:
            continue
        seg, rel = _sentence_around(text, pos, length)
        for word in DISOWN_WORDS:
            wpos = seg.rfind(word, 0, rel)      # 只看值之前出现的位置
            if wpos < 0:
                continue
            if rel - wpos > 40:                 # 同一句里也隔太远，基本不是同一个人的标签
                continue
            issues.append(
                f'{field}="{val}" 前面的原文是「{seg[:rel]}」，'
                f'其中出现「{word}」，该值可能不属于候选人本人')
            break
    return issues


def check_education(edu, text):
    """education 是数组，每个元素都要检查结构和依据"""
    issues = []
    if not isinstance(edu, list):
        return ["education 必须是数组"]

    norm_text = _norm(text)
    for i, item in enumerate(edu):
        tag = f"education[{i}]"
        if not isinstance(item, dict):
            issues.append(f"{tag} 不是对象")
            continue
        missing = [k for k in EDU_FIELDS if k not in item]
        if missing:
            issues.append(f"{tag} 缺少子字段：{missing}")
        if not item.get("school"):
            issues.append(f"{tag} 的 school 不能为空（没有学校名的学历段不该输出）")
        degree = item.get("degree")
        if degree not in (None, "") and degree not in DEGREES:
            issues.append(f'{tag} 的 degree 不在允许值内："{degree}"')
        year = item.get("graduation_year")
        if year not in (None, "") and not re.match(r"^\d{4}$", str(year)):
            issues.append(f'{tag} 的 graduation_year 应为四位数字，实际："{year}"')
        for sub in ("school", "major"):
            val = item.get(sub)
            if val not in (None, "") and _norm(val) not in norm_text:
                issues.append(f'{tag} 的 {sub}="{val}" 在原文中找不到，疑似编造')
    return issues


def check_projects(projects, text):
    issues = []
    if not isinstance(projects, list):
        return ["projects 必须是数组"]

    norm_text = _norm(text)
    for i, item in enumerate(projects):
        tag = f"projects[{i}]"
        if not isinstance(item, dict):
            issues.append(f"{tag} 不是对象")
            continue
        if not item.get("name"):
            issues.append(f"{tag} 的 name 不能为空（没有名称的项目不该输出）")
        if not isinstance(item.get("tech", []), list):
            issues.append(f"{tag} 的 tech 必须是数组")
        name = item.get("name")
        if name and _norm(name) not in norm_text:
            issues.append(f'{tag} 的 name="{name}" 在原文中找不到，疑似编造')
    return issues


def validate(data, text):
    """
    返回问题列表，空列表 = 通过。
    校验分四层：结构 → 格式 → 依据 → 归属
    """
    issues = []

    # 第一层：结构
    if not isinstance(data, dict):
        return ["顶层不是 JSON 对象"]
    missing = [f for f in FIELDS if f not in data]
    if missing:
        issues.append(f"缺少字段：{missing}")
    extra = [k for k in data if k not in FIELDS]
    if extra:
        issues.append(f"多出未定义字段：{extra}")

    # 第二层：格式
    phone = data.get("phone")
    if phone not in (None, ""):
        clean = re.sub(r"\D", "", str(phone))
        if not PHONE_RE.match(clean):
            issues.append(f'phone 格式不合法："{phone}"（应为 11 位手机号）')

    email = data.get("email")
    if email not in (None, "") and not EMAIL_RE.match(str(email)):
        issues.append(f'email 格式不合法："{email}"')

    if not isinstance(data.get("skills"), list):
        issues.append("skills 必须是数组")

    # 第三层：依据 —— 抽取结果必须能在原文找到
    # 这是抽取任务最便宜的质检手段：不比对原文，你就只能相信模型
    norm_text = _norm(text)
    for field in ("name", "city"):
        val = data.get(field)
        if val not in (None, "") and _norm(val) not in norm_text:
            issues.append(f'{field}="{val}" 在原文中找不到，疑似编造')

    issues += check_education(data.get("education"), text)
    issues += check_projects(data.get("projects"), text)

    # 第四层：归属 —— 值在原文里，但它属于谁？
    issues += check_attribution(data, text)

    return issues


# ============================================================
# 5. 展示
# ============================================================

def _fmt(v):
    if v is None:
        return "null"
    if isinstance(v, list):
        return "、".join(str(x) for x in v) or "[]"
    return str(v)


def show(title, data, issues, elapsed=None):
    print("\n" + "=" * 62)
    print(f"  {title}")
    print("=" * 62)
    if data is None:
        print("  [失败] " + "；".join(issues))
        return
    for k in FIELDS:
        v = data.get(k)
        if k in ("education", "projects") and isinstance(v, list):
            print(f"  {k}  ({len(v)} 条)")
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    body = " ｜ ".join(f"{sk}={_fmt(item.get(sk))}" for sk in item)
                    print(f"      [{i}] {body}")
        else:
            print(f"  {k:<18} {_fmt(v)}")
    if issues:
        print("\n  ⚠ 校验未通过：")
        for it in issues:
            print(f"    - {it}")
    else:
        print("\n  ✅ 结构、格式、依据、归属四层校验全部通过")
    if elapsed:
        print(f"  ⏱ {elapsed:.1f}s")


def dry_run():
    print("=" * 62)
    print("  将要发送的 system prompt（--dry 模式，不调用 API）")
    print("=" * 62)
    print(SYSTEM_PROMPT)
    print("\n" + "-" * 62)
    print(f"  system prompt 长度：{len(SYSTEM_PROMPT)} 字符")
    print("  说明：这段 prompt 每次调用都要重发，所以它也是成本的一部分。")
    print("  官方缓存机制会把这个固定前缀缓存下来，命中后输入价降到 1/50。")


def main():
    args = sys.argv[1:]

    if "--dry" in args:
        dry_run()
        return

    if not os.getenv("API_KEY"):
        print("未读取到 API_KEY，检查 .env")
        return

    if "--file" in args:
        path = args[args.index("--file") + 1]
        with open(path, "r", encoding="utf-8") as f:
            samples = {os.path.basename(path): f.read()}
    else:
        samples = SAMPLES

    client = make_client()
    meter = CostMeter()
    verbose = "--raw" in args

    for title, text in samples.items():
        t0 = time.time()
        data, issues = extract(client, text, meter=meter, verbose=verbose)
        show(title, data, issues, time.time() - t0)

    meter.report()
    print("\n  下一步：把 data 存成 JSON、入库、或者喂给下游打分程序——这就是结构化的意义。")


if __name__ == "__main__":
    main()
