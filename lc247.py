import os
import time
import json
import random
import string
import logging
import threading
import requests
import telebot
from datetime import datetime
from telebot import types
from flask import Flask, jsonify

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8844628964:AAE3Wm5VUQIRqhBuwonAFRuuW5eHwPIczIw")
ADMIN_IDS = [7564889663]
CHAT_ID   = os.environ.get("CHAT_ID", "-1004315877426")

API_URL = "https://api.tool247.fun/api/pred-log"
GAME_ID = "lc79_md5"
LIMIT = 50
POLL_INTERVAL = 20

GROUP_LINK = "https://t.me/+LaaT-vDzLo02MDJl"
GROUP_LINK_TEXT = "t.me/+LaaT-vDzLo02MDJl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lc79-bot")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== USER DATA + KEY ====================
user_data = {}
valid_keys = {}
used_keys = set()

def is_admin(user_id):
    return user_id in ADMIN_IDS

def generate_key(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def parse_duration(s):
    s = s.lower().strip()
    if not s: return None
    try:
        if s.endswith('h'): return int(s[:-1]) * 3600
        elif s.endswith('d'): return int(s[:-1]) * 86400
        elif s.endswith('m'): return int(s[:-1]) * 30 * 86400
        else: return None
    except:
        return None

def clean_expired_keys():
    now = time.time()
    expired = [k for k, exp in valid_keys.items() if exp is not None and now > exp]
    for k in expired:
        del valid_keys[k]
    return len(expired)

# ==================== API ====================
def get_data():
    try:
        r = requests.get(API_URL, params={"game": GAME_ID, "limit": LIMIT}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("lich_su"):
            return None
        return {
            "game": data.get("game"),
            "tong": data.get("tong"),
            "dung": data.get("dung"),
            "sai": data.get("sai"),
            "bo_qua": data.get("bo_qua"),
            "chinh_xac": data.get("chinh_xac"),
            "lich_su": data.get("lich_su", []),
        }
    except Exception as e:
        log.warning(f"API err: {e}")
        return None

# ==================== FORMAT ====================
def to_txt(x):
    if not x: return "?"
    x = str(x).lower()
    if "tài" in x or "tai" in x: return "TÀI"
    if "xỉu" in x or "xiu" in x: return "XỈU"
    return "?"

def conf_label(conf):
    try:
        n = int(conf)
    except:
        return "?"
    if n >= 80: return "CAO"
    elif n >= 70: return "KHÁ CAO"
    elif n >= 60: return "TRUNG BÌNH"
    elif n >= 50: return "THẤP"
    else: return "RẤT THẤP"

def send_ai_signal(chat_id, entry):
    """Gửi AI SIGNAL từ 1 entry trong lich_su[]."""
    phien = entry.get("phien", 0)
    ket_qua = to_txt(entry.get("ket_qua"))
    du_doan = to_txt(entry.get("du_doan"))
    conf = entry.get("do_tin_cay", 0)
    pattern = entry.get("loai_cau", "")
    ket_luan = entry.get("ket_luan", "")

    if "Đúng" in ket_luan:
        check_line = f"📊 Kết quả #{phien}: ✅ CHÍNH XÁC  ({ket_qua})"
    elif "Sai" in ket_luan:
        check_line = f"📊 Kết quả #{phien}: ❌ SAI  ({ket_qua})"
    else:
        check_line = f"📊 Kết quả #{phien}: ℹ️  ({ket_qua})"

    caption = (
        f"🎯 <b>AI SIGNAL — LC79 MD5</b>\n"
        f"🏷️ Phiên <b>#{phien}</b> → Dự đoán <b>#{phien + 1}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{check_line}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🔮 Ván <b>#{phien + 1}</b> — Dự báo: <b>{du_doan}</b>\n"
        f"💯 Điểm tin cậy: <b>{conf}%</b>  ({conf_label(conf)})\n"
        f"🎴 <i>{pattern}</i>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💬 Nhóm: <a href='{GROUP_LINK}'>{GROUP_LINK_TEXT}</a>"
    )

    try:
        bot.send_message(chat_id, caption, parse_mode="HTML")
        return True
    except Exception as e:
        log.warning(f"send_ai_signal err to {chat_id}: {e}")
        return False

# ==================== KEYBOARD ====================
def get_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("▶️ Bắt đầu theo dõi"),
        types.KeyboardButton("⏹️ Dừng theo dõi"),
        types.KeyboardButton("📊 Thống kê"),
        types.KeyboardButton("📜 Lịch sử gần đây"),
        types.KeyboardButton("ℹ️ Hướng dẫn"),
    )
    return markup

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start', 'menu'])
def send_menu(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        user_data[chat_id] = {
            "running": False,
            "last_phien": None,
            "activated": False,
        }

    if is_admin(message.from_user.id):
        user_data[chat_id]["activated"] = True

    if not user_data[chat_id]["activated"]:
        bot.send_message(chat_id,
            "🔒 <b>Bot chưa kích hoạt</b>\n\n"
            "Vui lòng nhập key để sử dụng:\n"
            "<code>/key YOUR_KEY</code>",
            parse_mode="HTML")
        return

    text = (
        "🤖 <b>LC79 MD5 BOT v2</b>\n"
        "🧠 Dùng API tool247\n\n"
        "Chọn chức năng:\n"
        "/start_follow — Bắt đầu theo dõi\n"
        "/stop — Dừng theo dõi\n"
        "/stats — Thống kê\n"
        "/history — Lịch sử 10 phiên gần nhất"
    )
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=get_menu_keyboard())

@bot.message_handler(commands=['key'])
def activate_key(message):
    chat_id = message.chat.id
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Cú pháp: /key YOUR_KEY")
        return
    key = args[1].upper().strip()
    if chat_id not in user_data:
        user_data[chat_id] = {
            "running": False,
            "last_phien": None,
            "activated": False,
        }
    if user_data[chat_id]["activated"]:
        bot.reply_to(message, "✅ Tài khoản đã kích hoạt.")
        return
    if key in used_keys:
        bot.reply_to(message, "❌ Key đã được sử dụng.")
        return
    clean_expired_keys()
    if key in valid_keys:
        expire = valid_keys[key]
        if expire is not None and time.time() > expire:
            del valid_keys[key]
            bot.reply_to(message, "❌ Key đã hết hạn.")
            return
        del valid_keys[key]
        used_keys.add(key)
        user_data[chat_id]["activated"] = True
        bot.reply_to(message, "✅ <b>Kích hoạt thành công!</b>\nGõ /menu để bắt đầu.", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Key không hợp lệ hoặc đã hết hạn.")

@bot.message_handler(commands=['taokey'])
def create_key(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Bạn không phải Admin.")
        return
    args = message.text.split()
    so_luong = 1
    duration_str = None
    expire_ts = None
    duration_text = "vĩnh viễn"
    if len(args) >= 2:
        if args[1].isdigit():
            so_luong = min(int(args[1]), 20)
            if len(args) >= 3:
                duration_str = args[2]
        else:
            duration_str = args[1]
    if duration_str:
        seconds = parse_duration(duration_str)
        if seconds is None or seconds <= 0:
            bot.reply_to(message, "❌ Thời hạn không hợp lệ!\nVD: /taokey 1h, /taokey 1d", parse_mode="HTML")
            return
        expire_ts = time.time() + seconds
        num = duration_str[:-1]
        unit = duration_str[-1].lower()
        if unit == 'h': duration_text = f"{num} giờ"
        elif unit == 'd': duration_text = f"{num} ngày"
        elif unit == 'm': duration_text = f"{num} tháng"
    keys = []
    for _ in range(so_luong):
        k = generate_key()
        valid_keys[k] = expire_ts
        keys.append(k)
    text = f"🔑 <b>Đã tạo {so_luong} key</b> ({duration_text}):\n\n"
    for k in keys:
        text += f"<code>{k}</code>\n"
    if expire_ts:
        expire_dt = datetime.fromtimestamp(expire_ts).strftime("%H:%M %d/%m/%Y")
        text += f"\n⏰ Hết hạn: {expire_dt}"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['xoakey', 'delkey'])
def delete_key(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Bạn không phải Admin.")
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Cú pháp: /xoakey KEY hoặc /xoakey all")
        return
    if args[1].upper() == "ALL":
        count = len(valid_keys)
        valid_keys.clear()
        bot.reply_to(message, f"✅ Đã xóa tất cả {count} key.")
        return
    deleted = []; not_found = []
    for raw in args[1:]:
        key = raw.upper().strip()
        if key in valid_keys:
            del valid_keys[key]; deleted.append(key)
        else:
            not_found.append(key)
    text = ""
    if deleted:
        text += f"✅ Đã xóa: <code>{'</code>, <code>'.join(deleted)}</code>\n"
    if not_found:
        text += f"❌ Không tìm thấy: <code>{'</code>, <code>'.join(not_found)}</code>"
    bot.reply_to(message, text.strip() or "Không có key nào được xóa.", parse_mode="HTML")

@bot.message_handler(commands=['listkey'])
def list_keys(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Bạn không phải Admin.")
        return
    clean_expired_keys()
    if not valid_keys:
        bot.reply_to(message, "📭 Không có key nào đang hiệu lực.")
        return
    text = f"🔑 <b>Danh sách key ({len(valid_keys)}):</b>\n\n"
    sorted_keys = sorted(valid_keys.items(), key=lambda x: (x[1] is not None, x[1] or 0))
    for k, exp in sorted_keys:
        if exp is None:
            text += f"<code>{k}</code> — <b>Vĩnh viễn</b>\n"
        else:
            dt = datetime.fromtimestamp(exp).strftime("%H:%M %d/%m/%Y")
            remain = exp - time.time()
            if remain > 86400: remain_text = f"{int(remain // 86400)} ngày"
            elif remain > 3600: remain_text = f"{int(remain // 3600)} giờ"
            else: remain_text = f"{int(remain // 60)} phút"
            text += f"<code>{k}</code> — Hết: {dt} (còn {remain_text})\n"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['start_follow'])
@bot.message_handler(func=lambda m: m.text == "▶️ Bắt đầu theo dõi")
def start_follow(message):
    chat_id = message.chat.id
    if chat_id not in user_data or not user_data[chat_id].get("activated"):
        bot.reply_to(message, "🔒 Chưa kích hoạt."); return
    if user_data[chat_id]["running"]:
        bot.reply_to(message, "⚠️ Đang theo dõi rồi!"); return
    user_data[chat_id]["running"] = True
    user_data[chat_id]["last_phien"] = None
    bot.reply_to(message, "▶️ Bắt đầu theo dõi LC79 MD5.\nSẽ gửi AI SIGNAL mỗi phiên.", parse_mode="HTML")

@bot.message_handler(commands=['stop'])
@bot.message_handler(func=lambda m: m.text == "⏹️ Dừng theo dõi")
def stop_follow(message):
    chat_id = message.chat.id
    if chat_id in user_data:
        user_data[chat_id]["running"] = False
    bot.reply_to(message, "⏹️ Đã dừng theo dõi.")

@bot.message_handler(commands=['stats'])
@bot.message_handler(func=lambda m: m.text == "📊 Thống kê")
def show_stats(message):
    chat_id = message.chat.id
    if chat_id not in user_data or not user_data[chat_id].get("activated"):
        bot.reply_to(message, "🔒 Chưa kích hoạt."); return
    data = get_data()
    if not data:
        bot.reply_to(message, "❌ Không lấy được dữ liệu API"); return
    text = (
        f"📊 <b>THỐNG KÊ TOOL247 — {data['game'].upper()}</b>\n\n"
        f"📦 Tổng: <b>{data['tong']}</b>\n"
        f"✅ Đúng: <b>{data['dung']}</b>\n"
        f"❌ Sai: <b>{data['sai']}</b>\n"
        f"⏸ Bỏ qua: <b>{data['bo_qua']}</b>\n"
        f"🎯 Chính xác: <b>{data['chinh_xac']}</b>"
    )
    bot.send_message(chat_id, text, parse_mode="HTML")

@bot.message_handler(commands=['history'])
@bot.message_handler(func=lambda m: m.text == "📜 Lịch sử gần đây")
def show_history(message):
    chat_id = message.chat.id
    if chat_id not in user_data or not user_data[chat_id].get("activated"):
        bot.reply_to(message, "🔒 Chưa kích hoạt."); return
    data = get_data()
    if not data:
        bot.reply_to(message, "❌ Không lấy được dữ liệu API"); return
    text = "📜 <b>10 PHIÊN GẦN NHẤT</b>\n\n"
    for entry in data["lich_su"][:10]:
        phien = entry.get("phien", 0)
        ket_qua = to_txt(entry.get("ket_qua"))
        du_doan = to_txt(entry.get("du_doan"))
        conf = entry.get("do_tin_cay", 0)
        ket_luan = entry.get("ket_luan", "")
        icon = "✅" if "Đúng" in ket_luan else "❌" if "Sai" in ket_luan else "•"
        text += f"{icon} <b>#{phien}</b>: {ket_qua} → dự đoán {du_doan} ({conf}%)\n"
    bot.send_message(chat_id, text, parse_mode="HTML")

@bot.message_handler(commands=['group_on'])
def group_on(m):
    if not is_admin(m.from_user.id): return
    if CHAT_ID:
        user_data[CHAT_ID] = {"running": True, "last_phien": None, "activated": True}
        bot.reply_to(m, f"✅ Bật gửi nhóm: <code>{CHAT_ID}</code>", parse_mode="HTML")

@bot.message_handler(commands=['group_off'])
def group_off(m):
    if not is_admin(m.from_user.id): return
    if CHAT_ID and CHAT_ID in user_data:
        user_data[CHAT_ID]["running"] = False
        bot.reply_to(m, "🔴 Tắt gửi nhóm.")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Hướng dẫn")
def help_msg(message):
    text = (
        "<b>📖 HƯỚNG DẪN LC79 MD5 BOT</b>\n\n"
        "1. Nhập key: <code>/key YOUR_KEY</code>\n"
        "2. Bắt đầu: <b>▶️ Bắt đầu theo dõi</b>\n"
        "3. Xem thống kê: <b>📊 Thống kê</b>\n"
        "4. Xem lịch sử: <b>📜 Lịch sử gần đây</b>\n\n"
        "<b>Admin:</b>\n"
        "/taokey 1d — Tạo key 1 ngày\n"
        "/xoakey KEY — Xóa key\n"
        "/listkey — Xem key\n"
        "/group_on — Bật gửi nhóm\n"
        "/group_off — Tắt gửi nhóm"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# ==================== MONITORING LOOP ====================
def monitoring_loop():
    log.info("Monitoring loop started")
    while True:
        try:
            data = get_data()
            if not data:
                time.sleep(POLL_INTERVAL); continue

            lich_su = data.get("lich_su", [])
            if not lich_su:
                time.sleep(POLL_INTERVAL); continue

            entry = lich_su[0]
            current_phien = entry.get("phien", 0)

            for chat_id, info in list(user_data.items()):
                if not info.get("running") or not info.get("activated"):
                    continue
                if info.get("last_phien") == current_phien:
                    continue

                send_ai_signal(chat_id, entry)
                info["last_phien"] = current_phien

            time.sleep(POLL_INTERVAL)
        except Exception as e:
            log.error(f"Lỗi monitoring: {e}")
            time.sleep(5)

# ==================== FLASK ====================
flask_app = Flask(__name__)
_start = time.time()

@flask_app.route("/")
def home():
    return jsonify({
        "status": "ok", "service": "lc79-bot-v2",
        "uptime": round(time.time() - _start, 2),
        "users": len(user_data),
        "keys": len(valid_keys),
        "group_chat": CHAT_ID,
    })

@flask_app.route("/health")
def health():
    return jsonify({"status": "healthy", "users": len(user_data)})

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==================== MAIN ====================
def main():
    log.info("=" * 60)
    log.info("LC79 MD5 BOT v2 ĐANG CHẠY")
    log.info(f"API: {API_URL}?game={GAME_ID}&limit={LIMIT}")
    log.info(f"Admin IDs: {ADMIN_IDS}")
    log.info(f"Group Chat: {CHAT_ID}")
    log.info("=" * 60)

    # Tự động bật theo dõi cho nhóm chat
    if CHAT_ID:
        try:
            user_data[CHAT_ID] = {
                "running": True,
                "last_phien": None,
                "activated": True,
            }
            log.info(f"✅ Đã bật auto gửi cho nhóm {CHAT_ID}")
        except Exception as e:
            log.warning(f"Không thể setup group chat: {e}")

    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=monitoring_loop, daemon=True).start()
    bot.infinity_polling(timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    main()
