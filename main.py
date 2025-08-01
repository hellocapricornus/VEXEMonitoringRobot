import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

BOT_TOKEN = "8281720118:AAFBTiE2NHqeYJ5L4o53GPuFFDbEJMDlrpY"
TARGET_GROUP = -1002741490869
CHANNEL_ID = "@VEXEGX"
OWNER_GROUP_ID = -1002615680129
ADMIN_USER_ID = 7596698993

FILTER_KEYWORDS = [
    "精聊", "刷单", "大区", "股票", "换汇", "博彩", "菠菜", "公检法",
    "料", "车", "通道", "源头", "支付"
]
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

AD_KEYWORDS = [
    "买卖", "拉群", "招募", "代理", "广告", "推广", "刷单", "加群",
    "联系我", "扫码", "兼职", "刷信誉"
]
AD_PATTERNS = [
    r"t\.me\/", r"telegram\.me\/", r"tg:\/\/join",
    r"@[\w_]+", r"https?:\/\/",
]

ADD_KEYWORD = 1

# 记录待关注用户，格式 {user_id: join_time}
pending_users = {}

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
        ch = await app.bot.get_chat_member(CHANNEL_ID, user_id)
        gp = await app.bot.get_chat_member(OWNER_GROUP_ID, user_id)
    except Exception as e:
        print(f"[订阅检查异常] user_id={user_id} 错误: {e}")
        return False
    valid_status = {ChatMember.MEMBER, ChatMember.OWNER, ChatMember.ADMINISTRATOR}
    return ch.status in valid_status and gp.status in valid_status

async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    app = context.application
    for member in update.message.new_chat_members:
        user_id = member.id
        subscribed = await check_user_subscribed(app, user_id)
        if subscribed:
            print(f"用户{user_id}已关注频道和群组")
        else:
            await update.message.reply_text(
                f"👋 欢迎 {member.full_name}！请先关注频道 https://t.me/VEXEGX 和群组 https://t.me/VEXECN ，"
                "否则24小时后将被移出本群。"
            )
            pending_users[user_id] = datetime.utcnow()

async def remove_unsubscribed_users(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow()
    to_remove = []
    for user_id, join_time in list(pending_users.items()):
        if now - join_time > timedelta(hours=24):
            try:
                await context.bot.ban_chat_member(chat_id=TARGET_GROUP, user_id=user_id)
                print(f"踢出未关注用户：{user_id}")
                to_remove.append(user_id)
            except Exception as e:
                print(f"踢出用户失败: {e}")

    for user_id in to_remove:
        pending_users.pop(user_id, None)

# 关键词管理入口和处理省略，可参考你原有代码，确保在 main() 中注册好 handler

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.message
    if chat.type not in ["group", "supergroup", "channel"]:
        return
    text = msg.text or ""

    if text_contains_ads(text):
        try:
            await msg.delete()
            print(f"删除广告消息: {text}")
        except Exception as e:
            print(f"删除消息失败: {e}")
        return

    if text and not text_matches_filters(text):
        return

    try:
        await context.bot.forward_message(
            chat_id=TARGET_GROUP,
            from_chat_id=chat.id,
            message_id=msg.message_id
        )
        print(f"转发消息来自 {chat.type}：{chat.title or chat.id} ({chat.id})")
    except Exception as e:
        print(f"转发失败: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # 这里注册你的关键词管理、按钮回调等handler

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_members))
    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), forward_message))

    # 启动定时任务检查未关注用户（注意：PTB要求job_queue非None）
    app.job_queue.run_repeating(remove_unsubscribed_users, interval=3600, first=10)

    print("机器人启动，监听消息和新成员，自动管理订阅和踢人。")
    app.run_polling()

if __name__ == "__main__":
    main()
