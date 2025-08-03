import json
import os
from datetime import datetime, timedelta
import pytz
from telegram import Update, ChatMember
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ChatMemberHandler

# ========== 配置 ==========
BOT_TOKEN = "8281720118:AAFBTiE2NHqeYJ5L4o53GPuFFDbEJMDlrpY"
ADMIN_USER_ID = 7596698993
TARGET_GROUP = -1002741490869  # 目标群组ID

# 文件路径
MEMBER_FILE = "members.json"  # 会员文件
PENDING_USERS_FILE = "pending_users.json"  # 记录试用用户的文件

members = {}
pending_users = {}

# 北京时间
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ========== 会员数据管理 ==========
def load_members():
    global members
    if os.path.exists(MEMBER_FILE):
        try:
            with open(MEMBER_FILE, "r", encoding="utf-8") as f:
                members = json.load(f)
            print(f"[加载] 已加载 {len(members)} 位会员")
        except Exception as e:
            print(f"[加载] 读取失败: {e}")
            members = {}
    else:
        members = {}

def save_members():
    try:
        with open(MEMBER_FILE, "w", encoding="utf-8") as f:
            json.dump(members, f, ensure_ascii=False, indent=2)
        print(f"[保存] 已保存 {len(members)} 位会员")
    except Exception as e:
        print(f"[保存] 保存失败: {e}")

def load_pending_users():
    global pending_users
    if os.path.exists(PENDING_USERS_FILE):
        try:
            with open(PENDING_USERS_FILE, "r", encoding="utf-8") as f:
                pending_users = json.load(f)
            # 确保 join_time 是 datetime 对象
            pending_users = {int(k): datetime.fromisoformat(v) for k, v in pending_users.items()}
            print(f"[加载] 待关注用户 {len(pending_users)} 条")
        except Exception as e:
            print(f"[加载] 读取失败: {e}")
            pending_users = {}
    else:
        pending_users = {}

