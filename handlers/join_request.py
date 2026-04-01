import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import add_trial, get_user, get_user_status, has_valid_membership, is_user_following_channel
from config import CHANNEL_LINK, MONITOR_GROUP_LINK, GROUP_ID

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户申请加入监听群时，自动批准并开始24小时试用"""
    request = update.chat_join_request
    user_id = request.from_user.id

    logging.info(f"收到入群申请: 用户 {user_id}")

    # 1. 首先检查用户是否关注了频道
    is_following = await is_user_following_channel(context, user_id)

    if not is_following:
        await request.decline()
        logging.info(f"用户 {user_id} 未关注频道，拒绝入群")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 关注频道", url=CHANNEL_LINK)],
            [InlineKeyboardButton("✅ 我已关注", callback_data="check_follow")]
        ])
        try:
            await context.bot.send_message(
                user_id,
                "❌ 您需要先关注我们的频道才能加入群组。\n\n"
                "请先关注频道，然后点击「我已关注」按钮，再重新申请加入群组。\n\n"
                f"👉 {CHANNEL_LINK}",
                reply_markup=keyboard
            )
        except Exception as e:
            logging.warning(f"无法私聊用户 {user_id}: {e}")
        return

    # 2. 已关注频道，批准入群并解封
    await request.approve()

    # 解封用户（如果之前被封禁）
    try:
        await context.bot.unban_chat_member(GROUP_ID, user_id)
        logging.info(f"用户 {user_id} 已解封")
    except Exception as e:
        logging.warning(f"解封用户 {user_id} 失败: {e}")

    # 3. 检查用户资格并开始试用
    row = get_user(user_id)
    is_valid, status = get_user_status(user_id)

    if is_valid:
        logging.info(f"用户 {user_id} 有有效资格 ({status})，自动批准入群")
        try:
            await context.bot.send_message(
                user_id,
                f"✅ 欢迎加入群组！\n\n您的状态: {status}\n\n请遵守群规，祝您使用愉快！"
            )
        except:
            pass
        return

    # 新用户，开始试用
    if not row or not row[2]:
        add_trial(user_id)
        logging.info(f"新用户 {user_id}，开始24小时试用，批准入群")
        try:
            await context.bot.send_message(
                user_id,
                f"✅ 欢迎加入群组！\n\n"
                f"🧪 您已获得24小时免费试用期。\n"
                f"试用期间请遵守群规。\n\n"
                f"试用结束后如需继续使用，请购买会员。\n\n"
                f"发送 /start 查看您的会员状态。"
            )
        except:
            pass
