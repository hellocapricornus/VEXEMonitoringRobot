import logging
import random
import time
import hashlib
import json
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db_execute, now

from config import (
    TRIAL_HOURS, CHANNEL_LINK, MONITOR_GROUP_LINK, ADMIN_ID, GROUP_ID,
    USDT_WALLET_ADDRESS, USDT_ORDER_TIMEOUT, USDT_PLANS
)
from database import now, BEIJING, get_user, get_user_status, is_admin, is_user_following_channel, has_valid_membership, save_message, extend_member, unban_user, db_execute
from utils import send_temp

async def show_user_menu(update: Update, status: str, in_group: bool = True):
    """显示用户菜单"""
    keyboard = [
        [InlineKeyboardButton("🕒 查询会员时间", callback_data="user_query")],
        [InlineKeyboardButton("💰 购买会员", callback_data="user_buy_usdt")],  # 改为 USDT 支付
        [InlineKeyboardButton("📞 联系管理员", callback_data="contact_admin")]
    ]

    if not in_group:
        keyboard.insert(0, [InlineKeyboardButton("🔗 加入监听群", url=MONITOR_GROUP_LINK)])

    await update.message.reply_text(
        f"✅ {status}\n\n🎛 用户菜单",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_channel_guide(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """显示频道关注引导"""
    is_following = await is_user_following_channel(context, user_id)

    logging.info(f"用户 {user_id} 频道关注状态: {is_following}")

    if not is_following:
        # 未关注频道 -> 显示关注引导
        keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 关注频道", url=CHANNEL_LINK)],
                [InlineKeyboardButton("✅ 我已关注", callback_data="check_follow")]
            ])
        await update.message.reply_text(
            "❌ 您需要先关注我们的频道\n\n"
            "请先关注频道，然后点击「我已关注」按钮。\n\n"
            f"👉 {CHANNEL_LINK}",
            reply_markup=keyboard
        )
        return

    # 已关注频道 -> 检查用户资格状态
    is_valid, status = get_user_status(user_id)

    # 根据状态设置不同的提示文字
    if is_valid:
        if "试用" in status:
            status_text = f"🧪 {status}"
        elif "会员" in status:
            status_text = f"💎 {status}"
        else:
            status_text = f"✅ {status}"
    else:
        if "试用已结束" in status:
            status_text = "⏰ 您的试用期已结束，请购买会员后继续使用。"
        elif "会员已过期" in status:
            status_text = "⚠️ 您的会员已过期，请续费后继续使用。"
        else:
            status_text = f"❌ {status}"

    # 检查用户是否在群组中
    try:
        member = await context.bot.get_chat_member(GROUP_ID, user_id)
        in_group = member.status in ["member", "administrator", "creator"]
    except:
        in_group = False

    # 构建菜单按钮
    keyboard = [
        [InlineKeyboardButton("🔗 加入群组", url=MONITOR_GROUP_LINK)],
        [InlineKeyboardButton("🕒 查询会员时间", callback_data="user_query")],
        [InlineKeyboardButton("💰 购买会员", callback_data="user_buy_usdt")],  # 改为 USDT 支付
        [InlineKeyboardButton("📞 联系管理员", callback_data="contact_admin")]
    ]

    await update.message.reply_text(
        f"{status_text}\n\n"
        f"🎛 功能菜单",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= 用户私聊命令 =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户私聊 /start - 引导关注频道或显示菜单"""
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id

    if is_admin(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 统计", callback_data="admin_stats"),
             InlineKeyboardButton("➕ 添加临时会员", callback_data="admin_add_trial")],
            [InlineKeyboardButton("⭐ 添加永久会员", callback_data="admin_add_permanent"),
             InlineKeyboardButton("⏰ 延长会员时间", callback_data="admin_extend")],
            [InlineKeyboardButton("👢 踢出用户", callback_data="admin_kick"),
             InlineKeyboardButton("🔓 解封用户", callback_data="admin_unban")],
            [InlineKeyboardButton("📋 会员列表", callback_data="admin_members"),
             InlineKeyboardButton("🧪 试用列表", callback_data="admin_trials"),
             InlineKeyboardButton("🚫 封禁列表", callback_data="admin_banned")],
            [InlineKeyboardButton("💎 USDT订单", callback_data="admin_usdt_orders"),  # 新增
             InlineKeyboardButton("💬 回复用户", callback_data="admin_reply")]
        ])
        await update.message.reply_text("👑 管理员菜单", reply_markup=keyboard)
        return

    await show_channel_guide(update, context, user_id)

# ================= 联系管理员（保持不变）=================
async def contact_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户联系管理员"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    try:
        user = await context.bot.get_chat(user_id)
        user_name = user.full_name or user.username or str(user_id)
    except:
        user_name = str(user_id)

    await query.edit_message_text(
        "📝 请输入您要发送给管理员的消息：\n\n"
        "（直接回复此消息即可，我会帮您转达）\n\n"
        "💡 提示：请一次性发送完整消息，管理员回复后您会收到通知。",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 返回", callback_data="back_to_user_menu")]
        ])
    )

    context.user_data['waiting_for_admin_msg'] = True
    context.user_data['user_name'] = user_name

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户发送给管理员的消息（只在私聊中处理）"""
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    message_text = update.message.text

    if context.user_data.get('waiting_for_admin_msg'):
        user_name = context.user_data.get('user_name', str(user_id))

        from database import save_message
        from config import ADMIN_ID

        save_message(user_id, ADMIN_ID, message_text)

        try:
            reply_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 回复用户", callback_data=f"reply_user_{user_id}")]
            ])

            await context.bot.send_message(
                ADMIN_ID,
                f"📨 来自用户 {user_name} (ID: {user_id}) 的消息：\n\n{message_text}\n\n"
                f"💡 点击下方按钮回复该用户：",
                reply_markup=reply_keyboard
            )
            await update.message.reply_text("✅ 消息已发送给管理员，请耐心等待回复。")
        except Exception as e:
            await update.message.reply_text(f"❌ 发送失败：{e}")
            logging.error(f"转发消息给管理员失败: {e}")

        context.user_data['waiting_for_admin_msg'] = False
        context.user_data['user_name'] = None
        return

    await update.message.reply_text(
        "请先点击「联系管理员」按钮后再发送消息。\n\n"
        "使用方法：\n"
        "1. 发送 /start\n"
        "2. 点击「联系管理员」按钮\n"
        "3. 然后输入您的消息"
    )

