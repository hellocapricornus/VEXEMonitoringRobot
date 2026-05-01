# database.py - 完整修复版本
import os
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pytz

BEIJING = pytz.timezone("Asia/Shanghai")

# 🔧 修复：使用绝对路径，确保无论从哪个目录启动都使用同一个数据库
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "vip.db")

# ================= 线程安全的数据库连接 =================
# 使用 ThreadLocal 确保每个线程有独立的连接
_thread_local = threading.local()

def get_db_connection():
    """获取当前线程的数据库连接"""
    if not hasattr(_thread_local, "connection"):
        _thread_local.connection = sqlite3.connect(
            DB_PATH,
            check_same_thread=False,  # 允许不同线程使用不同连接
            isolation_level=None      # 自动提交模式
        )
        _thread_local.connection.row_factory = sqlite3.Row  # 返回字典形式
    return _thread_local.connection

def db_execute(sql, args=()):
    """执行SQL语句（线程安全）"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql, args)
    conn.commit()
    return cur

def now():
    return datetime.now(BEIJING)

# ================= 初始化数据库表 =================
def init_db():
    """初始化所有数据库表"""

    # ================= 套餐表 =================
    db_execute("""
        CREATE TABLE IF NOT EXISTS vip_plans (
            plan_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            days INTEGER NOT NULL,
            price REAL NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    """)

    # 插入默认套餐（如果表为空）
    existing = db_execute("SELECT COUNT(*) FROM vip_plans").fetchone()[0]
    if existing == 0:
        default_plans = [
            ("buy_1m", "1个月会员", 30, 40),
            ("buy_3m", "3个月会员", 90, 98),
            ("buy_6m", "6个月会员", 180, 160),
            ("buy_1y", "1年会员", 365, 288),
        ]
        for plan_id, name, days, price in default_plans:
            db_execute("INSERT INTO vip_plans (plan_id, name, days, price) VALUES (?, ?, ?, ?)",
                       (plan_id, name, days, price))

    # ================= 地址池表 =================
    db_execute("""
        CREATE TABLE IF NOT EXISTS vip_addresses (
            address TEXT PRIMARY KEY,
            status TEXT DEFAULT 'idle',
            added_at TEXT
        )
    """)

    # 用户表
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

    # 封禁表
    db_execute("""
    CREATE TABLE IF NOT EXISTS banned (
        user_id INTEGER PRIMARY KEY,
        reason TEXT,
        banned_at TEXT
    )
    """)

    # 管理员日志表
    db_execute("""
    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT,
        target_id INTEGER,
        timestamp TEXT
    )
    """)

    # 消息记录表
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

    # USDT 交易记录表
    db_execute("""
    CREATE TABLE IF NOT EXISTS processed_transactions (
        tx_id TEXT PRIMARY KEY,
        user_id INTEGER,
        days INTEGER,
        processed_at TEXT
    )
    """)
    logging.info("USDT 交易记录表已初始化")

    # USDT 订单表
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

    # ================= 添加缺失的列（使用 PRAGMA 更安全）=================
    columns_to_add = [
        ("users", "last_channel_check", "TEXT"),
        ("users", "needs_channel_check", "INTEGER DEFAULT 0"),
        ("users", "reminded_type", "TEXT DEFAULT NULL"),
    ]
    # 在 init_db() 的 columns_to_add 部分添加
    try:
        db_execute("ALTER TABLE usdt_orders ADD COLUMN address TEXT DEFAULT ''")
        logging.info("已添加 usdt_orders.address 字段")
    except sqlite3.OperationalError:
        pass

    for table, column, col_type in columns_to_add:
        try:
            db_execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logging.info(f"已添加列 {table}.{column}")
        except sqlite3.OperationalError:
            pass  # 列已存在，忽略错误

    logging.info("数据库表结构已更新")

    # ================= 创建索引（优化查询性能）=================
    indexes = [
        # usdt_orders 表索引
        ("idx_orders_status_created", "usdt_orders", "status, created_at"),
        ("idx_orders_plan_name", "usdt_orders", "plan_name"),
        ("idx_orders_user_id", "usdt_orders", "user_id"),
        # users 表索引
        ("idx_users_expire", "users", "expire_time"),
        ("idx_users_banned", "users", "is_banned"),
        ("idx_users_permanent", "users", "is_permanent"),
        # messages 表索引
        ("idx_messages_timestamp", "messages", "timestamp"),
        ("idx_messages_users", "messages", "from_user, to_user"),
    ]

    for idx_name, table, columns in indexes:
        try:
            db_execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})")
        except Exception as e:
            logging.warning(f"创建索引 {idx_name} 时出错: {e}")

    logging.info("数据库索引创建完成")


# ================= 辅助函数 =================
def get_pending_orders():
    """获取所有待处理的订单"""
    rows = db_execute("""
        SELECT order_id, user_id, plan_name, days, amount, created_at 
        FROM usdt_orders 
        WHERE status='pending'
    """).fetchall()
    return rows


def is_admin(user_id: int) -> bool:
    from config import ADMIN_ID
    return user_id == ADMIN_ID


def get_user(user_id: int):
    return db_execute(
        "SELECT expire_time, is_permanent, trial_start_time, is_banned FROM users WHERE user_id=?",
        (user_id,)
    ).fetchone()


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


# ================= 订单清理函数 =================
def get_retention_days(plan_name: str) -> int:
    """根据套餐名称返回保留天数"""
    retention_map = {
        "1个月会员": 35,
        "3个月会员": 100,
        "6个月会员": 200,
        "1年会员": 400,
    }

    # 精确匹配
    if plan_name in retention_map:
        return retention_map[plan_name]

    # 模糊匹配（兼容可能的变体）
    if "1个月" in plan_name:
        return 35
    elif "3个月" in plan_name:
        return 100
    elif "6个月" in plan_name:
        return 200
    elif "1年" in plan_name or "一年" in plan_name:
        return 400

    # 默认保留90天
    return 90


def clean_old_orders():
    """根据套餐类型清理不同期限的订单"""
    from datetime import datetime, timedelta
    import logging

    current = now()
    deleted_count = 0

    # 1. 清理过期订单（所有套餐统一7天）
    expired_cutoff = (current - timedelta(days=7)).isoformat()
    expired_deleted = db_execute("""
        DELETE FROM usdt_orders 
        WHERE status = 'expired' 
        AND created_at < ?
    """, (expired_cutoff,)).rowcount
    deleted_count += expired_deleted
    logging.info(f"清理过期订单: {expired_deleted} 条")

    # 2. 清理取消订单（所有套餐统一7天）
    cancelled_cutoff = (current - timedelta(days=7)).isoformat()
    cancelled_deleted = db_execute("""
        DELETE FROM usdt_orders 
        WHERE status = 'cancelled' 
        AND created_at < ?
    """, (cancelled_cutoff,)).rowcount
    deleted_count += cancelled_deleted
    logging.info(f"清理取消订单: {cancelled_deleted} 条")

    # 3. 清理支付成功的订单（根据套餐类型）
    paid_orders = db_execute("""
        SELECT order_id, plan_name, created_at 
        FROM usdt_orders 
        WHERE status = 'paid'
    """).fetchall()

    for order_id, plan_name, created_at_str in paid_orders:
        created_at = datetime.fromisoformat(created_at_str)

        retention_days = get_retention_days(plan_name)

        if retention_days:
            cutoff_date = created_at + timedelta(days=retention_days)
            if current > cutoff_date:
                db_execute("DELETE FROM usdt_orders WHERE order_id=?", (order_id,))
                deleted_count += 1
                logging.info(f"清理支付订单: {order_id} ({plan_name}), 已保留 {retention_days} 天")

    logging.info(f"总计清理订单: {deleted_count} 条")
    return deleted_count


def update_expired_pending_orders():
    from config import USDT_ORDER_TIMEOUT
    timeout_seconds = USDT_ORDER_TIMEOUT
    cutoff_time = (now() - timedelta(seconds=timeout_seconds)).isoformat()

    # ✅ 先获取要过期的订单地址，用于释放
    expired_orders = db_execute("""
        SELECT order_id, plan_name FROM usdt_orders 
        WHERE status = 'pending' AND created_at < ?
    """, (cutoff_time,)).fetchall()

    updated = db_execute("""
        UPDATE usdt_orders 
        SET status = 'expired' 
        WHERE status = 'pending' 
        AND created_at < ?
    """, (cutoff_time,)).rowcount

    if updated > 0:
        logging.info(f"已将 {updated} 个超时待处理订单标记为过期")
        # ✅ 注意：这里无法获取 address 字段（usdt_orders 表没存地址）
        # 需要先在 usdt_orders 表中添加 address 字段

    return updated

# database.py - 末尾添加

def get_active_plans():
    """获取所有启用的套餐"""
    rows = db_execute("SELECT plan_id, name, days, price FROM vip_plans WHERE is_active=1 ORDER BY price").fetchall()
    return [{"plan_id": r[0], "name": r[1], "days": r[2], "price": r[3]} for r in rows]

def get_all_plans():
    """获取所有套餐（包括禁用的）"""
    rows = db_execute("SELECT plan_id, name, days, price, is_active FROM vip_plans ORDER BY plan_id").fetchall()
    return [{"plan_id": r[0], "name": r[1], "days": r[2], "price": r[3], "is_active": r[4]} for r in rows]

def add_plan(plan_id: str, name: str, days: int, price: float):
    """添加套餐"""
    db_execute("INSERT OR IGNORE INTO vip_plans (plan_id, name, days, price) VALUES (?, ?, ?, ?)",
               (plan_id, name, days, price))

def delete_plan(plan_id: str):
    """删除套餐"""
    db_execute("DELETE FROM vip_plans WHERE plan_id=?", (plan_id,))

def toggle_plan(plan_id: str):
    """启用/禁用套餐"""
    row = db_execute("SELECT is_active FROM vip_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if row:
        new_state = 0 if row[0] else 1
        db_execute("UPDATE vip_plans SET is_active=? WHERE plan_id=?", (new_state, plan_id))

def get_available_address():
    """获取空闲地址"""
    row = db_execute("SELECT address FROM vip_addresses WHERE status='idle' LIMIT 1").fetchone()
    return row[0] if row else None

def mark_address_used(address: str):
    """标记地址已使用"""
    db_execute("UPDATE vip_addresses SET status='used' WHERE address=?", (address,))

def mark_address_idle(address: str):
    """标记地址为空闲"""
    db_execute("UPDATE vip_addresses SET status='idle' WHERE address=?", (address,))

def add_address(address: str):
    """添加收款地址"""
    db_execute("INSERT OR IGNORE INTO vip_addresses (address, status, added_at) VALUES (?, 'idle', ?)",
               (address, now().isoformat()))

def delete_address(address: str):
    """删除收款地址"""
    db_execute("DELETE FROM vip_addresses WHERE address=?", (address,))
