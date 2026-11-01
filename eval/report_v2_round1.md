# 抽取器评测报告（schema v2.0 · 嵌套结构）

- 样本数：40
- schema 版本：v2.0
- 完全正确（8 字段全对）：27/40 = **67.5%**
- 被归属检测（上下文含联系人/家属等）拦下的记录：0 条

| 字段 | 类型 | 准确率 | 错误数 |
|---|---|---|---|
| skills | 字符串数组 | 75.0% | 10 |
| education | 对象数组 | 92.5% | 3 |
| phone | 标量 | 95.0% | 2 |
| name | 标量 | 97.5% | 1 |
| projects | 对象数组 | 97.5% | 1 |
| email | 标量 | 100.0% | 0 |
| city | 标量 | 100.0% | 0 |
| years_experience | 标量 | 100.0% | 0 |

**技能集合**：精确率 78.7% ｜ 召回率 79.2% ｜ F1 78.9%

**学历条目**：精确率 97.5% ｜ 召回率 97.5% ｜ F1 97.5%

**项目条目**：精确率 100.0% ｜ 召回率 100.0% ｜ F1 100.0%

- 字段平均准确率（macro）：**94.7%**

## 错误明细（16 处）

- `r01` **skills**：应为 ['Spring Boot', 'MySQL', 'Redis', 'Kafka']，实际 ['Java', 'Spring Boot', 'MySQL', 'Redis', 'Kafka']
- `r08` **skills**：应为 ['Python', 'Selenium', 'JMeter']，实际 ['Python 自动化测试', 'Selenium', 'JMeter']
- `r10` **phone**：漏抽（应为「13598765432」）
- `r20` **education**：条目「武汉理工大学|本科」的 graduation_year：漏抽（应为「2027」）
- `r24` **skills**：应为 []，实际 ['Python', 'XGBoost', 'Pandas']
- `r25` **skills**：应为 []，实际 ['C', 'STM32', 'MQTT']
- `r27` **skills**：应为 []，实际 ['Python', 'LangChain', 'FAISS', 'Java', 'Spring Boot', 'MySQL']
- `r29` **education**：条目「广东工业大学|本科」的 graduation_year：漏抽（应为「2026」）
- `r29` **skills**：应为 []，实际 ['Python']
- `r31` **skills**：应为 []，实际 ['Flutter', 'Dart', 'Firebase']
- `r36` **skills**：应为 []，实际 ['MATLAB', 'Simulink', 'ANSYS']
- `r32` **phone**：漏抽（应为「13911112222」）
- `r37` **skills**：应为 []，实际 ['MATLAB', 'Python', 'Shell', 'Vue', 'ECharts', 'Java', 'MySQL']
- `r33` **name**：应留空却填了「郑轻」
- `r33` **education**：漏条目「郑轻|本科」
- `r33` **skills**：应为 []，实际 ['Python', 'DeepSeek API']
