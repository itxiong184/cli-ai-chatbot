"""
build_v3.py — 把评测集从 40 条扩到 60 条，并按 skills v2.1 口径重标

为什么要有这个脚本而不是手改 jsonl：
    标注变更必须留痕。半年后你看到分数变了，得能回答"当时改了什么"。
    这个文件的 SKILL_FIX 和 NEW 两段，就是 v2 -> v3 的变更记录本身。

跑法：
    python eval/build_v3.py          # 生成 eval/samples_v3.jsonl 并打印变更
"""

import os
import sys
import json

# 脚本在 eval/ 子目录里，跑起来时 sys.path[0] 是 eval/，
# 不手动补一下父目录就 import 不到 extractor。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractor import GENERIC_SKILLS, MAX_SKILL_LEN

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

V2 = "eval/samples_v2.jsonl"
OUT = "eval/samples_v3.jsonl"
FIELDS = ["name", "phone", "email", "city", "education",
          "skills", "years_experience", "projects"]

# ---- 变更一：skills v2.1 口径（只收具体技术专名）— 必须逐条留痕 ----
SKILL_FIX = {
    "r08": ["Python", "Selenium", "JMeter"],
    # 原 ["Python 自动化测试", "Selenium", "JMeter"]：
    # "Python 自动化测试" 是"技术名 + 领域词"的拼接，匹配 JD 时应该拆成 Python。
    "r09": ["R", "Python", "SQL"],
    # 原 [..., "统计建模"]：统计建模是方法泛称，不是工具名。
    "r20": ["Python", "Java"],
    # 原 [..., "数据结构与算法"]：这是学科，不是技能。
}


def g(name=None, phone=None, email=None, city=None,
      education=None, skills=None, years=None, projects=None):
    return {"name": name, "phone": phone, "email": email, "city": city,
            "education": education or [], "skills": skills or [],
            "years_experience": years, "projects": projects or []}


def edu(school, major=None, degree=None, year=None):
    return {"school": school, "major": major, "degree": degree, "graduation_year": year}


def proj(name, tech=None):
    return {"name": name, "tech": tech or [], "summary": None}


