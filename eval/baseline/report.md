# 抽取器评测报告

- 样本数：20
- schema 版本：v1.1
- 完全正确（10 字段全对）：15/20 = **75.0%**

| 字段 | 准确率 | 错误数 |
|---|---|---|
| skills | 90.0% | 2 |
| phone | 95.0% | 1 |
| email | 95.0% | 1 |
| city | 95.0% | 1 |
| graduation_year | 95.0% | 1 |
| name | 100.0% | 0 |
| school | 100.0% | 0 |
| major | 100.0% | 0 |
| degree | 100.0% | 0 |
| years_experience | 100.0% | 0 |

**skills 细项**：精确率 97.3% ｜ 召回率 98.3% ｜ F1 97.8%

- 字段平均准确率（macro）：**97.0%**

## 错误明细（6 处）

- `r04` **phone**：应留空却填了「13700001111」
- `r04` **email**：应留空却填了「hr@company.com」
- `r01` **skills**：应为 ['Spring Boot', 'MySQL', 'Redis', 'Kafka']，实际 ['Java', 'Spring Boot', 'MySQL', 'Redis', 'Kafka']
- `r08` **skills**：应为 ['Python', 'Selenium', 'JMeter']，实际 ['Python 自动化测试', 'Selenium', 'JMeter']
- `r12` **city**：漏抽（应为「苏州」）
- `r20` **graduation_year**：漏抽（应为「2027」）