def save_pending_users():
    try:
        # 将 datetime 对象转换为 ISO 格式字符串
        data = {str(k): v.isoformat() for k, v in pending_users.items()}
        with open(PENDING_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[保存] 待关注用户 {len(pending_users)} 条")
    except Exception as e:
        print(f"[保存] 保存失败: {e}")

# ========== 工具函数 ==========
def is_admin(user_id):
    return user_id == ADMIN_USER_ID

async def check_user_subscribed(app, user_id) -> bool:
    """检测用户是否是会员"""
    return user_id in members

# 监听用户退出群组的事件
async def handle_user_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户退出群组"""
    if update.effective_chat.id != TARGET_GROUP:
        return

    # 如果是用户退出群组，尝试删除退出消息
    if update.chat_member and update.chat_member.status == ChatMember.Status.LEFT:
        user_id = update.chat_member.user.id
        try:
            # 尝试删除退出群组的消息（会被视作系统消息）
            await update.message.delete()
            print(f"[删除退出消息] 用户 {user_id} 退出群组，已删除自动生成的消息")
        except Exception as e:
            print(f"[删除退出消息] 失败: {e}")
        
# ========== 群组事件处理 ==========
async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """新用户加入时触发"""
    if update.effective_chat.id != TARGET_GROUP:
        return

    app = context.application
    # 删除 Telegram 自动生成的“加入群组”消息
    try:
        await update.message.delete()
    except Exception as e:
        print(f"[删除加入消息] 失败: {e}")

    for member in update.message.new_chat_members:
        user_id = member.id
        if await check_user_subscribed(app, user_id):
            print(f"[欢迎] 用户 {user_id} 已是会员，允许继续使用。")
        else:
            await context.bot.send_message(
                chat_id=TARGET_GROUP,
                text=f"👋 欢迎 {member.full_name}！你是新用户，24小时内可免费试用，试用期结束后将被踢出本群。如果需要继续使用，请联系管理员购买会员，每月 20 USDT。"
            )
            pending_users[user_id] = datetime.now(BEIJING_TZ)  # 记录加入时间 (北京时间)
            save_pending_users()

# ========== 定时检查并踢人 ==========
async def remove_unsubscribed_users(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(BEIJING_TZ)  # 获取当前北京时间
    to_remove = []

    # 获取群组所有成员
    chat = await context.bot.get_chat(chat_id=TARGET_GROUP)
    admins = await context.bot.get_chat_administrators(chat_id=TARGET_GROUP)

    # 获取群主 ID 和管理员 ID
    owner_id = admins[0].user.id  # 群主通常是第一个管理员
    admin_ids = [admin.user.id for admin in admins]  # 所有管理员 IDs

    # 获取群组成员数量，并逐个获取成员信息
    member_count = await context.bot.get_chat_members_count(chat_id=TARGET_GROUP)

    for user_id in range(0, member_count):  # 假设我们能通过此方式逐个获取群成员
        try:
            member = await context.bot.get_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
            user_id = member.user.id

            # 跳过群主和管理员
            if user_id == owner_id or user_id in admin_ids:
                print(f"[跳过] 用户 {user_id} 是群主或管理员，无法踢出")
                continue  # 跳过群主和管理员

            # 检查会员是否过期
            if user_id in members:
                expiry_time_str = members[user_id].get('expiry_time')
                if expiry_time_str:
                    expiry_time = datetime.fromisoformat(expiry_time_str)
                    time_left = expiry_time - now

                    # 提醒用户剩余 3 小时
                    if time_left <= timedelta(hours=3) and time_left > timedelta(hours=0):
                        try:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text="⏳ 您的会员有效期即将到期，剩余 3 小时。请尽快联系管理员续费，以继续使用本群。"
                            )
                            print(f"[提醒] 用户 {user_id} 剩余 3 小时，已发送提醒")
                        except Exception as e:
                            print(f"[提醒] 发送提醒失败: {e}")

                    # 超过有效期后踢出
                    if time_left <= timedelta(hours=0):
                        try:
                            await context.bot.ban_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
                            print(f"[踢人] 移除过期会员：{user_id}")
                            to_remove.append(user_id)
                        except Exception as e:
                            print(f"[踢人] 失败: {e}")

        except Exception as e:
            print(f"[获取成员信息失败] 用户ID {user_id} 获取失败: {e}")

    # 从待关注用户列表中移除已被踢出的用户
    for user_id in to_remove:
        pending_users.pop(user_id, None)
        members.pop(user_id, None)  # 同时移除过期会员

    # 保存更新后的数据
    if to_remove:
        save_pending_users()
        save_members()

# ========== 添加、删除、查看会员 ==========
async def add_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过命令添加会员"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限执行此操作")
        return

    if len(context.args) == 0:
        await update.message.reply_text("请提供会员的 Telegram ID")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("请输入有效的用户 ID")
        return

    if user_id in members:
        await update.message.reply_text(f"用户 {user_id} 已经是会员")
    else:
        members[user_id] = {'join_time': str(datetime.now(BEIJING_TZ)), 'expiry_time': None}  # 添加加入时间和有效期为空
        save_members()
        await update.message.reply_text(f"成功将用户 {user_id} 添加为会员")

async def set_member_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置会员有效期"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限执行此操作")
        return

    if len(context.args) < 2:
        await update.message.reply_text("请提供会员的 Telegram ID 和有效期天数")
        return

    try:
        user_id = int(context.args[0])
        expiry_days = int(context.args[1])
    except ValueError:
        await update.message.reply_text("请输入有效的用户 ID 和天数")
        return

    if user_id in members:
        expiry_time = datetime.now(BEIJING_TZ) + timedelta(days=expiry_days)
        members[user_id]['expiry_time'] = expiry_time.isoformat()
        save_members()
        await update.message.reply_text(f"成功为用户 {user_id} 设置了 {expiry_days} 天有效期，过期时间为 {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        await update.message.reply_text(f"用户 {user_id} 不是会员")

async def remove_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过命令删除会员"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限执行此操作")
        return

    if len(context.args) == 0:
        await update.message.reply_text("请提供要删除的会员的 Telegram ID")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("请输入有效的用户 ID")
        return

    if user_id in members:
        del members[user_id]
        save_members()
        await update.message.reply_text(f"成功删除用户 {user_id} 的会员资格")
    else:
        await update.message.reply_text(f"用户 {user_id} 不是会员")

async def view_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看所有会员"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限执行此操作")
        return

    if not members:
        await update.message.reply_text("当前没有会员")
    else:
        members_list = "\n".join([f"ID: {user_id}, 加入时间: {members[user_id]['join_time']}, 有效期到: {members[user_id]['expiry_time']}" for user_id in members])
        await update.message.reply_text(f"当前会员列表：\n{members_list}")

# ========== 机器人启动函数 ==========
def main():
    load_members()
    load_pending_users()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # 群组成员加入事件
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_members))

    # 添加管理员添加、删除和查看会员的命令处理器
    app.add_handler(CommandHandler("add_member", add_member))
    app.add_handler(CommandHandler("set_member_expiry", set_member_expiry))
    app.add_handler(CommandHandler("remove_member", remove_member))
    app.add_handler(CommandHandler("view_members", view_members))

    # 定时任务：每小时检查一次
    app.job_queue.run_repeating(remove_unsubscribed_users, interval=3600, first=10)

    print("🤖 机器人启动成功，管理试用会员与会员功能")
    app.run_polling()

if __name__ == "__main__":
    main()
