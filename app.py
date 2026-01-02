import logging
import sys
import os
import time

from datetime import datetime, timedelta
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)

from flask_sqlalchemy import SQLAlchemy
import midtransclient
import pymysql
from authlib.integrations.flask_client import OAuth

# Install MySQL driver
pymysql.install_as_MySQLdb()

# Konfigurasi Logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# [FIX] Middleware ProxyFix untuk Azure
# Setting ini memberitahu Flask untuk mempercayai header dari Load Balancer Azure
# x_proto=1: Mengatasi http vs https (Google Login Error)
# x_host=1: Mengatasi nama domain
# x_for=1 & x_prefix=1: Tambahan untuk kestabilan di Azure Linux
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = "rahasia_lokal_123"
basedir = os.path.abspath(os.path.dirname(__file__))

# --- KONFIGURASI DATABASE ---
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
app.config["UPLOAD_FOLDER"] = os.path.join(basedir, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

# --- KONFIGURASI MIDTRANS (SANDBOX) ---
# Sesuai dengan screenshot Anda sebelumnya
MIDTRANS_SERVER_KEY = "Mid-server-JEHBUtBFFwcJ8Sw8GypuXrQZ"
MIDTRANS_CLIENT_KEY = "Mid-client-wXRT3UdSUW4t95P6"

# --- KONFIGURASI GOOGLE OAUTH ---
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '')

oauth = OAuth(app)
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

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_premium = db.Column(db.Boolean, default=False)
    premium_expiry = db.Column(db.DateTime, nullable=True)
    company_logo = db.Column(db.String(200), nullable=True)
    company_address = db.Column(db.String(500), nullable=True)
    signature_file = db.Column(db.String(200), nullable=True)
    
    # Field Tambahan untuk Profil Invoice
    company_name = db.Column(db.String(120), nullable=True)
    signature_name = db.Column(db.String(120), nullable=True)
    signature_title = db.Column(db.String(120), nullable=True)

    @property
    def public_id(self):
        return f"INVNJ-{self.id}"

class PageVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    path = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, nullable=True)

def init_db():
    with app.app_context():
        try:
            db.create_all()
            print(">>> DATABASE SUKSES DIINISIALISASI.")
        except Exception as e:
            print(f">>> DB ERROR: {e}")

# Class Helper untuk User Tamu
class Guest:
    def __init__(self):
        self.id = None
        self.username = "Tamu (Guest)"
        self.is_premium = False
        self.is_admin = False
        self.company_logo = None
        self.company_address = ""
        self.company_name = None
        self.signature_file = None
        self.signature_name = None
        self.signature_title = None

# --- UTILITY ---
def get_current_user():
    uid = session.get("user_id")
    if not uid: return None
    return User.query.get(uid)

# --- ROUTES ---

@app.route("/")
def index():
    return redirect(url_for("dashboard"))

@app.route("/admin")
def admin_page():
    # 1. Cek Admin
    user_id = session.get("user_id")
    if not user_id: return redirect(url_for("login"))
    
    user = User.query.get(user_id)
    if not user or not user.is_admin:
        return redirect(url_for("dashboard"))

    # --- [FIX] LOGIKA TIMEZONE UNTUK GRAFIK ---
    
    # A. Grafik Pengunjung (7 Hari Terakhir)
    now_utc = datetime.utcnow()
    start_date = now_utc - timedelta(days=7)
    
    visit_rows = db.session.query(
        func.date(PageVisit.ts).label("d"),
        func.count(PageVisit.id).label("c"),
    ).filter(PageVisit.ts >= start_date).group_by(func.date(PageVisit.ts)).all()

    labels = [str(r.d) for r in visit_rows]
    data_visits = [int(r.c) for r in visit_rows]
    total_visits = sum(data_visits)

    # B. Grafik Input Invoice (HARI INI - WIB)
    # Server Azure pakai UTC. Kita perlu geser waktu agar sesuai "Hari Ini" di Indonesia (WIB)
    
    now_wib = now_utc + timedelta(hours=7)
    today_wib_start = now_wib.replace(hour=0, minute=0, second=0, microsecond=0)
    query_start_utc = today_wib_start - timedelta(hours=7)

    input_rows = db.session.query(PageVisit.ts).filter(
        PageVisit.ts >= query_start_utc,
        PageVisit.path == '/generate-invoice'
    ).all()

    input_data = [0] * 24
    
    for r in input_rows:
        # Konversi UTC ke WIB untuk tampilan
        log_time_wib = r.ts + timedelta(hours=7)
        hour_index = log_time_wib.hour
        if 0 <= hour_index < 24:
            input_data[hour_index] += 1

    input_labels = [f"{i:02d}:00" for i in range(24)]
    total_inputs = sum(input_data)

    # C. Tabel User (Pagination)
    sort = request.args.get("sort", "expiry")
    direction = request.args.get("dir", "asc")
    page = int(request.args.get("page", 1))
    per_page = 8

    q = User.query
    if sort == "id":
        q = q.order_by(User.id.asc() if direction == "asc" else User.id.desc())
    else: 
        q = q.order_by(User.premium_expiry.asc() if direction == "asc" else User.premium_expiry.desc())

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    
    row_data = []
    for u in pagination.items:
        is_active = False
        if u.is_premium and u.premium_expiry and u.premium_expiry > datetime.now():
            is_active = True
            
        row_data.append({
            "id": u.id,
            "public_id": u.public_id,
            "username": u.username,
            "subscribed": is_active,
            "premium_expiry": u.premium_expiry.strftime("%Y-%m-%d") if u.premium_expiry else "-"
        })

    return render_template(
        "dashboard_admin.html",
        admin=user,
        labels=labels,
        data=data_visits,
        total_visits=total_visits,
        input_labels=input_labels,
        input_data=input_data,
        total_inputs=total_inputs,
        rows=row_data,
        sort=sort, dir=direction, page=page,
        total_pages=pagination.pages,
        total_users=pagination.total,
        has_prev=pagination.has_prev, has_next=pagination.has_next
    )

