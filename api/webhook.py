from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage,
    QuickReply, QuickReplyButton, MessageAction
)
# GANTI DRIVER DATABASE DARI SQLITE KE POSTGRESQL
import psycopg2 
import psycopg2.extras # Untuk hasil query kolom bernama
import urllib.parse # Untuk memparsing DATABASE_URL
import os
from datetime import datetime
import random 
import traceback 

# ----------------- KUNCI API DARI ENVIRONMENT VARIABLES VERCEL -------------------------
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET', 'YOUR_DEFAULT_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN', 'YOUR_DEFAULT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost:5432/meteorent') # Ambil dari Vercel Env Var
KTM_FOLDER = os.environ.get('KTM_FOLDER', '/tmp/ktm_uploads') 
# ---------------------------------------------------------------------------------------

app = Flask(__name__)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# --- FUNGSI HELPER DB (FIX: MENGGUNAKAN POSTGRESQL) ---
def get_db_connection():
    # Parsing DATABASE_URL dari Vercel
    urllib.parse.uses_netloc.append("postgresql")
    url = urllib.parse.urlparse(os.environ.get('DATABASE_URL'))
    
    # KONEKSI POSTGRES
    conn = psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    # Menggunakan DictCursor agar hasil query bisa diakses dengan nama kolom
    return conn

def get_daily_pin(conn):
    # Mengambil PIN dari DB
    # NOTE: Menggunakan kursor standar, bukan DictRow
    cur = conn.cursor()
    cur.execute("SELECT pin_code FROM daily_pin WHERE id = 1")
    daily_pin_data = cur.fetchone()
    cur.close()
    return daily_pin_data[0] if daily_pin_data else '9999'

# Helper Quick Replies (Sama)
qr_shelter = QuickReply(items=[
    QuickReplyButton(action=MessageAction(label="Shelter 1 (Ganesha)", text="SHELTER_BORROW_1")),
    QuickReplyButton(action=MessageAction(label="Shelter 2 (Jati)", text="SHELTER_BORROW_2")),
])
qr_shelter_return = QuickReply(items=[
    QuickReplyButton(action=MessageAction(label="Shelter 1 (Ganesha)", text="SHELTER_RETURN_1")),
    QuickReplyButton(action=MessageAction(label="Shelter 2 (Jati)", text="SHELTER_RETURN_2")),
])


@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- LOGIKA BOT UTAMA ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id 
    user_text = event.message.text.upper().strip() 
    
    conn = None 
    reply_message = TextSendMessage(text="System Error: Unknown")

    try:
        conn = get_db_connection()
        current_stage = user_states.get(user_id, {}).get('stage', 'DEFAULT')
        
        # A. HANDLE AWAL PINJAM
        if user_text == "PINJAM" and current_stage == 'DEFAULT':
            # FIX: Menggunakan SQL dan parameter placeholder yang benar
            cur = conn.cursor()
            cur.execute("SELECT * FROM transactions WHERE user_id = %s AND status = 'ON_LOAN'", (user_id,))
            active_loan = cur.fetchone()
            cur.close()
            
            if active_loan:
                reply_message = TextSendMessage(text="❌ Kamu masih punya pinjaman aktif! Harap mengembalikan payung terlebih dahulu.")
            else:
                user_states[user_id] = {'stage': 'WAITING_FOR_BORROW_SHELTER'}
                reply_message = TextSendMessage(text="Baik, silakan pilih shelter tempat Anda akan meminjam payung:", quick_reply=qr_shelter)
        
        # ... (Semua logika lainnya harus diubah dari ? menjadi %s untuk PostgreSQL) ...

        # G. DEFAULT RESPONSE
        else: 
            reply_message = TextSendMessage(text="Selamat datang di Meteorent! Silakan pilih menu utama di bawah.")

        # --- Kirim Balasan Sukses ---
        line_bot_api.reply_message(
            event.reply_token,
            reply_message
        )
        
    except Exception as e:
        # Menangkap CRASH dan Mengirim Error ke Chat
        error_trace = traceback.format_exc()
        print(f"FATAL EXCEPTION TRACE:\n{error_trace}")
        
        error_msg = f"🚨 FATAL CRASH\nMohon maaf, terjadi error sistem. Berikut detailnya: {e}"
        
        try:
             line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=error_msg)
            )
        except:
             pass 

    finally:
        if conn:
            conn.close()

# ... (HANDLER IMAGE HARUS DIGANTI JUGA MENGGUNAKAN CURSOR DAN %S) ...
