import sqlite3
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path

def get_db_path():
    # 优先找AppData路径的生产环境数据库
    appdata_db = Path(os.environ.get("LOCALAPPDATA", "")) / "LearningDesk" / "learning_desk.db"
    if appdata_db.exists():
        return str(appdata_db)
    #  fallback到本地开发路径
    local_db = Path(__file__).parent / "src" / "data" / "learning_desk.db"
    if local_db.exists():
        return str(local_db)
    return None

def sync_learning_record():
    # 获取前一天的日期（凌晨2点同步前一天的学习记录）
    target_date = (date.today() - timedelta(days=1)).isoformat()
    db_path = get_db_path()
    
    if not db_path:
        print(f"[{date.today()}] 找不到学习数据库，同步失败")
        return
    
    try:
        # 读取学习记录
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 读任务
        cursor.execute("SELECT title, done FROM tasks WHERE task_date = ? ORDER BY id", (target_date,))
        tasks = cursor.fetchall()
        
        # 读笔记
        cursor.execute("SELECT content FROM daily_notes WHERE note_date = ?", (target_date,))
        note = cursor.fetchone()
        note_content = note[0] if note else "无"
        
        conn.close()
        
        # 整理内容
        done_tasks = [t[0] for t in tasks if t[1]]
        todo_tasks = [t[0] for t in tasks if not t[1]]
        content = f"""【{target_date} 学习记录同步】
✅ 已完成任务：
{chr(10).join(['  - ' + t for t in done_tasks]) if done_tasks else '  无'}
⏳ 未完成任务：
{chr(10).join(['  - ' + t for t in todo_tasks]) if todo_tasks else '  无'}
📝 学习收获/笔记：
{note_content}
"""
        
        # 保存到Hermes记忆库
        cmd = [
            "hermes", "memory", "add",
            "--target", "user",
            "--content", content.replace('"', '\\"')
        ]
        subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"[{date.today()}] 成功同步 {target_date} 学习记录到记忆库")
        
    except Exception as e:
        print(f"[{date.today()}] 同步失败：{str(e)}")

if __name__ == "__main__":
    sync_learning_record()
