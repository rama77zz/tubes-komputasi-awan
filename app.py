import os
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import midtransclient
import pymysql

pymysql.install_as_MySQLdb()

app = Flask(__name__)
app.secret_key = 'rahasia_lokal_123'

basedir = os.path.abspath(os.path.dirname(__file__))

# ambil dari env dulu, kalau tidak ada pakai default
database_uri = os.getenv('DATABASE_URL')

AZURE_DB_HOST = 'praktikum-crudtaufiq2311.mysql.database.azure.com'
AZURE_DB_USER = 'adminlogintest'
AZURE_DB_PASS = 'mpVYe8mXt8h2wdi'
AZURE_DB_NAME = 'invoiceinaja'

# if not database_uri:
#     database_uri = f"mysql+pymysql://{AZURE_DB_USER}:{AZURE_DB_PASS}@{AZURE_DB_HOST}/{AZURE_DB_NAME}"

# ssl_cert_path = os.path.join(basedir, "ssl", "combined-ca-certificates.pem")

if not database_uri:
    # fallback: pakai Azure MySQL TANPA SSL
    database_uri = f"mysql+pymysql://{AZURE_DB_USER}:{AZURE_DB_PASS}@{AZURE_DB_HOST}/{AZURE_DB_NAME}"

if database_uri:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'invoice.db')
    print(">>> MENGGUNAKAN DATABASE LOKAL.")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

MIDTRANS_SERVER_KEY = 'Mid-server-JEHBUtBFFwcJ8Sw8GypuXrQZ'
MIDTRANS_CLIENT_KEY = 'Mid-client-wXRT3UdSUW4t95P6'

snap = midtransclient.Snap(
    is_production=False,
    server_key=MIDTRANS_SERVER_KEY,
    client_key=MIDTRANS_CLIENT_KEY
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_premium = db.Column(db.Boolean, default=False)
    premium_expiry = db.Column(db.DateTime, nullable=True)
    company_logo = db.Column(db.String(200), nullable=True)
    company_address = db.Column(db.String(500), nullable=True)
    signature_file = db.Column(db.String(200), nullable=True)

def init_db():
    with app.app_context():
        try:
            db.create_all()
            print(">>> SUKSES: Tabel Database Siap.")

            try:
                if not User.query.filter_by(username='user_demo').first():
                    db.session.add(User(username='user_demo', password='123', is_premium=False))
                    db.session.commit()
                    print(">>> User Demo 'user_demo' berhasil dibuat.")
            except Exception:
                db.session.rollback()
                pass

        except Exception as e:
            print(f">>> ERROR DATABASE: {e}")

# DIPANGGIL DI SINI AGAR JALAN DI AZURE (gunicorn app:app)
init_db()

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            flash('Login Berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau Password salah.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    password = request.form['password']

    if User.query.filter_by(username=username).first():
        flash('Username sudah dipakai.', 'error')
        return redirect(url_for('login'))

    new_user = User(username=username, password=password, is_premium=False)
    db.session.add(new_user)
    db.session.commit()

    flash('Pendaftaran Berhasil! Silakan Login.', 'success')
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    user = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user and user.is_premium and user.premium_expiry:
            if datetime.now() > user.premium_expiry:
                user.is_premium = False
                user.premium_expiry = None
                db.session.commit()
                flash('Langganan Premium Berakhir.', 'warning')

    if not user:
        class Guest:
            def __init__(self):
                self.id = None
                self.username = "Tamu (Guest)"
                self.is_premium = False
                self.company_logo = None
                self.company_address = None
                self.signature_file = None
        user = Guest()

    return render_template('dashboard.html', user=user)
