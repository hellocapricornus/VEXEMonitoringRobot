import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import GROUP_ID, CHANNEL_LINK, MONITOR_GROUP_LINK, TRIAL_HOURS
from database import get_user, is_admin, now, BEIJING, db_execute
from utils import send_temp, kick_user, is_user_following_channel

async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """当有新用户加入管理群时（包括被邀请、通过链接加入等）"""
    if update.effective_chat.id != GROUP_ID:
        return

    # 删除系统消息
    try:
        await update.message.delete()
    except Exception as e:
        logging.warning(f"删除系统消息失败: {e}")

    # 获取所有新加入的成员
    new_members = update.message.new_chat_members
    logging.info(f"检测到新成员加入事件，新成员数量: {len(new_members)}")

    for member in new_members:
        user_id = member.id

        # 如果是机器人自己，跳过
        if user_id == context.bot.id:
            logging.info("机器人自己加入，跳过")
            continue

        logging.info(f"处理新成员: {member.full_name} (ID: {user_id})")

        # 确保用户在数据库中有记录
        db_execute("""
            INSERT OR IGNORE INTO users (user_id, is_banned)
            VALUES (?, 0)
        """, (user_id,))

        # 验证是否插入成功
        check_row = db_execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if check_row:
            logging.info(f"用户 {user_id} 已成功记录到数据库")
        else:
            logging.error(f"用户 {user_id} 记录到数据库失败！")

        # 管理员直接放行
        if is_admin(user_id):
            logging.info(f"管理员 {member.full_name} 加入，直接放行")
            await send_temp(context, f"👋 欢迎管理员 {member.full_name}", GROUP_ID)
            continue

        # 1. 首先检查频道关注状态（所有非管理员用户都必须关注频道）
        is_following = await is_user_following_channel(context, user_id)
        logging.info(f"用户 {user_id} 频道关注状态: {is_following}")

        # 未关注频道：只踢出不封禁（用户关注后可以重新加入）
        if not is_following:
            reason = "未关注频道"
            logging.info(f"用户 {user_id} 未关注频道，准备踢出")
            await kick_user(context, user_id, reason, ban=False)
            try:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 关注频道", url=CHANNEL_LINK)],
                    [InlineKeyboardButton("✅ 我已关注", callback_data="check_follow")]
                ])
                await context.bot.send_message(
                    user_id,
                    f"❌ 您未关注我们的频道，无法加入本群。\n\n"
                    f"请先关注频道后，点击「我已关注」，然后重新加入群组。\n\n"
                    f"👉 {CHANNEL_LINK}",
                    reply_markup=keyboard
                )
            except Exception as e:
                logging.warning(f"无法私聊用户 {user_id}: {e}")
            continue

        # 2. 已关注频道，获取用户数据库记录
        row = get_user(user_id)

        # 如果记录不存在，自动创建
        if not row:
            logging.info(f"用户 {user_id} 数据库记录不存在，正在创建...")
            db_execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, 0)", (user_id,))
            row = get_user(user_id)
            if row:
                logging.info(f"用户 {user_id} 记录创建成功")
            else:
                logging.error(f"用户 {user_id} 记录创建失败！")
                continue

        # 调试日志
        logging.info(f"用户 {user_id} 数据库状态: expire_time={row[0]}, is_permanent={row[1]}, trial_start={row[2]}, is_banned={row[3]}")

        # 3. 检查会员/试用资格
        is_valid = False
        reason = ""

        if row:
            # 永久会员
            if row[1] == 1:
                is_valid = True
                reason = "永久会员"
            # 付费会员（未过期）
            elif row[0]:
                try:
                    expire = datetime.fromisoformat(row[0]).astimezone(BEIJING)
                    if expire > now():
                        is_valid = True
                        reason = f"会员到期 {expire.strftime('%Y-%m-%d %H:%M')}"
                    else:
                        reason = "会员已过期，请续费"
                except:
                    reason = "会员已过期"
            # 试用用户（未过期）
            elif row[2]:
                try:
                    trial_start = datetime.fromisoformat(row[2]).astimezone(BEIJING)
                    trial_end = trial_start + timedelta(hours=TRIAL_HOURS)
                    if trial_end > now():
                        is_valid = True
                        reason = f"试用剩余 {(trial_end-now()).seconds//3600} 小时"
                    else:
                        reason = "试用已结束，请购买会员"
                except:
                    reason = "试用已结束"
            else:
                reason = "未获得试用资格"

        # 4. 如果有有效资格，直接放行（并确保解封）
        if is_valid:
            logging.info(f"用户 {user_id} 有有效资格 ({reason})，允许入群")
            # 确保 Telegram 解封
            try:
                await context.bot.unban_chat_member(GROUP_ID, user_id)
                logging.info(f"用户 {user_id} 已解封")
            except Exception as e:
                logging.warning(f"解封用户 {user_id} 失败: {e}")
            # 确保数据库解封
            if row and row[3] == 1:
                db_execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
                logging.info(f"用户 {user_id} 数据库已解封")
            await send_temp(context, f"👋 欢迎 {member.full_name}\n{reason}", GROUP_ID)
            continue

        # 5. 无有效资格，检查是否被封禁
        if row and row[3] == 1:
            reason = "您已被封禁"
            logging.info(f"用户 {user_id} 已被封禁，准备踢出")
            await kick_user(context, user_id, reason, ban=True)
            continue

        # 6. 无有效资格且未封禁，踢出并引导
        logging.info(f"用户 {user_id} 无有效资格 ({reason})，准备踢出")
        await kick_user(context, user_id, reason, ban=False)
        try:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 加入监听群获取试用", url=MONITOR_GROUP_LINK)],
                [InlineKeyboardButton("💰 购买会员", callback_data="user_buy_usdt")]
            ])
            await context.bot.send_message(
                user_id,
                f"❌ 无法加入群组\n原因: {reason}\n\n"
                f"请通过以下方式获取资格：",
                reply_markup=keyboard
            )
        except Exception as e:
            logging.warning(f"无法私聊用户 {user_id}: {e}")

async def left_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理成员离开消息"""
    msg = update.message
    if not msg or not msg.left_chat_member:
        return
    if msg.chat.id != GROUP_ID:
        return

    await send_temp(context, f"⚠️ 用户 {msg.left_chat_member.full_name} 已离开群聊", msg.chat.id)
    try:
        await msg.delete()
    except:
        pass
