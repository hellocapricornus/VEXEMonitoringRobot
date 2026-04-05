import asyncio
import logging
from telegram.ext import ContextTypes

from config import GROUP_ID, DELETE_DELAY
from database import db_execute

async def send_temp(context: ContextTypes.DEFAULT_TYPE, text: str, chat_id: int, delay: int = DELETE_DELAY):
    """发送临时消息并倒计时删除"""
    logging.info(f"发送临时消息到 {chat_id}: {text[:50]}...")
    msg = await context.bot.send_message(chat_id, f"{text}\n\n⏳ 消息将在 {delay} 秒后自动删除")
    for remaining in range(delay - 1, 0, -1):
        await asyncio.sleep(1)
        try:
            await msg.edit_text(f"{text}\n\n⏳ 消息将在 {remaining} 秒后自动删除")
        except:
            break
    try:
        await msg.delete()
    except:
        pass

async def kick_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, reason: str = "未通过验证", ban: bool = True):
    """踢出用户

    Args:
        ban: True=封禁（禁止重新加入），False=只踢出不封禁
    """
    from database import ban_user, unban_user, db_execute
    try:
        if ban:
            # 封禁用户（禁止重新加入）
            await context.bot.ban_chat_member(GROUP_ID, user_id)
            logging.info(f"已封禁用户 {user_id}")
            # 记录到数据库
            ban_user(user_id, reason)
        else:
            # 只踢出不封禁（先封禁再立即解封）
            await context.bot.ban_chat_member(GROUP_ID, user_id)
            await context.bot.unban_chat_member(GROUP_ID, user_id)
            # ⚠️ 只踢出不封禁时，不要设置数据库的 is_banned=1
            # 但需要确保数据库记录存在且 is_banned=0
            db_execute("""
                INSERT OR IGNORE INTO users (user_id, is_banned) 
                VALUES (?, 0)
            """, (user_id,))
            logging.info(f"已踢出用户 {user_id}（未封禁）")

        # 尝试私聊通知
        try:
            await context.bot.send_message(user_id, f"⚠️ 你已被移出群组\n原因: {reason}\n如有疑问请联系管理员。")
        except:
            pass

        logging.info(f"踢出用户 {user_id}, 原因: {reason}, 封禁: {ban}")
    except Exception as e:
        logging.error(f"踢人失败 {user_id}: {e}")

# 从 database 导入并重新导出
from database import is_user_following_channel
