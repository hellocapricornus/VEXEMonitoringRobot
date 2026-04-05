from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import GROUP_ID, ADMIN_ID, CHANNEL_LINK
from database import is_admin, add_trial, add_permanent, extend_member, ban_user, unban_user, get_user, db_execute, now, save_message, remove_permanent, delete_user_membership, log_admin_action
from utils import kick_user, is_user_following_channel
import logging

async def cmd_add_trial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("用法: /add_trial 用户ID")
        return
    uid = int(context.args[0])

    # 添加试用资格
    add_trial(uid)

    # 只在用户被封禁时才解封
    try:
        member = await context.bot.get_chat_member(GROUP_ID, uid)
        if member.status in ["left", "kicked"]:
            await context.bot.unban_chat_member(GROUP_ID, uid)
            logging.info(f"用户 {uid} 已解封")
    except Exception as e:
        logging.warning(f"解封用户 {uid} 失败: {e}")

    log_admin_action(update.effective_user.id, "add_trial", uid)
    await update.message.reply_text(f"✅ 已为用户 {uid} 添加24小时试用并解封")

async def cmd_add_permanent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("用法: /add_permanent 用户ID")
        return
    uid = int(context.args[0])

    # 添加永久会员
    add_permanent(uid)

    # 只在用户被封禁时才解封
    try:
        member = await context.bot.get_chat_member(GROUP_ID, uid)
        if member.status in ["left", "kicked"]:
            await context.bot.unban_chat_member(GROUP_ID, uid)
            logging.info(f"用户 {uid} 已解封")
    except Exception as e:
        logging.warning(f"解封用户 {uid} 失败: {e}")

    log_admin_action(update.effective_user.id, "add_permanent", uid)
    await update.message.reply_text(f"✅ 已将用户 {uid} 设为永久会员并解封")

async def cmd_extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("用法: /extend 用户ID 天数")
        return
    uid, days = int(context.args[0]), int(context.args[1])

    logging.info(f"=== 执行 extend 命令 ===")
    logging.info(f"用户ID: {uid}, 天数: {days}")

    # 查看执行前的数据
    before = db_execute("SELECT expire_time, trial_start_time, is_permanent, is_banned FROM users WHERE user_id=?", (uid,)).fetchone()
    logging.info(f"执行前: expire={before[0] if before else None}, trial={before[2] if before else None}")

    # 延长会员时间
    new_expire = extend_member(uid, days)

    # 查看执行后的数据
    after = db_execute("SELECT expire_time, trial_start_time, is_permanent, is_banned FROM users WHERE user_id=?", (uid,)).fetchone()
    logging.info(f"执行后: expire={after[0] if after else None}, trial={after[2] if after else None}")

    # 验证用户状态
    from database import get_user_status
    is_valid, status = get_user_status(uid)
    logging.info(f"执行后用户状态: is_valid={is_valid}, status={status}")

    # 关键修复：只解封被封禁的用户，不要对在群组中的用户调用 unban
    try:
        # 先检查用户是否在群组中
        member = await context.bot.get_chat_member(GROUP_ID, uid)
        if member.status in ["left", "kicked"]:
            # 用户不在群组或被封禁，才尝试解封
            await context.bot.unban_chat_member(GROUP_ID, uid)
            logging.info(f"用户 {uid} 已被解封")
        else:
            logging.info(f"用户 {uid} 已在群组中，跳过解封操作")
    except Exception as e:
        logging.warning(f"检查/解封用户 {uid} 失败: {e}")

    # 记录日志
    log_admin_action(update.effective_user.id, "extend", uid)

    await update.message.reply_text(
        f"✅ 已为用户 {uid} 延长 {days} 天\n"
        f"新到期时间: {new_expire.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"当前状态: {status}"
    )
    
async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("用法: /kick 用户ID [原因]")
        return
    uid = int(context.args[0])
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "管理员操作"

    # 记录日志
    log_admin_action(update.effective_user.id, "kick", uid)

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

    log_admin_action(update.effective_user.id, "unban", uid)
    await update.message.reply_text(f"已解封用户 {uid}")