@app.route("/get-payment-token", methods=["POST"])
def get_payment_token():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Silahkan login terlebih dahulu"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404

    if user.is_premium and user.premium_expiry and user.premium_expiry > datetime.now():
        return jsonify({"error": "Anda sudah Premium!"}), 403

    # --- [FIX] LOGIKA VALIDASI NAMA/EMAIL UNTUK MIDTRANS ---
    customer_email = ""
    customer_name = ""

    if "@" in user.username:
        # Kasus 1: Login via Google
        customer_email = user.username.strip()
        raw_name = user.username.split("@")[0]
        customer_name = ''.join(e for e in raw_name if e.isalnum())
        if len(customer_name) < 2:
            customer_name = "UserGoogle"
    else:
        # Kasus 2: Login Biasa
        customer_name = ''.join(e for e in user.username if e.isalnum())
        if not customer_name: customer_name = "UserApps"
        customer_email = f"{customer_name}@example.com"

    snap = midtransclient.Snap(
        is_production=False,
        server_key=MIDTRANS_SERVER_KEY
    )

    order_id = f"PREM-{user.id}-{int(time.time())}"

    param = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": 50000
        },
        "customer_details": {
            "first_name": customer_name,
            "email": customer_email
        },
        "credit_card": {
            "secure": True
        }
    }

    try:
        transaction = snap.create_transaction(param)
        return jsonify({"token": transaction['token']})
    except Exception as e:
        logger.error(f"Midtrans Payment Error for {user.username}: {e}")
        return jsonify({"error": "Gagal inisialisasi pembayaran. Cek koneksi server."}), 500

@app.route("/payment-success", methods=["POST"])
def payment_success():
    if "user_id" not in session: return jsonify({"error": "Unauthorized"}), 401

    user = User.query.get(session["user_id"])
    if user:
        user.is_premium = True
        user.premium_expiry = datetime.now() + timedelta(days=30)
        db.session.commit()
        return jsonify({"status": "success"})
    
    return jsonify({"error": "User not found"}), 404

@app.route("/generate-invoice", methods=["POST"])
def generate_invoice():
    # --- LOG VISIT MANUAL ---
    try:
        if "user_id" in session:
            v = PageVisit(path='/generate-invoice', user_id=session["user_id"])
            db.session.add(v)
            db.session.commit()
    except Exception as e:
        logger.error(f"Failed logging visit: {e}")
        db.session.rollback()

    # --- PROSES INVOICE ---
    try:
        user_id = session.get("user_id")
        user = User.query.get(user_id) if user_id else Guest()
        
        f = request.form
        template = f.get("template", "basic")
        
        bg_color = "#" + f.get("bgcolor", "ffffff").replace("#", "")
        line_color = "#" + f.get("linecolor", "000000").replace("#", "")
        
        customer = f.get("customername", "").strip() or "Pelanggan"
        header_title = f.get("headertitle", "INVOICE")
        
        names = f.getlist("itemname")
        qtys = f.getlist("itemqty")
        prices = f.getlist("itemprice")
        
        items = []
        grand_total = 0
        
        for i in range(len(names)):
            n = names[i].strip()
            if not n: continue
            try:
                q = int(qtys[i])
                p = int(prices[i])
                total = q * p
                grand_total += total
                items.append({
                    "name": n,
                    "qty": q,
                    "price": p,
                    "total": total
                })
            except:
                continue

        return render_template(
            "invoice_print_view.html",
            user=user,
            customer=customer,
            items=items,
            grand_total=grand_total,
            template=template,
            bg_color=bg_color,
            line_color=line_color,
            header_title=header_title,
            date=datetime.now().strftime("%d %B %Y")
        )
        
    except Exception as e:
        logger.error(f"Generate Invoice Error: {e}")
        return f"Terjadi kesalahan sistem: {str(e)}", 500

