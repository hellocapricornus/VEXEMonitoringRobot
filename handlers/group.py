import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from config import GROUP_ID
from database import get_user, is_admin, db_execute
from utils import send_temp

async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """当有新用户加入群组时 - 只发送欢迎消息"""
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
            continue

        if is_admin(user_id):
            await context.bot.send_message(GROUP_ID, f"👋 欢迎管理员 {member.full_name}")
            continue

        # 等待一下，确保数据库已更新
        await asyncio.sleep(1)

        # 关键修复：如果用户有会员资格，清除试用期
        row = get_user(user_id)
        if row and row[0]:  # 有 expire_time
            db_execute("UPDATE users SET trial_start_time=NULL, trial_reminded=0 WHERE user_id=?", (user_id,))
            logging.info(f"用户 {user_id} 有会员资格，已清除试用期")

        # 获取状态用于欢迎消息
        from database import get_user_status
        is_valid, status = get_user_status(user_id)

        # 只发送欢迎消息，不踢人（踢人已在 join_request 中处理）
        await context.bot.send_message(GROUP_ID, f"👋 欢迎 {member.full_name}\n{status}")

async def left_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理成员离开消息"""
    msg = update.message
    if not msg or not msg.left_chat_member:
        return
    if msg.chat.id != GROUP_ID:
        return

    await context.bot.send_message(GROUP_ID, f"⚠️ 用户 {msg.left_chat_member.full_name} 已离开群聊")
    try:
        await msg.delete()
    except:
        pass
