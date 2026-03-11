from flask import Flask, render_template, request, redirect, url_for, session, flash
import json, os, uuid, threading
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import urllib.request as urlreq

# ── Green API WhatsApp Ayarları ──
GREENAPI_INSTANCE = '7107542627'
GREENAPI_TOKEN    = '125b775fb9c04ffdafbc8b1f4cba063026daef4d2726430db6'
WHATSAPP_GROUP_ID = '120363404684824390@g.us'

app = Flask(__name__)
app.secret_key = 'kama-gizli-anahtar-2026'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

DATA_FILE  = os.path.join('data', 'kayitlar.json')
USERS_FILE = os.path.join('data', 'kullanicilar.json')
LOGS_FILE  = os.path.join('data', 'loglar.json')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(f):
    return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

def load_users():  return load_json(USERS_FILE, [])
def save_users(u): save_json(USERS_FILE, u)
def load_data():   return load_json(DATA_FILE, [])
def save_data(d):  save_json(DATA_FILE, d)
def load_logs():   return load_json(LOGS_FILE, [])

def get_user(username):
    return next((u for u in load_users() if u['username'] == username), None)

def get_ip():
    """Gerçek IP adresini al (proxy arkasında da çalışır)."""
    return (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.headers.get('X-Real-IP', '')
            or request.remote_addr
            or '?')

def log_kaydet(islem, detay='', durum='✅', kullanici=None):
    """Sistem logu kaydet."""
    try:
        loglar = load_logs()
        user = kullanici or session.get('user', {})
        loglar.append({
            'id': str(uuid.uuid4())[:8],
            'zaman': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            'kullanici_adi': user.get('ad_soyad', '—'),
            'username': user.get('username', '—'),
            'rol': user.get('role', '—'),
            'ip': get_ip(),
            'islem': islem,
            'detay': detay,
            'durum': durum,
            'sayfa': request.path
        })
        # Son 5000 logu tut
        if len(loglar) > 5000:
            loglar = loglar[-5000:]
        save_json(LOGS_FILE, loglar)
    except Exception as e:
        print(f"Log kayıt hatası: {e}")

