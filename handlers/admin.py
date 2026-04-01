import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import GROUP_ID, ADMIN_ID, CHANNEL_LINK
from database import is_admin, add_trial, add_permanent, extend_member, ban_user, unban_user, get_user, db_execute, now, save_message
from utils import kick_user, is_user_following_channel

async def cmd_add_trial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("用法: /add_trial 用户ID")
        return
    uid = int(context.args[0])
    add_trial(uid)

    # 添加试用资格后，解封用户
    try:
        await context.bot.unban_chat_member(GROUP_ID, uid)
        logging.info(f"用户 {uid} 获得试用资格，已解封")
    except Exception as e:
        logging.warning(f"解封用户 {uid} 失败: {e}")

    await update.message.reply_text(f"已为用户 {uid} 添加24小时试用")

async def cmd_add_permanent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("用法: /add_permanent 用户ID")
        return
    uid = int(context.args[0])
    add_permanent(uid)

    # 添加永久会员后，解封用户
    try:
        await context.bot.unban_chat_member(GROUP_ID, uid)
        logging.info(f"用户 {uid} 获得永久会员，已解封")
    except Exception as e:
        logging.warning(f"解封用户 {uid} 失败: {e}")

    await update.message.reply_text(f"已将用户 {uid} 设为永久会员")

async def cmd_extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("用法: /extend 用户ID 天数")
        return
    uid, days = int(context.args[0]), int(context.args[1])
    new_expire = extend_member(uid, days)

    # 延长会员后，解封用户
    try:
        await context.bot.unban_chat_member(GROUP_ID, uid)
        logging.info(f"用户 {uid} 会员已延长，已解封")
    except Exception as e:
        logging.warning(f"解封用户 {uid} 失败: {e}")

    await update.message.reply_text(f"已为用户 {uid} 延长 {days} 天，新到期时间: {new_expire.strftime('%Y-%m-%d')}")

async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("用法: /kick 用户ID [原因]")
        return
    uid = int(context.args[0])
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "管理员操作"
    await kick_user(context, uid, reason)
    await update.message.reply_text(f"已踢出并封禁用户 {uid}")

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("用法: /unban 用户ID")
        return
    uid = int(context.args[0])
    unban_user(uid)
    try:
        await context.bot.unban_chat_member(GROUP_ID, uid)
    except:
        pass
    await update.message.reply_text(f"已解封用户 {uid}")

# ================= 管理员回调 =================
async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """返回管理员菜单"""
    query = update.callback_query
    await query.answer()

    context.user_data.pop('replying_to_user', None)

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
        [InlineKeyboardButton("💎 USDT(待处理)", callback_data="admin_usdt_orders"),
         InlineKeyboardButton("📜 USDT(历史)", callback_data="admin_usdt_orders_history")],
        [InlineKeyboardButton("💬 回复用户", callback_data="admin_reply")]
    ])
    await query.edit_message_text("👑 管理员菜单", reply_markup=keyboard)

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from database import db_execute
    total_users = db_execute("SELECT COUNT(*) FROM users").fetchone()[0]
    trial_users = db_execute("SELECT COUNT(*) FROM users WHERE trial_start_time IS NOT NULL AND expire_time IS NULL AND is_permanent=0").fetchone()[0]
    paid_users = db_execute("SELECT COUNT(*) FROM users WHERE expire_time IS NOT NULL AND is_permanent=0").fetchone()[0]
    permanent = db_execute("SELECT COUNT(*) FROM users WHERE is_permanent=1").fetchone()[0]
    banned = db_execute("SELECT COUNT(*) FROM banned").fetchone()[0]
    text = f"📊 统计\n总用户: {total_users}\n试用中: {trial_users}\n付费会员: {paid_users}\n永久会员: {permanent}\n封禁: {banned}"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

