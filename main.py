import re
import asyncio
import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ========== 配置 ==========
BOT_TOKEN = "8281720118:AAFBTiE2NHqeYJ5L4o53GPuFFDbEJMDlrpY"
TARGET_GROUP = -1002741490869
CHANNEL_ID = "@VEXEGX"
OWNER_GROUP_ID = -1002615680129
ADMIN_USER_ID = 7596698993

FILTER_KEYWORDS = ["精聊", "刷单", "大区", "股票", "换汇", "博彩", "菠菜", "公检法", "料", "车", "通道", "源头", "支付"]
FILTER_REGEXES = [r".*支付.*群", r".*换汇.*", r".*博彩.*"]
COUNTRIES = [
    "阿富汗","阿尔巴尼亚","阿尔及利亚","安道尔","安哥拉","安提瓜和巴布达","阿根廷","亚美尼亚","澳大利亚","奥地利",
    "阿塞拜疆","巴哈马","巴林","孟加拉国","巴巴多斯","白俄罗斯","比利时","伯利兹","贝宁","不丹",
    "玻利维亚","波斯尼亚和黑塞哥维那","博茨瓦纳","巴西","文莱","保加利亚","布基纳法索","布隆迪","柬埔寨","喀麦隆",
    "加拿大","佛得角","中非共和国","乍得","智利","中国","哥伦比亚","科摩罗","刚果（布）","刚果（金）",
    "库克群岛","哥斯达黎加","克罗地亚","古巴","塞浦路斯","捷克","丹麦","吉布提","多米尼加","多米尼加共和国",
    "厄瓜多尔","埃及","萨尔瓦多","赤道几内亚","厄立特里亚","爱沙尼亚","斯威士兰","埃塞俄比亚","斐济","芬兰",
    "法国","加蓬","冈比亚","格鲁吉亚","德国","加纳","希腊","格林纳达","危地马拉","几内亚",
    "几内亚比绍","圭亚那","海地","洪都拉斯","匈牙利","冰岛","印度","印度尼西亚","伊朗","伊拉克",
    "爱尔兰","以色列","意大利","牙买加","日本","约旦","哈萨克斯坦","肯尼亚","基里巴斯","韩国",
    "科威特","吉尔吉斯斯坦","老挝","拉脱维亚","黎巴嫩","莱索托","利比里亚","利比亚","列支敦士登","立陶宛",
    "卢森堡","马达加斯加","马拉维","马来西亚","马尔代夫","马里","马耳他","马绍尔群岛","毛里塔尼亚","毛里求斯",
    "墨西哥","密克罗尼西亚","摩尔多瓦","摩纳哥","蒙古","黑山","摩洛哥","莫桑比克","缅甸","纳米比亚",
    "瑙鲁","尼泊尔","荷兰","新西兰","尼加拉瓜","尼日尔","尼日利亚","北马其顿","挪威","阿曼",
    "巴基斯坦","帕劳","巴拿马","巴布亚新几内亚","巴拉圭","秘鲁","菲律宾","波兰","葡萄牙","卡塔尔",
    "罗马尼亚","俄罗斯","卢旺达","圣基茨和尼维斯","圣卢西亚","圣文森特和格林纳丁斯","萨摩亚","圣马力诺","圣多美和普林西比","沙特阿拉伯",
    "塞内加尔","塞尔维亚","塞舌尔","塞拉利昂","新加坡","斯洛伐克","斯洛文尼亚","所罗门群岛","索马里","南非",
    "南苏丹","西班牙","斯里兰卡","苏丹","苏里南","瑞典","瑞士","叙利亚","塔吉克斯坦","坦桑尼亚",
    "泰国","多哥","汤加","特立尼达和多巴哥","突尼斯","土耳其","土库曼斯坦","图瓦卢","乌干达","乌克兰",
    "阿拉伯联合酋长国","英国","美国","乌拉圭","乌兹别克斯坦","瓦努阿图","梵蒂冈","委内瑞拉","越南","也门",
    "赞比亚","津巴布韦"
]
AD_KEYWORDS = ["买卖", "拉群", "招募", "代理", "广告", "推广", "刷单", "加群", "联系我", "中石化", "油卡", "实体卡", "联系我", "NFC", "快手", "抖音", "抖币", "油", "散户", "境外", "礼品卡", "核销", "ATM", "取现", "柜台", "扫码", "兼职", "刷信誉"]
AD_PATTERNS = [r"t\.me\/", r"telegram\.me\/", r"tg:\/\/join", r"@[\w_]+", r"https?:\/\/"]

ADD_KEYWORD, = range(1)

# ========== 待关注用户持久化 ==========
PENDING_USERS_FILE = "pending_users.json"
pending_users = {}

