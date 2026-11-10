import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime, time
from io import BytesIO
from PIL import Image
import math
import pytz

# Proteksi impor untuk streamlit-js-eval
try:
    from streamlit_js_eval import get_geolocation, streamlit_js_eval
    JS_EVAL_AVAILABLE = True
except ImportError:
    JS_EVAL_AVAILABLE = False

# Definisi Zona Waktu Asia/Jakarta (WIB)
TZ_WIB = pytz.timezone('Asia/Jakarta')

# Folder Penyimpanan Foto Selfie
FOLDER_FOTO = "folder_foto_absen"
os.makedirs(FOLDER_FOTO, exist_ok=True)

# ====================================================
# 1. KONFIGURASI HALAMAN & CUSTOM CSS STYLING
# ====================================================
st.set_page_config(
    page_title="Sistem Absensi Pintar - Kantor Utama",
    page_icon="🏢",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .stApp {
        background-color: #f8fafc;
    }
    h1 {
        color: #1e293b;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
        width: 100%;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
    </style>
""", unsafe_allow_html=True)

# ====================================================
# 2. KONFIGURASI DATA KANTOR & DATABASE
# ====================================================
KANTOR_LATITUDE = -6.983120          
KANTOR_LONGITUDE = 112.489525
RADIUS_MAKSIMAL_METER = 150

BATAS_JAM_MASUK = time(8, 0, 0)

KARYAWAN_DATA = {
    "05001908": "Lila Aditya Perdana",
    "05002370": "Hendra",
    "05002376": "Dian Candra Wijaya",
    "05002729": "Angga Setia Permana",
    "05002934": "Arif Yuliadi",
    "05003750": "Septian Chandra",
    "05003758": "Alfian Nurhuda",
    "05004639": "Budi Setyawan",
    "05004711": "Khoirul Rijal",
    "05005032": "Maxbafasya Aditya Wibowo",
    "05005331": "Dwi Nor Fais",
    "05007005": "Rachmad Dani",
    "05007150": "Lurico Umar Raffsanjani",
    "05007173": "Diska Akbar Hermanto",
    "05007712": "Nur Nuhammad Khoirul Firmansyah",
    "05008111": "Mohammad Holidi"
}

DB_NAME = "absen_master.db"

# ====================================================
# 3. SISTEM DATABASE (SQLITE)
# ====================================================
def inisialisasi_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS absensi (
            tanggal TEXT,
            id_karyawan TEXT,
            nama TEXT,
            waktu_presensi TEXT,
            koordinat_gps TEXT,
            latitude REAL,
            longitude REAL,
            jarak_dari_kantor REAL,
            status TEXT,
            device_info TEXT,
            path_foto TEXT
        )
    """)
    
    # Cek apakah kolom path_foto sudah ada (untuk migrasi database lama)
    cursor.execute("PRAGMA table_info(absensi)")
    kolom = [kol[1] for kol in cursor.fetchall()]
    if "path_foto" not in kolom:
        cursor.execute("ALTER TABLE absensi ADD COLUMN path_foto TEXT")
        conn.commit()

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_absen_unique 
        ON absensi(tanggal, id_karyawan)
    """)
    conn.commit()
    conn.close()

inisialisasi_database()

def muat_data_absen():
    conn = sqlite3.connect(DB_NAME)
    try:
        df = pd.read_sql_query("""
            SELECT tanggal AS Tanggal, id_karyawan AS ID, nama AS Nama, 
                   waktu_presensi AS [Waktu Presensi], koordinat_gps AS [Koordinat GPS], 
                   latitude AS Latitude, longitude AS Longitude, 
                   jarak_dari_kantor AS [Jarak (meter)], status AS Status,
                   device_info AS [Perangkat], path_foto AS [Path Foto]
            FROM absensi
            ORDER BY waktu_presensi DESC
        """, conn)
    except Exception:
        df = pd.DataFrame(columns=[
            "Tanggal", "ID", "Nama", "Waktu Presensi", "Koordinat GPS",
            "Latitude", "Longitude", "Jarak (meter)", "Status", "Perangkat", "Path Foto"
        ])
    conn.close()
    return df

def simpan_absen(tanggal, emp_id, nama, waktu_str, koordinat_str, lat, lon, jarak, status, device_info, path_foto):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO absensi 
            (tanggal, id_karyawan, nama, waktu_presensi, koordinat_gps, latitude, longitude, jarak_dari_kantor, status, device_info, path_foto)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tanggal, emp_id, nama, waktu_str, koordinat_str, lat, lon, jarak, status, device_info, path_foto))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# ====================================================
# 4. FUNGSI BANTU
# ====================================================
def hitung_jarak_meter(lat1, lon1, lat2, lon2):
    R = 6371000  
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def parsing_device_info(ua_string):
    if not ua_string:
        return "Unknown Device"
    ua_lower = ua_string.lower()
    os_name, browser_name = "Desktop / PC", "Browser Lain"

    if "iphone" in ua_lower: os_name = "iOS (iPhone)"
    elif "ipad" in ua_lower: os_name = "iOS (iPad)"
    elif "android" in ua_lower: os_name = "Android"
    elif "windows" in ua_lower: os_name = "Windows"
    elif "macintosh" in ua_lower or "mac os" in ua_lower: os_name = "MacOS"
    elif "linux" in ua_lower: os_name = "Linux"

    if "edg" in ua_lower: browser_name = "Edge"
    elif "chrome" in ua_lower and "chromium" not in ua_lower: browser_name = "Chrome"
    elif "safari" in ua_lower and "chrome" not in ua_lower: browser_name = "Safari"
    elif "firefox" in ua_lower: browser_name = "Firefox"
    elif "whatsapp" in ua_lower: browser_name = "WhatsApp In-App Browser"

    return f"{os_name} - {browser_name}"

# ====================================================
# 5. TAMPILAN UTAMA (UI)
# ====================================================
st.markdown("<h1 style='text-align: center; margin-bottom: 5px;'>Absensi Karyawan Gresik Bungah</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #64748b; margin-bottom: 30px;'>Sistem Verifikasi Geofencing & Live Selfie Terpadu</p>", unsafe_allow_html=True)

if 'notifikasi_sukses' in st.session_state:
    st.balloons()
    st.success(st.session_state.pop('notifikasi_sukses'))
elif 'notifikasi_peringatan' in st.session_state:
    st.warning(st.session_state.pop('notifikasi_peringatan'))

if not JS_EVAL_AVAILABLE:
    st.error("Library `streamlit-js-eval` belum terinstall di requirements.txt!")
    st.stop()

user_agent_header = ""
try:
    if hasattr(st, "context") and hasattr(st.context, "headers"):
        user_agent_header = st.context.headers.get("User-Agent", "")
except Exception:
    pass

waktu_sekarang_wib = datetime.now(TZ_WIB)
hari_ini = waktu_sekarang_wib.strftime("%Y-%m-%d")

with st.expander("📍 Informasi Radius & Lokasi Kantor"):
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        st.markdown(f"**Koordinat Pusat:**\n`{KANTOR_LATITUDE}, {KANTOR_LONGITUDE}`")
    with col_exp2:
        st.markdown(f"**Batas Maksimal Radius:**\n`{RADIUS_MAKSIMAL_METER} meter`\n\n**Batas Jam Masuk:** `08:00 WIB`")

# Cek Pembatasan 1 HP 1x Absen per Hari via localStorage
key_ls = f"sudah_absen_perangkat_{hari_ini}"
device_sudah_absen = streamlit_js_eval(js_expressions=f"localStorage.getItem('{key_ls}')", key=f"check_ls_{hari_ini}")

if device_sudah_absen == "true":
    st.error(f"❌ **Akses Ditolak!** Perangkat ini sudah digunakan untuk absensi pada hari ini ({hari_ini}).")
else:
    st.markdown("### 📍 Verifikasi Lokasi GPS Anda")
    st.info("💡 Pastikan GPS aktif dan berikan izin akses lokasi (*Allow*) pada browser.")

    loc = get_geolocation()

    if not loc or not isinstance(loc, dict) or not loc.get("coords"):
        st.warning("⏳ Menunggu sinyal koordinat GPS dari perangkat Anda...")
    else:
        user_lat = loc["coords"]["latitude"]
        user_lon = loc["coords"]["longitude"]
        jarak = hitung_jarak_meter(user_lat, user_lon, KANTOR_LATITUDE, KANTOR_LONGITUDE)
        dalam_radius = jarak <= RADIUS_MAKSIMAL_METER

        m1, m2 = st.columns(2)
        with m1:
            st.metric(label="📍 Jarak Anda ke Kantor", value=f"{jarak:.1f} meter")
        with m2:
            st.metric(label="🎯 Batas Maksimal", value=f"{RADIUS_MAKSIMAL_METER} meter")

        if dalam_radius:
            st.success("✅ **Lokasi Valid!** Anda berada di dalam jangkauan kantor.")
            st.markdown("---")
            st.markdown("### 📸 Form Presensi & Live Selfie")
            
            with st.form(key="form_absensi_selfie"):
                emp_id = st.selectbox(
                    "Pilih Nama Karyawan Anda",
                    list(KARYAWAN_DATA.keys()),
                    format_func=lambda x: f"{x} — {KARYAWAN_DATA[x]}"
                )
                
                # Wajib Foto Selfie Langsung Menggunakan Kamera HP
                picture = st.camera_input("Ambil Foto Selfie Kehadiran Anda Saat Ini")
                
                submit_button = st.form_submit_button("🚀 Kirim Absensi Sekarang", type="primary")
                
                if submit_button:
                    if picture is None:
                        st.error("❌ Anda wajib mengambil foto selfie terlebih dahulu melalui kamera!")
                    else:
                        waktu_sekarang = datetime.now(TZ_WIB)
                        waktu_str = waktu_sekarang.strftime("%Y-%m-%d %H:%M:%S")
                        koordinat_str = f"{user_lat:.6f},{user_lon:.6f}"
                        nama_karyawan = KARYAWAN_DATA[emp_id]
                        info_perangkat = parsing_device_info(user_agent_header)

                        # Simpan file fisik foto ke folder server
                        bytes_data = picture.getvalue()
                        img = Image.open(BytesIO(bytes_data))
                        
                        nama_file_foto = f"{FOLDER_FOTO}/{emp_id}_{waktu_sekarang.strftime('%Y%m%d_%H%M%S')}.jpg"
                        img.save(nama_file_foto, "JPEG")

                        # Logika Jam Masuk (08:00 WIB)
                        waktu_presensi_jam = waktu_sekarang.time()
                        status_teks = "Terima Kasih Telah Datang Tepat Waktu" if waktu_presensi_jam <= BATAS_JAM_MASUK else "Terlambat"

                        # Simpan ke Database SQLite
                        berhasil = simpan_absen(
                            hari_ini, emp_id, nama_karyawan, waktu_str, 
                            koordinat_str, user_lat, user_lon, jarak, status_teks, info_perangkat, nama_file_foto
                        )

                        if berhasil:
                            # Kunci browser ini agar tidak bisa absen lagi hari ini
                            streamlit_js_eval(js_expressions=f"localStorage.setItem('{key_ls}', 'true')", key=f"set_ls_{hari_ini}")

                            if waktu_presensi_jam <= BATAS_JAM_MASUK:
                                st.session_state['notifikasi_sukses'] = f"🎉 **Absensi Berhasil!**\nTerima kasih **{nama_karyawan}**, Anda datang Tepat Waktu pada pukul {waktu_sekarang.strftime('%H:%M:%S')} WIB."
                            else:
                                st.session_state['notifikasi_peringatan'] = f"⚠️ **Absensi Berhasil (Terlambat)!**\n**{nama_karyawan}** tercatat hadir pada pukul {waktu_sekarang.strftime('%H:%M:%S')} WIB."
                            
                            st.rerun()
                        else:
                            st.warning(f"⚠️ **{nama_karyawan}** sudah melakukan absensi sebelumnya hari ini ({hari_ini}). Data duplikat ditolak.")
        else:
            st.error(f"❌ **Lokasi Ditolak!** Jarak Anda ({jarak:.1f} m) berada di luar batas operasional kantor ({RADIUS_MAKSIMAL_METER} m).")

# ====================================================
# 6. PANEL ADMIN (MONITORING & EXPORT)
# ====================================================
st.markdown("---")
st.markdown("### 📊 Panel Monitoring Absensi Real-time")

df_absen = muat_data_absen()

if not df_absen.empty:
    st.dataframe(df_absen, use_container_width=True)
else:
    st.info("📭 Belum ada riwayat data presensi karyawan yang tercatat untuk hari ini.")

st.write("") 

col1, col2 = st.columns(2)
with col1:
    waktu_unduh = datetime.now(TZ_WIB).strftime("%Y%m%d_%H%M%S")
    data_excel = BytesIO()
    with pd.ExcelWriter(data_excel, engine='openpyxl') as writer:
        df_absen.to_excel(writer, index=False, sheet_name='Master Absensi')
    
    st.download_button(
        label="📥 Unduh Laporan (Excel)",
        data=data_excel.getvalue(),
        file_name=f"log_absensi_{waktu_unduh}_WIB.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
with col2:
    if st.button("🗑️ Reset Semua Log Absensi", type="secondary", use_container_width=True):
        st.session_state['konfirmasi_reset'] = True

if st.session_state.get('konfirmasi_reset', False):
    st.write("")
    st.warning("⚠️ **PERINGATAN:** Tindakan ini bersifat destruktif dan akan menghapus seluruh data riwayat absensi secara permanen.")
    
    input_pass = st.text_input("Masukkan Password Keamanan Admin:", type="password", key="pass_reset_admin")
    
    c_sub1, c_sub2 = st.columns(2)
    with c_sub1:
        if st.button("❌ Batalkan", use_container_width=True, key="btn_batal_reset"):
            st.session_state['konfirmasi_reset'] = False
            st.rerun()
            
    with c_sub2:
        if st.button("🔥 Hapus Permanen Sekarang", type="primary", use_container_width=True, key="btn_eksekusi_reset"):
            if input_pass == "admin123":
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM absensi")
                conn.commit()
                conn.close()
                
                st.session_state.pop('konfirmasi_reset', None)
                st.session_state['notifikasi_sukses'] = "🗑️ Seluruh riwayat log absensi berhasil dibersihkan secara permanen!"
                st.rerun()
            else:
                st.error("❌ Password Admin salah! Aksi dibatalkan.")
