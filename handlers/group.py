import logging
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

    new_members = update.message.new_chat_members
    logging.info(f"检测到新成员加入事件，新成员数量: {len(new_members)}")

    for member in new_members:
        user_id = member.id

        if user_id == context.bot.id:
            logging.info("机器人自己加入，跳过")
            continue

        logging.info(f"处理新成员: {member.full_name} (ID: {user_id})")

        # 管理员直接放行
        if is_admin(user_id):
            logging.info(f"管理员 {member.full_name} 加入，直接放行")
            await send_temp(context, f"👋 欢迎管理员 {member.full_name}", GROUP_ID)
            continue

        # 1. 首先检查频道关注状态
        is_following = await is_user_following_channel(context, user_id)
        logging.info(f"用户 {user_id} 频道关注状态: {is_following}")

        if not is_following:
            reason = "未关注频道"
            logging.info(f"用户 {user_id} 未关注频道，准备踢出（不封禁）")
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

        # 2. 确保用户在数据库中有记录
        db_execute("""
            INSERT OR IGNORE INTO users (user_id, is_banned)
            VALUES (?, 0)
        """, (user_id,))

        # 3. 获取用户状态
        row = get_user(user_id)
        is_valid, status = get_user_status(user_id)

        # 4. 检查用户是否被封禁（双重检查）
        if row and row[3] == 1:
            reason = "您已被封禁，请联系管理员"
            logging.info(f"用户 {user_id} 已被封禁 (is_banned={row[3]})，准备踢出")
            await kick_user(context, user_id, reason, ban=True)
            continue

        if is_valid:
            # 有有效资格，发送欢迎消息并确保解封
            logging.info(f"用户 {user_id} 有有效资格 ({status})，允许入群")
            
            # 确保用户没有被封禁（解封）
            if row and row[3] == 1:
                unban_user(user_id)
                try:
                    await context.bot.unban_chat_member(GROUP_ID, user_id)
                except:
                    pass
            
            await send_temp(context, f"👋 欢迎 {member.full_name}\n{status}", GROUP_ID)
        else:
            # 无有效资格，踢出并封禁
            logging.info(f"用户 {user_id} 无有效资格 ({status})，准备踢出并封禁")
            await kick_user(context, user_id, status, ban=True)
            try:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 加入监听群获取试用", url=MONITOR_GROUP_LINK)],
                    [InlineKeyboardButton("💰 购买会员", callback_data="user_buy_usdt")]
                ])
                await context.bot.send_message(
                    user_id,
                    f"❌ 无法加入群组\n原因: {status}\n\n"
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
