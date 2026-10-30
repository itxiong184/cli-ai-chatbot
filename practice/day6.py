import json

LOG_FILE = "server.log"
ERROR_FILE = "errors.json"

def read_log():
    """读日志文件；文件不存在不崩溃，返回空列表"""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return f.readlines()
    except FileNotFoundError:
        print(f"找不到日志文件: {LOG_FILE}")
        return []

def analyze(lines):
    """统计各级别行数，返回统计字典"""
    stats = {"total": 0, "ERROR": 0, "INFO": 0, "other": 0}
    for line in lines:
        line = line.strip()
        if not line:                      # 跳过空行
            continue
        stats["total"] += 1
        parts = line.split("] ", 1)       # 按 "] " 切一刀
        if len(parts) < 2:                # 格式不对的行归入"其他"
            stats["other"] += 1
            continue
        level = parts[1].split(" ", 1)[0] # 取级别：ERROR / INFO / WARNING
        if level == "ERROR":
            stats["ERROR"] += 1
        elif level == "INFO":
            stats["INFO"] += 1
        else:
            stats["other"] += 1
    return stats

def save_errors(lines):
    """提取所有 ERROR 行，存成结构化 json"""
    errors = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split("] ", 1)
        if len(parts) < 2:
            continue
        rest = parts[1]
        if rest.split(" ", 1)[0] == "ERROR":
            errors.append({
                "time": parts[0].lstrip("["),          # 去掉行首的 [
                "message": rest.split(" ", 1)[1],      # 级别后面的消息
            })
    with open(ERROR_FILE, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)
    print(f"已保存 {len(errors)} 条错误到 {ERROR_FILE}")

def print_report(stats):
    total = stats["total"]
    rate = stats["ERROR"] / total * 100 if total > 0 else 0   # 防止除 0
    print("日志分析报告")
    print(f"总行数: {total} | 错误: {stats['ERROR']} | 正常: {stats['INFO']} | 其他: {stats['other']}")
    print(f"错误率: {rate:.1f}%")

# ===== 主流程 =====
lines = read_log()
stats = analyze(lines)
save_errors(lines)
print_report(stats)
