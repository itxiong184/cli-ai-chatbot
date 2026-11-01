"""
test_extractor.py — 校验器的单元测试（不调用 API，不花钱，秒级）

为什么要有这个文件：
    模型是概率的，只能用评测集看准确率；
    但 validate() 是纯函数，输入固定就必须输出固定。
    纯函数用单元测试，概率部分用评测集 —— 两者不能互相替代。

跑法：
    python test_extractor.py
"""

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from extractor import validate, check_attribution

# ---------- 测试语料（真实样本，来自 eval/samples_v2.jsonl） ----------
T10 = "姓名：马丽。电话：13598765432。学历：高中。在郑州做过 3 年客服。"
T32 = ("姓名：赵磊。本人手机 13911112222。"
       "紧急联系人（母亲）：13911113333。"
       "2020 年本科毕业于太原理工大学 材料成型及控制工程，在太原工作 4 年。")
T04 = ("招聘岗位：Java 开发工程师，联系人赵女士，电话 13700001111，邮箱 hr@company.com。\n"
       "应聘者陈晨，男，2026 年本科毕业于南京邮电大学通信工程专业，熟悉 Java、Spring、MySQL。")
T12 = ("患者家属：李建国，电话 13000009999。\n"
       "本人：赵雪，女，25 岁，2023 年本科毕业于苏州大学护理学专业，在苏州市立医院工作 3 年。"
       "联系电话 13100008888。")
T21 = ("周衡，男，苏州，18600001111\n"
       "教育经历：2015.09-2018.06 苏州职业大学 计算机应用技术 专科；"
       "2018.09-2020.06 苏州科技大学 软件工程 本科；"
       "2020.09-2023.06 东南大学 软件工程 硕士\n"
       "在苏州做后端开发，至今 2 年。")


def blank(**kw):
    """造一个字段齐全的空壳，再覆盖指定字段"""
    d = {"name": None, "phone": None, "email": None, "city": None,
         "education": [], "skills": [], "years_experience": None, "projects": []}
    d.update(kw)
    return d


CASES = []


def case(name, text, data, expect_contains=None, expect_clean=False):
    CASES.append((name, text, data, expect_contains, expect_clean))


# 1-2 误报回归：这两条曾被误判，导致自修复把正确的电话改成 null
case("r10 普通电话不应被判为归属问题", T10,
     blank(name="马丽", city="郑州", phone="13598765432", years_experience=3),
     expect_clean=True)
case("r32 本人手机不应被判为归属问题", T32,
     blank(name="赵磊", city="太原", phone="13911112222", years_experience=4,
           education=[{"school": "太原理工大学", "major": "材料成型及控制工程",
                       "degree": "本科", "graduation_year": "2020"}]),
     expect_clean=True)

# 3-5 真干扰必须抓到
case("r32 紧急联系人的号码应报归属问题", T32,
     blank(name="赵磊", city="太原", phone="13911113333"), expect_contains="紧急联系")
case("r04 HR 的电话应报归属问题", T04,
     blank(name="陈晨", phone="13700001111"), expect_contains="联系人")
case("r04 HR 的邮箱应报归属问题", T04,
     blank(name="陈晨", email="hr@company.com"), expect_contains="联系人")
case("r12 家属的电话应报归属问题", T12,
     blank(name="赵雪", phone="13000009999"), expect_contains="家属")

# 6-9 结构与依据
case("学校在原文找不到应报幻觉", T10,
     blank(name="马丽", education=[{"school": "北京大学", "major": None,
                                   "degree": "本科", "graduation_year": "2018"}]),
     expect_contains="找不到")
case("学历段缺 school 应报结构问题", T10,
     blank(name="马丽", education=[{"school": "", "major": None,
                                   "degree": "本科", "graduation_year": "2018"}]),
     expect_contains="school 不能为空")
case("年份非四位应报格式问题", T32,
     blank(name="赵磊", education=[{"school": "太原理工大学", "major": None,
                                   "degree": "本科", "graduation_year": "20年"}]),
     expect_contains="四位数字")
case("多段学历都应保留，不应报错", T21,
     blank(name="周衡", city="苏州", phone="18600001111", years_experience=2,
           education=[{"school": "苏州职业大学", "major": "计算机应用技术",
                       "degree": "专科", "graduation_year": "2018"},
                      {"school": "苏州科技大学", "major": "软件工程",
                       "degree": "本科", "graduation_year": "2020"},
                      {"school": "东南大学", "major": "软件工程",
                       "degree": "硕士", "graduation_year": "2023"}]),
     expect_clean=True)


def main():
    ok = fail = 0
    for name, text, data, expect_contains, expect_clean in CASES:
        issues = validate(data, text)
        if expect_clean:
            passed = not issues
            detail = "无问题" if passed else f"误报：{issues}"
        else:
            passed = any(expect_contains in i for i in issues)
            detail = "" if passed else f"没抓到「{expect_contains}」，实际：{issues or '无'}"
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        if not passed:
            print(f"         {detail}")
        ok, fail = (ok + 1, fail) if passed else (ok, fail + 1)

    print(f"\n{ok} passed, {fail} failed  (共 {len(CASES)} 项)")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