# ================= 新增：删除会员功能 =================
async def cmd_delete_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """删除用户的所有会员资格（包括永久会员）"""
    logging.info("=== DELETE_MEMBER 命令被触发 ===")
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 1:
        await update.message.reply_text("用法: /delete_member 用户ID")
        return
    uid = int(context.args[0])

    logging.info(f"=== 执行 delete_member 命令 ===, 用户ID: {uid}")

    # 先查看用户当前状态
    before = db_execute("SELECT is_permanent, expire_time, is_banned FROM users WHERE user_id=?", (uid,)).fetchone()
    logging.info(f"删除前: is_permanent={before[0] if before else None}, expire={before[1] if before else None}, is_banned={before[2] if before else None}")

    # 删除所有会员资格
    delete_user_membership(uid)

    # 查看删除后状态
    after = db_execute("SELECT is_permanent, expire_time, is_banned FROM users WHERE user_id=?", (uid,)).fetchone()
    logging.info(f"删除后: is_permanent={after[0] if after else None}, expire={after[1] if after else None}, is_banned={after[2] if after else None}")

    # 踢出群组并封禁
    try:
        await context.bot.ban_chat_member(GROUP_ID, uid)
        logging.info(f"已从群组封禁用户 {uid}")
    except Exception as e:
        logging.warning(f"封禁用户 {uid} 失败: {e}")

    log_admin_action(update.effective_user.id, "delete_member", uid)
    await update.message.reply_text(f"✅ 已删除用户 {uid} 的所有会员资格并封禁")

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
        [InlineKeyboardButton("📢 广播消息", callback_data="admin_broadcast")],
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
    trial_users = db_execute("SELECT COUNT(*) FROM users WHERE trial_start_time IS NOT NULL AND expire_time IS NULL AND is_permanent=0 AND is_banned=0").fetchone()[0]
    paid_users = db_execute("SELECT COUNT(*) FROM users WHERE expire_time IS NOT NULL AND is_permanent=0 AND is_banned=0").fetchone()[0]
    permanent = db_execute("SELECT COUNT(*) FROM users WHERE is_permanent=1 AND is_banned=0").fetchone()[0]
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

# 新增：删除会员回调
async def admin_delete_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚠️ **删除会员功能**\n\n"
        "此操作将：\n"
        "1. 删除用户的所有会员资格（包括永久会员）\n"
        "2. 将用户封禁\n"
        "3. 踢出群组\n\n"
        "请回复: /delete_member 用户ID\n"
        "例如: /delete_member 123456789\n\n"
        "⚠️ 此操作不可撤销！",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")]]),
        parse_mode="Markdown"
    )

async def admin_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from database import db_execute
    from datetime import datetime
    rows = db_execute("SELECT user_id, expire_time, is_permanent FROM users WHERE (expire_time IS NOT NULL OR is_permanent=1) AND is_banned=0").fetchall()
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
    rows = db_execute("SELECT user_id, trial_start_time FROM users WHERE trial_start_time IS NOT NULL AND expire_time IS NULL AND is_permanent=0 AND is_banned=0").fetchall()
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

