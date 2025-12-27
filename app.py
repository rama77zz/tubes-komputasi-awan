import os
import time
from datetime import datetime, timedelta
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash


# Load environment variables untuk development lokal
from dotenv import load_dotenv
load_dotenv()  # Load .env file

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

import midtransclient
import pymysql

# OAuth imports
from authlib.integrations.flask_client import OAuth

# Mendaftarkan driver pymysql
pymysql.install_as_MySQLdb()

app = Flask(__name__)
app.secret_key = "rahasia_lokal_123"

basedir = os.path.abspath(os.path.dirname(__file__))

# --- KONFIGURASI DATABASE (AZURE MYSQL TANPA SSL) ---

AZURE_DB_HOST = "praktikum-crudtaufiq2311.mysql.database.azure.com"
AZURE_DB_USER = "adminlogintest"
AZURE_DB_PASS = "mpVYe8mXt8h2wdi"
AZURE_DB_NAME = "invoiceinaja"

database_uri = (
    f"mysql+pymysql://{AZURE_DB_USER}:{AZURE_DB_PASS}"
    f"@{AZURE_DB_HOST}/{AZURE_DB_NAME}"
)

app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# folder upload
app.config["UPLOAD_FOLDER"] = os.path.join(basedir, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

# --- KONFIGURASI MIDTRANS ---

MIDTRANS_SERVER_KEY = "Mid-server-JEHBUtBFFwcJ8Sw8GypuXrQZ"
MIDTRANS_CLIENT_KEY = "Mid-client-wXRT3UdSUW4t95P6"

snap = midtransclient.Snap(
    is_production=False,
    server_key=MIDTRANS_SERVER_KEY,
    client_key=MIDTRANS_CLIENT_KEY,
)

# --- KONFIGURASI OAUTH GOOGLE ---

app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '')

# Inisialisasi OAuth
oauth = OAuth(app)

# Register Google sebagai OAuth provider
google = oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account'
    }
)

# --- MODEL DATABASE ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)

    # hash biasanya > 100 char, jadi harus lebih panjang
    password = db.Column(db.String(255), nullable=True)

    is_admin = db.Column(db.Boolean, default=False)

    is_premium = db.Column(db.Boolean, default=False)
    premium_expiry = db.Column(db.DateTime, nullable=True)
    company_logo = db.Column(db.String(200), nullable=True)
    company_address = db.Column(db.String(500), nullable=True)
    signature_file = db.Column(db.String(200), nullable=True)
    company_name = db.Column(db.String(120), nullable=True)       # Nama perusahaan custom
    signature_name = db.Column(db.String(120), nullable=True)     # Nama penanda tangan custom
    signature_title = db.Column(db.String(120), nullable=True)    # Jabatan/posisi (opsional)

    @property
    def public_id(self):
        return f"INVNJ-{self.id}"

class PageVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.now, index=True)
    path = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, nullable=True)

# --- INIT DB ---
def init_db():
    with app.app_context():
        try:
            db.create_all()
            print(">>> SUKSES: Tabel Database Siap.")
            try:
               if not User.query.filter_by(username="user_demo").first():
                    db.session.add(
                        User(
                            username="user_demo",
                            password=generate_password_hash("123"),
                            is_premium=False,
                            is_admin=False,
                        )
                    )
                    db.session.commit()
                    print(">>> User Demo 'user_demo' berhasil dibuat.")
            except Exception:
                db.session.rollback()
        except Exception as e:
            print(f">>> ERROR DATABASE: {e}")

# --- HELPER GUEST ---
class Guest:
    def __init__(self):
        self.id = None
        self.username = "Tamu (Guest)"
        self.is_premium = False
        self.company_logo = None
        self.company_address = None
        self.signature_file = None
        self.is_admin = False

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)

def require_admin_user():
    u = get_current_user()
    if not u or not getattr(u, "is_admin", False):
        return None
    return u

@app.route("/admin/dashboard")
def admin_dashboard():
    admin = require_admin_user()
    if not admin:
        return redirect(url_for("login", next=request.path))

    # render tampilan persis seperti dashboard.html
    # admin dikirim sebagai user supaya variabel {{ user.username }} tetap jalan
    return render_template(
        "dashboard.html",
        user=admin,
        admin=admin,
        admin_page="dashboard"   # penanda untuk navbar admin (Kembali)
    )