async def admin_add_trial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("请回复: /add_trial 用户ID\n例如: /add_trial 123456789", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

async def admin_add_permanent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("请回复: /add_permanent 用户ID", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

async def admin_extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("请回复: /extend 用户ID 天数", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

async def admin_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("请回复: /kick 用户ID [原因]", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("请回复: /unban 用户ID", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

async def admin_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from database import db_execute
    from datetime import datetime
    rows = db_execute("SELECT user_id, expire_time, is_permanent FROM users WHERE expire_time IS NOT NULL OR is_permanent=1").fetchall()
    if not rows:
        await query.edit_message_text("暂无会员", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))
        return
    text = "📋 会员列表\n"
    for uid, exp, perm in rows[:20]:
        try:
            member = await context.bot.get_chat_member(GROUP_ID, uid)
            name = member.user.full_name
        except:
            name = "未知"
        if perm:
            text += f"• {name} ({uid}) - 永久会员\n"
        else:
            exp_date = datetime.fromisoformat(exp).strftime("%Y-%m-%d")
            text += f"• {name} ({uid}) - 到期 {exp_date}\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

async def admin_trials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from database import db_execute
    from datetime import datetime, timedelta
    from config import TRIAL_HOURS
    rows = db_execute("SELECT user_id, trial_start_time FROM users WHERE trial_start_time IS NOT NULL AND expire_time IS NULL AND is_permanent=0").fetchall()
    if not rows:
        await query.edit_message_text("暂无试用用户", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))
        return
    text = "🧪 试用用户\n"
    for uid, start in rows[:20]:
        start_time = datetime.fromisoformat(start)
        end_time = start_time + timedelta(hours=TRIAL_HOURS)
        try:
            member = await context.bot.get_chat_member(GROUP_ID, uid)
            name = member.user.full_name
        except:
            name = "未知"
        text += f"• {name} ({uid}) - 到期 {end_time.strftime('%Y-%m-%d %H:%M')}\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

async def admin_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from database import db_execute
    rows = db_execute("SELECT user_id, reason FROM banned").fetchall()
    if not rows:
        await query.edit_message_text("暂无封禁用户", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))
        return
    text = "🚫 封禁列表\n"
    for uid, reason in rows[:20]:
        text += f"• {uid} - {reason}\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]))

# ================= 管理员回复用户 =================
async def admin_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员回复用户 - 显示最近联系的用户列表"""
    query = update.callback_query
    await query.answer()

    from database import db_execute

    rows = db_execute("""
        SELECT DISTINCT from_user, MAX(timestamp) 
        FROM messages 
        WHERE to_user=? 
        GROUP BY from_user 
        ORDER BY MAX(timestamp) DESC 
        LIMIT 20
    """, (ADMIN_ID,)).fetchall()

    if not rows:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]
        ])
        await query.edit_message_text(
            "📭 暂无用户联系记录。\n\n当用户联系管理员时，会显示在这里。",
            reply_markup=keyboard
        )
        return

    buttons = []
    for row in rows:
        user_id = row[0]
        try:
            member = await context.bot.get_chat_member(GROUP_ID, user_id)
            name = member.user.full_name
        except:
            try:
                user = await context.bot.get_chat(user_id)
                name = user.full_name or user.username or str(user_id)
            except:
                name = str(user_id)

        buttons.append([InlineKeyboardButton(f"💬 {name}", callback_data=f"reply_user_{user_id}")])

    buttons.append([InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")])

    await query.edit_message_text(
        "📋 最近联系的用户：\n\n点击用户即可回复。",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def admin_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员回复用户消息 - 使用命令 /reply"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ 只有管理员可以使用此命令。")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "用法：/reply 用户ID 回复内容\n\n"
            "例如：/reply 123456 你好，有什么可以帮助你的？\n\n"
            "或者点击用户消息下方的「回复用户」按钮。"
        )
        return

    try:
        user_id = int(context.args[0])
        reply_text = " ".join(context.args[1:])

        save_message(ADMIN_ID, user_id, reply_text)

        await context.bot.send_message(
            user_id,
            f"📨 管理员回复：\n\n{reply_text}\n\n"
            f"如需继续联系，请使用 /start 后点击「联系管理员」。"
        )
        await update.message.reply_text(f"✅ 已回复用户 {user_id}")
    except ValueError:
        await update.message.reply_text("❌ 用户ID必须是数字。")
    except Exception as e:
        await update.message.reply_text(f"❌ 发送失败：{e}")

# ================= 定时任务 =================
async def check_expired(context: ContextTypes.DEFAULT_TYPE):
    """检查试用和会员到期，以及频道关注状态"""
    from datetime import datetime, timedelta
    from database import db_execute, now
    from config import TRIAL_HOURS, REMIND_HOURS, GROUP_ID, CHANNEL_LINK
    from utils import kick_user, is_user_following_channel
    from database import is_admin as check_admin
    import logging

    current = now()
    logging.info("定时任务执行：检查频道关注、试用到期、会员到期")

    # ================= 1. 检查频道关注状态 =================
    # 获取数据库中的所有用户（有记录的）
    all_users = db_execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
    logging.info(f"数据库中共有 {len(all_users)} 名用户需要检查")

    # 显示所有用户ID
    for (uid,) in all_users:
        logging.info(f"数据库中的用户: {uid}")

    for (uid,) in all_users:
        # 跳过管理员
        if check_admin(uid):
            logging.info(f"用户 {uid} 是管理员，跳过检查")
            continue

        # 检查用户是否还在群组中
        try:
            member = await context.bot.get_chat_member(GROUP_ID, uid)
            if member.status not in ["member", "administrator", "creator"]:
                logging.info(f"用户 {uid} 不在群组中，从数据库删除")
                db_execute("DELETE FROM users WHERE user_id=?", (uid,))
                continue
        except Exception as e:
            logging.info(f"用户 {uid} 不在群组中，从数据库删除: {e}")
            db_execute("DELETE FROM users WHERE user_id=?", (uid,))
            continue

        # 检查用户是否关注频道
        is_following = await is_user_following_channel(context, uid)
        logging.info(f"用户 {uid} 频道关注状态: {is_following}")

        if not is_following:
            logging.info(f"用户 {uid} 未关注频道，准备踢出群组")
            await kick_user(context, uid, "您未关注频道，请重新关注后加入")
            try:
                await context.bot.send_message(
                    uid,
                    f"❌ 您未关注我们的频道，无法继续留在群组。\n\n"
                    f"请重新关注频道后，再次申请加入群组。\n\n"
                    f"👉 {CHANNEL_LINK}"
                )
            except Exception as e:
                logging.warning(f"无法私聊用户 {uid}: {e}")

    # ================= 2. 检查试用到期 =================
    trials = db_execute("SELECT user_id, trial_start_time, trial_reminded FROM users WHERE trial_start_time IS NOT NULL AND expire_time IS NULL AND is_permanent=0").fetchall()
    for uid, start, reminded in trials:
        start_time = datetime.fromisoformat(start)
        end_time = start_time + timedelta(hours=TRIAL_HOURS)
        if current >= end_time:
            logging.info(f"用户 {uid} 试用到期，踢出群组")
            await kick_user(context, uid, "试用到期")
            db_execute("UPDATE users SET trial_start_time=NULL WHERE user_id=?", (uid,))
        elif (end_time - current) <= timedelta(hours=REMIND_HOURS) and reminded == 0:
            try:
                await context.bot.send_message(uid, f"⏰ 您的试用剩余 {REMIND_HOURS} 小时，请购买会员以继续使用。")
            except:
                pass
            db_execute("UPDATE users SET trial_reminded=1 WHERE user_id=?", (uid,))

        # ================= 3. 检查会员到期 =================
    members = db_execute("SELECT user_id, expire_time FROM users WHERE expire_time IS NOT NULL AND is_permanent=0").fetchall()
    for uid, exp in members:
        expire = datetime.fromisoformat(exp)
        if current >= expire:
            logging.info(f"用户 {uid} 会员到期，踢出群组")
            await kick_user(context, uid, "会员到期")
            db_execute("UPDATE users SET expire_time=NULL WHERE user_id=?", (uid,))
    # 函数结束的闭合括号在这里

# ================= USDT 订单管理 =================
# 注意：clean_expired_orders 函数在 user.py 中定义，这里直接导入使用
# 不需要重复定义！

async def admin_usdt_orders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员查看待处理 USDT 订单"""
    query = update.callback_query
    await query.answer()

    # 从 user.py 导入所需的函数和变量
    from handlers.user import pending_usdt_orders, clean_expired_orders
    from config import USDT_ORDER_TIMEOUT
    import time

    # 调用 user.py 中的清理函数
    clean_expired_orders()

    if not pending_usdt_orders:
        await query.edit_message_text(
            "📭 当前没有待处理的 USDT 订单。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]
            ])
        )
        return

    text = "💎 **待处理 USDT 订单**\n\n"
    for amount_key, order in pending_usdt_orders.items():
        remaining = int(USDT_ORDER_TIMEOUT - (time.time() - order["created_at"]))
        minutes = remaining // 60
        seconds = remaining % 60
        text += f"• 用户ID: `{order['user_id']}`\n"
        text += f"  套餐: {order['plan_name']}\n"
        text += f"  金额: {order['amount']} USDT\n"
        text += f"  剩余: {minutes}分{seconds}秒\n"
        text += f"  订单号: `{order['order_id']}`\n\n"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 刷新", callback_data="admin_usdt_orders")],
            [InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]
        ])
    )

