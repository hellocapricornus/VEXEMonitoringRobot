import json
import os
from datetime import datetime, timedelta
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ========== 配置 ==========
BOT_TOKEN = "8281720118:AAFBTiE2NHqeYJ5L4o53GPuFFDbEJMDlrpY"
ADMIN_USER_ID = 7596698993
TARGET_GROUP = -1002741490869  # 目标群组ID

# 文件路径
MEMBER_FILE = "members.json"  # 会员文件
PENDING_USERS_FILE = "pending_users.json"  # 记录试用用户的文件
KICKED_FILE = "kicked.json"  # 记录已踢用户文件

members = {}
pending_users = {}
kicked_users = {}

# 北京时间
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

# ========== 读取和保存踢出用户 ==========
def load_kicked_users():
    global kicked_users
    if os.path.exists(KICKED_FILE):
        try:
            with open(KICKED_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            kicked_users = {int(k): v for k, v in raw.items()}
            print(f"[加载] 已加载 {len(kicked_users)} 位被踢用户")
        except Exception as e:
            print(f"[加载] 读取踢出用户文件失败: {e}")
            kicked_users = {}
    else:
        kicked_users = {}

def save_kicked_users():
    try:
        with open(KICKED_FILE, "w", encoding="utf-8") as f:
            json.dump(kicked_users, f, ensure_ascii=False, indent=2)
        print(f"[保存] 已保存 {len(kicked_users)} 位被踢用户")
    except Exception as e:
        print(f"[保存] 保存踢出用户文件失败: {e}")

# ========== 数据修复 ==========
def migrate_data():
    """自动修复会员和试用用户文件结构"""
    if os.path.exists(MEMBER_FILE):
        try:
            with open(MEMBER_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            fixed = {}
            for k, v in raw_data.items():
                if isinstance(v, dict):
                    fixed[int(k)] = {
                        "join_time": v.get("join_time"),
                        "expiry_time": v.get("expiry_time"),
                        "reminded": v.get("reminded", False)
                    }
                else:
                    fixed[int(k)] = {
                        "join_time": v,
                        "expiry_time": None,
                        "reminded": False
                    }

            with open(MEMBER_FILE, "w", encoding="utf-8") as f:
                json.dump(fixed, f, ensure_ascii=False, indent=2)
            print(f"[修复] 会员文件完成，共 {len(fixed)} 条记录")
        except Exception as e:
            print(f"[修复] 会员文件失败: {e}")

    if os.path.exists(PENDING_USERS_FILE):
        try:
            with open(PENDING_USERS_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            fixed = {}
            for k, v in raw_data.items():
                if isinstance(v, dict):
                    fixed[int(k)] = {
                        "join_time": v.get("join_time"),
                        "reminded": v.get("reminded", False)
                    }
                else:
                    fixed[int(k)] = {
                        "join_time": v,
                        "reminded": False
                    }

            with open(PENDING_USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(fixed, f, ensure_ascii=False, indent=2)
            print(f"[修复] 试用用户文件完成，共 {len(fixed)} 条记录")
        except Exception as e:
            print(f"[修复] 试用用户文件失败: {e}")

# ========== 会员数据管理 ==========
def load_members():
    global members
    if os.path.exists(MEMBER_FILE):
        try:
            with open(MEMBER_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            members = {
                int(k): {
                    "join_time": v.get("join_time"),
                    "expiry_time": v.get("expiry_time"),
                    "reminded": v.get("reminded", False)
                }
                for k, v in raw_data.items()
            }
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
                raw_data = json.load(f)
            fixed_users = {}
            for k, v in raw_data.items():
                try:
                    if isinstance(v, dict):
                        join_time = datetime.fromisoformat(v["join_time"])
                        if join_time.tzinfo is None:
                            join_time = join_time.replace(tzinfo=BEIJING_TZ)
                        else:
                            join_time = join_time.astimezone(BEIJING_TZ)
                        fixed_users[int(k)] = {
                            "join_time": join_time,
                            "reminded": v.get("reminded", False)
                        }
                    else:
                        join_time = datetime.fromisoformat(v)
                        if join_time.tzinfo is None:
                            join_time = join_time.replace(tzinfo=BEIJING_TZ)
                        fixed_users[int(k)] = {
                            "join_time": join_time,
                            "reminded": False
                        }
                except Exception as e:
                    print(f"[修正] 用户 {k} 的时间数据无效: {e}")
            pending_users = fixed_users
            print(f"[加载] 待关注用户 {len(pending_users)} 条")
        except Exception as e:
            print(f"[加载] 读取失败: {e}")
            pending_users = {}
    else:
        pending_users = {}

def save_pending_users():
    try:
        data = {
            str(k): {
                "join_time": v["join_time"] if isinstance(v["join_time"], str) else v["join_time"].isoformat(),
                "reminded": v.get("reminded", False)
            }
            for k, v in pending_users.items()
        }
        with open(PENDING_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[保存] 待关注用户 {len(pending_users)} 条")
    except Exception as e:
        print(f"[保存] 保存失败: {e}")

# ========== 工具函数 ==========
def is_admin(user_id):
    return user_id == ADMIN_USER_ID

async def check_user_subscribed(app, user_id) -> bool:
    data = members.get(user_id)
    if not data:
        return False
    expiry_time = data.get("expiry_time")
    if not expiry_time:
        return True
    expiry_time = datetime.fromisoformat(expiry_time)
    if expiry_time.tzinfo is None:
        expiry_time = expiry_time.replace(tzinfo=BEIJING_TZ)
    else:
        expiry_time = expiry_time.astimezone(BEIJING_TZ)
    return expiry_time > datetime.now(BEIJING_TZ)

# 延迟删除消息
async def delete_message_after_delay(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    message_id = context.job.data["message_id"]
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"[删除消息失败] {e}")

# 监听用户退出群组
async def handle_user_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != TARGET_GROUP:
        return
    try:
        if update.message:
            await update.message.delete()
            print(f"[删除退出消息] 用户 {update.message.from_user.id} 退出群组")
    except Exception as e:
        print(f"[删除退出消息] 失败: {e}")

# ========== 群组事件 ==========
async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != TARGET_GROUP:
        return
    try:
        await update.message.delete()
    except Exception as e:
        print(f"[删除加入消息] 失败: {e}")

    for member in update.message.new_chat_members:
        user_id = member.id
        
        # 检查是否曾被踢出
        if user_id in kicked_users:
            try:
                msg = await context.bot.send_message(
                    chat_id=TARGET_GROUP,
                    text=f"⚠️ 用户 {member.full_name} 曾被移除，需购买会员后才能加入。"
                )
                context.job_queue.run_once(delete_message_after_delay, 10, data={"chat_id": msg.chat_id, "message_id": msg.message_id})
                await context.bot.ban_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
                print(f"[踢人] 用户 {user_id} 曾被踢出，已拒绝加入")
            except Exception as e:
                print(f"[踢人失败] 用户 {user_id} 被拒绝加入: {e}")
            continue

        if await check_user_subscribed(context.application, user_id):
            print(f"[欢迎] 用户 {user_id} 已是会员")
            pending_users.pop(user_id, None)
            save_pending_users()
        else:
            if user_id in pending_users:
                msg = await context.bot.send_message(
                    chat_id=TARGET_GROUP,
                    text=f"⚠️ 用户 {member.full_name} 试用已结束，请购买会员后再加入。"
                )
                context.job_queue.run_once(delete_message_after_delay, 10, data={"chat_id": msg.chat_id, "message_id": msg.message_id})
                try:
                    await context.bot.ban_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
                except Exception as e:
                    print(f"[踢人失败] 试用用户 {user_id}: {e}")
                print(f"[踢人] 用户 {user_id} 试用已结束")
            else:
                msg = await context.bot.send_message(
                    chat_id=TARGET_GROUP,
                    text=f"👋 欢迎 {member.full_name}！你是新用户，24小时内可免费试用，试用期结束后将被踢出本群。续费 20 USDT 请联系管理员。"
                )
                context.job_queue.run_once(delete_message_after_delay, 10, data={"chat_id": msg.chat_id, "message_id": msg.message_id})
                pending_users[user_id] = {"join_time": datetime.now(BEIJING_TZ), "reminded": False}
                save_pending_users()

async def safe_send_message(bot, user_id, text):
    try:
        await bot.send_message(chat_id=user_id, text=text)
        return True
    except Exception as e:
        if "Forbidden" in str(e):
            return False
        print(f"[提醒] 发送消息失败: {e}")
        return False

# ========== 定时检查 ==========
async def remove_unsubscribed_users(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(BEIJING_TZ)

    # 检查试用用户
    for user_id, data in list(pending_users.items()):
        join_time = data["join_time"]
        if isinstance(join_time, str):
            join_time = datetime.fromisoformat(join_time).astimezone(BEIJING_TZ)
        time_left = join_time + timedelta(hours=24) - now

        if timedelta(hours=0) < time_left <= timedelta(hours=3) and not data.get("reminded", False):
            reminder_text = "⏳ 您的 24 小时试用即将到期，剩余 3 小时，请联系管理员续费 20 USDT 成为会员。"
            if not await safe_send_message(context.bot, user_id, reminder_text):
                msg = await context.bot.send_message(
                    chat_id=TARGET_GROUP,
                    text=f"⏳ <a href='tg://user?id={user_id}'>用户</a> {reminder_text}",
                    parse_mode="HTML"
                )
                context.job_queue.run_once(delete_message_after_delay, 10, data={"chat_id": msg.chat_id, "message_id": msg.message_id})
            pending_users[user_id]["reminded"] = True

        # 试用过期 → 踢人并移除记录 + 写入踢出列表
        if time_left <= timedelta(hours=0):
            msg = await context.bot.send_message(
                chat_id=TARGET_GROUP,
                text=f"⚠️ <a href='tg://user?id={user_id}'>用户</a> 试用已到期，将被移出群组！",
                parse_mode="HTML"
            )
            context.job_queue.run_once(delete_message_after_delay, 10, data={"chat_id": msg.chat_id, "message_id": msg.message_id})
            try:
                await context.bot.ban_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
                # 写入踢出列表
                kicked_users[user_id] = {"kicked_time": datetime.now(BEIJING_TZ).isoformat()}
                save_kicked_users()
            except Exception as e:
                print(f"[踢人失败] 试用用户 {user_id}: {e}")
            pending_users.pop(user_id, None)  # 删除试用记录

    # 检查会员
    for user_id, data in list(members.items()):
        expiry_time = data.get("expiry_time")
        if expiry_time:
            expiry_time = datetime.fromisoformat(expiry_time).astimezone(BEIJING_TZ)
            time_left = expiry_time - now
            if timedelta(hours=0) < time_left <= timedelta(hours=3) and not data.get("reminded", False):
                reminder_text = "⏳ 您的会员即将到期，剩余 3 小时，请联系管理员续费。"
                if not await safe_send_message(context.bot, user_id, reminder_text):
                    msg = await context.bot.send_message(
                        chat_id=TARGET_GROUP,
                        text=f"⏳ <a href='tg://user?id={user_id}'>用户</a> {reminder_text}",
                        parse_mode="HTML"
                    )
                    context.job_queue.run_once(delete_message_after_delay, 10, data={"chat_id": msg.chat_id, "message_id": msg.message_id})
                members[user_id]["reminded"] = True

            # 会员过期 → 踢人并移除记录 + 写入踢出列表
            if time_left <= timedelta(hours=0):
                msg = await context.bot.send_message(
                    chat_id=TARGET_GROUP,
                    text=f"⚠️ <a href='tg://user?id={user_id}'>用户</a> 会员已到期，将被移出群组！",
                    parse_mode="HTML"
                )
                context.job_queue.run_once(delete_message_after_delay, 10, data={"chat_id": msg.chat_id, "message_id": msg.message_id})
                try:
                    await context.bot.ban_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
                    # 写入踢出列表
                    kicked_users[user_id] = {"kicked_time": datetime.now(BEIJING_TZ).isoformat()}
                    save_kicked_users()
                except Exception as e:
                    print(f"[踢人失败] 会员 {user_id}: {e}")
                members.pop(user_id, None)  # 删除会员记录

    save_pending_users()
    save_members()

# ========== 会员管理命令 ==========
async def add_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限")
        return
    if len(context.args) == 0:
        await update.message.reply_text("请输入会员的 Telegram ID")
        return
    user_id = int(context.args[0])
    members[user_id] = {
        "join_time": datetime.now(BEIJING_TZ).isoformat(),
        "expiry_time": None,
        "reminded": False
    }
    # 会员加入时，从踢出列表移除
    if user_id in kicked_users:
        kicked_users.pop(user_id)
        save_kicked_users()

    pending_users.pop(user_id, None)
    save_members()
    save_pending_users()
    await update.message.reply_text(f"✅ 已将用户 {user_id} 添加为会员")

async def set_member_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限")
        return
    if len(context.args) < 2:
        await update.message.reply_text("请输入用户ID和天数")
        return
    user_id = int(context.args[0])
    expiry_days = int(context.args[1])
    if user_id in members:
        expiry_time = datetime.now(BEIJING_TZ) + timedelta(days=expiry_days)
        members[user_id]["expiry_time"] = expiry_time.isoformat()
        members[user_id]["reminded"] = False
        # 会员更新时，从踢出列表移除
        if user_id in kicked_users:
            kicked_users.pop(user_id)
            save_kicked_users()

        pending_users.pop(user_id, None)
        save_members()
        save_pending_users()
        await update.message.reply_text(f"✅ 用户 {user_id} 会员有效期设置为 {expiry_days} 天")
    else:
        await update.message.reply_text(f"用户 {user_id} 不是会员")

async def remove_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限")
        return
    if len(context.args) == 0:
        await update.message.reply_text("请输入要删除的会员ID")
        return

    user_id = int(context.args[0])

    if user_id in members:
        # 删除会员记录
        members.pop(user_id)
        save_members()

        # 踢出群组 + 加入踢出列表
        try:
            await context.bot.ban_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
            kicked_users[user_id] = {"kicked_time": datetime.now(BEIJING_TZ).isoformat()}
            save_kicked_users()
            await update.message.reply_text(f"✅ 已删除会员 {user_id} 并踢出群组")
        except Exception as e:
            await update.message.reply_text(f"❌ 删除会员成功，但踢人失败: {e}")
    else:
        await update.message.reply_text(f"用户 {user_id} 不是会员")


async def view_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限")
        return
    if not members:
        await update.message.reply_text("当前没有会员")
    else:
        members_list = "\n".join([
            f"ID: {uid}, 加入: {data['join_time']}, 到期: {data['expiry_time']}"
            for uid, data in members.items()
        ])
        await update.message.reply_text(f"当前会员：\n{members_list}")

# ========== 机器人启动 ==========
def main():
    migrate_data()
    load_members()
    load_pending_users()
    load_kicked_users()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_members))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_user_left))
    app.add_handler(CommandHandler("add_member", add_member))
    app.add_handler(CommandHandler("set_member_expiry", set_member_expiry))
    app.add_handler(CommandHandler("remove_member", remove_member))
    app.add_handler(CommandHandler("view_members", view_members))
    app.job_queue.run_repeating(remove_unsubscribed_users, interval=300, first=10)
    print("🤖 机器人启动成功，管理试用会员与会员功能")
    app.run_polling()

if __name__ == "__main__":
    main()
