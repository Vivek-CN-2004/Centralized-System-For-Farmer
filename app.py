
import os
import sqlite3
import base64
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = 'super-secret-key-change-me'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

# ---------- DB Utilities ----------
def get_db():
    conn = sqlite3.connect(os.path.join(BASE_DIR, 'app.db'))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # users: role = farmer | buyer | admin
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    # products
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            phone TEXT,
            image_filename TEXT,
            sold INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(farmer_id) REFERENCES users(id)
        )
    """)
    # cart
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            FOREIGN KEY(buyer_id) REFERENCES users(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    """)
    # orders
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            farmer_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(buyer_id) REFERENCES users(id),
            FOREIGN KEY(farmer_id) REFERENCES users(id)
        )
    """)
    # reviews
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            text TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(buyer_id) REFERENCES users(id)
        )
    """)
    # notifications
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- Language (simple toggle) ----------
TRANSLATIONS = {
    'en': {'title': 'Centralized Farmer System', 'farmer': 'Farmer', 'buyer': 'Buyer', 'admin':'Admin', 'logout':'Logout'},
    'kn': {'title': 'ಕೇಂದ್ರೀಕೃತ ರೈತ ವ್ಯವಸ್ಥೆ', 'farmer': 'ರೈತ', 'buyer': 'ಖರೀದಿದಾರ', 'admin':'ನಿರ್ವಾಹಕ', 'logout':'ಲಾಗ್ ಔಟ್'}
}
def t(key):
    lang = session.get('lang', 'en')
    return TRANSLATIONS.get(lang, TRANSLATIONS['en']).get(key, key)

@app.context_processor
def inject_translations():
    return {'t': t, 'lang': session.get('lang','en')}

@app.route('/set-lang/<code>')
def set_lang(code):
    session['lang'] = 'kn' if code == 'kn' else 'en'
    return redirect(request.referrer or url_for('index'))

# ---------- Auth Helpers ----------
def login_user(user):
    session['user_id'] = user['id']
    session['role'] = user['role']
    session['name'] = user['name']

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    user = cur.fetchone()
    conn.close()
    return user

def require_role(role):
    user = current_user()
    return user and user['role'] == role

# ---------- Routes ----------
@app.route('/')
def index():
    return render_template('index.html')

