import os
import subprocess
import sys
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
import pytz
import asyncio

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

# ================= 配置 =================

BOT_TOKEN = "8327100795:AAHrFOBT5K-LHgW4IqdGY1CyJysSCXiQXDU"

ADMIN_ID = 8107909168
GROUP_ID = -1003878983546

TRIAL_HOURS = 24
REMIND_HOURS = 3
DELETE_DELAY = 3

BEIJING = pytz.timezone("Asia/Shanghai")

# ================= 日志 =================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ================= 数据库 =================

db = sqlite3.connect(
    "bot.db",
    check_same_thread=False,
    isolation_level=None
)

db_lock = threading.Lock()


def db_execute(sql, args=()):
    with db_lock:
        cur = db.cursor()
        cur.execute(sql, args)
        db.commit()
        return cur


db_execute("""
CREATE TABLE IF NOT EXISTS members(
user_id INTEGER PRIMARY KEY,
expire_time TEXT
)
""")

db_execute("""
CREATE TABLE IF NOT EXISTS trials(
user_id INTEGER PRIMARY KEY,
join_time TEXT,
reminded INTEGER
)
""")

db_execute("""
CREATE TABLE IF NOT EXISTS kicked(
user_id INTEGER PRIMARY KEY,
kick_time TEXT
)
""")

# ================= 工具 =================


def now():
    return datetime.now(BEIJING)


def is_admin(uid):
    return uid == ADMIN_ID


async def auto_delete(context: ContextTypes.DEFAULT_TYPE):
    msg = context.job.data
    try:
        await context.bot.delete_message(msg.chat_id, msg.message_id)
    except:
        pass


# ================= 工具 =================

async def send_temp(context, text, chat_id=GROUP_ID, delay=DELETE_DELAY):
    """
    发送临时消息，并显示倒计时
    """
    # 发送初始消息
    msg = await context.bot.send_message(
        chat_id,
        f"{text}\n\n⏳ 消息将在 {delay} 秒后自动删除"
    )

    # 每秒更新倒计时
    for remaining in range(delay - 1, 0, -1):
        try:
            await msg.edit_text(f"{text}\n\n⏳ 消息将在 {remaining} 秒后自动删除")
            await asyncio.sleep(1)
        except Exception as e:
            # 消息被删除或编辑失败就停止
            logging.warning(f"倒计时更新失败: {e}")
            break

    # 最终删除消息
    try:
        await msg.delete()
    except Exception as e:
        logging.warning(f"自动删除消息失败: {e}")


async def kick_user(context, uid, reason="未通过试用或会员到期"):
    """
    踢出用户并私聊通知原因，同时在群里显示倒计时提示
    """
    try:
        # 先尝试私聊通知
        try:
            await context.bot.send_message(
                uid,
                f"⚠️ 你已被移出群聊\n原因: {reason}\n如有疑问请联系管理员"
            )
        except Exception as e:
            logging.warning(f"通知用户 {uid} 失败，用户可能未与机器人私聊过: {e}")

        # 踢出群
        await context.bot.ban_chat_member(GROUP_ID, uid)
        await context.bot.unban_chat_member(GROUP_ID, uid)

        # 在群里发送临时消息显示倒计时
        await send_temp(context, f"⚠️ 用户 {uid} 已被移出群聊，原因: {reason}")

        # 记录数据库
        db_execute(
            "INSERT OR REPLACE INTO kicked VALUES(?,?)",
            (uid, now().isoformat())
        )

        logging.info(f"踢出用户 {uid}, 原因: {reason}")

    except Exception as e:
        logging.error(f"踢人失败 {uid}: {e}")


# ================= 群成员检测 =================


async def user_in_group(context, uid):

    try:

        m = await context.bot.get_chat_member(GROUP_ID, uid)

        if m.status in ["member", "administrator", "creator"]:
            return True

        return False

    except:
        return False


async def clean_database(context):

    logging.info("同步群成员状态")

    rows = db_execute("SELECT user_id FROM trials").fetchall()

    for (uid,) in rows:

        inside = await user_in_group(context, uid)

        if not inside:

            db_execute(
                "DELETE FROM trials WHERE user_id=?",
                (uid,)
            )

    rows = db_execute("SELECT user_id FROM members").fetchall()

    for (uid,) in rows:

        inside = await user_in_group(context, uid)

        if not inside:

            db_execute(
                "DELETE FROM members WHERE user_id=?",
                (uid,)
            )


# ================= 新成员 =================


