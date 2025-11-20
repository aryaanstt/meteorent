from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage,
    QuickReply, QuickReplyButton, MessageAction
)
import sqlite3
import os
from datetime import datetime
import random 
import traceback 

# ----------------- KUNCI API DARI ENVIRONMENT VARIABLES VERCEL -------------------------
# Gunakan os.environ.get untuk membaca kunci dari Vercel
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET', 'YOUR_DEFAULT_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN', 'YOUR_DEFAULT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL', './meteorent_db.db') 
KTM_FOLDER = os.environ.get('KTM_FOLDER', '/tmp/ktm_uploads') # Vercel hanya bisa menyimpan di /tmp

# PENTING: Jika menggunakan PostgreSQL/Supabase, kode koneksi DB di bawah HARUS diubah
# menggunakan psycopg2 dan alamat DATABASE_URL
# ---------------------------------------------------------------------------------------

app = Flask(__name__)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# --- FUNGSI HELPER DB (Perlu disesuaikan untuk Postgres) ---
def get_db_connection():
    # SAAT INI MASIH MENGGUNAKAN SQLITE UNTUK SIMPLISITAS
    # UNTUK VERSEL PRODUKSI, GANTI KODE INI KE POSTGRESQL/PSYCOPG2
    conn = sqlite3.connect(DATABASE_URL) 
    conn.row_factory = sqlite3.Row
    return conn

def generate_pin():
    # FUNGSI INI SUDAH TIDAK DIPAKAI, KARENA PIN DIAMBIL DARI TABEL daily_pin
    return "0000" 

def get_daily_pin(conn):
    # Mengambil PIN dari DB
    daily_pin_data = conn.execute("SELECT pin_code FROM daily_pin WHERE id = 1").fetchone()
    return daily_pin_data['pin_code'] if daily_pin_data else '9999'

# Helper Quick Replies (Sama seperti sebelumnya)
qr_shelter = QuickReply(items=[
    QuickReplyButton(action=MessageAction(label="Shelter 1 (Ganesha)", text="SHELTER_BORROW_1")),
    QuickReplyButton(action=MessageAction(label="Shelter 2 (Jati)", text="SHELTER_BORROW_2")), 
])
qr_shelter_return = QuickReply(items=[
    QuickReplyButton(action=MessageAction(label="Shelter 1 (Ganesha)", text="SHELTER_RETURN_1")),
    QuickReplyButton(action=MessageAction(label="Shelter 2 (Jati)", text="SHELTER_RETURN_2")),
])
qr_verifikasi = QuickReply(items=[
    QuickReplyButton(action=MessageAction(label="1. Nama", text="MASUKKAN NAMA")),
    QuickReplyButton(action=MessageAction(label="2. NIM", text="MASUKKAN NIM")),
    QuickReplyButton(action=MessageAction(label="3. KTM", text="UPLOAD KTM")),
])


# Dictionary untuk menyimpan status percakapan setiap user (State Management)
# CATATAN: DI SERVERLESS VERCEL, DICTIONARY INI AKAN DIRESET SETIAP ADA PESAN.
# STATE HARUSNYA DISIMPAN DI DATABASE (e.g., Redis/Postgres JSONB Field).
# UNTUK APLIKASI AWAL, KITA TETAP GUNAKAN DICT INI UNTUK DEBUGGING CEPAT.
user_states = {} 


@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        # Panggil handler untuk memproses event
        handler.handle(body, signature, callback)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 1. HANDLER UTAMA ---
# Fungsi ini dipanggil oleh WebhookHandler
def callback(event):
    if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
        handle_text_message(event)
    elif isinstance(event, MessageEvent) and isinstance(event.message, ImageMessage):
        handle_image_message(event)
    # Tambahkan handler untuk event lain jika diperlukan (e.g., PostbackEvent)