# --- ROUTES ---
@app.route("/admin")
def admin_page():
    admin = require_admin_user()
    if not admin:
        return redirect(url_for("login", next=request.path))

    # 1. LOGIKA GRAFIK PENGUNJUNG (7 Hari Terakhir)
    start_date = datetime.now() - timedelta(days=7)
    visit_rows = db.session.query(
        func.date(PageVisit.ts).label("d"),
        func.count(PageVisit.id).label("c"),
    ).filter(PageVisit.ts >= start_date).group_by(func.date(PageVisit.ts)).order_by(func.date(PageVisit.ts)).all()
    
    labels = [str(r.d) for r in visit_rows]
    data_visits = [int(r.c) for r in visit_rows]

    # 2. LOGIKA GRAFIK INPUT HARI INI (Per Jam)
    # Menghitung akses ke route generate-invoice sebagai indikator input
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    input_rows = db.session.query(
        func.hour(PageVisit.ts).label("h"),
        func.count(PageVisit.id).label("c"),
    ).filter(PageVisit.ts >= today_start, PageVisit.path == '/generate-invoice')\
     .group_by(func.hour(PageVisit.ts)).all()
    
    input_data = [0] * 24
    for r in input_rows:
        input_data[r.h] = r.c
    input_labels = [f"{i}:00" for i in range(24)]

    # 3. LOGIKA DAFTAR USER & SORTING
    sort = request.args.get("sort", "expiry")
    direction = request.args.get("dir", "asc")
    
    q = User.query
    if sort == "id":
        q = q.order_by(User.id.asc() if direction == "asc" else User.id.desc())
    else: # Default sort by expiry
        q = q.order_by(User.premium_expiry.asc() if direction == "asc" else User.premium_expiry.desc())
    
    users = q.all()
    now = datetime.now()
    rows = []
    for u in users:
        is_active = False
        if u.is_premium and u.premium_expiry and u.premium_expiry > now:
            is_active = True
        
        rows.append({
            "id": u.id,
            "public_id": u.public_id,
            "username": u.username,
            "subscribed": is_active,
            "premium_expiry": u.premium_expiry.strftime("%Y-%m-%d %H:%M") if u.premium_expiry else "-"
        })

    return render_template(
        "dashboard_admin.html",
        admin=admin,
        labels=labels,
        data=data_visits,
        input_labels=input_labels,
        input_data=input_data,
        rows=rows,
        sort=sort,
        dir=direction
    )
    
@app.route("/admin/analytics")
def admin_analytics():
    admin = require_admin_user()
    if not admin:
        flash("Access denied.", "error")
        return redirect(url_for("login", next=request.path))

    start = datetime.now() - timedelta(days=7)

    rows = (
        db.session.query(
            func.date(PageVisit.ts).label("d"),
            func.count(PageVisit.id).label("c"),
        )
        .filter(PageVisit.ts >= start)
        .group_by(func.date(PageVisit.ts))
        .order_by(func.date(PageVisit.ts))
        .all()
    )

    labels = [str(r.d) for r in rows]
    data = [int(r.c) for r in rows]

    return render_template("admin_analytics.html", admin=admin, labels=labels, data=data)

@app.route("/admin/users")
def admin_users():
    admin = require_admin_user()
    if not admin:
        flash("Access denied.", "error")
        return redirect(url_for("login", next=request.path))

    users = User.query.order_by(User.id.desc()).all()

    now = datetime.now()
    rows = []
    for u in users:
        subscribed = bool(u.is_premium and u.premium_expiry and u.premium_expiry > now)
        rows.append({
            "id": u.id,
            "username": u.username,
            "subscribed": subscribed,
            "premium_expiry": u.premium_expiry
        })

    return redirect(url_for("admin_page"))

@app.route("/premium/profile", methods=["POST"])
def premium_profile():
    if "user_id" not in session:
        return jsonify(error="Login required"), 401

    user = User.query.get(session["user_id"])
    if not user or not user.is_premium:
        return jsonify(error="Premium only"), 403

    payload = request.get_json(silent=True) or {}

    def clean(key, maxlen):
        v = (payload.get(key) or "").strip()
        if not v:
            return None
        return v[:maxlen]

    user.company_name = clean("company_name", 160)
    user.signature_name = clean("signature_name", 120)
    user.signature_title = clean("signature_title", 120)

    db.session.commit()
    return jsonify(success=True)