# ---- Farmer Auth ----
@app.route('/farmer/register', methods=['GET','POST'])
def farmer_register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form.get('email','').strip().lower()
        phone = request.form.get('phone','').strip()
        password = request.form['password']
        conn = get_db(); cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO users (role, name, email, phone, password_hash, created_at)
                           VALUES (?,?,?,?,?,?)""",                        ('farmer', name, email or None, phone, generate_password_hash(password), datetime.utcnow().isoformat()))
            conn.commit()
            flash('Farmer registered! Please login.', 'success')
            return redirect(url_for('farmer_login'))
        except sqlite3.IntegrityError:
            flash('Email already in use.', 'danger')
        finally:
            conn.close()
    return render_template('farmer_login.html', mode='register')

@app.route('/farmer/login', methods=['GET','POST'])
def farmer_login():
    if request.method == 'POST':
        email_or_phone = request.form['email_or_phone'].strip().lower()
        password = request.form['password']
        conn = get_db(); cur = conn.cursor()
        if '@' in email_or_phone:
            cur.execute("SELECT * FROM users WHERE role='farmer' AND email=?", (email_or_phone,))
        else:
            cur.execute("SELECT * FROM users WHERE role='farmer' AND phone=?", (email_or_phone,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            login_user(user)
            return redirect(url_for('farmer_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('farmer_login.html', mode='login')

@app.route('/farmer/logout')
def farmer_logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/farmer/dashboard')
def farmer_dashboard():
    if not require_role('farmer'):
        flash('Please login as farmer.', 'warning')
        return redirect(url_for('farmer_login'))
    user = current_user()
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE farmer_id=? ORDER BY created_at DESC", (user['id'],))
    my_products = cur.fetchall()
    cur.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user['id'],))
    notes = cur.fetchall()
    conn.close()
    return render_template('farmer_dashboard.html', products=my_products, notes=notes)
@app.route('/farmer/add', methods=['GET','POST'])
def farmer_add():
    if not require_role('farmer'):
        flash('Please login as farmer.', 'warning')
        return redirect(url_for('farmer_login'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        price = float(request.form['price'])
        description = request.form.get('description','').strip()
        phone = request.form.get('phone','').strip()

        filename = None

        # 1️⃣ Handle file upload
        file = request.files.get('image')
        if file and allowed_file(file.filename):
            from werkzeug.utils import secure_filename
            filename = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(save_path)

        # 2️⃣ Handle camera image (base64)
        camera_data = request.form.get('camera_image')
        if camera_data:
            # Remove 'data:image/png;base64,' prefix
            header, encoded = camera_data.split(",", 1)
            data = base64.b64decode(encoded)
            filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_camera.png"
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(data)

        # Insert product into DB
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""INSERT INTO products (farmer_id, name, description, price, phone, image_filename, created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (session['user_id'], name, description, price, phone, filename, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()

        flash('Product added!', 'success')
        return redirect(url_for('farmer_dashboard'))

    return render_template('add_product.html')

@app.route('/farmer/delete/<int:pid>')
def farmer_delete(pid):
    if not require_role('farmer'):
        flash('Please login as farmer.', 'warning')
        return redirect(url_for('farmer_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=? AND farmer_id=?", (pid, session['user_id']))
    conn.commit(); conn.close()
    flash('Product deleted.', 'info')
    return redirect(url_for('farmer_dashboard'))

# ---- Buyer Auth ----
@app.route('/buyer/register', methods=['GET','POST'])
def buyer_register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form.get('email','').strip().lower()
        phone = request.form.get('phone','').strip()
        password = request.form['password']
        conn = get_db(); cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO users (role, name, email, phone, password_hash, created_at)
                           VALUES (?,?,?,?,?,?)""",                        ('buyer', name, email or None, phone, generate_password_hash(password), datetime.utcnow().isoformat()))
            conn.commit()
            flash('Buyer registered! Please login.', 'success')
            return redirect(url_for('buyer_login'))
        except sqlite3.IntegrityError:
            flash('Email already in use.', 'danger')
        finally:
            conn.close()
    return render_template('buyer_login.html', mode='register')

