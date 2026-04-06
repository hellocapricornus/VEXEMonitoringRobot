#!/usr/bin/env python3
import logging

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    filters,
)

from config import BOT_TOKEN, ADMIN_ID
from database import init_db
from handlers.user import (
    start,
    check_follow_callback,
    user_query_time,
    back_to_user_menu,
    restart_callback,
    contact_admin_callback,
    handle_user_message,
    reply_user_callback,
    handle_admin_reply,
    user_buy_usdt,
    usdt_plan_callback,
    check_usdt_payment_callback,
)
from handlers.admin import (
    cmd_add_trial,
    cmd_add_permanent,
    cmd_extend,
    cmd_kick,
    cmd_unban,
    cmd_delete_member,
    back_to_admin_menu,
    admin_stats,
    admin_add_trial,
    admin_add_permanent,
    admin_extend,
    admin_kick,
    admin_unban,
    admin_delete_member,
    admin_members,
    admin_trials,
    admin_banned,
    check_expired,
    admin_reply_callback,
    admin_reply_command,
    admin_usdt_orders_callback,
    admin_usdt_orders_history_callback,
    admin_confirm_usdt_callback,
    admin_broadcast_callback,
    handle_broadcast,
)
from handlers.group import new_member_handler, left_member_handler
from handlers.join_request import handle_join_request
from handlers.user import clean_expired_orders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# main.py - 修改消息处理器部分

def main():
    # 初始化数据库
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ================= 命令 =================
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_trial", cmd_add_trial))
    app.add_handler(CommandHandler("add_permanent", cmd_add_permanent))
    app.add_handler(CommandHandler("extend", cmd_extend))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("reply", admin_reply_command))

    # ================= 消息处理器 - 调整优先级 =================
    # 1. 广播消息处理器（最高优先级，group=1）
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Chat(chat_id=ADMIN_ID) & filters.ChatType.PRIVATE,
        handle_broadcast
    ), group=1)

    # 2. 管理员回复处理器（中等优先级，group=2）
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Chat(chat_id=ADMIN_ID) & filters.ChatType.PRIVATE, 
        handle_admin_reply
    ), group=2)

    # 3. 用户消息处理器（最低优先级，group=3）
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE & ~filters.Chat(chat_id=ADMIN_ID), 
        handle_user_message
    ), group=3)

    # ================= 群组消息事件 =================
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_member_handler))

    # ================= 入群申请 =================
    app.add_handler(ChatJoinRequestHandler(handle_join_request))

    # ================= 回调 =================
    # 用户回调
    app.add_handler(CallbackQueryHandler(check_follow_callback, pattern="^check_follow$"))
    app.add_handler(CallbackQueryHandler(user_query_time, pattern="^user_query$"))
    app.add_handler(CallbackQueryHandler(back_to_user_menu, pattern="^back_to_user_menu$"))
    app.add_handler(CallbackQueryHandler(restart_callback, pattern="^restart$"))
    app.add_handler(CallbackQueryHandler(contact_admin_callback, pattern="^contact_admin$"))
    app.add_handler(CallbackQueryHandler(reply_user_callback, pattern="^reply_user_"))

    # 用户回调 - USDT 支付
    app.add_handler(CallbackQueryHandler(user_buy_usdt, pattern="^user_buy_usdt$"))
    app.add_handler(CallbackQueryHandler(usdt_plan_callback, pattern="^usdt_plan_"))
    app.add_handler(CallbackQueryHandler(check_usdt_payment_callback, pattern="^check_usdt_"))

    # 管理员回调
    app.add_handler(CallbackQueryHandler(back_to_admin_menu, pattern="^back_to_admin_menu$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_add_trial, pattern="^admin_add_trial$"))
    app.add_handler(CallbackQueryHandler(admin_add_permanent, pattern="^admin_add_permanent$"))
    app.add_handler(CallbackQueryHandler(admin_extend, pattern="^admin_extend$"))
    app.add_handler(CallbackQueryHandler(admin_kick, pattern="^admin_kick$"))
    app.add_handler(CallbackQueryHandler(admin_unban, pattern="^admin_unban$"))
    app.add_handler(CallbackQueryHandler(admin_members, pattern="^admin_members$"))
    app.add_handler(CallbackQueryHandler(admin_trials, pattern="^admin_trials$"))
    app.add_handler(CallbackQueryHandler(admin_banned, pattern="^admin_banned$"))
    app.add_handler(CallbackQueryHandler(admin_reply_callback, pattern="^admin_reply$"))
    app.add_handler(CallbackQueryHandler(admin_usdt_orders_callback, pattern="^admin_usdt_orders$"))
    app.add_handler(CallbackQueryHandler(admin_usdt_orders_history_callback, pattern="^admin_usdt_orders_history$"))
    app.add_handler(CallbackQueryHandler(admin_confirm_usdt_callback, pattern="^admin_confirm_usdt_"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_callback, pattern="^admin_broadcast$"))

    # ================= 定时任务 =================
    if app.job_queue:
        app.job_queue.run_repeating(check_expired, interval=30, first=5)

        # 清理过期订单的定时任务
        async def clean_orders_job(context):
            clean_expired_orders()

        app.job_queue.run_repeating(clean_orders_job, interval=300, first=10)
        logging.info("定时任务已启动")
    else:
        logging.warning("JobQueue 不可用，定时任务未启动")

    # 启动时恢复待处理订单
    from handlers.user import restore_orders_on_startup
    restore_orders_on_startup()

    logging.info("机器人启动，使用 polling 模式")
    app.run_polling()

if __name__ == "__main__":
    main()
