# config.py
import os

# ================= 配置 =================
BOT_TOKEN = "8350269629:AAGl3saDMy8M7O5OLW2jogwfp1ERkPhUrRY"
ADMIN_ID = 8107909168
GROUP_ID = -1003878983546
CHANNEL_ID = -1003539038789

# 统一使用 GROUP_ID 和 GROUP_LINK
GROUP_LINK = "https://t.me/+BjHkQhpqknczYjk5"  # 原 MONITOR_GROUP_LINK
CHANNEL_LINK = "https://t.me/+x_Fm8Eyp-edlNjgx"

TRIAL_HOURS = 24  # 24小时正式，测试用1分钟
REMIND_HOURS = 3  # 3小时正式，测试用1分钟
DELETE_DELAY = 10

# ================= USDT 支付配置 =================
USDT_WALLET_ADDRESS = "TWYctLLCbvavefuCqRXxgKzS7hVe6cpbp9"
USDT_ORDER_TIMEOUT = 600  # 10分钟 = 600秒

# 套餐配置 (天数, USDT价格)
USDT_PLANS = {
    "buy_1m": ("1个月会员", 30, 40),   # (名称, 天数, 价格)
    "buy_3m": ("3个月会员", 90, 98),
    "buy_6m": ("6个月会员", 180, 160),
    "buy_1y": ("1年会员", 365, 288),
}