async def admin_usdt_orders_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员查看 USDT 订单历史"""
    query = update.callback_query
    await query.answer()

    from database import db_execute
    from datetime import datetime

    # 获取最近的订单记录（最近20条）
    rows = db_execute("""
        SELECT order_id, user_id, plan_name, amount, status, created_at, paid_at, tx_id
        FROM usdt_orders 
        ORDER BY created_at DESC 
        LIMIT 20
    """).fetchall()

    if not rows:
        await query.edit_message_text(
            "📭 暂无订单记录。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]
            ])
        )
        return

    text = "💎 **USDT 订单历史**\n\n"
    for row in rows:
        order_id, user_id, plan_name, amount, status, created_at, paid_at, tx_id = row

        status_map = {
            "pending": ("⏳", "待支付"),
            "paid": ("✅", "已支付"),
            "expired": ("❌", "已过期"),
            "cancelled": ("🚫", "已取消")
        }
        icon, status_text = status_map.get(status, ("❓", status))

        created_time = datetime.fromisoformat(created_at).strftime("%m-%d %H:%M")
        text += f"{icon} **{plan_name}** - {amount} USDT ({status_text})\n"
        text += f"   用户: `{user_id}`\n"
        text += f"   创建: {created_time}\n"
        if status == "paid" and paid_at:
            paid_time = datetime.fromisoformat(paid_at).strftime("%m-%d %H:%M")
            text += f"   支付: {paid_time}\n"
        if tx_id:
            text += f"   交易: `{tx_id[:16]}...`\n"
        text += "\n"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 刷新", callback_data="admin_usdt_orders_history")],
            [InlineKeyboardButton("📊 待处理订单", callback_data="admin_usdt_orders")],
            [InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]
        ])
    )
