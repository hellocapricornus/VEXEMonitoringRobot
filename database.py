import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pytz

BEIJING = pytz.timezone("Asia/Shanghai")

db = sqlite3.connect("bot.db", check_same_thread=False, isolation_level=None)
db_lock = threading.Lock()

def db_execute(sql, args=()):
    with db_lock:
        cur = db.cursor()
        cur.execute(sql, args)
        db.commit()
        return cur

def now():
    return datetime.now(BEIJING)

# 初始化数据库表
def init_db():
    db_execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        expire_time TEXT,
        is_permanent INTEGER DEFAULT 0,
        trial_start_time TEXT,
        trial_reminded INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0
    )
    """)
    logging.info("数据库表 users 已初始化")

    db_execute("""
    CREATE TABLE IF NOT EXISTS banned (
        user_id INTEGER PRIMARY KEY,
        reason TEXT,
        banned_at TEXT
    )
    """)

    db_execute("""
    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT,
        target_id INTEGER,
        timestamp TEXT
    )
    """)

    db_execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user INTEGER,
        to_user INTEGER,
        message TEXT,
        timestamp TEXT,
        is_reply INTEGER DEFAULT 0
    )
    """)

    db_execute("""
    CREATE TABLE IF NOT EXISTS processed_transactions (
        tx_id TEXT PRIMARY KEY,
        user_id INTEGER,
        days INTEGER,
        processed_at TEXT
    )
    """)
    logging.info("USDT 交易记录表已初始化")

    db_execute("""
    CREATE TABLE IF NOT EXISTS usdt_orders (
        order_id TEXT PRIMARY KEY,
        user_id INTEGER,
        plan_name TEXT,
        days INTEGER,
        amount REAL,
        status TEXT,
        created_at TEXT,
        paid_at TEXT,
        tx_id TEXT
    )
    """)
    logging.info("USDT 订单记录表已初始化")

def is_admin(user_id: int) -> bool:
    from config import ADMIN_ID
    return user_id == ADMIN_ID

