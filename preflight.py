"""
preflight.py — 调用模型之前的「输入侧预检」（纯函数，不联网，不花钱）

为什么要有这一层：
    validate() 是输出侧校验，只能事后发现错误，而且发现得越多、误报越多。
    有些错误在输入侧就能提前消解 —— 比如"我是郑轻 2027 届的"，
    模型完全可能把"郑轻"当姓名（r33 就是这样错的）。
    与其事后用正则去猜，不如事前在 prompt 里明说一句。

设计原则（今天最重要的一条）：
    单个信号不判决，两个独立信号交叉才报警。
    "X 2027 届" 单独出现时，X 也可能真是人名；
    只有当 X 还出现在"我是…的""毕业于…"等学校语境里、
    且全文没有任何姓名锚点时，才判定为疑似机构名。
    —— 这条规则的来源，就是 D3 那次"校验器误报把正确电话清成 null"的事故。

用法：
    from preflight import preflight
    pre = preflight(text)
    pre["banned_names"]   # 不许当作姓名的词
    pre["hints"]          # 要追加进 system prompt 的约束句
    pre["flags"]          # 机器可读的标记，用于统计与埋点
"""

import re

# ---------- 信号一：姓名锚点（出现即认为姓名可信） ----------
PAT_NAME_LABEL = re.compile(r"(?:姓\s*名|名\s*字)\s*[:：]\s*([\u4e00-\u9fa5]{2,4})")
PAT_NAME_CALL = re.compile(r"我\s*叫\s*([\u4e00-\u9fa5]{2,4})")
# 裸姓名：行首 2~3 个汉字，后面紧跟分隔符或性别字（"熊阳阳 男 | 郑州"、"张伟，2020 年毕业于…"）
PAT_NAME_BARE = re.compile(r"(?:^|\n)\s*([\u4e00-\u9fa5]{2,3})(?=\s*(?:[，,、|｜/（(]|男|女|\n|$))")

# ---------- 信号二：学校语境（出现在这些结构里的 2~4 字片段，疑似校名缩写） ----------
PAT_YEAR_JIE = re.compile(r"([\u4e00-\u9fa5]{2,4})\s*(?:\d{2,4}|[零一二三四五六])\s*届")
PAT_GRADUATED = re.compile(r"(?:毕业于|就读于|读于)\s*([\u4e00-\u9fa5]{2,10})")
PAT_SELF_DE = re.compile(r"我\s*是\s*([\u4e00-\u9fa5]{2,4})\s*的")
PAT_SELF_JIE = re.compile(r"我\s*是\s*([\u4e00-\u9fa5]{2,4})\s*\d{2,4}\s*届")

# 带这些后缀的一定是机构，不可能是人名，不必进黑名单（模型也不会认错）
SCHOOL_SUFFIX = ("大学", "学院", "职院", "高职", "中学", "附中", "一中", "小学")

# 候选片段的排除：以这些字开头／包含这些字的，是句子残留而不是实体名
BAD_PREFIX = "我是在于系和与及为做个了的有"
BAD_CONTAIN = ("我", "是", "我们", "你们", "他们")

# 第三方角色词：出现即说明文中存在"别人的联系方式"
THIRD_PARTY = ("联系人", "家属", "家长", "推荐人", "证明人", "紧急联系", "人事", "HR", "hr", "辅导员")


def _anchors(text):
    """全文的姓名锚点，命中即认为存在可信姓名"""
    found = set()
    for pat in (PAT_NAME_LABEL, PAT_NAME_CALL, PAT_NAME_BARE):
        for m in pat.finditer(text):
            found.add(m.group(1))
    return found


def _school_candidates(text):
    """出现在学校语境里的短片段（可能被误认成人名）"""
    found = set()
    for pat in (PAT_YEAR_JIE, PAT_GRADUATED, PAT_SELF_DE, PAT_SELF_JIE):
        for m in pat.finditer(text):
            found.add(m.group(1).strip())
    return found


def has_mobile(text):
    """
    判断原文里到底有没有手机号。
    不能简单地"去掉所有非数字再匹配" —— 那样 "2023 届…电话 13800138000"
    会粘成 "202313800138000"，左右边界全被污染，永远匹配不到。
    正确做法：先按连续数字块切开，再在每一块里找。
    """
    for m in re.finditer(r"\d[\d\s\-]{8,}\d", text):
        digits = re.sub(r"\D", "", m.group())
        if re.search(r"1[3-9]\d{9}", digits):
            return True
    return False


def preflight(text):
    """
    返回 dict:
      anchors       姓名锚点集合
      banned_names  疑似机构简称，禁止填进 name
      flags         机器可读标记
      hints         要追加到 system prompt 末尾的约束（每条一句话）
    """
    anchors = _anchors(text)
    candidates = _school_candidates(text)

    banned = sorted(
        c for c in candidates - anchors
        if 2 <= len(c) <= 4
        and c[0] not in BAD_PREFIX
        and not any(w in c for w in BAD_CONTAIN)
        and not any(s in c for s in SCHOOL_SUFFIX)
    )

    flags, hints = [], []

    # 关键：只有"没有姓名锚点"时，黑名单才需要写进 prompt。
    # 已经有"姓名：李明"了，模型不可能把"郑大"当名字，再提示只是噪音。
    if banned and not anchors:
        flags.append("NAME_ROLE_RISK")
        hints.append(
            "以下词在原文中出现在「我是…的 / …届 / 毕业于…」这类学校语境里，"
            f"它们不是姓名，禁止填进 name：{'、'.join(banned)}")
    elif not anchors:
        flags.append("NAME_UNANCHORED")
        hints.append(
            "原文没有「姓名：」「我叫」这类明确标注。不要用学校名、城市名、专业名、"
            "项目名代替姓名；确实找不到任何人名字样时才取 null。")

    if not has_mobile(text):
        flags.append("NO_MOBILE_IN_TEXT")
        hints.append("原文中没有出现任何 11 位手机号，phone 必须为 null。")

    hit = [w for w in THIRD_PARTY if w in text]
    if hit:
        flags.append("THIRD_PARTY_CONTACT")
        hints.append(
            f"原文出现「{hit[0]}」等第三方角色，属于他们的电话与邮箱不要填进 phone / email。")

    return {
        "anchors": sorted(anchors),
        "banned_names": banned,
        "flags": flags,
        "hints": hints,
    }


def show(pre):
    """调试用：打印预检结果"""
    print(f"  姓名锚点   : {pre['anchors'] or '无'}")
    print(f"  禁止作姓名 : {pre['banned_names'] or '无'}")
    print(f"  标记       : {pre['flags'] or '无'}")
    for h in pre["hints"]:
        print(f"  → {h}")


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    DEMO = {
        "r33 校名缩写易被当姓名": "我是郑轻 2027 届的，网络工程专业，本科。",
        "有锚点则安全": "我叫李明，郑大 2023 届，计算机专业，电话 13800138000。",
        "裸姓名行首": "张伟，2020 年毕业于河南大学，软件工程，本科。",
        "第三方联系人": "招聘岗位：Java 开发，联系人赵女士，电话 13700001111。应聘者陈晨，南邮 2026 届。",
        "手机号带空格": "姓名：周洋。手机 138 0013 8000。在郑州。",
    }
    for title, text in DEMO.items():
        print("\n" + "=" * 60)
        print("  " + title)
        print("=" * 60)
        print(f"  原文: {text}")
        show(preflight(text))
