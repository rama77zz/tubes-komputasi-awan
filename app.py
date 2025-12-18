import os
import time
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import OperationalError
from werkzeug.utils import secure_filename

import midtransclient
import pymysql

# Mendaftarkan driver pymysql
pymysql.install_as_MySQLdb()

app = Flask(__name__)
app.secret_key = "rahasia_lokal_123"

basedir = os.path.abspath(os.path.dirname(__file__))

# --- KONFIGURASI DATABASE (PRIORITAS ENV -> MANUAL AZURE -> LOKAL) ---

database_uri = os.getenv("DATABASE_URL")

# Data Koneksi Azure Manual
AZURE_DB_HOST = "praktikum-crudtaufiq2311.mysql.database.azure.com"
AZURE_DB_USER = "adminlogintest"
AZURE_DB_PASS = "mpVYe8mXt8h2wdi"
AZURE_DB_NAME = "invoiceinaja"

if not database_uri:
    # Coba gunakan konfigurasi Azure manual (pymysql)
    database_uri = (
        f"mysql+pymysql://{AZURE_DB_USER}:{AZURE_DB_PASS}"
        f"@{AZURE_DB_HOST}/{AZURE_DB_NAME}"
    )

# Konfigurasi Sertifikat SSL (opsional tapi disarankan untuk Azure)
ssl_cert_path = os.path.join(basedir, "DigiCertGlobalRootCA.crt.pem")
connect_args = {}
if os.path.exists(ssl_cert_path):
    connect_args = {"ssl": {"ca": ssl_cert_path}}

if database_uri:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": connect_args}
    print(f">>> MENGGUNAKAN DATABASE: {AZURE_DB_HOST} (atau Env)")
else:
    # Fallback ke lokal (SQLite)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
        basedir, "invoice.db"
    )
    print(">>> MENGGUNAKAN DATABASE LOKAL (SQLite).")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(basedir, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)

# --- KONFIGURASI MIDTRANS (TANPA SNAP BI) ---
MIDTRANS_SERVER_KEY = "Mid-server-JEHBUtBFFwcJ8Sw8GypuXrQZ"
MIDTRANS_CLIENT_KEY = "Mid-client-wXRT3UdSUW4t95P6"

snap = midtransclient.Snap(
    is_production=False,  # tetap False untuk tugas praktikum
    server_key=MIDTRANS_SERVER_KEY,
    client_key=MIDTRANS_CLIENT_KEY,
)

# --- MODEL DATABASE ---


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_premium = db.Column(db.Boolean, default=False)
    premium_expiry = db.Column(db.DateTime, nullable=True)
    company_logo = db.Column(db.String(200), nullable=True)
    company_address = db.Column(db.String(500), nullable=True)
    signature_file = db.Column(db.String(200), nullable=True)


# Fungsi Init DB
def init_db():
    with app.app_context():
        try:
            db.create_all()
            print(">>> SUKSES: Tabel Database Siap.")
            try:
                # Cek user demo
                if not User.query.filter_by(username="user_demo").first():
                    db.session.add(
                        User(
                            username="user_demo",
                            password="123",
                            is_premium=False,
                        )
                    )
                    db.session.commit()
                    print(">>> User Demo 'user_demo' berhasil dibuat.")
            except Exception:
                db.session.rollback()
        except Exception as e:
            print(f">>> ERROR DATABASE: {e}")


# --- HELPER GUEST (MODE TAMU) ---


class Guest:
    def __init__(self):
        self.id = None
        self.username = "Tamu (Guest)"
        self.is_premium = False
        self.company_logo = None
        self.company_address = None
        self.signature_file = None


