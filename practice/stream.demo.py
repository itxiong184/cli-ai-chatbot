import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("API_KEY"), base_url="https://api.deepseek.com")

stream = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "用 200 字介绍一下流式输出。"}],
    stream=True,                    # ← 唯一的新东西
)

for chunk in stream:                # 回信不再是 1 个对象，是一串
    piece = chunk.choices[0].delta.content   # 注意：是 delta，不是 message
    if piece:                       # ← 有些块里没有内容，必须判空
        print(piece, end="", flush=True)
print()
