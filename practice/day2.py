#一、第一题
docs = ["合同.pdf","财报.pdf","规章制度.pdf"]
print(docs[0])#1
print(docs[-1])#2
#打印前两个文档（用切片）
print(docs[0:2])#3
docs.append("员工手册.pdf")#4
print(docs)
#二、第二题
for i in docs:
    print(f"文档：{i}",end=" ")
print()
if("年报.pdf" in docs):
    print("年报.pdf在库中")
else:
    print("年报.pdf不在库中")
#三、第三题
chunk = {"id":1,"text":"RAG是检索增强生成","page":3}
print(chunk["text"])
print(chunk.get("score",0.0))
chunk["source"]="入门手册.pdf"
print(chunk)
#四、第四题
for x,y in chunk.items():
    print(f"{x}：{y}")
#五、第五题
students = [
    {"name":"小明","score":"92"},
    {"name":"小红","score":"88"},
    {"name":"小刚","score":"95"}
]
best_score=0
for i in students:
    print(f"姓名：{i["name"]} 分数：{i["score"]}")
    if(int(i["score"]) > best_score):
        best_score = int(i["score"])
print(best_score)
#六、第六题
messages=[]
def add_messages(role,content):
    messages.append({"role": role, "content": content})

# 示例用法
add_messages("system", "你是简洁的助手")
add_messages("user", "什么是RAG")
add_messages("assistant", "RAG是检索增强生成")
print(messages)