def handle_text_message(event):
    user_id = event.source.user_id 
    user_text = event.message.text.upper().strip() 
    
    conn = None 
    reply_message = TextSendMessage(text="System Error: Unknown")

    try:
        conn = get_db_connection()
        current_stage = user_states.get(user_id, {}).get('stage', 'DEFAULT')
        
        # ------------------ LOGIKA MULTISTEP FORM & VALIDASI ------------------
        # [KODE LOGIKA UTAMA PINJAM/KEMBALI/NAMA/NIM ADA DI SINI, SAMA DENGAN SEL 5 FINAL]

        # A. HANDLE AWAL PINJAM
        if user_text == "PINJAM" and current_stage == 'DEFAULT':
            active_loan = conn.execute("SELECT * FROM transactions WHERE user_id = ? AND status = 'ON_LOAN'", (user_id,)).fetchone()
            
            if active_loan:
                reply_message = TextSendMessage(text="❌ Kamu masih punya pinjaman aktif! Harap mengembalikan payung terlebih dahulu.")
            else:
                user_states[user_id] = {'stage': 'WAITING_FOR_BORROW_SHELTER'}
                reply_message = TextSendMessage(text="Baik, silakan pilih shelter tempat Anda akan meminjam payung:", quick_reply=qr_shelter)
        
        # B. HANDLE PEMILIHAN SHELTER PINJAM
        elif "SHELTER_BORROW_" in user_text and current_stage == 'WAITING_FOR_BORROW_SHELTER':
            shelter = 'Shelter 1 (Ganesha)' if user_text == 'SHELTER_BORROW_1' else 'Shelter 2 (Jatinangor)'
            user_states[user_id]['shelter'] = shelter
            
            user_data = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            
            if not user_data:
                user_states[user_id]['stage'] = 'WAITING_FOR_NAMA_INPUT' 
                reply_message = TextSendMessage(text=f"Shelter {shelter} dicatat. Sekarang, masukkan **Nama Lengkap** Anda:")
            else:
                user_nim = user_data['nim']
                user_states[user_id]['stage'] = 'WAITING_FOR_NIM_CONFIRM' 
                user_states[user_id]['nim_terdaftar'] = user_nim
                reply_message = TextSendMessage(text=f"Shelter {shelter} dicatat. Mohon konfirmasi **NIM** Anda ({user_nim[:-3]}XXX):")

        # C. PENGGUNA BARU: Minta Nama
        elif current_stage == 'WAITING_FOR_NAMA_INPUT':
            nama = event.message.text 
            user_states[user_id]['nama'] = nama
            user_states[user_id]['stage'] = 'WAITING_FOR_NIM_INPUT'
            reply_message = TextSendMessage(text=f"Nama **{nama}** sudah dicatat. Masukkan **NIM** Anda:")
            
        # D. PENGGUNA BARU: Minta NIM
        elif current_stage == 'WAITING_FOR_NIM_INPUT': 
            nim = event.message.text.strip()
            user_states[user_id]['nim'] = nim
            user_states[user_id]['stage'] = 'WAITING_FOR_KTM_UPLOAD'
            reply_message = TextSendMessage(text=f"NIM **{nim}** sudah dicatat. Terakhir, silakan **Upload FOTO KTM** Anda untuk verifikasi.")

        # E. PENGGUNA LAMA: Handle Konfirmasi NIM
        elif current_stage == 'WAITING_FOR_NIM_CONFIRM':
            input_nim = event.message.text.strip()
            nim_terdaftar = user_states[user_id]['nim_terdaftar']

            if input_nim == nim_terdaftar:
                pin_code = get_daily_pin(conn) 
                borrow_shelter = user_states[user_id]['shelter']
                
                conn.execute(
                    "INSERT INTO transactions (user_id, pinjam_time, borrow_shelter, pin, status) VALUES (?, datetime('now'), ?, ?, 'ON_LOAN')",
                    (user_id, borrow_shelter, pin_code)
                )
                conn.commit()
                del user_states[user_id] 
                
                reply_message = TextSendMessage(text=f"✅ Pinjaman dicatat! **PIN UNTUK MEMBUKA GEMBOK: {pin_code}**\nPayung siap digunakan di {borrow_shelter}. Selamat menggunakan!")
                
                line_bot_api.reply_message(event.reply_token, reply_message)
                conn.close()
                return 
            else:
                del user_states[user_id] 
                reply_message = TextSendMessage(text="❌ NIM salah. Transaksi dibatalkan. Mohon coba PINJAM lagi dengan NIM yang benar.")

        # F. HANDLE BALIK / KEMBALI
        elif user_text in ["BALIK", "KEMBALI"] and current_stage == 'DEFAULT':
            active_loan = conn.execute("SELECT id FROM transactions WHERE user_id = ? AND status = 'ON_LOAN'", (user_id,)).fetchone()
            
            if active_loan:
                user_states[user_id] = {'stage': 'WAITING_FOR_RETURN_SHELTER', 'loan_id': active_loan['id']}
                reply_message = TextSendMessage(text="Silakan pilih shelter tempat Anda mengembalikan payung:", quick_reply=qr_shelter_return)
            else:
                reply_message = TextSendMessage(text="🤔 Kamu tidak sedang meminjam payung saat ini.")

        # G. HANDLE PEMILIHAN SHELTER KEMBALI
        elif "SHELTER_RETURN_" in user_text and current_stage == 'WAITING_FOR_RETURN_SHELTER':
            return_shelter = 'Shelter 1 (Ganesha)' if user_text == 'SHELTER_RETURN_1' else 'Shelter 2 (Jatinangor)'
            loan_id = user_states[user_id]['loan_id']
            
            conn.execute(
                "UPDATE transactions SET kembali_time = datetime('now'), return_shelter = ?, status = 'RETURNED' WHERE id = ?",
                (return_shelter, loan_id)
            )
            conn.commit()
            del user_states[user_id]
            reply_message = TextSendMessage(text=f"🎉 Terima kasih! Payung berhasil dikembalikan di {return_shelter}. Transaksi selesai.")
        
        # H. DEFAULT RESPONSE
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
        # Logika Vercel error handling harus lebih efisien, tapi kita kirim pesan error untuk debugging
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


