# -*- coding: utf-8 -*-
"""
历史记录：flat(v1.1) gold -> nested(v2.0) gold 的迁移映射，附带 20 条新增样本。

注意：这是当时的迁移过程留档，不要直接重跑（会覆盖 eval/samples_v2.jsonl 里已修正的标注）。
产物在 eval/baseline/samples_v1.jsonl -> eval/samples_v2.jsonl。
"""
import json

FLAT = ["name", "phone", "email", "city", "school", "major",
        "degree", "graduation_year", "skills", "years_experience"]


def to_v2(g):
    edu = []
    if g.get("school"):
        edu.append({
            "school": g["school"],
            "major": g.get("major"),
            "degree": g.get("degree"),
            "graduation_year": g.get("graduation_year"),
        })
    return {
        "name": g.get("name"), "phone": g.get("phone"), "email": g.get("email"),
        "city": g.get("city"), "education": edu,
        "skills": g.get("skills") or [],
        "years_experience": g.get("years_experience"),
        "projects": [],
    }


rows = []
with open("eval/baseline/samples_v1.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        rows.append({"id": r["id"], "text": r["text"], "gold": to_v2(r["gold"])})

# r09 手工修正：原文有两段学历，迁移脚本只能还原一段
by_id = {r["id"]: r for r in rows}
by_id["r09"]["gold"]["education"] = [
    {"school": "中山大学", "major": "数学与应用数学", "degree": "本科", "graduation_year": "2018"},
    {"school": "中山大学", "major": "应用统计", "degree": "硕士", "graduation_year": "2021"},
]

# ---------------- 新增 20 条：专打 v1 结构撑不住的场景 ----------------
NEW = [
    ("r21", """周衡，男，苏州，18600001111，zhouheng@mail.com
教育经历：
2015.09-2018.06 苏州职业大学 计算机应用技术 专科
2018.09-2020.06 苏州科技大学 软件工程 本科
2020.09-2023.06 东南大学 软件工程 硕士
2023 年硕士毕业后在苏州一家公司做后端开发，至今 2 年。熟悉 Python、Java、MySQL、Redis。""",
     {"name": "周衡", "phone": "18600001111", "email": "zhouheng@mail.com", "city": "苏州",
      "education": [
          {"school": "苏州职业大学", "major": "计算机应用技术", "degree": "专科", "graduation_year": "2018"},
          {"school": "苏州科技大学", "major": "软件工程", "degree": "本科", "graduation_year": "2020"},
          {"school": "东南大学", "major": "软件工程", "degree": "硕士", "graduation_year": "2023"}],
      "skills": ["Python", "Java", "MySQL", "Redis"], "years_experience": 2, "projects": []}),

    ("r22", """陈立，杭州，13900001111。2019 年本科毕业于浙江工业大学计算机科学与技术。
项目经历：
1. 校园二手交易小程序：负责后端，用 Java、Spring Boot、MySQL，日活约 800。
2. 日志分析平台：用 Python、Elasticsearch、Kibana，把排障时间从 30 分钟降到 5 分钟。
技能：Java、Python、Spring Boot、MySQL、Elasticsearch。工作 6 年。""",
     {"name": "陈立", "phone": "13900001111", "email": None, "city": "杭州",
      "education": [{"school": "浙江工业大学", "major": "计算机科学与技术", "degree": "本科", "graduation_year": "2019"}],
      "skills": ["Java", "Python", "Spring Boot", "MySQL", "Elasticsearch"], "years_experience": 6,
      "projects": [
          {"name": "校园二手交易小程序", "tech": ["Java", "Spring Boot", "MySQL"], "summary": None},
          {"name": "日志分析平台", "tech": ["Python", "Elasticsearch", "Kibana"], "summary": None}]}),

    ("r23", """Zhang Wei
Beijing, China | zhangwei@example.com | 13812345678
EDUCATION
2016-2020 Beijing Institute of Technology, B.E. in Computer Science
EXPERIENCE
Backend engineer with 6 years of experience.
SKILLS: Java, Spring Boot, MySQL, Redis, Kafka
PROJECTS
Order Service: rebuilt the order pipeline with Java and Kafka, reducing latency by 40%. """,
     {"name": "Zhang Wei", "phone": "13812345678", "email": "zhangwei@example.com", "city": "Beijing",
      "education": [{"school": "Beijing Institute of Technology", "major": "Computer Science", "degree": "本科", "graduation_year": "2020"}],
      "skills": ["Java", "Spring Boot", "MySQL", "Redis", "Kafka"], "years_experience": 6,
      "projects": [{"name": "Order Service", "tech": ["Java", "Kafka"], "summary": None}]}),

    ("r24", """姓名 | 何静
电话 | 13511112222
邮箱 | hejing@test.com
学历 | 硕士
毕业院校 | 南开大学
专业 | 统计学
毕业年份 | 2021
项目 | 用户流失预警模型
技术栈 | Python、XGBoost、Pandas
工作年限 | 3 年""",
     {"name": "何静", "phone": "13511112222", "email": "hejing@test.com", "city": None,
      "education": [{"school": "南开大学", "major": "统计学", "degree": "硕士", "graduation_year": "2021"}],
      "skills": [], "years_experience": 3,
      "projects": [{"name": "用户流失预警模型", "tech": ["Python", "XGBoost", "Pandas"], "summary": None}]}),

    ("r25", """本人 2021 年毕业于合肥工业大学 物联网工程 本科。
做过的项目：智能仓储温控系统，用 C、STM32、MQTT 实现。
电话 13700008888，目前在合肥。""",
     {"name": None, "phone": "13700008888", "email": None, "city": "合肥",
      "education": [{"school": "合肥工业大学", "major": "物联网工程", "degree": "本科", "graduation_year": "2021"}],
      "skills": [], "years_experience": None,
      "projects": [{"name": "智能仓储温控系统", "tech": ["C", "STM32", "MQTT"], "summary": None}]}),

    ("r26", """推荐人：王老师，电话 13500001111，可核实工作态度。
被推荐人：许静，女，2022 年硕士毕业于湖南师范大学教育学专业。
本人电话 13500002222，在长沙某中学任教 3 年。""",
     {"name": "许静", "phone": "13500002222", "email": None, "city": "长沙",
      "education": [{"school": "湖南师范大学", "major": "教育学", "degree": "硕士", "graduation_year": "2022"}],
      "skills": [], "years_experience": 3, "projects": []}),

    ("r27", """项目：企业知识库问答系统
负责检索模块，用 Python、LangChain、FAISS，把 3 万份文档做成可检索知识库，回答准确率从 61% 提到 84%。
另一个项目：订单对账平台，用 Java、Spring Boot、MySQL，把人工核对从 4 小时压到 20 分钟。""",
     {"name": None, "phone": None, "email": None, "city": None, "education": [],
      "skills": [], "years_experience": None,
      "projects": [
          {"name": "企业知识库问答系统", "tech": ["Python", "LangChain", "FAISS"], "summary": None},
          {"name": "订单对账平台", "tech": ["Java", "Spring Boot", "MySQL"], "summary": None}]}),

    ("r28", """姓名：邓宇。电话 13600007777。
本科：2016-2020 四川大学 软件工程。
硕士在读：2024 年 9 月入学 电子科技大学 人工智能，预计 2027 年 6 月毕业。
会 Python、PyTorch。""",
     {"name": "邓宇", "phone": "13600007777", "email": None, "city": None,
      "education": [
          {"school": "四川大学", "major": "软件工程", "degree": "本科", "graduation_year": "2020"},
          {"school": "电子科技大学", "major": "人工智能", "degree": "硕士", "graduation_year": "2027"}],
      "skills": ["Python", "PyTorch"], "years_experience": None, "projects": []}),

    ("r29", """林可，2026 届本科，广东工业大学 信息工程。
2025 年 7-9 月在腾讯实习，实习期间负责「客服会话摘要」项目，用 Python 调大模型接口生成摘要，人工抽检通过率 92%。
邮箱 linke@stu.gdut.edu.cn。""",
     {"name": "林可", "phone": None, "email": "linke@stu.gdut.edu.cn", "city": None,
      "education": [{"school": "广东工业大学", "major": "信息工程", "degree": "本科", "graduation_year": "2026"}],
      "skills": [], "years_experience": None,
      "projects": [{"name": "客服会话摘要", "tech": ["Python"], "summary": None}]}),

    ("r30", """苏航，南京，2018 年本科毕业于南京航空航天大学自动化专业。
平时用 C++ 写控制算法，也用 Python 做数据处理，仿真用 MATLAB 和 Simulink，版本管理用 Git。
在南京一家制造企业做了 7 年。手机 13800009999。""",
     {"name": "苏航", "phone": "13800009999", "email": None, "city": "南京",
      "education": [{"school": "南京航空航天大学", "major": "自动化", "degree": "本科", "graduation_year": "2018"}],
      "skills": ["C++", "Python", "MATLAB", "Simulink", "Git"], "years_experience": 7, "projects": []}),

    ("r31", """董倩 15800001111
项目：校园跑腿 App
技术：Flutter、Dart、Firebase""",
     {"name": "董倩", "phone": "15800001111", "email": None, "city": None, "education": [],
      "skills": [], "years_experience": None,
      "projects": [{"name": "校园跑腿 App", "tech": ["Flutter", "Dart", "Firebase"], "summary": None}]}),

    ("r32", """姓名：赵磊。本人手机 13911112222。
紧急联系人（母亲）：13911113333。
2020 年本科毕业于太原理工大学 材料成型及控制工程，在太原工作 4 年。""",
     {"name": "赵磊", "phone": "13911112222", "email": None, "city": "太原",
      "education": [{"school": "太原理工大学", "major": "材料成型及控制工程", "degree": "本科", "graduation_year": "2020"}],
      "skills": [], "years_experience": 4, "projects": []}),

    ("r33", """我是郑轻 2027 届的，网络工程专业，本科。电话 13700001234，邮箱 xyy@test.com。
做过一个命令行 AI 对话工具，用 Python 和 DeepSeek API。""",
     {"name": None, "phone": "13700001234", "email": "xyy@test.com", "city": None,
      "education": [{"school": "郑轻", "major": "网络工程", "degree": "本科", "graduation_year": "2027"}],
      "skills": [], "years_experience": None,
      "projects": [{"name": "命令行 AI 对话工具", "tech": ["Python", "DeepSeek API"], "summary": None}]}),

    ("r34", """姓名 高远。2021 年本科毕业于郑州轻工业大学 网络工程（云计算方向）。
技能：Linux、Kubernetes、Docker、Ansible、Prometheus。
在郑州做运维 3 年，电话 13600001234。""",
     {"name": "高远", "phone": "13600001234", "email": None, "city": "郑州",
      "education": [{"school": "郑州轻工业大学", "major": "网络工程（云计算方向）", "degree": "本科", "graduation_year": "2021"}],
      "skills": ["Linux", "Kubernetes", "Docker", "Ansible", "Prometheus"], "years_experience": 3, "projects": []}),

    ("r35", """孙浩，专科毕业后专升本，2022 年本科毕业于山东理工大学 会计学。
在济南做财务 3 年，电话 13500006666。""",
     {"name": "孙浩", "phone": "13500006666", "email": None, "city": "济南",
      "education": [{"school": "山东理工大学", "major": "会计学", "degree": "本科", "graduation_year": "2022"}],
      "skills": [], "years_experience": 3, "projects": []}),

    ("r36", """姓名：王思远（Wang Siyuan）。邮箱 siyuan.wang@uni-stuttgart.de。
2019 年硕士毕业于斯图加特大学 机械工程，2021 年博士毕业于同校 车辆工程。
在德国工作 4 年，2025 年回国，现在上海。
项目：Battery Thermal Management Simulation，用 MATLAB、Simulink、ANSYS 做电池热管理仿真。""",
     {"name": "王思远", "phone": None, "email": "siyuan.wang@uni-stuttgart.de", "city": "上海",
      "education": [
          {"school": "斯图加特大学", "major": "机械工程", "degree": "硕士", "graduation_year": "2019"},
          {"school": "斯图加特大学", "major": "车辆工程", "degree": "博士", "graduation_year": "2021"}],
      "skills": [], "years_experience": 4,
      "projects": [{"name": "Battery Thermal Management Simulation", "tech": ["MATLAB", "Simulink", "ANSYS"], "summary": None}]}),

    ("r37", """姓名：白露，电话 13700007778，成都。
2020 年本科毕业于电子科技大学 通信工程。
项目：
A 项目 5G 信号覆盖仿真，用 MATLAB。
B 项目 基站日志采集脚本，用 Python、Shell。
C 项目 运维可视化看板，用 Vue、ECharts。
D 项目 内部工单系统，用 Java、MySQL。""",
     {"name": "白露", "phone": "13700007778", "email": None, "city": "成都",
      "education": [{"school": "电子科技大学", "major": "通信工程", "degree": "本科", "graduation_year": "2020"}],
      "skills": [], "years_experience": None,
      "projects": [
          {"name": "5G 信号覆盖仿真", "tech": ["MATLAB"], "summary": None},
          {"name": "基站日志采集脚本", "tech": ["Python", "Shell"], "summary": None},
          {"name": "运维可视化看板", "tech": ["Vue", "ECharts"], "summary": None},
          {"name": "内部工单系统", "tech": ["Java", "MySQL"], "summary": None}]}),

    ("r38", """姓名：顾晨。2017 年硕士毕业于大连理工大学 化学工程。
电话 13800005555，在大连工作 9 年。""",
     {"name": "顾晨", "phone": "13800005555", "email": None, "city": "大连",
      "education": [{"school": "大连理工大学", "major": "化学工程", "degree": "硕士", "graduation_year": "2017"}],
      "skills": [], "years_experience": 9, "projects": []}),

    ("r39", """姓名 罗晨，电话 13600008888。2019 年本科毕业于南京审计大学 审计学。
之后一直在苏州分公司做内审，6 年经验。
邮箱 luochen@test.com。""",
     {"name": "罗晨", "phone": "13600008888", "email": "luochen@test.com", "city": "苏州",
      "education": [{"school": "南京审计大学", "major": "审计学", "degree": "本科", "graduation_year": "2019"}],
      "skills": [], "years_experience": 6, "projects": []}),

    ("r40", """招聘方：某互联网公司，HR 邮箱 hr@example.com，电话 13000000000。
候选人：唐悦，女，1998 年生，现居武汉。
2016-2019 武汉软件工程职业学院 软件技术 专科
2019-2021 武汉纺织大学 计算机科学与技术 本科（专升本）
项目经历：
「课程直播平台」用 Vue、Node.js、MySQL 做直播与回放，支撑 2000 人同时在线。
「教学数据看板」用 Python、Pandas、ECharts 做学习行为分析。
2021 年本科毕业后在武汉做前端开发 4 年，熟悉 Vue、JavaScript、Node.js。
本人电话 13600009999。""",
     {"name": "唐悦", "phone": "13600009999", "email": None, "city": "武汉",
      "education": [
          {"school": "武汉软件工程职业学院", "major": "软件技术", "degree": "专科", "graduation_year": "2019"},
          {"school": "武汉纺织大学", "major": "计算机科学与技术", "degree": "本科", "graduation_year": "2021"}],
      "skills": ["Vue", "JavaScript", "Node.js"], "years_experience": 4,
      "projects": [
          {"name": "课程直播平台", "tech": ["Vue", "Node.js", "MySQL"], "summary": None},
          {"name": "教学数据看板", "tech": ["Python", "Pandas", "ECharts"], "summary": None}]}),
]

for rid, text, gold in NEW:
    rows.append({"id": rid, "text": text, "gold": gold})

# 顺序校验：FIELDS 必须齐
for r in rows:
    for k in ["name", "phone", "email", "city", "education", "skills", "years_experience", "projects"]:
        assert k in r["gold"], (r["id"], k)

with open("eval/samples_v2.jsonl", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print("写入 eval/samples_v2.jsonl，共", len(rows), "条")
print("其中多段学历样本：", [r["id"] for r in rows if len(r["gold"]["education"]) > 1])
print("含项目样本数：", sum(1 for r in rows if r["gold"]["projects"]))