def init_admin():
    users = load_users()
    if not any(u['role'] == 'admin' for u in users):
        users.append({
            'id': str(uuid.uuid4())[:8],
            'username': 'admin',
            'password': generate_password_hash('admin123'),
            'ad_soyad': 'Sistem Yöneticisi',
            'role': 'admin',
            'olusturma': datetime.now().strftime('%d.%m.%Y %H:%M')
        })
        save_users(users)
        print("✅  Varsayılan admin  →  kullanıcı: admin  |  şifre: admin123")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        if session['user']['role'] != 'admin':
            flash('Bu sayfaya erişim yetkiniz yok.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ── WhatsApp ──────────────────────────────────────────────────────
def _wa_post(endpoint, payload_dict):
    url = f"https://7107.api.greenapi.com/waInstance{GREENAPI_INSTANCE}/{endpoint}/{GREENAPI_TOKEN}"
    payload = json.dumps(payload_dict, ensure_ascii=False).encode('utf-8')
    req = urlreq.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    with urlreq.urlopen(req, timeout=15) as resp:
        return resp.status

def whatsapp_bildir(kayit, base_url=None):
    def _gonder():
        try:
            bos = '—'
            c = '—' * 25
            detay_link = f"{base_url}/detay/{kayit['id']}" if base_url else ''
            mesaj = (
                f"🔴 *UYGUN OLMAYAN ÜRÜN ETİKETİ*\n"
                f"*(RET KARTI)*\n"
                f"{c}\n"
                f"📦 *PARÇA / MALZEME BİLGİSİ*\n"
                f"*Parça/Malzeme Adı* : {kayit.get('parca_malzeme_adi') or bos}\n"
                f"*Parça/Malzeme Kodu* : {kayit.get('parca_malzeme_kodu') or bos}\n"
                f"{c}\n"
                f"⚠️ *UYGUNSUZLUK BİLGİLERİ*\n"
                f"*Tespit Yeri* : {kayit.get('tespit_yeri') or bos}\n"
                f"*Kaynağı* : {kayit.get('uygunsuzluk_kaynagi') or bos}\n"
                f"*Tanımı* : {kayit.get('uygunsuzluk_tanimi') or bos}\n"
                f"*Kök Sebebi* : {kayit.get('kok_sebep') or bos}\n"
                f"{c}\n"
                f"🔧 *MAKİNE BİLGİLERİ*\n"
                f"*Rapor No* : {kayit.get('rapor_no') or bos}\n"
                f"*Makine Adı* : {kayit.get('makine_adi') or bos}\n"
                f"*Makine ID / İrsaliye-Sipariş No* : {kayit.get('makine_id') or bos}\n"
                f"*Tarih* : {kayit.get('tarih') or bos}\n"
                f"*Miktar* : {kayit.get('miktar') or bos}\n"
                f"{c}\n"
                f"👤 *PERSONEL*\n"
                f"*Raporlayan* : {kayit.get('raporlayan') or bos}\n"
                f"*Kontrol Eden* : {kayit.get('kontrol_eden') or bos}\n"
                f"{c}\n"
                f"📝 *NOT*\n"
                f"_Uygunsuzluklar aynı gün içinde kapatılmalıdır._\n"
                f"_Kaynağı bölüm tarafından, kanıt doküman ve uygunsuzluğu yapan personel bilgisi iletilmelidir._\n"
            )
            if detay_link:
                mesaj += f"{c}\n🔗 *Detay:* {detay_link}"
            _wa_post('sendMessage', {"chatId": WHATSAPP_GROUP_ID, "message": mesaj})
            print("✅ WhatsApp metin bildirimi gönderildi")
            if base_url and kayit.get('gorseller'):
                for i, gorsel in enumerate(kayit['gorseller']):
                    try:
                        _wa_post('sendFileByUrl', {
                            "chatId": WHATSAPP_GROUP_ID,
                            "urlFile": f"{base_url}/static/uploads/{gorsel}",
                            "fileName": gorsel,
                            "caption": f"📷 Görsel {i+1}/{len(kayit['gorseller'])} — Kayıt #{kayit['id']}"
                        })
                        print(f"✅ Görsel {i+1} gönderildi")
                    except Exception as eg:
                        print(f"⚠️ Görsel {i+1} gönderilemedi: {eg}")
        except Exception as e:
            print(f"⚠️ WhatsApp bildirimi gönderilemedi: {e}")
    threading.Thread(target=_gonder, daemon=True).start()

def whatsapp_kapandi_bildir(kayit, kapatan, base_url=None):
    def _gonder():
        try:
            bos = '—'
            c = '—' * 25
            detay_link = f"{base_url}/detay/{kayit['id']}" if base_url else ''
            mesaj = (
                f"✅ *UYGUNSUZLUK KAPATILDI*\n"
                f"{c}\n"
                f"*Parça/Malzeme* : {kayit.get('parca_malzeme_adi') or bos}\n"
                f"*Uygunsuzluk* : {kayit.get('uygunsuzluk_tanimi') or bos}\n"
                f"{c}\n"
                f"*Çözüm Önerisi :*\n{kayit.get('cozum_onerisi') or bos}\n"
                f"*Alınan Aksiyon :*\n{kayit.get('acil_aksiyon') or bos}\n"
                f"{c}\n"
                f"*Kapatan* : {kapatan}\n"
                f"*Kapatma Zamanı* : {kayit.get('kapanis_zamani', bos)}\n"
            )
            if detay_link:
                mesaj += f"{c}\n🔗 *Detay:* {detay_link}"
            _wa_post('sendMessage', {"chatId": WHATSAPP_GROUP_ID, "message": mesaj})
            print("✅ WhatsApp kapanış bildirimi gönderildi")
        except Exception as e:
            print(f"⚠️ WhatsApp kapanış bildirimi gönderilemedi: {e}")
    threading.Thread(target=_gonder, daemon=True).start()

# ── Routes ────────────────────────────────────────────────────────
@app.route('/giris', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = get_user(username)
        if user and check_password_hash(user['password'], password):
            session['user'] = {'id': user['id'], 'username': user['username'],
                               'ad_soyad': user['ad_soyad'], 'role': user['role']}
            log_kaydet('🔑 Giriş', f'{user["ad_soyad"]} sisteme giriş yaptı', '✅', session['user'])
            return redirect(url_for('index'))
        log_kaydet('🔑 Başarısız Giriş', f'Kullanıcı adı: {username}', '❌', {'ad_soyad': username, 'username': username, 'role': '—'})
        error = 'Kullanıcı adı veya şifre hatalı.'
    return render_template('login.html', error=error)

@app.route('/cikis')
def logout():
    log_kaydet('🚪 Çıkış', f'{session.get("user", {}).get("ad_soyad", "?")} çıkış yaptı', '✅')
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    kayitlar = load_data()
    user = session['user']
    if user['role'] != 'admin':
        kayitlar = [k for k in kayitlar if k.get('olusturan_id') == user['id']]
    toplam = len(kayitlar)
    acik   = sum(1 for k in kayitlar if k.get('durum') == 'Açık')
    kapali = sum(1 for k in kayitlar if k.get('durum') == 'Kapalı')
    return render_template('index.html', kayitlar=kayitlar, toplam=toplam, acik=acik, kapali=kapali)

@app.route('/yeni')
@login_required
def yeni_form():
    log_kaydet('📝 Yeni Form', 'Yeni uygunsuzluk formu açıldı', '✅')
    return render_template('form.html')

@app.route('/kaydet', methods=['POST'])
@login_required
def kaydet():
    kayitlar = load_data()
    gorseller = []
    if 'gorseller' in request.files:
        for file in request.files.getlist('gorseller'):
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                gorseller.append(filename)
    kayit_id = str(uuid.uuid4())[:8].upper()
    user = session['user']
    yeni = {
        'id': kayit_id,
        'olusturan_id': user['id'],
        'olusturan_adi': user['ad_soyad'],
        'tarih': request.form.get('tarih', datetime.now().strftime('%d.%m.%Y')),
        'parca_malzeme_adi': request.form.get('parca_malzeme_adi', ''),
        'parca_malzeme_kodu': request.form.get('parca_malzeme_kodu', ''),
        'tespit_yeri': request.form.get('tespit_yeri', ''),
        'uygunsuzluk_kaynagi': request.form.get('uygunsuzluk_kaynagi', ''),
        'uygunsuzluk_tanimi': request.form.get('uygunsuzluk_tanimi', ''),
        'kok_sebep': request.form.get('kok_sebep', ''),
        'rapor_no': request.form.get('rapor_no', ''),
        'makine_adi': request.form.get('makine_adi', ''),
        'makine_id': request.form.get('makine_id', ''),
        'miktar': request.form.get('miktar', ''),
        'cozum_onerisi': request.form.get('cozum_onerisi', ''),
        'acil_aksiyon': request.form.get('acil_aksiyon', ''),
        'aciklama': request.form.get('aciklama', ''),
        'raporlayan': request.form.get('raporlayan', user['ad_soyad']),
        'kontrol_eden': request.form.get('kontrol_eden', ''),
        'durum': 'Açık',
        'olusturma_zamani': datetime.now().strftime('%d.%m.%Y %H:%M'),
        'gorseller': gorseller
    }
    kayitlar.append(yeni)
    save_data(kayitlar)
    log_kaydet('➕ Kayıt Oluşturuldu', f'Kayıt #{kayit_id} — {yeni["parca_malzeme_adi"]}', '✅')
    base_url = request.host_url.rstrip('/')
    whatsapp_bildir(yeni, base_url)
    return redirect(url_for('detay', kayit_id=kayit_id))

@app.route('/detay/<kayit_id>')
@login_required
def detay(kayit_id):
    kayitlar = load_data()
    kayit = next((k for k in kayitlar if k['id'] == kayit_id), None)
    if not kayit:
        return redirect(url_for('index'))
    user = session['user']
    if user['role'] != 'admin' and kayit.get('olusturan_id') != user['id']:
        log_kaydet('🚫 Yetkisiz Erişim', f'Kayıt #{kayit_id} görüntüleme girişimi', '❌')
        flash('Bu kaydı görme yetkiniz yok.', 'error')
        return redirect(url_for('index'))
    log_kaydet('👁️ Kayıt Görüntülendi', f'Kayıt #{kayit_id} — {kayit.get("parca_malzeme_adi", "")}', '✅')
    return render_template('detay.html', kayit=kayit)

@app.route('/durum_guncelle/<kayit_id>', methods=['POST'])
@login_required
def durum_guncelle(kayit_id):
    kayitlar = load_data()
    user = session['user']
    for k in kayitlar:
        if k['id'] == kayit_id:
            if user['role'] != 'admin' and k.get('olusturan_id') != user['id']:
                log_kaydet('🚫 Yetkisiz İşlem', f'Kayıt #{kayit_id} güncelleme girişimi', '❌')
                flash('Yetkiniz yok.', 'error')
                return redirect(url_for('index'))
            eski_durum = k.get('durum', '')
            k['durum'] = request.form.get('durum', k['durum'])
            k['cozum_onerisi'] = request.form.get('cozum_onerisi', k.get('cozum_onerisi', ''))
            k['acil_aksiyon'] = request.form.get('acil_aksiyon', k.get('acil_aksiyon', ''))
            if k['durum'] == 'Kapalı':
                k['kapanis_zamani'] = datetime.now().strftime('%d.%m.%Y %H:%M')
                k['kapatan'] = user['ad_soyad']
                log_kaydet('🔒 Kayıt Kapatıldı', f'Kayıt #{kayit_id} — {k.get("parca_malzeme_adi", "")}', '✅')
                whatsapp_kapandi_bildir(k, user['ad_soyad'], request.host_url.rstrip('/'))
            else:
                log_kaydet('✏️ Durum Güncellendi', f'Kayıt #{kayit_id} — {eski_durum} → {k["durum"]}', '✅')
            break
    save_data(kayitlar)
    return redirect(url_for('detay', kayit_id=kayit_id))

@app.route('/sil/<kayit_id>', methods=['POST'])
@admin_required
def sil(kayit_id):
    kayitlar = load_data()
    silinen = next((k for k in kayitlar if k['id'] == kayit_id), {})
    kayitlar = [k for k in kayitlar if k['id'] != kayit_id]
    save_data(kayitlar)
    log_kaydet('🗑️ Kayıt Silindi', f'Kayıt #{kayit_id} — {silinen.get("parca_malzeme_adi", "")}', '⚠️')
    return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin_panel():
    log_kaydet('⚙️ Admin Panel', 'Admin paneli açıldı', '✅')
    return render_template('admin.html', users=load_users())

@app.route('/admin/loglar')
@admin_required
def admin_loglar():
    loglar = load_logs()
    loglar = list(reversed(loglar))  # En yeni üstte
    filtre_kullanici = request.args.get('kullanici', '')
    filtre_islem = request.args.get('islem', '')
    filtre_durum = request.args.get('durum', '')
    if filtre_kullanici:
        loglar = [l for l in loglar if filtre_kullanici.lower() in l.get('username', '').lower()]
    if filtre_islem:
        loglar = [l for l in loglar if filtre_islem.lower() in l.get('islem', '').lower()]
    if filtre_durum:
        loglar = [l for l in loglar if filtre_durum in l.get('durum', '')]
    # Filtreler için unique değerler
    tum_loglar = load_logs()
    kullanicilar = sorted(set(l.get('username', '') for l in tum_loglar if l.get('username')))
    return render_template('loglar.html', loglar=loglar[:500], kullanicilar=kullanicilar,
                           filtre_kullanici=filtre_kullanici, filtre_islem=filtre_islem, filtre_durum=filtre_durum,
                           toplam=len(loglar))

@app.route('/admin/kullanici_ekle', methods=['POST'])
@admin_required
def kullanici_ekle():
    users = load_users()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    ad_soyad = request.form.get('ad_soyad', '').strip()
    role     = request.form.get('role', 'user')
    if not username or not password or not ad_soyad:
        flash('Tüm alanları doldurun.', 'error')
        return redirect(url_for('admin_panel'))
    if any(u['username'] == username for u in users):
        flash('Bu kullanıcı adı zaten mevcut.', 'error')
        return redirect(url_for('admin_panel'))
    users.append({'id': str(uuid.uuid4())[:8], 'username': username,
                  'password': generate_password_hash(password), 'ad_soyad': ad_soyad,
                  'role': role, 'olusturma': datetime.now().strftime('%d.%m.%Y %H:%M')})
    save_users(users)
    log_kaydet('👤 Kullanıcı Eklendi', f'{ad_soyad} ({username}) eklendi', '✅')
    flash(f'"{ad_soyad}" kullanıcısı eklendi.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/kullanici_sil/<uid>', methods=['POST'])
@admin_required
def kullanici_sil(uid):
    if uid == session['user']['id']:
        flash('Kendi hesabınızı silemezsiniz.', 'error')
        return redirect(url_for('admin_panel'))
    users = load_users()
    silinen = next((u for u in users if u['id'] == uid), {})
    users = [u for u in users if u['id'] != uid]
    save_users(users)
    log_kaydet('👤 Kullanıcı Silindi', f'{silinen.get("ad_soyad", uid)} silindi', '⚠️')
    flash('Kullanıcı silindi.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/sifre_degistir/<uid>', methods=['POST'])
@admin_required
def sifre_degistir(uid):
    yeni_sifre = request.form.get('yeni_sifre', '').strip()
    if not yeni_sifre or len(yeni_sifre) < 4:
        flash('Şifre en az 4 karakter olmalı.', 'error')
        return redirect(url_for('admin_panel'))
    users = load_users()
    for u in users:
        if u['id'] == uid:
            log_kaydet('🔐 Şifre Değiştirildi', f'{u["ad_soyad"]} şifresi güncellendi', '⚠️')
            u['password'] = generate_password_hash(yeni_sifre)
            break
    save_users(users)
    flash('Şifre güncellendi.', 'success')
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('data', exist_ok=True)
    init_admin()
    app.run(host='0.0.0.0', port=443, debug=True)
