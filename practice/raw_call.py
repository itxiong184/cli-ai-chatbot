import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = "https://api.deepseek.com/chat/completions"

headers = {
    "Authorization": "Bearer " + os.getenv("API_KEY")+"xxx",
    "Content-Type": "application/json",
}

body = {
    "model": "deepseek-flash",
    "messages": [
        {"role": "system", "content": "你是一个简洁的助手。"},
        {"role": "user", "content": "用一句话解释什么是 RAG。"}
    ]
}

resp = requests.post(url, headers=headers, json=body, timeout=30)

print("状态码:", resp.status_code)
print()

if resp.status_code == 200:
    data = resp.json()
    reply = data["choices"][0]["message"]["content"]
    tokens = data["usage"]["total_tokens"]
    print("模型回复:", reply)
    print("本次花费 tokens:", tokens)
else:
    print("请求失败")
    print(resp.text)        # 失败时把服务器原话打出来，里面写着具体原因