# --- AUTH ROUTES ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")

        user = User.query.filter_by(username=u).first()

        if not user:
            flash("Username atau Password salah.", "error")
        elif not user.password:
            flash("Akun ini login via Google. Silakan gunakan tombol Google.", "error")
        elif not check_password_hash(user.password, p):
            flash("Username atau Password salah.", "error")
        else:
            session["user_id"] = user.id
            if user.is_admin:
                return redirect(url_for("admin_page"))
            return redirect(url_for("dashboard"))
            
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"].strip()
    password = request.form["password"]

    if User.query.filter_by(username=username).first():
        flash("Username sudah digunakan.", "error")
        return redirect(url_for("login"))

    try:
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            is_premium=False
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Pendaftaran sukses, silakan login.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "error")

    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Berhasil logout.", "info")
    return redirect(url_for("dashboard"))

# --- GOOGLE OAUTH ROUTES ---

@app.route("/login/google")
def login_google():
    # Dengan ProxyFix, _external=True akan otomatis generate HTTPS jika di Azure
    redirect_uri = url_for("google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route("/login/google/callback")
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        info = token.get('userinfo')
        
        if not info:
            flash("Gagal mengambil data dari Google.", "error")
            return redirect(url_for('login'))
        
        email = info.get('email')
        
        user = User.query.filter_by(username=email).first()
        
        if not user:
            # Buat user baru tanpa password (karena login sosmed)
            user = User(
                username=email,
                password=None,
                is_premium=False
            )
            db.session.add(user)
            db.session.commit()
            flash("Akun baru berhasil dibuat!", "success")
        
        session['user_id'] = user.id
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"OAuth Error: {e}")
        # Pesan ini akan muncul di Log Stream jika gagal
        flash("Gagal login dengan Google. Cek Log Server.", "error")
        return redirect(url_for('login'))

@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if user_id:
        user = User.query.get(user_id)
        if user and user.is_admin:
            user.is_premium = True 
    else:
        user = Guest()

    return render_template("dashboard.html",
                         user=user,
                         admin=user if getattr(user, 'is_admin', False) else None,
                         client_key=MIDTRANS_CLIENT_KEY)

# --- UPLOAD & PROFILE ROUTES ---

@app.route("/upload-logo", methods=["POST"])
def upload_logo():
    if "user_id" not in session: return jsonify(error="Login required"), 401
    
    f = request.files.get("logo")
    if f:
        fn = secure_filename(f"logo_{session['user_id']}_{f.filename}")
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
        
        u = User.query.get(session['user_id'])
        u.company_logo = fn
        db.session.commit()
        return jsonify(success=True, filename=fn)
    return jsonify(error="File missing"), 400

@app.route("/upload-signature", methods=["POST"])
def upload_signature():
    if "user_id" not in session: return jsonify(error="Login required"), 401
    
    f = request.files.get("signature")
    if f:
        fn = secure_filename(f"sig_{session['user_id']}_{f.filename}")
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
        
        u = User.query.get(session['user_id'])
        u.signature_file = fn
        db.session.commit()
        return jsonify(success=True, filename=fn)
    return jsonify(error="File missing"), 400

@app.route("/premium/profile", methods=["POST"])
def update_profile():
    if "user_id" not in session: return jsonify(error="Login required"), 401
    
    user = User.query.get(session["user_id"])
    if not user.is_premium: return jsonify(error="Premium only"), 403
    
    data = request.get_json(silent=True) or {}
    
    user.company_name = data.get("company_name", "").strip()[:150] or None
    user.signature_name = data.get("signature_name", "").strip()[:100] or None
    user.signature_title = data.get("signature_title", "").strip()[:100] or None
    
    db.session.commit()
    return jsonify(success=True)

@app.route("/update-address", methods=["POST"])
def update_address():
    if "user_id" not in session: return jsonify(error="Login required"), 401
    user = User.query.get(session["user_id"])
    if not user.is_premium: return jsonify(error="Premium only"), 403
    
    data = request.get_json() or {}
    user.company_address = data.get("address", "").strip()
    db.session.commit()
    return jsonify(success=True)

@app.before_request
def track_visit():
    if request.method != "GET": return
    if request.path.startswith(("/static", "/admin")): return
    
    try:
        v = PageVisit(path=request.path, user_id=session.get("user_id"))
        db.session.add(v)
        db.session.commit()
    except:
        db.session.rollback()


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)