# --- ROUTES ---


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        try:
            user = User.query.filter_by(
                username=username, password=password
            ).first()
            if user:
                session["user_id"] = user.id
                flash("Login Berhasil!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("Username atau Password salah.", "error")
        except Exception as e:
            flash(f"Database Error: {str(e)}", "error")
    return render_template("login.html")


@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]
    try:
        if User.query.filter_by(username=username).first():
            flash("Username sudah dipakai.", "error")
            return redirect(url_for("login"))

        new_user = User(username=username, password=password, is_premium=False)
        db.session.add(new_user)
        db.session.commit()
        flash("Pendaftaran Berhasil! Silakan Login.", "success")
    except Exception as e:
        flash(f"Error Register: {str(e)}", "error")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    user = None

    if "user_id" in session:
        try:
            user = User.query.get(session["user_id"])
            if user and user.is_premium and user.premium_expiry:
                if datetime.now() > user.premium_expiry:
                    user.is_premium = False
                    user.premium_expiry = None
                    db.session.commit()
                    flash("Langganan Premium Berakhir.", "warning")
        except Exception:
            # jika koneksi putus tiba-tiba
            pass

    if not user:
        user = Guest()

    return render_template(
        "dashboard.html",
        user=user,
        client_key=MIDTRANS_CLIENT_KEY,
    )


@app.route("/upload_logo", methods=["POST"])
def upload_logo():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    user = User.query.get(session["user_id"])
    if not user or not user.is_premium:
        return jsonify({"error": "Premium only"}), 403

    file = request.files.get("logo")
    if file:
        filename = secure_filename(f"logo_{user.id}_{int(time.time())}.png")
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        user.company_logo = filename
        db.session.commit()
        return jsonify({"success": True, "filename": filename})

    return jsonify({"error": "Upload gagal"}), 400


@app.route("/upload_signature", methods=["POST"])
def upload_signature():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    user = User.query.get(session["user_id"])
    if not user or not user.is_premium:
        return jsonify({"error": "Premium only"}), 403

    file = request.files.get("signature")
    if file:
        filename = secure_filename(f"sig_{user.id}_{int(time.time())}.png")
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        user.signature_file = filename
        db.session.commit()
        return jsonify({"success": True, "filename": filename})

    return jsonify({"error": "Upload gagal"}), 400


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


# Terima dua URL agar tidak 404 karena beda penamaan endpoint
@app.route("/getpaymenttoken", methods=["POST"])
@app.route("/get_payment_token", methods=["POST"])
def get_payment_token():
    # Samakan kunci session: di project banyak yang pakai 'user_id' / 'userid'
    uid = session.get("user_id") or session.get("userid")
    if not uid:
        return jsonify({"error": "login_required"}), 401

    user = User.query.get(uid)
    if not user:
        return jsonify({"error": "user_not_found"}), 401

    order_id = f"SUB-{user.id}-{int(time.time())}"
    param = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": 50000,
        },
        "customer_details": {
            "first_name": user.username,
            "email": "user@lokal.com",
        },
    }

    try:
        transaction = snap.create_transaction(param)
        return jsonify({"token": transaction["token"]})
    except Exception as e:
        print(f"Midtrans Error: {e}")
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
    return jsonify({"status": "success"})


@app.route("/generate_invoice", methods=["POST"])
def generate_invoice():
    # tentukan user / guest
    if "user_id" in session:
        user = User.query.get(session["user_id"])
    else:
        user = Guest()

    data = request.form
    template = data.get("template", "basic")

    # non-premium hanya boleh template basic
    if not getattr(user, "is_premium", False) and template != "basic":
        template = "basic"

    header_title = data.get("header_title", "INVOICE")
    bg_color = data.get("bg_color", "#ffffff")
    line_color = data.get("line_color", "#000000")

    items = []
    # nama field disesuaikan dengan dashboard.html (itemname, itemqty, itemprice)
    names = request.form.getlist("itemname")
    qtys = request.form.getlist("itemqty")
    prices = request.form.getlist("itemprice")

    grand_total = 0
    max_items = 10

    for i in range(min(len(names), max_items)):
        try:
            qty = int(qtys[i])
            price = int(prices[i])
        except (ValueError, IndexError):
            continue

        if price <= 0:
            continue

        total = qty * price
        grand_total += total
        items.append(
            {
                "name": names[i],
                "qty": qty,
                "price": price,
                "total": total,
            }
        )

    return render_template(
        "invoice_print_view.html",
        user=user,
        customer=data.get("customername", ""),
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