async def reply_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员回复用户的回调"""
    query = update.callback_query
    await query.answer()

    from database import is_admin
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ 只有管理员可以使用此功能。")
        return

    try:
        user_id = int(query.data.split("_")[2])
    except:
        await query.edit_message_text("❌ 无法识别用户。")
        return

    context.user_data['replying_to_user'] = user_id

    try:
        user = await context.bot.get_chat(user_id)
        user_name = user.full_name or user.username or str(user_id)
    except:
        user_name = str(user_id)

    await query.edit_message_text(
        f"📝 正在回复用户：{user_name} (ID: {user_id})\n\n"
        "请输入您要回复的内容：\n\n"
        "（直接回复此消息即可）\n\n"
        "💡 提示：回复内容将直接发送给用户。",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 取消", callback_data="back_to_admin_menu")]
        ])
    )

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理管理员回复用户的消息"""
    if update.effective_chat.type != "private":
        return

    admin_id = update.effective_user.id

    from database import is_admin
    if not is_admin(admin_id):
        return

    replying_to = context.user_data.get('replying_to_user')

    if replying_to:
        user_id = replying_to
        reply_text = update.message.text

        from database import save_message
        from config import ADMIN_ID

        save_message(ADMIN_ID, user_id, reply_text)

        try:
            await context.bot.send_message(
                user_id,
                f"📨 管理员回复：\n\n{reply_text}\n\n"
                f"如需继续联系，请使用 /start 后点击「联系管理员」。"
            )
            await update.message.reply_text(f"✅ 已回复用户 {user_id}")

            context.user_data['replying_to_user'] = None

        except Exception as e:
            await update.message.reply_text(f"❌ 发送失败：{e}")
            logging.error(f"回复用户失败: {e}")
        return

    await update.message.reply_text(
        "请先点击「回复用户」按钮后再发送回复。\n\n"
        "使用方法：\n"
        "1. 点击用户消息下方的「回复用户」按钮\n"
        "2. 然后输入回复内容\n\n"
        "或者使用命令：/reply 用户ID 回复内容"
    )

