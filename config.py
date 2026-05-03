# config.py
import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("VIP_BOT_TOKEN")
ADMIN_ID = int(os.getenv("VIP_ADMIN", "0"))


# ================= 从数据库动态读取 =================
def _get_setting(key: str, default: str) -> str:
    try:
        from database import db_execute
        row = db_execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row:
            return row[0]
    except:
        pass
    return default


def get_group_id():
    return int(_get_setting("GROUP_ID", "0"))

def get_channel_id():
    return int(_get_setting("CHANNEL_ID", "0"))

def get_trial_hours():
    return float(_get_setting("TRIAL_HOURS", "24"))

def get_remind_hours():
    return float(_get_setting("REMIND_HOURS", "3"))

def get_usdt_order_timeout():
    return int(_get_setting("USDT_ORDER_TIMEOUT", "600"))

def get_delete_delay():
    return int(_get_setting("DELETE_DELAY", "10"))

def get_group_link():
    return _get_setting("GROUP_LINK", "")

def get_channel_link():
    return _get_setting("CHANNEL_LINK", "")

def get_member_remind_days():
    return float(_get_setting("MEMBER_REMIND_DAYS", "3"))


# 兼容旧代码的默认值
GROUP_ID = 0
CHANNEL_ID = 0
TRIAL_HOURS = 24
REMIND_HOURS = 3
MEMBER_REMIND_DAYS = 3
USDT_ORDER_TIMEOUT = 600
DELETE_DELAY = 10
GROUP_LINK = ""
CHANNEL_LINK = ""
USDT_WALLET_ADDRESS = ""


def refresh_config():
    """刷新配置"""
    global GROUP_ID, CHANNEL_ID, TRIAL_HOURS, REMIND_HOURS
    global USDT_ORDER_TIMEOUT, DELETE_DELAY, GROUP_LINK, CHANNEL_LINK
    global MEMBER_REMIND_DAYS
    MEMBER_REMIND_DAYS = get_member_remind_days()

    GROUP_ID = get_group_id()
    CHANNEL_ID = get_channel_id()
    TRIAL_HOURS = get_trial_hours()
    REMIND_HOURS = get_remind_hours()
    USDT_ORDER_TIMEOUT = get_usdt_order_timeout()
    DELETE_DELAY = get_delete_delay()

    db_link = get_group_link()
    if db_link:
        GROUP_LINK = db_link
    elif GROUP_ID:
        GROUP_LINK = f"https://t.me/+{str(GROUP_ID).replace('-100', '')}"
    else:
        GROUP_LINK = ""

    db_channel_link = get_channel_link()
    if db_channel_link:
        CHANNEL_LINK = db_channel_link
    elif CHANNEL_ID:
        CHANNEL_LINK = f"https://t.me/+{str(CHANNEL_ID).replace('-100', '')}"
    else:
        CHANNEL_LINK = ""


# 启动时刷新
refresh_config()
