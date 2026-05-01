# config.py - 添加环境变量支持（token保持原样）
import os
from dotenv import load_dotenv
load_dotenv()

# ================= 配置 =================
# 🔧 建议生产环境使用环境变量，这里保留原样
BOT_TOKEN = os.getenv("VIP_BOT_TOKEN")
ADMIN_ID = int(os.getenv("VIP_ADMIN", "0"))
GROUP_ID = int(os.getenv("VIP_GROUP", "0"))
CHANNEL_ID = int(os.getenv("VIP_CHANNEL", "0"))

# 统一使用 GROUP_ID 和 GROUP_LINK
GROUP_LINK = "https://t.me/+BjHkQhpqknczYjk5"
CHANNEL_LINK = "https://t.me/+x_Fm8Eyp-edlNjgx"

# 🔧 修复：正式环境使用正确的值
TRIAL_HOURS = int(os.environ.get("TRIAL_HOURS", "24"))  # 24小时正式
REMIND_HOURS = int(os.environ.get("REMIND_HOURS", "3"))  # 3小时正式
DELETE_DELAY = int(os.environ.get("DELETE_DELAY", "10"))  # 可以调整更长，如30秒

# ================= USDT 支付配置 =================
USDT_WALLET_ADDRESS = "TWYctLLCbvavefuCqRXxgKzS7hVe6cpbp9"
USDT_ORDER_TIMEOUT = int(os.environ.get("USDT_ORDER_TIMEOUT", "600"))  # 10分钟 = 600秒

# 套餐配置 (天数, USDT价格)
USDT_PLANS = {
    "buy_1m": ("1个月会员", 30, 40),
    "buy_3m": ("3个月会员", 90, 98),
    "buy_6m": ("6个月会员", 180, 160),
    "buy_1y": ("1年会员", 365, 288),
}

# 🔧 添加运行环境配置
ENABLE_SCHEDULER = os.environ.get("ENABLE_SCHEDULER", "true").lower() == "true"
WORKER_ID = os.environ.get("WORKER_ID", "default")