async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.id != GROUP_ID:
        return

    try:
        await update.message.delete()
    except:
        pass

    for m in update.message.new_chat_members:

        uid = m.id

        r = db_execute(
            "SELECT * FROM kicked WHERE user_id=?",
            (uid,)
        ).fetchone()

        if r:
            await kick_user(context, uid)
            continue

        r = db_execute(
            "SELECT * FROM members WHERE user_id=?",
            (uid,)
        ).fetchone()

        if r:
            continue

        r = db_execute(
            "SELECT * FROM trials WHERE user_id=?",
            (uid,)
        ).fetchone()

        if r:
            await kick_user(context, uid)
            continue

        db_execute(
            "INSERT INTO trials VALUES(?,?,0)",
            (uid, now().isoformat())
        )

        await send_temp(
            context,
            f"👋 欢迎 {m.full_name}\n\n"
            f"你可以免费试用 {TRIAL_HOURS} 小时"
        )


    # ================= 删除离开消息 =================
async def delete_kick_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not hasattr(msg, "left_chat_member"):
        return
    try:
        user_name = msg.left_chat_member.full_name
        text = f"⚠️ 用户 {user_name} 已离开群聊"
        # 用 send_temp 处理倒计时删除
        await send_temp(context, text, chat_id=msg.chat_id, delay=DELETE_DELAY)
        # 删除原消息
        await msg.delete()
    except Exception as e:
        logging.warning(f"删除 LEFT_CHAT_MEMBER 消息失败: {e}")

# ================= 定时检查 =================


async def check_users(context: ContextTypes.DEFAULT_TYPE):

    current = now()

    logging.info("定时检查运行")

    rows = db_execute("SELECT * FROM trials").fetchall()

    for uid, join, reminded in rows:

        # 如果已经是会员，跳过
        r = db_execute(
            "SELECT * FROM members WHERE user_id=?",
            (uid,)
        ).fetchone()

        if r:
            continue

        join = datetime.fromisoformat(join).astimezone(BEIJING)

        expire = join + timedelta(hours=TRIAL_HOURS)

        left = expire - current

        if left <= timedelta(0):
            await send_temp(context, f"⚠️ 用户 {uid} 试用到期")
            await kick_user(context, uid, reason="试用到期")
            db_execute("DELETE FROM trials WHERE user_id=?", (uid,))

        elif left <= timedelta(hours=REMIND_HOURS) and reminded == 0:
            try:
                await context.bot.send_message(uid, "⏳ 试用剩余3小时，请联系管理员续费")
            except:
                pass

            await send_temp(context, f"⏳ 用户 {uid} 试用剩余3小时")
            db_execute("UPDATE trials SET reminded=1 WHERE user_id=?", (uid,))

    rows = db_execute("SELECT * FROM members").fetchall()

    for uid, expire in rows:

        if expire is None:
            continue

        expire = datetime.fromisoformat(expire).astimezone(BEIJING)

        if expire <= current:
            await send_temp(context, f"⚠️ 用户 {uid} 会员到期")
            await kick_user(context, uid, reason="会员到期")
            db_execute("DELETE FROM members WHERE user_id=?", (uid,))

    await clean_database(context)


# ================= 管理命令 =================

async def kicked_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    rows = db_execute("SELECT * FROM kicked").fetchall()

    if not rows:
        await update.message.reply_text("没有封禁用户")
        return

    text = "封禁用户列表\n\n"

    for uid, kick_time in rows:
        kick_time = datetime.fromisoformat(kick_time).astimezone(BEIJING)
        try:
            member = await context.bot.get_chat_member(GROUP_ID, uid)
            name = member.user.full_name
        except:
            name = "未知用户"

        text += f"{name} ({uid}) 封禁时间 {kick_time.strftime('%Y-%m-%d %H:%M')}\n"

    await update.message.reply_text(text)

def update_bot():
    try:
        # 拉取最新代码
        subprocess.run(["git", "pull"], check=True)
        # 重启脚本
        os.execv(sys.executable, ["python"] + sys.argv)
    except Exception as e:
        print("更新失败:", e)

async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 只允许管理员私聊机器人触发
    if update.effective_user.id != ADMIN_ID:
        return

    if update.effective_chat.type != "private":
        await update.message.reply_text("请在私聊中使用此命令更新机器人")
        return

    msg = await update.message.reply_text("🔄 正在检查更新...")

    try:
        # git 拉取最新代码
        result = subprocess.run(
            ["git", "pull"], capture_output=True, text=True
        )

        output = result.stdout.strip()

        if "Already up to date." in output:
            await msg.edit_text("✅ 未找到新代码，已经是最新版本")
            return

        # 找到新代码
        await msg.edit_text("⚡ 找到新代码，正在更新...")

        # 可选：显示 git 输出摘要
        summary = "\n".join(output.splitlines()[-5:])  # 只取最后5行
        await context.bot.send_message(
            ADMIN_ID,
            f"Git 拉取输出:\n{summary}"
        )

        await msg.edit_text("✅ 更新完成，正在重启机器人...")

        # 重启脚本
        os.execv(sys.executable, [sys.executable] + sys.argv)

    except Exception as e:
        await msg.edit_text(f"❌ 更新失败: {e}")