# ---- 变更二：新增 20 条，每条针对一个具体失败模式 ----
NEW = [
    {  # r41 校名缩写 + 无姓名锚点：预检的主战场
        "id": "r41",
        "text": "我是河工大 2026 届的，软件工程专业，本科。电话 13900001234，邮箱 hgd2026@163.com。",
        "gold": g(phone="13900001234", email="hgd2026@163.com",
                  education=[edu("河工大", "软件工程", "本科", "2026")]),
    },
    {  # r42 技能区混入大量角色词/流程词
        "id": "r42",
        "text": ("李强，男，28 岁，杭州。电话 13712345678。5 年后端开发经验，"
                 "负责接口联调与数据库设计，熟悉 Java、Spring Boot、MySQL、Redis，"
                 "参与过需求分析和项目管理。"),
        "gold": g(name="李强", phone="13712345678", city="杭州",
                  skills=["Java", "Spring Boot", "MySQL", "Redis"], years=5),
    },
    {  # r43 项目没有名称：宁可空着，也不能自己起名
        "id": "r43",
        "text": ("姓名：孙悦。手机 18600002222。2024 年本科毕业于浙江工业大学 环境设计，"
                 "现在做 UI 设计，参与过公司内部的几个系统改版，没有具体项目名。"),
        "gold": g(name="孙悦", phone="18600002222",
                  education=[edu("浙江工业大学", "环境设计", "本科", "2024")]),
    },
    {  # r44 city 有三个来源，只能取"现居/工作地"
        "id": "r44",
        "text": ("我叫陈默，家在周口，公司总部在深圳，目前住在郑州。电话 13522223333。"
                 "2021 年本科毕业于河南财经政法大学 会计学。"),
        "gold": g(name="陈默", phone="13522223333", city="郑州",
                  education=[edu("河南财经政法大学", "会计学", "本科", "2021")]),
    },
    {  # r45 英文简历：姓名顺序、电话带国家码、学位是 B.Sc.
        "id": "r45",
        "text": ("Zhang Wei\nMale | Shanghai | +86 138 0013 8000 | zhangwei@example.com\n"
                 "Education: 2016-2020 Fudan University, B.Sc. in Computer Science\n"
                 "Skills: Python, Java, Docker, Kubernetes\n"
                 "Work: 2020-2024 backend engineer at a fintech company, 4 years."),
        "gold": g(name="Zhang Wei", phone="13800138000", email="zhangwei@example.com",
                  city="Shanghai", skills=["Python", "Java", "Docker", "Kubernetes"],
                  years=4,
                  education=[edu("Fudan University", "Computer Science", "本科", "2020")]),
    },
    {  # r46 表格型：标签和值被竖线隔开，"姓名："这种锚点不存在
        "id": "r46",
        "text": ("| 姓名 | 王浩 |\n| 手机 | 13988887777 |\n| 学历 | 硕士 |\n"
                 "| 学校 | 西安电子科技大学 |\n| 专业 | 电子与通信工程 |\n"
                 "| 毕业年份 | 2022 |\n| 技能 | MATLAB、C、Verilog |"),
        "gold": g(name="王浩", phone="13988887777", skills=["MATLAB", "C", "Verilog"],
                  education=[edu("西安电子科技大学", "电子与通信工程", "硕士", "2022")]),
    },
    {  # r47 只有教育、没有联系方式：两段学历，本科那年没写
        "id": "r47",
        "text": "赵敏，2023 年硕士毕业于南开大学 化学工程，本科就读于天津大学 应用化学。",
        "gold": g(name="赵敏",
                  education=[edu("天津大学", "应用化学", "本科", None),
                             edu("南开大学", "化学工程", "硕士", "2023")]),
    },
    {  # r48 四个项目，tech 全部要进 skills
        "id": "r48",
        "text": ("姓名：吴桐 手机：13600007777\n项目经历：\n"
                 "1. 智能客服机器人：用 Python、Rasa、Redis 实现多轮问答；\n"
                 "2. 电商推荐系统：用 Spark、Scala 做离线召回；\n"
                 "3. 数据看板：用 Vue、ECharts、MySQL；\n"
                 "4. 日志采集：用 Fluentd、Kafka、Elasticsearch。"),
        "gold": g(name="吴桐", phone="13600007777",
                  skills=["Python", "Rasa", "Redis", "Spark", "Scala", "Vue",
                          "ECharts", "MySQL", "Fluentd", "Kafka", "Elasticsearch"],
                  projects=[proj("智能客服机器人", ["Python", "Rasa", "Redis"]),
                            proj("电商推荐系统", ["Spark", "Scala"]),
                            proj("数据看板", ["Vue", "ECharts", "MySQL"]),
                            proj("日志采集", ["Fluentd", "Kafka", "Elasticsearch"])]),
    },
    {  # r49 硕士在读：本科没写毕业年份，硕士写的是"预计"
        "id": "r49",
        "text": ("姓名：郑一鸣，男，1999 年生。电话 13566667777。"
                 "现在在华中科技大学读硕士，预计 2027 年 6 月毕业，本科是武汉理工大学 自动化。"
                 "熟悉 C++、ROS、Linux。"),
        "gold": g(name="郑一鸣", phone="13566667777",
                  skills=["C++", "ROS", "Linux"],
                  education=[edu("武汉理工大学", "自动化", "本科", None),
                             edu("华中科技大学", None, "硕士", "2027")]),
    },
    {  # r50 专升本：专科和本科是两段，不能合并
        "id": "r50",
        "text": ("我叫刘洋，电话 13711119999。\n"
                 "2019-2022 郑州铁路职业技术学院 铁道机车 专科\n"
                 "2022-2024 河南理工大学 电气工程及其自动化 本科（专升本）"),
        "gold": g(name="刘洋", phone="13711119999",
                  education=[edu("郑州铁路职业技术学院", "铁道机车", "专科", "2022"),
                             edu("河南理工大学", "电气工程及其自动化", "本科", "2024")]),
    },
    {  # r51 手机号带空格、邮箱大小写混排
        "id": "r51",
        "text": ("姓名：何静。手机：159 8888 6666。邮箱：HeJing@Example.COM。现居成都。"
                 "硕士，2018 年毕业于四川大学 口腔医学。"),
        "gold": g(name="何静", phone="15988886666", email="HeJing@Example.COM",
                  city="成都",
                  education=[edu("四川大学", "口腔医学", "硕士", "2018")]),
    },
    {  # r52 姓名出现在最后一句
        "id": "r52",
        "text": ("2020 年本科毕业于东北大学 材料科学与工程，之后在沈阳做工艺工程师 4 年，"
                 "手机 13844445555。以上，孙鹏。"),
        "gold": g(name="孙鹏", phone="13844445555", city="沈阳", years=4,
                  education=[edu("东北大学", "材料科学与工程", "本科", "2020")]),
    },
    {  # r53 推荐人电话是干扰项
        "id": "r53",
        "text": ("姓名：黄磊，电话 13011112222。2020 年本科毕业于合肥工业大学 机械设计制造及其自动化。"
                 "推荐人：王教授，电话 13033334444。"),
        "gold": g(name="黄磊", phone="13011112222",
                  education=[edu("合肥工业大学", "机械设计制造及其自动化", "本科", "2020")]),
    },
    {  # r54 全文没有一个具体技术名词：skills 必须为空
        "id": "r54",
        "text": ("姓名：马青。手机 13122223333。熟悉软件开发流程、需求分析、项目管理、团队协作，"
                 "做过 3 年前端。"),
        "gold": g(name="马青", phone="13122223333", years=3),
    },
    {  # r55 海外院校 + 中英混排
        "id": "r55",
        "text": ("姓名：徐蕾。手机 13233334444。2019 年本科毕业于 University of Melbourne 会计学，"
                 "2021 年硕士毕业于 悉尼大学 金融学。现居广州。"),
        "gold": g(name="徐蕾", phone="13233334444", city="广州",
                  education=[edu("University of Melbourne", "会计学", "本科", "2019"),
                             edu("悉尼大学", "金融学", "硕士", "2021")]),
    },
    {  # r56 实习和全职要分开算：年限只算全职
        "id": "r56",
        "text": ("姓名：邓超。电话 13344445555。2023 年本科毕业，2022 年 7 月-2023 年 6 月"
                 "在字节跳动实习 11 个月，2023 年 7 月至今在杭州一家创业公司做后端开发，全职 2 年。"),
        "gold": g(name="邓超", phone="13344445555", city="杭州", years=2),
    },
    {  # r57 极简一行，"Java开发"要拆成 Java
        "id": "r57",
        "text": "王涛 13955556666 Java开发 3年",
        "gold": g(name="王涛", phone="13955556666", skills=["Java"], years=3),
    },
    {  # r58 求职意向里的角色词不能进 skills
        "id": "r58",
        "text": ("姓名：许安。手机 13666667777。求职意向：后端开发工程师。"
                 "技能：Python、Django、PostgreSQL、Redis。"
                 "2021 年本科毕业于南京理工大学 计算机科学与技术。"),
        "gold": g(name="许安", phone="13666667777",
                  skills=["Python", "Django", "PostgreSQL", "Redis"],
                  education=[edu("南京理工大学", "计算机科学与技术", "本科", "2021")]),
    },
    {  # r59 项目 tech 与 skills 重复是允许的
        "id": "r59",
        "text": ("姓名：蒋楠。手机 13777778888。\n"
                 "项目一 校园二手交易平台：Vue + Spring Boot + MySQL，负责前端与订单模块。\n"
                 "项目二 图书借阅系统：Java Swing + SQLite。"),
        "gold": g(name="蒋楠", phone="13777778888",
                  skills=["Vue", "Spring Boot", "MySQL", "Java", "Swing", "SQLite"],
                  projects=[proj("校园二手交易平台", ["Vue", "Spring Boot", "MySQL"]),
                            proj("图书借阅系统", ["Java", "Swing", "SQLite"])]),
    },
    {  # r60 本硕同校：两段 school 相同，配对必须靠 school+degree
        "id": "r60",
        "text": ("姓名：韩雪。电话 13888889999。2016-2020 武汉大学 电子信息工程 本科；"
                 "2020-2023 武汉大学 信息与通信工程 硕士。现居武汉。"),
        "gold": g(name="韩雪", phone="13888889999", city="武汉",
                  education=[edu("武汉大学", "电子信息工程", "本科", "2020"),
                             edu("武汉大学", "信息与通信工程", "硕士", "2023")]),
    },
]