# ================= 广播消息功能 =================
async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """广播消息回调"""
    query = update.callback_query
    await query.answer()

    context.user_data['broadcast_mode'] = True
    await query.edit_message_text(
        "📢 **广播消息**\n\n"
        "请输入要广播的消息内容：\n\n"
        "⚠️ 此消息将发送给所有用户（包括试用、会员、永久会员）\n"
        "⚠️ 广播可能需要一些时间，请耐心等待\n\n"
        "回复 /cancel 取消广播",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 取消", callback_data="back_to_admin_menu")]
        ])
    )

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理广播消息"""
    if not is_admin(update.effective_user.id):
        return

    if not context.user_data.get('broadcast_mode'):
        return

    if update.message.text == "/cancel":
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("✅ 已取消广播")
        return

    broadcast_text = update.message.text
    user_id = update.effective_user.id

    await update.message.reply_text("⏳ 正在发送广播消息，请稍候...")

    # 获取所有用户
    from database import db_execute
    users = db_execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()

    success_count = 0
    fail_count = 0

    for (uid,) in users:
        try:
            await context.bot.send_message(
                uid,
                f"📢 **系统广播**\n\n{broadcast_text}\n\n"
                f"——————————\n"
                f"💡 如需帮助，请发送 /start"
            )
            success_count += 1
            await asyncio.sleep(0.05)  # 避免触发频率限制
        except Exception as e:
            fail_count += 1
            logging.warning(f"广播给用户 {uid} 失败: {e}")

    context.user_data['broadcast_mode'] = False

    # 记录日志
    log_admin_action(user_id, f"broadcast: {broadcast_text[:50]}...")

    await update.message.reply_text(
        f"✅ 广播完成！\n\n"
        f"成功: {success_count} 人\n"
        f"失败: {fail_count} 人"
    )

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

    # ================= 1. 检查频道关注状态（只踢出不封禁）=================
    all_users = db_execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()

    for (uid,) in all_users:
        if check_admin(uid):
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

        # 检查频道关注（只踢出不封禁，让用户可以重新申请）
        is_following = await is_user_following_channel(context, uid)
        if not is_following:
            logging.info(f"用户 {uid} 未关注频道，准备踢出群组（不封禁）")
            try:
                await context.bot.ban_chat_member(GROUP_ID, uid)
                await context.bot.unban_chat_member(GROUP_ID, uid)  # 只踢出不封禁
                logging.info(f"已踢出用户 {uid}（未封禁）")
            except Exception as e:
                logging.error(f"踢出用户 {uid} 失败: {e}")

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
    trials = db_execute("SELECT user_id, trial_start_time, trial_reminded FROM users WHERE trial_start_time IS NOT NULL AND expire_time IS NULL AND is_permanent=0 AND is_banned=0").fetchall()
    for uid, start, reminded in trials:
        start_time = datetime.fromisoformat(start)
        end_time = start_time + timedelta(hours=TRIAL_HOURS)

        if current >= end_time:
            logging.info(f"用户 {uid} 试用到期，准备封禁并踢出")
            await kick_user(context, uid, "试用到期", ban=True)
            db_execute("UPDATE users SET trial_start_time=NULL, is_banned=1 WHERE user_id=?", (uid,))
        elif (end_time - current) <= timedelta(hours=REMIND_HOURS) and reminded == 0:
            try:
                await context.bot.send_message(
                    uid, 
                    f"⏰ **试用即将到期**\n\n您的试用剩余 {REMIND_HOURS} 小时，请购买会员以继续使用。\n\n发送 /start 查看购买选项。"
                )
            except:
                pass
            db_execute("UPDATE users SET trial_reminded=1 WHERE user_id=?", (uid,))

    # ================= 3. 检查会员到期 =================
    members = db_execute("SELECT user_id, expire_time FROM users WHERE expire_time IS NOT NULL AND is_permanent=0 AND is_banned=0").fetchall()
    for uid, exp in members:
        expire = datetime.fromisoformat(exp)

        if current >= expire:
            logging.info(f"用户 {uid} 会员到期，准备封禁并踢出")
            await kick_user(context, uid, "会员到期", ban=True)
            db_execute("UPDATE users SET expire_time=NULL, is_banned=1 WHERE user_id=?", (uid,))
        elif (expire - current) <= timedelta(days=3):
            reminded = db_execute("SELECT trial_reminded FROM users WHERE user_id=?", (uid,)).fetchone()
            if reminded and reminded[0] == 0:
                days_left = (expire - current).days
                try:
                    await context.bot.send_message(
                        uid,
                        f"⏰ **会员即将到期**\n\n您的会员还剩 {days_left} 天到期，请及时续费。\n\n发送 /start 查看续费选项。"
                    )
                    db_execute("UPDATE users SET trial_reminded=1 WHERE user_id=?", (uid,))
                except:
                    pass

async def admin_usdt_orders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员查看待处理 USDT 订单 - 添加手动确认按钮"""
    query = update.callback_query
    await query.answer()

    from handlers.user import pending_usdt_orders, clean_expired_orders
    from config import USDT_ORDER_TIMEOUT
    import time

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
    buttons = []

    for amount_key, order in pending_usdt_orders.items():
        remaining = int(USDT_ORDER_TIMEOUT - (time.time() - order["created_at"]))
        minutes = remaining // 60
        seconds = remaining % 60
        text += f"• 用户ID: `{order['user_id']}`\n"
        text += f"  套餐: {order['plan_name']}\n"
        text += f"  金额: {order['amount']} USDT\n"
        text += f"  剩余: {minutes}分{seconds}秒\n"
        text += f"  订单号: `{order['order_id']}`\n\n"

        # 添加手动确认按钮
        buttons.append([InlineKeyboardButton(
            f"✅ 手动确认 - {order['plan_name']} ({order['amount']} USDT)", 
            callback_data=f"admin_confirm_usdt_{amount_key}"
        )])

    buttons.append([InlineKeyboardButton("🔄 刷新", callback_data="admin_usdt_orders")])
    buttons.append([InlineKeyboardButton("◀️ 返回", callback_data="back_to_admin_menu")])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def admin_confirm_usdt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员手动确认 USDT 订单"""
    query = update.callback_query
    await query.answer()

    amount_key = query.data.replace("admin_confirm_usdt_", "")

    from handlers.user import pending_usdt_orders
    from database import extend_member, unban_user, db_execute, now, get_user_status
    from config import GROUP_ID

    if amount_key not in pending_usdt_orders:
        await query.edit_message_text("❌ 订单不存在或已过期")
        return

    order = pending_usdt_orders[amount_key]
    user_id = order["user_id"]
    days = order["days"]
    plan_name = order["plan_name"]

    logging.info(f"=== 手动确认订单 ===, 用户ID: {user_id}, 天数: {days}, 套餐: {plan_name}")

    # 查看确认前的用户状态
    before = db_execute("SELECT expire_time, trial_start_time, is_permanent, is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    logging.info(f"确认前: expire={before[0] if before else None}, trial={before[2] if before else None}")

    # 1. 解封用户（数据库）
    unban_user(user_id)

    # 2. 延长会员时间（关键步骤）
    new_expire = extend_member(user_id, days)
    logging.info(f"会员延期后到期时间: {new_expire}")

    # 3. 解封群组中的用户（只在用户被封禁时）
    try:
        member = await context.bot.get_chat_member(GROUP_ID, user_id)
        if member.status in ["left", "kicked"]:
            await context.bot.unban_chat_member(GROUP_ID, user_id)
            logging.info(f"用户 {user_id} 已从群组解封")
        else:
            logging.info(f"用户 {user_id} 已在群组中")
    except Exception as e:
        logging.warning(f"解封用户 {user_id} 失败: {e}")

    # 4. 验证确认后的状态
    after = db_execute("SELECT expire_time, trial_start_time, is_permanent, is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    logging.info(f"确认后: expire={after[0] if after else None}, trial={after[2] if after else None}")

    # 获取用户状态
    is_valid, status = get_user_status(user_id)
    logging.info(f"确认后用户状态: is_valid={is_valid}, status={status}")

    # 5. 更新数据库中的订单状态
    db_execute("""
        UPDATE usdt_orders 
        SET status='paid', paid_at=?, tx_id='manual_confirm'
        WHERE order_id=?
    """, (now().isoformat(), order["order_id"]))

    # 6. 删除内存中的订单
    del pending_usdt_orders[amount_key]

    # 7. 通知用户
    try:
        await context.bot.send_message(
            user_id,
            f"✅ **支付已确认！**\n\n"
            f"套餐：{plan_name}\n"
            f"会员到期时间：{new_expire.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"感谢您的支持！"
        )
    except Exception as e:
        logging.warning(f"通知用户失败: {e}")

    log_admin_action(update.effective_user.id, f"manual_confirm_usdt_{order['order_id']}", user_id)

    await query.edit_message_text(
        f"✅ 已手动确认订单\n\n"
        f"用户ID: {user_id}\n"
        f"套餐: {plan_name}\n"
        f"天数: {days}\n"
        f"已开通会员至: {new_expire.strftime('%Y-%m-%d %H:%M')}\n"
        f"用户状态: {status}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ 返回订单列表", callback_data="admin_usdt_orders")]
        ])
    )

async def admin_usdt_orders_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员查看 USDT 订单历史"""
    query = update.callback_query
    await query.answer()

    from database import db_execute
    from datetime import datetime

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
        if tx_id and tx_id != 'manual_confirm':
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
