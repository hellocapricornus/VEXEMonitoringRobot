# scheduler_lock.py - 用于多 worker 环境下的定时任务锁
import os
import time
import logging
import sqlite3
from database import db_execute

class SchedulerLock:
    """简单的基于数据库的分布式锁"""

    def __init__(self, lock_name: str, timeout: int = 300):
        self.lock_name = lock_name
        self.timeout = timeout
        self._locked = False

    def acquire(self) -> bool:
        """获取锁"""
        try:
            # 清理过期锁
            db_execute("""
                DELETE FROM scheduler_locks 
                WHERE lock_name = ? AND expires_at < ?
            """, (self.lock_name, time.time()))

            # 尝试插入锁
            now_ts = time.time()
            expires_at = now_ts + self.timeout

            db_execute("""
                INSERT INTO scheduler_locks (lock_name, acquired_at, expires_at, worker_id)
                VALUES (?, ?, ?, ?)
            """, (self.lock_name, now_ts, expires_at, os.environ.get("WORKER_ID", "default")))

            self._locked = True
            logging.info(f"获取锁成功: {self.lock_name}")
            return True
        except sqlite3.IntegrityError:
            logging.debug(f"锁已被占用: {self.lock_name}")
            return False
        except Exception as e:
            logging.error(f"获取锁失败: {e}")
            return False

    def release(self):
        """释放锁"""
        if self._locked:
            db_execute("DELETE FROM scheduler_locks WHERE lock_name = ?", (self.lock_name,))
            self._locked = False
            logging.info(f"释放锁: {self.lock_name}")

# 需要在 init_db 中添加 scheduler_locks 表
def init_scheduler_locks_table():
    db_execute("""
        CREATE TABLE IF NOT EXISTS scheduler_locks (
            lock_name TEXT PRIMARY KEY,
            acquired_at REAL,
            expires_at REAL,
            worker_id TEXT
        )
    """)