def handle_image_message(event):
    user_id = event.source.user_id 
    current_state_info = user_states.get(user_id, {})
    current_stage = current_state_info.get('stage', 'DEFAULT')
    conn = None
    reply_message = TextSendMessage(text="System Error: Unknown")

    try:
        conn = get_db_connection()
        
        if current_stage == 'WAITING_FOR_KTM_UPLOAD': 
            nama = current_state_info.get('nama')
            nim = current_state_info.get('nim')
            borrow_shelter = current_state_info.get('shelter')

            if not (nama and nim and borrow_shelter):
                reply_message = TextSendMessage(text="❌ Proses verifikasi belum lengkap. Mohon ulangi dari awal [PINJAM].")
                del user_states[user_id] 
                line_bot_api.reply_message(event.reply_token, reply_message)
                return

            # 1. Simpan KTM (HANYA placeholder, perlu AWS S3/Cloudinary untuk Vercel)
            message_content = line_bot_api.get_message_content(event.message.id)
            file_name = f'ktm_{user_id}_{datetime.now().strftime("%Y%m%d%H%M%S")}.jpg'
            save_path = os.path.join(KTM_FOLDER, file_name) 
            
            # Placeholder for saving file: In Vercel, files saved to /tmp are deleted after the function runs
            with open(save_path, 'wb') as wf:
                for chunk in message_content.iter_content():
                    wf.write(chunk)
            
            # 2. Masukkan data user ke database
            conn.execute(
                "INSERT OR REPLACE INTO users (user_id, nama, nim, ktm_url, is_verified) VALUES (?, ?, ?, ?, 1)",
                (user_id, nama, nim, save_path) 
            )
            conn.commit()
            
            # 3. AMBIL PIN DARI DB dan Catat Transaksi
            pin_code = get_daily_pin(conn) 
            
            conn.execute(
                "INSERT INTO transactions (user_id, pinjam_time, borrow_shelter, pin, status) VALUES (?, datetime('now'), ?, ?, 'ON_LOAN')",
                (user_id, borrow_shelter, pin_code)
            )
            conn.commit()
            
            del user_states[user_id] 
            
            reply_message = TextSendMessage(text=f"✅ Verifikasi berhasil dan pinjaman dicatat!\n**PIN UNTUK MEMBUKA GEMBOK: {pin_code}**\nPayung siap digunakan di {borrow_shelter}. Selamat menggunakan!")
        
        else:
            reply_message = TextSendMessage(text="Terima kasih atas gambarnya! Kami hanya menerima foto KTM saat proses verifikasi.")
             
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"FATAL IMAGE EXCEPTION TRACE:\n{error_trace}")
        
        error_msg = f"🚨 FATAL CRASH (Image Handler):\n {e}"
        reply_message = TextSendMessage(text=error_msg)
             
    finally:
        if conn:
            conn.close()
            
    line_bot_api.reply_message(event.reply_token, reply_message)


# Handle callback from webhook
def handler(environ, start_response):
    return app(environ, start_response)
