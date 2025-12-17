import os
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import midtransclient

app = Flask(__name__)
app.secret_key = 'rahasia_lokal_123'

basedir = os.path.abspath(os.path.dirname(__file__))

# Ambil URL koneksi dari Environment Variables (Azure/Docker)
database_uri = os.getenv('DATABASE_URL') 

if database_uri:
    # Mode Produksi/Docker: Gunakan MySQL
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
    print(f">>> MENGGUNAKAN DATABASE EKSTERNAL.")
else:
    # Mode Lokal: Gunakan SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'invoice.db')
    print(">>> MENGGUNAKAN DATABASE LOKAL (SQLite).")
    
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# ... (lanjutan di bawahnya)

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
    company_address = db.Column(db.String(500), nullable=True) # Alamat Perusahaan
    signature_file = db.Column(db.String(200), nullable=True) # File Tanda Tangan

def init_db():
    with app.app_context():
        try:
            db.create_all()
            print(">>> SUKSES: Database Lokal SQLite Siap.")
            if not User.query.filter_by(username='user_demo').first():
                db.session.add(User(username='user_demo', password='123', is_premium=False))
                db.session.commit()
                print(">>> User Demo 'user_demo' berhasil dibuat.")
        except Exception as e:
            print(f">>> ERROR DATABASE: {e}")


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
            id = None
            username = "Tamu (Guest)"
            is_premium = False
            company_logo = None
            company_address = None
            signature_file = None
        user = Guest()

    return render_template('dashboard.html', user=user, client_key=MIDTRANS_CLIENT_KEY)

@app.route('/upload_logo', methods=['POST'])
def upload_logo():
    if 'user_id' not in session: return jsonify({'error': 'Login required'}), 401
    user = User.query.get(session['user_id'])
    if not user.is_premium: return jsonify({'error': 'Premium only'}), 403

    file = request.files.get('logo')
    if file:
        filename = secure_filename(f"logo_{user.id}_{int(time.time())}.png")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        user.company_logo = filename
        db.session.commit()
        return jsonify({'success': True, 'filename': filename})
    return jsonify({'error': 'Upload gagal'}), 400

@app.route('/upload_signature', methods=['POST'])
def upload_signature():
    if 'user_id' not in session: return jsonify({'error': 'Login required'}), 401
    user = User.query.get(session['user_id'])
    if not user.is_premium: return jsonify({'error': 'Premium only'}), 403

    file = request.files.get('signature')
    if file:
        filename = secure_filename(f"sig_{user.id}_{int(time.time())}.png")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        user.signature_file = filename
        db.session.commit()
        return jsonify({'success': True, 'filename': filename})
    return jsonify({'error': 'Upload gagal'}), 400

@app.route('/update_address', methods=['POST'])
def update_address():
    if 'user_id' not in session: return jsonify({'error': 'Login required'}), 401
    user = User.query.get(session['user_id'])
    if not user.is_premium: return jsonify({'error': 'Premium only'}), 403
    
    address = request.json.get('address')
    user.company_address = address
    db.session.commit()
    return jsonify({'success': True})

@app.route('/get_payment_token', methods=['POST'])
def get_payment_token():
    if 'user_id' not in session: return jsonify({'error': 'login_required'}), 401
    user = User.query.get(session['user_id'])
    param = {
        "transaction_details": {"order_id": f"SUB-{user.id}-{int(time.time())}", "gross_amount": 50000},
        "customer_details": {"first_name": user.username, "email": "user@lokal.com"}
    }
    try:
        transaction = snap.create_transaction(param)
        return jsonify({'token': transaction['token']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/payment_success', methods=['POST'])
def payment_success():
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    user = User.query.get(session['user_id'])
    user.is_premium = True
    user.premium_expiry = datetime.now() + timedelta(days=30)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/generate_invoice', methods=['POST'])
def generate_invoice():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
    else:
        class Guest:
            username = "Tamu"
            is_premium = False
            company_logo = None
            company_address = None
            signature_file = None
        user = Guest()
    
    data = request.form
    template = data.get('template', 'basic')
    if not user.is_premium and template != 'basic': template = 'basic'

    header_title = data.get('header_title', 'INVOICE') 
    bg_color = data.get('bg_color', '#ffffff') 
    line_color = data.get('line_color', '#000000') 

    items = []
    names = request.form.getlist('item_name[]')
    qtys = request.form.getlist('item_qty[]')
    prices = request.form.getlist('item_price[]')
    
    grand_total = 0
    max_items = 10
    for i in range(min(len(names), max_items)):
        qty = int(qtys[i])
        price = int(prices[i])
        if price <= 0: continue 
        
        total = qty * price
        grand_total += total
        items.append({'name': names[i], 'qty': qty, 'price': price, 'total': total})

    return render_template('invoice_print_view.html',
                           user=user,
                           customer=data['customer_name'],
                           items=items,
                           grand_total=grand_total,
                           template=template,
                           header_title=header_title,
                           bg_color=bg_color,
                           line_color=line_color,
                           date=datetime.now().strftime("%d %B %Y"))

if __name__ == '__main__':
    init_db()
    print("Menjalankan Server (Mode Lokal SQLite)...")
    app.run(debug=True, port=5000)