def load_pending_users():
    global pending_users
    if os.path.exists(PENDING_USERS_FILE):
        try:
            with open(PENDING_USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            pending_users = {int(k): datetime.fromisoformat(v) for k, v in data.items()}
            print(f"[加载] 待关注用户 {len(pending_users)} 条")
        except Exception as e:
            print(f"[加载] 读取失败: {e}")
            pending_users = {}
    else:
        pending_users = {}

def save_pending_users():
    try:
        data = {str(k): v.isoformat() for k, v in pending_users.items()}
        with open(PENDING_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[保存] 待关注用户 {len(pending_users)} 条")
    except Exception as e:
        print(f"[保存] 保存失败: {e}")

# ========== 工具函数 ==========
def is_admin(user_id):
    return user_id == ADMIN_USER_ID

def text_matches_filters(text: str) -> bool:
    text_lower = text.lower()
    for kw in FILTER_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    for country in COUNTRIES:
        if country.lower() in text_lower:
            return True
    for pattern in FILTER_REGEXES:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def text_contains_ads(text: str) -> bool:
    text_lower = text.lower()
    for kw in AD_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    for pattern in AD_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

async def check_user_subscribed(app, user_id) -> bool:
    try:
        channel_status = await app.bot.get_chat_member(CHANNEL_ID, user_id)
        group_status = await app.bot.get_chat_member(OWNER_GROUP_ID, user_id)
    except Exception as e:
        print(f"[检查订阅] user_id={user_id} 查询异常: {e}")
        return False

    def is_subscribed(status):
        return status.status in [ChatMember.MEMBER, ChatMember.OWNER, ChatMember.ADMINISTRATOR]

    return is_subscribed(channel_status) and is_subscribed(group_status)

# ========== 关键词管理 ==========
async def start_manage_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限使用此命令")
        return
    keyboard = [
        [InlineKeyboardButton("添加关键词", callback_data="add_keyword")],
        [InlineKeyboardButton("删除关键词", callback_data="del_keyword")],
        [InlineKeyboardButton("查看关键词列表", callback_data="show_keywords")],
    ]
    await update.message.reply_text("请选择操作：", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ 你没有权限操作")
        return

    data = query.data
    if data == "add_keyword":
        await query.edit_message_text("请输入要添加的关键词：")
        return ADD_KEYWORD

    elif data == "show_keywords":
        if not FILTER_KEYWORDS:
            await query.edit_message_text("关键词列表为空")
        else:
            text = "当前关键词列表：\n" + "\n".join(f"{i+1}. {kw}" for i, kw in enumerate(FILTER_KEYWORDS))
            await query.edit_message_text(text)

    elif data == "del_keyword":
        if not FILTER_KEYWORDS:
            await query.edit_message_text("关键词列表为空")
            return
        keyboard = [[InlineKeyboardButton(kw, callback_data=f"del_kw_{i}")] for i, kw in enumerate(FILTER_KEYWORDS)]
        keyboard.append([InlineKeyboardButton("取消", callback_data="cancel")])
        await query.edit_message_text("选择要删除的关键词：", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("del_kw_"):
        idx = int(data.split("_")[-1])
        if 0 <= idx < len(FILTER_KEYWORDS):
            removed = FILTER_KEYWORDS.pop(idx)
            await query.edit_message_text(f"✅ 已删除关键词：{removed}")
        else:
            await query.edit_message_text("索引错误")

    elif data == "cancel":
        await query.edit_message_text("操作已取消")

async def add_keyword_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限")
        return ConversationHandler.END
    text = update.message.text.strip()
    if text in FILTER_KEYWORDS:
        await update.message.reply_text("⚠️ 关键词已存在")
    else:
        FILTER_KEYWORDS.append(text)
        await update.message.reply_text(f"✅ 添加成功：{text}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("操作已取消")
    return ConversationHandler.END

# ========== 新成员加入检查 ==========
async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):

# 只针对目标群
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
        subscribed = await check_user_subscribed(app, user_id)
        if subscribed:
            print(f"[欢迎] 用户 {user_id} 已关注频道和群组")
        else:
            await context.bot.send_message(
                chat_id=TARGET_GROUP,
                text=f"👋 欢迎 {member.full_name}！请先关注频道 https://t.me/VEXEGX 和群组 https://t.me/VEXECN ，否则24小时后将被移出本群。"
            )
            pending_users[user_id] = datetime.utcnow()
            save_pending_users()

# ========== 定时踢人 ==========
async def remove_unsubscribed_users(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow()
    to_remove = []
    for user_id, join_time in pending_users.items():
        if now - join_time > timedelta(hours=24):
            try:
                await context.bot.ban_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
                print(f"[踢人] 移除未关注用户：{user_id}")
                to_remove.append(user_id)
            except Exception as e:
                print(f"[踢人] 失败: {e}")
    for user_id in to_remove:
        pending_users.pop(user_id, None)
    if to_remove:
        save_pending_users()

# ========== 自动删广告 & 转发 ==========
async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message

    # 不监听目标群组消息，避免重复转发或循环转发
    if chat.id == TARGET_GROUP:
        return

    if chat.type not in ["group", "supergroup", "channel"]:
        return
    text = msg.text or ""
    if text_contains_ads(text):
        try:
            await msg.delete()
            print(f"[广告] 删除广告消息: {text}")
        except Exception as e:
            print(f"[广告] 删除失败: {e}")
        return
    if text and not text_matches_filters(text):
        return
    try:
        await context.bot.forward_message(
            chat_id=TARGET_GROUP,
            from_chat_id=chat.id,
            message_id=msg.message_id
        )
        print(f"[转发] 来自 {chat.id}")
    except Exception as e:
        print(f"[转发] 失败: {e}")

# ========== 主程序 ==========
def main():
    load_pending_users()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("manage_filters", start_manage_filters)],
        states={ADD_KEYWORD: [MessageHandler(filters.TEXT & (~filters.COMMAND), add_keyword_received)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_members))
    app.job_queue.run_repeating(remove_unsubscribed_users, interval=3600, first=10)
    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), forward_message))

    print("🤖 机器人启动成功，监控广告、管理关键词，检查关注并24小时踢未关注用户")
    app.run_polling()

if __name__ == "__main__":
    main()