def get_user(user_id: int):
    return db_execute("SELECT expire_time, is_permanent, trial_start_time, is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()

def get_user_status(user_id: int) -> Tuple[bool, str]:
    """返回 (是否有效, 状态描述) - 付费会员绝对优先"""
    from config import TRIAL_HOURS
    row = get_user(user_id)
    if not row:
        return False, "未获得试用资格"

    # 优先级1: 永久会员
    if row[1] == 1:
        return True, "永久会员"

    # 优先级2: 付费会员（必须在试用期之前检查）
    if row[0]:  # expire_time
        try:
            expire = datetime.fromisoformat(row[0]).astimezone(BEIJING)
            if expire > now():
                days_left = (expire - now()).days
                if days_left > 0:
                    return True, f"会员剩余 {days_left} 天"
                else:
                    hours_left = (expire - now()).seconds // 3600
                    return True, f"会员剩余 {hours_left} 小时"
            else:
                return False, "会员已过期"
        except:
            return False, "会员已过期"

    # 优先级3: 检查封禁（只有在没有会员资格时才封禁）
    if row[3] == 1:
        return False, "被封禁"

    # 优先级4: 试用用户（只有在没有付费会员和封禁时才检查）
    if row[2]:  # trial_start_time
        try:
            trial_start = datetime.fromisoformat(row[2]).astimezone(BEIJING)
            trial_end = trial_start + timedelta(hours=TRIAL_HOURS)
            if trial_end > now():
                return True, f"试用剩余 {(trial_end-now()).seconds//3600} 小时"
            else:
                return False, "试用已结束"
        except:
            return False, "试用已结束"

    return False, "未获得试用资格"

def has_valid_membership(user_id: int) -> bool:
    """检查用户是否有有效会员资格（包括试用）"""
    is_valid, _ = get_user_status(user_id)
    return is_valid

def add_trial(user_id: int):
    """添加试用资格 - 同时清除封禁标记"""
    db_execute("""
        INSERT INTO users (user_id, trial_start_time, trial_reminded, is_banned)
        VALUES (?, ?, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET 
            trial_start_time=excluded.trial_start_time, 
            expire_time=NULL, 
            is_permanent=0, 
            is_banned=0,
            trial_reminded=0
    """, (user_id, now().isoformat()))

def add_permanent(user_id: int):
    """添加永久会员 - 同时清除封禁标记"""
    db_execute("""
        INSERT INTO users (user_id, is_permanent, expire_time, trial_start_time, is_banned)
        VALUES (?, 1, NULL, NULL, 0)
        ON CONFLICT(user_id) DO UPDATE SET 
            is_permanent=1, 
            expire_time=NULL, 
            trial_start_time=NULL, 
            is_banned=0
    """, (user_id,))

def remove_permanent(user_id: int):
    """删除永久会员资格"""
    db_execute("""
        UPDATE users SET is_permanent=0, expire_time=NULL, trial_start_time=NULL, is_banned=1
        WHERE user_id=?
    """, (user_id,))
    logging.info(f"已删除用户 {user_id} 的永久会员资格")

def extend_member(user_id: int, days: int):
    """延长会员时间 - 同时清除封禁标记和试用期"""
    from datetime import timedelta
    import logging

    row = db_execute("SELECT expire_time FROM users WHERE user_id=?", (user_id,)).fetchone()
    current = now()

    if row and row[0]:
        old_expire = datetime.fromisoformat(row[0]).astimezone(BEIJING)
        new_expire = max(old_expire, current) + timedelta(days=days)
    else:
        new_expire = current + timedelta(days=days)

    # 关键修复：强制清除所有试用相关字段
    db_execute("""
        INSERT INTO users (user_id, expire_time, is_permanent, trial_start_time, is_banned, trial_reminded)
        VALUES (?, ?, 0, NULL, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET 
            expire_time=excluded.expire_time, 
            is_permanent=0, 
            trial_start_time=NULL, 
            is_banned=0,
            trial_reminded=0
    """, (user_id, new_expire.isoformat()))

    # 验证更新
    verify = db_execute("SELECT trial_start_time, expire_time, is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    logging.info(f"extend_member 验证: trial={verify[0]}, expire={verify[1]}, banned={verify[2]}")

    return new_expire

def ban_user(user_id: int, reason: str):
    db_execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    db_execute("INSERT OR IGNORE INTO banned (user_id, reason, banned_at) VALUES (?,?,?)",
               (user_id, reason, now().isoformat()))

def unban_user(user_id: int):
    """解封用户 - 同时解封群组"""
    db_execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    db_execute("DELETE FROM banned WHERE user_id=?", (user_id,))

def delete_user_membership(user_id: int):
    """删除用户的所有会员资格（包括永久会员）"""
    db_execute("""
        UPDATE users SET 
            expire_time=NULL, 
            is_permanent=0, 
            trial_start_time=NULL, 
            is_banned=1
        WHERE user_id=?
    """, (user_id,))
    logging.info(f"已删除用户 {user_id} 的所有会员资格")
    
    # 验证是否执行成功
    row = db_execute("SELECT is_permanent, expire_time, is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    if row:
        logging.info(f"验证结果: is_permanent={row[0]}, expire_time={row[1]}, is_banned={row[2]}")

async def is_user_following_channel(context, user_id: int) -> bool:
    """检查用户是否关注了频道"""
    from config import CHANNEL_ID

    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        logging.info(f"用户 {user_id} 频道状态: {member.status}")
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except Exception as e:
        logging.error(f"检查用户 {user_id} 频道关注状态失败: {e}")
        return False

def save_message(from_user: int, to_user: int, message: str):
    """保存消息记录"""
    db_execute("""
        INSERT INTO messages (from_user, to_user, message, timestamp)
        VALUES (?, ?, ?, ?)
    """, (from_user, to_user, message, now().isoformat()))

def log_admin_action(admin_id: int, action: str, target_id: int = None):
    """记录管理员操作日志"""
    db_execute("""
        INSERT INTO admin_logs (admin_id, action, target_id, timestamp)
        VALUES (?, ?, ?, ?)
    """, (admin_id, action, target_id, now().isoformat()))
