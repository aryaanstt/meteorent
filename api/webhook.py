# --- IMPORTS WAJIB ---
import os
import json
import logging # Tambahkan untuk debugging
from airtable import Airtable
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage 

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# --- KONEKSI AIRTABLE ---
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.getenv('AIRTABLE_TABLE_NAME', 'Table 1') # Default 'Table 1'

airtable = None
if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
    try:
        airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, AIRTABLE_API_KEY)
        logging.info("Airtable Connection Initiated Successfully!")
    except Exception as e:
        logging.error(f"Error initializing Airtable: {e}")
else:
    logging.warning("Airtable Environment Variables Missing!")


# --- LINE BOT API ---
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')

if CHANNEL_ACCESS_TOKEN and CHANNEL_SECRET:
    line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(CHANNEL_SECRET)
else:
    logging.error("LINE API keys are missing!")


# --- ROUTE WEBHOOK ---
@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/secret.")
        abort(400)
    
    return 'OK'

# --- FUNGSI UTAMA: MENANGANI PESAN ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    if airtable is None:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="Error: Database tidak terhubung. Cek log server.")
        )
        return

    text_from_user = event.message.text
    line_user_id = event.source.user_id

    # 1. CARI USER DI AIRTABLE UNTUK CEK STATUS
    try:
        user_records = airtable.match('LINE_ID', line_user_id) 
    except Exception as e:
        logging.error(f"Airtable lookup error: {e}")
        user_records = None

    if user_records:
        # --- USER LAMA DITEMUKAN (LOGIKA STATE MANAGEMENT) ---
        user_data = user_records['fields']
        user_record_id = user_records['id']
        current_status = user_data.get('STATUS')

        if current_status == 'MENUNGGU_NAMA':
            # LOGIKA MENYIMPAN NAMA & NIM DARI INPUT TEKS
            # Pastikan format input (misal: "Budi, 120220123") di sini
            try:
                nama, nim = text_from_user.split(', ')
                
                # Update Airtable
                airtable.update(user_record_id, {'NAMA': nama, 'NIM': nim, 'STATUS': 'MENUNGGU_KTM'})
                
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='Data dicatat. Sekarang, silakan kirim foto KTM kamu sebagai Image Message.')
                )
            except ValueError:
                 line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text='Format salah. Mohon kirim dengan format: Nama, NIM (contoh: Budi, 120220123).')
                )

        elif current_status == 'READY':
            # LOGIKA PINJAM / TRANSAKSI DARI INPUT TEKS
            # ... LOGIKA KAMU DI SINI
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f'Hai {user_data.get("NAMA")}. Statusmu READY. Kamu bisa PINJAM.')
            )

        else:
            # RESPON DEFAULT JIKA STATUS DIKENAL
            pass
            
    else:
        # --- USER BARU (REGISTRASI AWAL) ---
        new_record = {
            'LINE_ID': line_user_id,
            'STATUS': 'MENUNGGU_NAMA'
        }
        airtable.insert(new_record)
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='Selamat datang! Silakan kirim Nama dan NIM (contoh: Budi, 120220123).')
        )

# --- HANDLE IMAGE MESSAGE (untuk KTM) ---
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    # LOGIKA KAMU DI SINI untuk mengambil image dan mendapatkan URL
    # Setelah URL didapatkan, gunakan airtable.update() untuk menyimpan LINK_KTM
    pass


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 8000))