async def trials_list(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    rows = db_execute("SELECT * FROM trials").fetchall()

    if not rows:
        await update.message.reply_text("没有试用用户")
        return

    text = "试用用户\n\n"

    for uid, join, _ in rows:

        join = datetime.fromisoformat(join).astimezone(BEIJING)

        expire = join + timedelta(hours=TRIAL_HOURS)

        # 获取用户名
        try:
            member = await context.bot.get_chat_member(GROUP_ID, uid)
            name = member.user.full_name
        except:
            name = "未知用户"

        text += f"{name} ({uid}) 到期 {expire.strftime('%Y-%m-%d %H:%M')}\n"

    await update.message.reply_text(text)

async def members_list(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    rows = db_execute("SELECT * FROM members").fetchall()

    if not rows:
        await update.message.reply_text("没有会员")
        return

    text = "会员列表\n\n"

    for uid, expire in rows:

        if expire:

            expire = datetime.fromisoformat(expire).astimezone(BEIJING)

            try:
                member = await context.bot.get_chat_member(GROUP_ID, uid)
                name = member.user.full_name
            except:
                name = "未知用户"

            text += f"{name} ({uid}) 到期 {expire.strftime('%Y-%m-%d %H:%M')}\n"

        else:
            try:
                member = await context.bot.get_chat_member(GROUP_ID, uid)
                name = member.user.full_name
            except:
                name = str(uid)
            text += f"{name} 永久会员\n"

    await update.message.reply_text(text)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 1:
        await update.message.reply_text("用法: /unban 用户ID")
        return

    uid = int(context.args[0])

    try:
        await context.bot.unban_chat_member(GROUP_ID, uid)
    except:
        pass

    db_execute(
        "DELETE FROM kicked WHERE user_id=?",
        (uid,)
    )

    await update.message.reply_text("用户已解封")

async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 1:
        await update.message.reply_text("用法: /kick 用户ID [原因]")
        return

    uid = int(context.args[0])
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "管理员操作"

    await kick_user(context, uid, reason=reason)

    await update.message.reply_text("用户已踢出")

async def add_trial(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 1:
        await update.message.reply_text("用法: /trial 用户ID")
        return

    uid = int(context.args[0])

    r = db_execute(
        "SELECT * FROM members WHERE user_id=?",
        (uid,)
    ).fetchone()

    if r:
        await update.message.reply_text("该用户已经是会员")
        return

    r = db_execute(
        "SELECT * FROM trials WHERE user_id=?",
        (uid,)
    ).fetchone()

    if r:
        await update.message.reply_text("该用户已经在试用")
        return

    db_execute(
        "INSERT INTO trials VALUES(?,?,0)",
        (uid, now().isoformat())
    )

    await update.message.reply_text("试用添加成功")

async def add_member(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 1:
        await update.message.reply_text("用法: /add 用户ID")
        return

    uid = int(context.args[0])

    db_execute(
        "INSERT OR REPLACE INTO members VALUES(?,NULL)",
        (uid,)
    )

    db_execute("DELETE FROM trials WHERE user_id=?", (uid,))
    db_execute("DELETE FROM kicked WHERE user_id=?", (uid,))

    await update.message.reply_text("会员添加成功")


async def extend_member(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text("用法: /extend 用户ID 天数")
        return

    uid = int(context.args[0])
    days = int(context.args[1])

    r = db_execute(
        "SELECT expire_time FROM members WHERE user_id=?",
        (uid,)
    ).fetchone()

    if r and r[0]:

        old = datetime.fromisoformat(r[0]).astimezone(BEIJING)

        if old > now():
            expire = old + timedelta(days=days)
        else:
            expire = now() + timedelta(days=days)

    else:

        expire = now() + timedelta(days=days)

    db_execute(
        "INSERT OR REPLACE INTO members VALUES(?,?)",
        (uid, expire.isoformat())
    )

    db_execute(
        "DELETE FROM trials WHERE user_id=?",
        (uid,)
    )

    await update.message.reply_text("会员延期成功")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    trials = db_execute("SELECT COUNT(*) FROM trials").fetchone()[0]
    members = db_execute("SELECT COUNT(*) FROM members").fetchone()[0]
    kicked = db_execute("SELECT COUNT(*) FROM kicked").fetchone()[0]

    text = (
        f"📊 机器人统计\n\n"
        f"试用用户: {trials}\n"
        f"会员: {members}\n"
        f"封禁: {kicked}"
    )

    await update.message.reply_text(text)


# ================= 启动 =================


def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            new_member
        )
    )

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.LEFT_CHAT_MEMBER,
            delete_kick_message
        )
    )

    app.add_handler(CommandHandler("add", add_member))
    app.add_handler(CommandHandler("extend", extend_member))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("trial", add_trial))
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("members", members_list))
    app.add_handler(CommandHandler("trials", trials_list))
    app.add_handler(CommandHandler("update", update_command))
    app.add_handler(CommandHandler("kicked", kicked_list))

    app.job_queue.run_repeating(check_users, 300, first=10)

    logging.info("机器人启动成功")

    app.run_polling()


if __name__ == "__main__":
    main()