def check_gold_skills(row):
    """按 v2.1 口径自检 gold，防止我自己的标注违规"""
    bad = []
    for s in row["gold"]["skills"]:
        if s in GENERIC_SKILLS:
            bad.append(f"{s}（泛化词）")
        elif len(s) > MAX_SKILL_LEN:
            bad.append(f"{s}（过长）")
        else:
            for w in GENERIC_SKILLS:
                if w != s and len(s) > len(w) and (s.endswith(w) or s.startswith(w)):
                    bad.append(f"{s}（拼接短语，应只留 {s.replace(w, '').strip()}）")
                    break
    return bad


def main():
    rows = [json.loads(l) for l in open(V2, encoding="utf-8") if l.strip()]

    print("=" * 64)
    print("  变更一：按 skills v2.1 重标")
    print("=" * 64)
    for r in rows:
        if r["id"] in SKILL_FIX:
            old = r["gold"]["skills"]
            r["gold"]["skills"] = SKILL_FIX[r["id"]]
            print(f"  {r['id']}: {old} → {SKILL_FIX[r['id']]}")

    rows += NEW

    print("\n" + "=" * 64)
    print("  自检")
    print("=" * 64)
    ids = [r["id"] for r in rows]
    dup = {i for i in ids if ids.count(i) > 1}
    print(f"  条数        : {len(rows)}（原 {len(rows) - len(NEW)} + 新增 {len(NEW)}）")
    print(f"  重复 id     : {dup or '无'}")
    missing = [r["id"] for r in rows if set(r["gold"]) != set(FIELDS)]
    print(f"  字段不完整  : {missing or '无'}")
    violations = [(r["id"], v) for r in rows for v in check_gold_skills(r)]
    print(f"  gold 违规   : {violations or '无'}")

    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n  已写入 {OUT}")


if __name__ == "__main__":
    main()
