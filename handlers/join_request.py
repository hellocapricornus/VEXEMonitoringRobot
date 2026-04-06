import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import add_trial, get_user, get_user_status, unban_user, db_execute
from config import CHANNEL_LINK, GROUP_ID, GROUP_LINK, TRIAL_HOURS

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户申请加入群组时处理（唯一群组）"""
    request = update.chat_join_request
    user_id = request.from_user.id
    chat_id = request.chat.id

    logging.info(f"收到入群申请: 用户 {user_id}")

    if chat_id != GROUP_ID:
        await request.decline()
        return

    # 1. 检查频道关注
    from database import is_user_following_channel
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
                "❌ 您需要先关注频道才能加入群组。\n\n"
                f"👉 {CHANNEL_LINK}",
                reply_markup=keyboard
            )
        except:
            pass
        return

    # 2. 获取用户状态
    row = get_user(user_id)
    is_valid, status = get_user_status(user_id)

    logging.info(f"用户 {user_id} 状态: is_valid={is_valid}, status={status}")
    logging.info(f"数据库原始数据: expire={row[0] if row else None}, trial={row[2] if row else None}, banned={row[3] if row else None}")

    # 3. 关键修复：如果用户有会员资格，强制清除试用期
    if row and row[0]:  # 有 expire_time
        db_execute("UPDATE users SET trial_start_time=NULL, trial_reminded=0, is_banned=0 WHERE user_id=?", (user_id,))
        logging.info(f"用户 {user_id} 有会员资格，已清除试用期并解封")
        is_valid = True
        status = get_user_status(user_id)[1]

    # 4. 根据资格决定是否批准
    if is_valid:
        await request.approve()
        logging.info(f"用户 {user_id} 批准入群，状态: {status}")

        # 发送欢迎消息
        try:
            await context.bot.send_message(
                user_id,
                f"✅ 欢迎加入群组！\n\n{status}\n\n请遵守群规！"
            )
        except:
            pass
    else:
        # 无资格，尝试添加试用
        if not row or not row[2]:
            add_trial(user_id)
            await request.approve()
            logging.info(f"新用户 {user_id}，获得试用资格")
            try:
                await context.bot.send_message(
                    user_id,
                    f"✅ 欢迎加入群组！\n\n🧪 您已获得 {TRIAL_HOURS * 60} 分钟免费试用。\n\n试用结束后请购买会员。"
                )
            except:
                pass
        else:
            await request.decline()
            logging.info(f"用户 {user_id} 无有效资格，拒绝入群")
            try:
                await context.bot.send_message(
                    user_id,
                    f"❌ 无法加入群组\n\n原因: {status}\n\n请购买会员后重新申请。"
                )
            except:
                pass
