# main.py - 修复定时任务和导入问题

#!/usr/bin/env python3
import logging
import datetime as dt
import os
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
    clean_expired_orders,  # 统一从这里导入
)
from handlers.admin import (
    cmd_add_trial,
    cmd_add_permanent,
    cmd_extend,
    cmd_kick,
    cmd_unban,
    back_to_admin_menu,
    admin_stats,
    admin_add_trial,
    admin_add_permanent,
    admin_extend,
    admin_kick,
    admin_unban,
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
    cmd_check_user,
    cmd_add_plan,           # ✅ 新增
    cmd_del_plan,           # ✅ 新增
    cmd_toggle_plan,        # ✅ 新增
    cmd_add_address,        # ✅ 新增
    cmd_del_address,        # ✅ 新增
    admin_user_manage_callback,
    admin_member_manage_callback,
    admin_plans_callback,
    admin_addresses_callback,
)
from handlers.group import new_member_handler, left_member_handler
from handlers.join_request import handle_join_request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

# 🔧 添加分布式锁标记（如果使用多个 worker，需要外部存储如 Redis）
# 这里使用环境变量标记，单实例部署时安全
WORKER_ID = os.environ.get("WORKER_ID", "default")
SCHEDULER_LOCK_KEY = "scheduler_running"

def main():
    # 初始化数据库
    init_db()

    # 🔧 添加：启动时验证数据库完整性
    from database import db_execute, get_user_status

    # 1. 显示所有付费用户
    paid_users = db_execute("SELECT user_id, expire_time, is_permanent FROM users WHERE expire_time IS NOT NULL OR is_permanent=1").fetchall()
    logging.info(f"=== 启动时数据库状态 ===")
    logging.info(f"付费用户总数: {len(paid_users)}")

    for user in paid_users:
        user_id = user[0]
        expire_time = user[1]
        is_permanent = user[2]

        # 验证每个付费用户的状态
        is_valid, status = get_user_status(user_id)
        logging.info(f"用户 {user_id}: 永久={is_permanent}, 到期={expire_time}, 有效={is_valid}, 状态={status}")

        # 🔧 如果有资格但不在群组，不删除，只记录
        if is_valid:
            logging.info(f"✅ 用户 {user_id} 有有效会员资格，已保留")

    # 2. 检查数据库文件位置
    import os
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")
    logging.info(f"数据库文件位置: {db_path}")
    logging.info(f"数据库文件存在: {os.path.exists(db_path)}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ================= 命令 =================
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add_trial", cmd_add_trial))
    app.add_handler(CommandHandler("add_permanent", cmd_add_permanent))
    app.add_handler(CommandHandler("extend", cmd_extend))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("reply", admin_reply_command))
    app.add_handler(CommandHandler("check_user", cmd_check_user))
    # ✅ 套餐和地址管理
    app.add_handler(CommandHandler("addplan", cmd_add_plan))
    app.add_handler(CommandHandler("delplan", cmd_del_plan))
    app.add_handler(CommandHandler("toggleplan", cmd_toggle_plan))
    app.add_handler(CommandHandler("addaddr", cmd_add_address))
    app.add_handler(CommandHandler("deladdr", cmd_del_address))

    

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
    # 新增子菜单回调
    app.add_handler(CallbackQueryHandler(admin_user_manage_callback, pattern="^admin_user_manage$"))
    app.add_handler(CallbackQueryHandler(admin_member_manage_callback, pattern="^admin_member_manage$"))
    app.add_handler(CallbackQueryHandler(admin_plans_callback, pattern="^admin_plans$"))
    app.add_handler(CallbackQueryHandler(admin_addresses_callback, pattern="^admin_addresses$"))

    # ================= 定时任务 =================
    if app.job_queue:
        # 🔧 使用环境变量判断是否启用定时任务（避免多 worker 重复）
        enable_scheduler = os.environ.get("ENABLE_SCHEDULER", "true").lower() == "true"

        if enable_scheduler:
            # 原有的任务
            app.job_queue.run_repeating(check_expired, interval=30, first=5)

            # 新增：每天凌晨3点清理旧订单
            from database import clean_old_orders, update_expired_pending_orders

            async def clean_database_job(context):
                """定时清理数据库任务 - 包含释放过期地址"""
                import logging
                from database import db_execute, mark_address_idle, update_expired_pending_orders, clean_old_orders

                logging.info(f"Worker {WORKER_ID}: 开始执行数据库清理任务...")

                # 1. 先将超时的待处理订单转为过期
                updated = update_expired_pending_orders()
                logging.info(f"已将 {updated} 个超时订单转为过期")

                # 2. 释放过期/取消订单占用的地址
                expired_with_address = db_execute("""
                    SELECT DISTINCT address FROM usdt_orders 
                    WHERE status IN ('expired', 'cancelled') AND address IS NOT NULL AND address != ''
                """).fetchall()

                released = 0
                for (address,) in expired_with_address:
                    # 检查这个地址是否还有其他 pending 订单在用
                    still_in_use = db_execute("""
                        SELECT COUNT(*) FROM usdt_orders 
                        WHERE address = ? AND status = 'pending'
                    """, (address,)).fetchone()[0]

                    if still_in_use == 0:
                        mark_address_idle(address)
                        released += 1
                        logging.info(f"释放地址: {address}")

                if released > 0:
                    logging.info(f"已释放 {released} 个过期订单地址")

                # 3. 清理旧订单
                deleted = clean_old_orders()
                logging.info(f"数据库清理完成，共删除 {deleted} 条记录")

            # ✅ 注册定时任务（每5分钟检查一次释放地址，每天凌晨3点清理旧订单）
            app.job_queue.run_repeating(clean_database_job, interval=300, first=15)
            app.job_queue.run_daily(clean_database_job, time=dt.time(hour=3, minute=0), days=tuple(range(7)))

    # 启动时恢复待处理订单（只恢复内存，不检查支付）
    from handlers.user import restore_orders_on_startup, check_all_pending_orders_on_startup
    restore_orders_on_startup()

    logging.info(f"机器人启动 (Worker: {WORKER_ID})，使用 polling 模式")
    app.run_polling()

if __name__ == "__main__":
    main()