@app.route("/")
def index():
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            user = User.query.filter_by(username=username).first()

            # user tidak ada
            if not user:
                flash("Username atau Password salah.", "error")
                return render_template("login.html")

            # user OAuth (password kosong / None) jangan boleh login via form password
            if not user.password:
                flash("Akun ini terdaftar via Google. Silakan login dengan Google.", "error")
                return render_template("login.html")

            # verifikasi hash
            if not check_password_hash(user.password, password):
                flash("Username atau Password salah.", "error")
                return render_template("login.html")

            session["user_id"] = user.id
            flash("Login Berhasil!", "success")

            next_url = request.args.get("next") or request.form.get("next")
            if next_url:
                return redirect(next_url)

            if getattr(user, "is_admin", False):
                return redirect(url_for("admin_page"))

            return redirect(url_for("dashboard"))

        except Exception as e:
            flash(f"Database Error: {str(e)}", "error")

    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"].strip()
    password = request.form["password"]

    try:
        if User.query.filter_by(username=username).first():
            flash("Username sudah dipakai.", "error")
            return redirect(url_for("login"))

        new_user = User(
            username=username,
            password=generate_password_hash(password),
            is_premium=False,
            is_admin=False,
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Pendaftaran Berhasil! Silakan Login.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error Register: {str(e)}", "error")

    return redirect(url_for("login"))


# --- GOOGLE OAUTH ROUTES ---
@app.route("/login/google")
def login_google():
    # Pastikan redirect_uri menggunakan HTTPS jika di Azure
    redirect_uri = url_for("auth_google", _external=True)
    if "azurewebsites.net" in redirect_uri:
        redirect_uri = redirect_uri.replace("http://", "https://")
    return oauth.google.authorize_redirect(redirect_uri)

@app.route("/auth/google")
def auth_google():
    token = oauth.google.authorize_access_token()
    user_info = token.get('userinfo')
    if not user_info:
        flash("Gagal mengambil info user dari Google")
        return redirect(url_for("login"))
    
    # Cari atau buat user berdasarkan email Google
    user = User.query.filter_by(username=user_info['email']).first()
    if not user:
        user = User(username=user_info['email'], public_id=str(uuid.uuid4()))
        db.session.add(user)
        db.session.commit()
    
    session["user_id"] = user.id
    return redirect(url_for("dashboard"))

@app.before_request
def track_visit():
    # catat hanya GET dan bukan static
    if request.method != "GET":
        return
    if request.path.startswith("/static"):
        return
    # opsional: jangan catat endpoint admin agar data tidak bias
    if request.path.startswith("/admin"):
        return

    try:
        v = PageVisit(path=request.path, user_id=session.get("user_id"))
        db.session.add(v)
        db.session.commit()
    except Exception:
        db.session.rollback()


@app.route("/login/google/callback")
def google_callback():
    """
    Handle callback dari Google setelah user approve
    """
    try:
        # Ambil access token dari Google
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            flash("Gagal mendapatkan info user dari Google.", "error")
            return redirect(url_for('login'))
        
        # Debug log
        import json
        print(f">>> [OAuth] Google user_info: {json.dumps(user_info, indent=2)}")
        
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0] if email else 'User')
        
        if not email:
            flash("Email tidak ditemukan di akun Google.", "error")
            return redirect(url_for('login'))
        
        # Cek apakah user sudah ada
        user = User.query.filter_by(username=email).first()
        
        if not user:
            # Auto-register user baru
            print(f">>> [OAuth] Creating new user: {email}")
            user = User(
                username=email,
                password=None,  # OAuth user tidak pakai password
                is_premium=False
            )
            db.session.add(user)
            db.session.commit()
            flash(f"Akun baru berhasil dibuat untuk {name}!", "success")
        else:
            print(f">>> [OAuth] Existing user logged in: {email}")
        
        # Set session (login)
        session['user_id'] = user.id
        flash(f"Selamat datang, {name}!", "success")
        return redirect(url_for('dashboard'))
    
    except Exception as e:
        print(f">>> [OAuth] ERROR: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Login gagal: {str(e)}", "error")
        return redirect(url_for('login'))


