"""验证：temperature=0 就真的确定吗？同一个请求跑 4 次看差异"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
from extractor import SYSTEM_PROMPT, SAMPLES, make_client, parse_json
from dotenv import load_dotenv
load_dotenv()
c = make_client()
text = SAMPLES["② 口语化自我介绍"]
print("样本②原文里有没有『本科』两个字：", "本科" in text)
print("样本②原文里有没有『2027』：", "2027" in text)
print("-" * 60)
for i in range(4):
    r = c.chat.completions.create(model=os.getenv("MODEL") or "deepseek-chat",
        messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":text}],
        temperature=0.0, response_format={"type":"json_object"}, timeout=60)
    d = parse_json(r.choices[0].message.content)
    print(f"第{i+1}次: degree={d['degree']!r:8} graduation_year={d['graduation_year']!r:8} "
          f"years={d['years_experience']!r:6} skills={len(d['skills'])}项")