# ================= 用户回调 =================
async def check_follow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """检查用户是否真的关注了频道"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    is_following = await is_user_following_channel(context, user_id)
    logging.info(f"check_follow: 用户 {user_id} 关注状态: {is_following}")

    if not is_following:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 关注频道", url=CHANNEL_LINK)],
            [InlineKeyboardButton("🔄 我已关注", callback_data="check_follow")]
        ])
        await query.edit_message_text(
            "❌ 检测到您还没有关注频道！\n\n"
            "请先点击下方按钮关注频道，关注后再点击「我已关注」。\n\n"
            "👉 关注后请等待几秒钟再点击确认。",
            reply_markup=keyboard
        )
        return

    is_valid, status = get_user_status(user_id)

    if is_valid:
        if "试用" in status:
            status_text = f"🧪 {status}"
        elif "会员" in status:
            status_text = f"💎 {status}"
        else:
            status_text = f"✅ {status}"
    else:
        if "试用已结束" in status:
            status_text = "⏰ 您的试用期已结束，请购买会员后继续使用。"
        elif "会员已过期" in status:
            status_text = "⚠️ 您的会员已过期，请续费后继续使用。"
        else:
            status_text = f"❌ {status}"

    try:
        member = await context.bot.get_chat_member(GROUP_ID, user_id)
        in_group = member.status in ["member", "administrator", "creator"]
    except:
        in_group = False

    keyboard = [
        [InlineKeyboardButton("🔗 加入群组", url=MONITOR_GROUP_LINK)],
        [InlineKeyboardButton("🕒 查询会员时间", callback_data="user_query")],
        [InlineKeyboardButton("💰 购买会员", callback_data="user_buy_usdt")],
        [InlineKeyboardButton("📞 联系管理员", callback_data="contact_admin")]
    ]

    await query.edit_message_text(
        f"{status_text}\n\n"
        f"🎛 功能菜单",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def user_query_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查询会员剩余时间"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    is_following = await is_user_following_channel(context, user_id)

    if not is_following:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 关注频道", url=CHANNEL_LINK)],
            [InlineKeyboardButton("🔄 重新检查", callback_data="check_follow")]
        ])
        await query.edit_message_text(
            "❌ 检测到您没有关注频道！\n\n"
            "请先关注频道后重新查询。",
            reply_markup=keyboard
        )
        return

    is_valid, status = get_user_status(user_id)

    if is_valid:
        row = get_user(user_id)
        if row and row[1] == 1:
            text = "🎉 您拥有永久会员，无时间限制。"
        elif row and row[0]:
            expire = datetime.fromisoformat(row[0]).astimezone(BEIJING)
            if expire > now():
                remain = expire - now()
                days = remain.days
                hours = remain.seconds // 3600
                minutes = (remain.seconds % 3600) // 60
                text = f"⏰ 会员剩余时间: {days}天 {hours}小时 {minutes}分钟"
            else:
                text = "⚠️ 您的会员已过期，请购买续期。"
        elif row and row[2]:
            trial_start = datetime.fromisoformat(row[2]).astimezone(BEIJING)
            trial_end = trial_start + timedelta(hours=TRIAL_HOURS)
            if trial_end > now():
                remain = trial_end - now()
                hours = remain.seconds // 3600
                minutes = (remain.seconds % 3600) // 60
                text = f"🧪 试用剩余时间: {hours}小时 {minutes}分钟"
            else:
                text = "❌ 试用已结束，请购买会员。"
        else:
            text = status
    else:
        if "试用已结束" in status:
            text = "⏰ 您的试用期已结束，请购买会员后继续使用。"
        elif "会员已过期" in status:
            text = "⚠️ 您的会员已过期，请续费后继续使用。"
        else:
            text = f"❌ {status}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ 返回菜单", callback_data="back_to_user_menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard)

async def back_to_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """返回用户菜单"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    is_following = await is_user_following_channel(context, user_id)

    if not is_following:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 关注频道", url=CHANNEL_LINK)],
            [InlineKeyboardButton("✅ 我已关注", callback_data="check_follow")]
        ])
        await query.edit_message_text(
            "❌ 您需要先关注我们的频道\n\n"
            "请先关注频道，然后点击「我已关注」按钮。\n\n"
            f"👉 {CHANNEL_LINK}",
            reply_markup=keyboard
        )
        return

    is_valid, status = get_user_status(user_id)

    if is_valid:
        if "试用" in status:
            status_text = f"🧪 {status}"
        elif "会员" in status:
            status_text = f"💎 {status}"
        else:
            status_text = f"✅ {status}"
    else:
        if "试用已结束" in status:
            status_text = "⏰ 您的试用期已结束，请购买会员后继续使用。"
        elif "会员已过期" in status:
            status_text = "⚠️ 您的会员已过期，请续费后继续使用。"
        else:
            status_text = f"❌ {status}"

    keyboard = [
        [InlineKeyboardButton("🔗 加入群组", url=MONITOR_GROUP_LINK)],
        [InlineKeyboardButton("🕒 查询会员时间", callback_data="user_query")],
        [InlineKeyboardButton("💰 购买会员", callback_data="user_buy_usdt")],
        [InlineKeyboardButton("📞 联系管理员", callback_data="contact_admin")]
    ]

    await query.edit_message_text(
        f"{status_text}\n\n"
        f"🎛 功能菜单",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """重新开始"""
    query = update.callback_query
    await query.answer()
    await start(update, context)

# ================= USDT 支付 =================

pending_usdt_orders = {}

async def check_usdt_transaction(amount: float) -> dict:
    """通过 TronGrid API 查询 USDT 交易是否到账"""
    try:
        url = f"https://api.trongrid.io/v1/accounts/{USDT_WALLET_ADDRESS}/transactions/trc20"
        params = {
            "limit": 50,
            "only_confirmed": True
        }

        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            transactions = data.get("data", [])

            for tx in transactions:
                if tx.get("type") == "Transfer" and tx.get("token_info", {}).get("symbol") == "USDT":
                    tx_amount = float(tx.get("value", 0)) / 1000000
                    to_address = tx.get("to")

                    if abs(tx_amount - amount) < 0.01 and to_address == USDT_WALLET_ADDRESS:
                        tx_id = tx.get("transaction_id")
                        if not is_transaction_processed(tx_id):
                            return {"success": True, "tx_id": tx_id, "amount": tx_amount}

            return {"success": False, "message": "未找到匹配交易"}
        else:
            return {"success": False, "message": "API 请求失败"}

    except Exception as e:
        logging.error(f"查询 USDT 交易失败: {e}")
        return {"success": False, "message": str(e)}

def is_transaction_processed(tx_id: str) -> bool:
    """检查交易是否已经处理过"""
    row = db_execute("SELECT 1 FROM processed_transactions WHERE tx_id=?", (tx_id,)).fetchone()
    return row is not None

def mark_transaction_processed(tx_id: str, user_id: int, days: int):
    """标记交易已处理"""
    db_execute("""
        INSERT INTO processed_transactions (tx_id, user_id, days, processed_at)
        VALUES (?, ?, ?, ?)
    """, (tx_id, user_id, days, now().isoformat()))

def init_usdt_table():
    """初始化 USDT 交易记录表"""
    db_execute("""
        CREATE TABLE IF NOT EXISTS processed_transactions (
            tx_id TEXT PRIMARY KEY,
            user_id INTEGER,
            days INTEGER,
            processed_at TEXT
        )
    """)
    logging.info("USDT 交易记录表已初始化")

async def user_buy_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """USDT 购买会员 - 显示套餐"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    is_following = await is_user_following_channel(context, user_id)
    if not is_following:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 关注频道", url=CHANNEL_LINK)],
            [InlineKeyboardButton("🔄 重新检查", callback_data="check_follow")]
        ])
        await query.edit_message_text(
            "❌ 检测到您没有关注频道！\n\n请先关注频道后再购买会员。",
            reply_markup=keyboard
        )
        return

    keyboard = []
    for plan_id, (name, days, price) in USDT_PLANS.items():
        keyboard.append([InlineKeyboardButton(f"{name} - {price} USDT", callback_data=f"usdt_plan_{plan_id}")])
    keyboard.append([InlineKeyboardButton("◀️ 返回", callback_data="back_to_user_menu")])

    await query.edit_message_text(
        "💎 **购买会员（USDT 支付）**\n\n"
        "请选择套餐，支付使用 **USDT (TRC20 网络)**：\n\n"
        "💡 选择后我会生成一个**专属转账金额**，请按精确金额转账。\n"
        "⏰ 请在 **10分钟** 内完成支付，超时需重新获取金额。",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def usdt_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户选择套餐，生成唯一金额订单"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    plan_id = query.data.replace("usdt_plan_", "")

    if plan_id not in USDT_PLANS:
        return

    name, days, base_price = USDT_PLANS[plan_id]

    # 清理该用户的旧订单
    for amount_str, order in list(pending_usdt_orders.items()):
        if order["user_id"] == user_id:
            # 将旧订单标记为取消
            old_order = pending_usdt_orders[amount_str]
            db_execute("""
                UPDATE usdt_orders 
                SET status='cancelled' 
                WHERE order_id=?
            """, (old_order["order_id"],))
            del pending_usdt_orders[amount_str]

    # 生成唯一金额
    random_cents = random.randint(1, 99)
    unique_amount = base_price + random_cents / 100
    order_id = f"{user_id}_{int(time.time())}_{random_cents}"
    amount_key = f"{unique_amount:.2f}"

    # 存储到内存
    pending_usdt_orders[amount_key] = {
        "order_id": order_id,
        "user_id": user_id,
        "days": days,
        "amount": unique_amount,
        "plan_name": name,
        "plan_id": plan_id,
        "status": "pending",
        "created_at": time.time()
    }

    # 存储到数据库
    db_execute("""
        INSERT INTO usdt_orders (order_id, user_id, plan_name, days, amount, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (order_id, user_id, name, days, unique_amount, now().isoformat()))

    # 清理过期订单
    clean_expired_orders()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ 我已支付", callback_data=f"check_usdt_{amount_key}")],
        [InlineKeyboardButton("❌ 取消订单", callback_data="back_to_user_menu")]
    ])

    await query.edit_message_text(
        f"💎 **{name}** - {unique_amount} USDT\n\n"
        f"📌 **转账信息**\n"
        f"网络：**TRC20**\n"
        f"地址：`{USDT_WALLET_ADDRESS}`\n"
        f"金额：**{unique_amount} USDT**\n\n"
        f"📝 **订单号**：`{order_id}`\n\n"
        f"⚠️ **重要提示**\n"
        f"1. 请转账**精确金额** `{unique_amount} USDT`\n"
        f"2. 必须使用 **TRC20** 网络\n"
        f"3. 转账后点击「我已支付」\n"
        f"4. ⏰ **请在 10 分钟内完成支付**\n\n"
        f"💡 转账完成后，系统会自动检测并开通会员。",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

def clean_expired_orders():
    """清理超时订单"""
    from config import USDT_ORDER_TIMEOUT
    import time
    import logging
    
    current_time = time.time()
    expired_keys = []
    for amount_key, order in pending_usdt_orders.items():
        if current_time - order["created_at"] > USDT_ORDER_TIMEOUT:
            expired_keys.append(amount_key)
            # 更新数据库中的订单状态为 expired
            from database import db_execute
            db_execute("""
                UPDATE usdt_orders 
                SET status='expired' 
                WHERE order_id=? AND status='pending'
            """, (order["order_id"],))
    for key in expired_keys:
        del pending_usdt_orders[key]
        logging.info(f"清理过期订单: {key}")

async def check_usdt_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户点击「我已支付」，检查订单状态"""
    query = update.callback_query
    await query.answer()

    amount_key = query.data.replace("check_usdt_", "")

    clean_expired_orders()

    if amount_key not in pending_usdt_orders:
        await query.edit_message_text(
            "❌ 订单不存在或已过期，请重新购买。\n\n"
            "⏰ 订单有效期为 10 分钟，超时需重新获取金额。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 重新购买", callback_data="user_buy_usdt")]
            ])
        )
        return

    order = pending_usdt_orders[amount_key]
    user_id = order["user_id"]

    if user_id != query.from_user.id:
        await query.answer("这不是您的订单！", show_alert=True)
        return

    if time.time() - order["created_at"] > USDT_ORDER_TIMEOUT:
        del pending_usdt_orders[amount_key]
        await query.edit_message_text(
            "⏰ 订单已超时（超过10分钟），请重新购买。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 重新购买", callback_data="user_buy_usdt")]
            ])
        )
        return

    await query.edit_message_text(
        f"⏳ 正在检测转账...\n\n"
        f"金额：{order['amount']} USDT\n"
        f"请稍等，这可能需要几秒钟。",
        reply_markup=None
    )

    result = await check_usdt_transaction(order["amount"])

    if result["success"]:
        new_expire = extend_member(user_id, order["days"])
        unban_user(user_id)

        # 更新数据库中的订单状态为 paid
        db_execute("""
            UPDATE usdt_orders 
            SET status='paid', paid_at=?, tx_id=?
            WHERE order_id=?
        """, (now().isoformat(), result["tx_id"], order["order_id"]))

        # 标记交易已处理
        mark_transaction_processed(result["tx_id"], user_id, order["days"])

        # 解封群组
        try:
            await context.bot.unban_chat_member(GROUP_ID, user_id)
        except:
            pass

        # 删除内存中的订单
        del pending_usdt_orders[amount_key]

        await query.edit_message_text(
            f"✅ **支付成功！**\n\n"
            f"套餐：{order['plan_name']}\n"
            f"金额：{order['amount']} USDT\n"
            f"会员到期时间：{new_expire.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"感谢您的支持！",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 加入群组", url=MONITOR_GROUP_LINK)],
                [InlineKeyboardButton("📊 查看状态", callback_data="user_query")],
                [InlineKeyboardButton("◀️ 返回菜单", callback_data="back_to_user_menu")]
            ]),
            parse_mode="Markdown"
        )
    else:
        remaining_time = int(USDT_ORDER_TIMEOUT - (time.time() - order["created_at"]))
        minutes = remaining_time // 60
        seconds = remaining_time % 60

        await query.edit_message_text(
            f"⏳ 未检测到 {order['amount']} USDT 的转账记录\n\n"
            f"请确认：\n"
            f"1. 已转账**精确金额** {order['amount']} USDT\n"
            f"2. 使用的是 **TRC20** 网络\n"
            f"3. 转账已完成（需要约 1-3 分钟确认）\n\n"
            f"⏰ 订单剩余时间：{minutes}分{seconds}秒\n\n"
            f"确认无误后请稍后再次点击「我已支付」。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 重新检测", callback_data=f"check_usdt_{amount_key}")],
                [InlineKeyboardButton("📞 联系管理员", callback_data="contact_admin")],
                [InlineKeyboardButton("❌ 取消订单", callback_data="back_to_user_menu")]
            ])
        )