@app.route("/logout")
def logout():
    session.clear()
    flash("Anda telah logout.", "info")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if user_id:
        user = User.query.get(user_id)
        # FIX: Admin mendapatkan privilege premium otomatis
        if user and user.is_admin:
            user.is_premium = True 
    else:
        user = Guest()

    return render_template("dashboard.html", 
                           user=user, 
                           admin=user if getattr(user, 'is_admin', False) else None,
                           client_key=MIDTRANS_CLIENT_KEY)

@app.route("/upload-logo", methods=["POST"])
def upload_logo():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    file = request.files.get("logo")
    if file:
        filename = secure_filename(f"logo_{user_id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        user = User.query.get(user_id)
        user.logo_file = filename
        db.session.commit()
        return jsonify({"success": True, "filename": filename})
    return jsonify({"error": "No file"}), 400

@app.route("/upload-signature", methods=["POST"])
def upload_signature():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    file = request.files.get("signature")
    if file:
        filename = secure_filename(f"sig_{user_id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        user = User.query.get(user_id)
        user.signature_file = filename
        db.session.commit()
        return jsonify({"success": True, "filename": filename})
    return jsonify({"error": "No file"}), 400


@app.route("/update_address", methods=["POST"])
def update_address():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    user = User.query.get(session["user_id"])
    if not user or not user.is_premium:
        return jsonify({"error": "Premium only"}), 403

    data = request.get_json(silent=True) or {}
    address = data.get("address", "")
    user.company_address = address
    db.session.commit()
    return jsonify({"success": True})


def get_payment_token():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Silahkan login terlebih dahulu"}), 401
    
    user = User.query.get(user_id)
    
    # Inisialisasi Midtrans Snap
    snap = midtransclient.Snap(
        is_production=False, # Set True jika sudah live
        server_key=MIDTRANS_SERVER_KEY
    )

    order_id = f"PREMIUM-{user.id}-{int(time.time())}"
    param = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": 50000 # Contoh harga Rp 50.000
        },
        "customer_details": {
            "first_name": user.username,
            "email": f"{user.username}@example.com"
        },
        "usage_limit": 1
    }

    try:
        transaction = snap.create_transaction(param)
        return jsonify({"token": transaction['token']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/payment_success", methods=["POST"])
def payment_success():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user = User.query.get(session["user_id"])
    if not user:
        return jsonify({"error": "user_not_found"}), 401

    user.is_premium = True
    user.premium_expiry = datetime.now() + timedelta(days=30)
    db.session.commit()
    
    print(f">>> [Payment] User {user.username} upgraded to premium until {user.premium_expiry}")
    
    return jsonify({"status": "success"})


@app.route("/generate-invoice", methods=["POST"])
def generate_invoice():
    # Pastikan nama route ini '/generate-invoice' sesuai fetch di dashboard.html
    user_id = session.get("user_id")
    user = User.query.get(user_id) if user_id else Guest()
    
    # Ambil data dari form (request.form)
    f = request.form

    # Hidden inputs dari dashboard.html
    template = f.get("template", "basic")
    bg_color = f.get("bgcolor", "ffffff")
    line_color = f.get("linecolor", "000000")
    header_title = f.get("headertitle", "INVOICE")

    # Rapikan value warna (dashboard kirim tanpa '#')
    if bg_color and not bg_color.startswith("#"):
        bg_color = "#" + bg_color
    if line_color and not line_color.startswith("#"):
        line_color = "#" + line_color

    # Field customer dari dashboard.html
    customer = (f.get("customername") or "").strip()

    # Item fields dari dashboard.html
    names = f.getlist("itemname")
    qtys = f.getlist("itemqty")
    prices = f.getlist("itemprice")

    items = []
    grand_total = 0
    max_items = 10

    for i in range(min(len(names), len(qtys), len(prices), max_items)):
        name = (names[i] or "").strip()
        try:
            qty = int(qtys[i])
            price = int(prices[i])
        except (ValueError, TypeError):
            continue

        if not name or qty <= 0 or price <= 0:
            continue

        total = qty * price
        grand_total += total
        items.append(
            {"name": name, "qty": qty, "price": price, "total": total}
        )

    print(">>> [Invoice] customer:", customer)
    print(">>> [Invoice] items:", items)

    return render_template(
        "invoice_print_view.html",
        user=user,
        customer=customer,
        items=items,
        grand_total=grand_total,
        template=template,
        header_title=header_title,
        bg_color=bg_color,
        line_color=line_color,
        date=datetime.now().strftime("%d %B %Y"),
    )


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