@app.route('/buyer/login', methods=['GET','POST'])
def buyer_login():
    if request.method == 'POST':
        email_or_phone = request.form['email_or_phone'].strip().lower()
        password = request.form['password']
        conn = get_db(); cur = conn.cursor()
        if '@' in email_or_phone:
            cur.execute("SELECT * FROM users WHERE role='buyer' AND email=?", (email_or_phone,))
        else:
            cur.execute("SELECT * FROM users WHERE role='buyer' AND phone=?", (email_or_phone,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            login_user(user)
            return redirect(url_for('buyer_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('buyer_login.html', mode='login')

@app.route('/buyer/logout')
def buyer_logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/buyer/dashboard')
def buyer_dashboard():
    if not require_role('buyer'):
        flash('Please login as buyer.', 'warning')
        return redirect(url_for('buyer_login'))
    uid = session['user_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT p.*, u.name AS farmer_name 
        FROM products p 
        JOIN users u ON p.farmer_id = u.id
        WHERE p.sold = 0
        ORDER BY p.created_at DESC
    """)
    products = cur.fetchall()
    cur.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (uid,))
    notes = cur.fetchall()
    conn.close()
    return render_template('buyer_dashboard.html', products=products, notes=notes)

# ---- Search & Suggest (English + simple Kannada synonyms) ----
KANNADA_MAP = {
    "akki": "rice",
    "godhi": "wheat",
    "ragi": "finger millet",
    "huruli": "horse gram",
    "togari": "pigeon pea",
    "kadale": "chickpea",
    "hasi avare": "beans",
    "bhatta": "paddy",
    "sakkare": "sugar",
    "tengu": "coconut",
    "hannu": "fruit"
}

@app.route('/api/suggest')
def api_suggest():
    q = request.args.get('q','').strip().lower()
    if not q:
        return jsonify([])
    qx = KANNADA_MAP.get(q, q)
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT name, COUNT(reviews.id) AS review_count, 
               COALESCE(AVG(reviews.rating),0) AS avg_rating
        FROM products
        LEFT JOIN reviews ON products.id = reviews.product_id
        WHERE sold=0 AND LOWER(name) LIKE ?
        GROUP BY name
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT 5
    """, (f'%{qx}%',))
    results = [{'name': r['name'], 'avg_rating': r['avg_rating'], 'review_count': r['review_count']} for r in cur.fetchall()]
    conn.close()
    return jsonify(results)

@app.route('/search')
def search():
    q = request.args.get('q','').strip().lower()
    qx = KANNADA_MAP.get(q, q)
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT p.*, u.name AS farmer_name
        FROM products p
        JOIN users u ON p.farmer_id = u.id
        LEFT JOIN reviews r ON p.id = r.product_id
        WHERE p.sold=0 AND (LOWER(p.name) LIKE ? OR LOWER(p.description) LIKE ?)
        GROUP BY p.id
        ORDER BY COALESCE(AVG(r.rating),0) DESC
    """, (f'%{qx}%', f'%{qx}%',))
    rows = cur.fetchall()
    conn.close()
    return render_template('buyer_dashboard.html', products=rows, notes=[], query=q)

# ---- Cart & Checkout ----
@app.route('/buyer/add_to_cart/<int:pid>')
def add_to_cart(pid):
    if not require_role('buyer'):
        flash('Please login as buyer.', 'warning')
        return redirect(url_for('buyer_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT sold FROM products WHERE id=?", (pid,))
    pr = cur.fetchone()
    if not pr or pr['sold'] == 1:
        flash('Item not available.', 'danger')
        conn.close()
        return redirect(url_for('buyer_dashboard'))
    cur.execute("SELECT id FROM cart WHERE buyer_id=? AND product_id=?", (session['user_id'], pid))
    if not cur.fetchone():
        cur.execute("INSERT INTO cart (buyer_id, product_id, added_at) VALUES (?,?,?)",
                    (session['user_id'], pid, datetime.utcnow().isoformat()))
        conn.commit()
    conn.close()
    flash('Added to cart.', 'success')
    return redirect(url_for('buyer_cart'))

@app.route('/buyer/cart')
def buyer_cart():
    if not require_role('buyer'):
        flash('Please login as buyer.', 'warning')
        return redirect(url_for('buyer_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT c.id as cart_id, p.* , u.name AS farmer_name
        FROM cart c
        JOIN products p ON c.product_id = p.id
        JOIN users u ON p.farmer_id = u.id
        WHERE c.buyer_id=?
    """, (session['user_id'],))
    items = cur.fetchall()
    conn.close()
    return render_template('cart.html', items=items)

@app.route('/buyer/remove_from_cart/<int:cart_id>')
def remove_from_cart(cart_id):
    if not require_role('buyer'):
        flash('Please login as buyer.', 'warning')
        return redirect(url_for('buyer_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM cart WHERE id=? AND buyer_id=?", (cart_id, session['user_id']))
    conn.commit(); conn.close()
    flash('Removed from cart.', 'info')
    return redirect(url_for('buyer_cart'))

@app.route('/buyer/checkout', methods=['POST'])
def checkout():
    if not require_role('buyer'):
        flash('Please login as buyer.', 'warning')
        return redirect(url_for('buyer_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT c.id as cart_id, p.id as pid, p.farmer_id
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.buyer_id=? AND p.sold=0
    """, (session['user_id'],))
    rows = cur.fetchall()
    if not rows:
        flash('Cart is empty or items unavailable.', 'warning')
        conn.close()
        return redirect(url_for('buyer_cart'))
    for r in rows:
        cur.execute("""INSERT INTO orders (product_id, buyer_id, farmer_id, status, created_at) VALUES (?,?,?,?,?)""",                    (r['pid'], session['user_id'], r['farmer_id'], 'placed_cod', datetime.utcnow().isoformat()))
        cur.execute("UPDATE products SET sold=1 WHERE id=?", (r['pid'],))
        cur.execute("""INSERT INTO notifications (user_id, message, created_at) VALUES (?,?,?)""",                    (r['farmer_id'], f"Your product #{r['pid']} was ordered (Cash on Delivery).", datetime.utcnow().isoformat()))
        cur.execute("""INSERT INTO notifications (user_id, message, created_at) VALUES (?,?,?)""",                    (session['user_id'], f"Order placed for product #{r['pid']} (COD).", datetime.utcnow().isoformat()))
    cur.execute("DELETE FROM cart WHERE buyer_id=?", (session['user_id'],))
    conn.commit(); conn.close()
    flash('Order placed! Seller and you have been notified. Items removed from listing.', 'success')
    return redirect(url_for('buyer_dashboard'))

# ---- Reviews ----
@app.route('/buyer/review/<int:pid>', methods=['POST'])
def review(pid):
    if not require_role('buyer'):
        flash('Login as buyer to review.', 'warning')
        return redirect(url_for('buyer_login'))
    rating = int(request.form['rating'])
    text = request.form.get('text','').strip()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""INSERT INTO reviews (product_id, buyer_id, rating, text, created_at) VALUES (?,?,?,?,?)""",                (pid, session['user_id'], rating, text, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    flash('Thanks for your review!', 'success')
    return redirect(request.referrer or url_for('buyer_dashboard'))

# ---- Admin ----
@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    # Permanent developer admin credentials (only known to developer)
    DEV_ADMIN_EMAIL = "developer@dev.com"
    DEV_ADMIN_PASSWORD = "vivekcn"

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        # Check if credentials match permanent developer admin
        if email == DEV_ADMIN_EMAIL and password == DEV_ADMIN_PASSWORD:
            # Create a fake user object for session
            user = {'id': 0, 'role': 'admin', 'name': 'Developer Admin'}
            login_user(user)
            # Set developer admin flag for require_role checks
            session['is_developer_admin'] = True
            flash('Developer admin logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

        flash('Invalid admin credentials', 'danger')

    return render_template('admin_login.html')

def require_role(role):
    user = current_user()
    # Normal users
    if user and user['role'] == role:
        return True

    # Special case: permanent developer admin
    if session.get('role') == 'admin' and session.get('is_developer_admin'):
        return True

    return False


@app.route('/admin/dashboard')
def admin_dashboard():
    if not require_role('admin'):
        flash('Admin only.', 'danger')
        return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE role!='admin' ORDER BY created_at DESC")
    users = cur.fetchall()
    cur.execute("""
        SELECT p.*, u.name as farmer_name FROM products p
        JOIN users u ON p.farmer_id=u.id
        ORDER BY p.created_at DESC
    """)
    products = cur.fetchall()
    conn.close()
    return render_template('admin_dashboard.html', users=users, products=products)

@app.route('/admin/delete_user/<int:uid>')
def admin_delete_user(uid):
    if not require_role('admin'):
        flash('Admin only.', 'danger')
        return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=? AND role!='admin'", (uid,))
    conn.commit(); conn.close()
    flash('User removed.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_product/<int:pid>')
def admin_delete_product(pid):
    if not require_role('admin'):
        flash('Admin only.', 'danger')
        return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit(); conn.close()
    flash('Product removed.', 'info')
    return redirect(url_for('admin_dashboard'))

# ---------- Static uploads serving ----------
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------- App start ----------
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True)
