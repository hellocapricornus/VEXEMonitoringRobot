import json
import os
from datetime import datetime
import pytz

# 文件路径
MEMBER_FILE = "members.json"
PENDING_USERS_FILE = "pending_users.json"

BEIJING_TZ = pytz.timezone("Asia/Shanghai")

def fix_members():
    if not os.path.exists(MEMBER_FILE):
        print("[会员] 文件不存在，跳过")
        return

    try:
        with open(MEMBER_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        fixed = {}
        for k, v in raw_data.items():
            if isinstance(v, dict):
                fixed[int(k)] = {
                    "join_time": v.get("join_time"),
                    "expiry_time": v.get("expiry_time"),
                    "reminded": v.get("reminded", False)
                }
            else:
                # 兼容旧版：仅存时间字符串
                fixed[int(k)] = {
                    "join_time": v,
                    "expiry_time": None,
                    "reminded": False
                }

        with open(MEMBER_FILE, "w", encoding="utf-8") as f:
            json.dump(fixed, f, ensure_ascii=False, indent=2)
        print(f"[会员] 修复完成，共 {len(fixed)} 条记录")

    except Exception as e:
        print(f"[会员] 修复失败: {e}")

def fix_pending_users():
    if not os.path.exists(PENDING_USERS_FILE):
        print("[试用用户] 文件不存在，跳过")
        return

    try:
        with open(PENDING_USERS_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        fixed = {}
        for k, v in raw_data.items():
            try:
                if isinstance(v, dict):
                    join_time = v.get("join_time")
                    fixed[int(k)] = {
                        "join_time": join_time,
                        "reminded": v.get("reminded", False)
                    }
                else:
                    # 兼容旧版：仅存时间字符串
                    fixed[int(k)] = {
                        "join_time": v,
                        "reminded": False
                    }
            except Exception as e:
                print(f"[试用用户] 修复用户 {k} 失败: {e}")

        with open(PENDING_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(fixed, f, ensure_ascii=False, indent=2)
        print(f"[试用用户] 修复完成，共 {len(fixed)} 条记录")

    except Exception as e:
        print(f"[试用用户] 修复失败: {e}")

if __name__ == "__main__":
    print("🔧 正在修复数据结构...")
    fix_members()
    fix_pending_users()
    print("✅ 数据修复完成")
