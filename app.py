import os, sqlite3, secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY') or secrets.token_hex(32)
DB_PATH = os.path.join(os.path.dirname(__file__), 'novatrade.db')
START_BALANCE = 10000.0
PROFIT_TARGET = 0.08
DAILY_LOSS_LIMIT = 500.0
TOTAL_LOSS_LIMIT = 1000.0


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    with connect_db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            start_balance REAL NOT NULL DEFAULT 10000,
            balance REAL NOT NULL DEFAULT 10000,
            high_water REAL NOT NULL DEFAULT 10000,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            challenge_id INTEGER,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            amount REAL NOT NULL,
            pnl REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(challenge_id) REFERENCES challenges(id)
        );
        ''')


@app.before_request
def load_user():
    g.user = None
    if session.get('user_id'):
        with connect_db() as db:
            g.user = db.execute('SELECT id, username, email FROM users WHERE id=?', (session['user_id'],)).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.user:
            flash('برای ادامه ابتدا وارد حساب شو.', 'warning')
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper


def get_active_challenge(user_id):
    with connect_db() as db:
        return db.execute("SELECT * FROM challenges WHERE user_id=? AND status='active' ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()


def create_challenge(user_id):
    with connect_db() as db:
        db.execute('INSERT INTO challenges(user_id,start_balance,balance,high_water,status,created_at) VALUES(?,?,?,?,?,?)',
                   (user_id, START_BALANCE, START_BALANCE, START_BALANCE, 'active', datetime.utcnow().isoformat()))


@app.route('/')
def index():
    if g.user:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if len(username) < 3:
            flash('نام کاربری باید حداقل ۳ حرف باشد.', 'error')
        elif '@' not in email or '.' not in email:
            flash('ایمیل معتبر وارد کن.', 'error')
        elif len(password) < 8:
            flash('رمز عبور باید حداقل ۸ کاراکتر باشد.', 'error')
        else:
            try:
                with connect_db() as db:
                    cur = db.execute('INSERT INTO users(username,email,password_hash,created_at) VALUES(?,?,?,?)',
                                     (username, email, generate_password_hash(password), datetime.utcnow().isoformat()))
                    user_id = cur.lastrowid
                create_challenge(user_id)
                session['user_id'] = user_id
                flash('حساب ساخته شد. چالش آزمایشی NVProp آماده است.', 'success')
                return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError:
                flash('این نام کاربری یا ایمیل قبلاً ثبت شده است.', 'error')
    return render_template('auth.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identity = request.form.get('identity', '').strip().lower()
        password = request.form.get('password', '')
        with connect_db() as db:
            user = db.execute('SELECT * FROM users WHERE lower(username)=? OR lower(email)=?', (identity, identity)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            if not get_active_challenge(user['id']):
                create_challenge(user['id'])
            return redirect(url_for('dashboard'))
        flash('اطلاعات ورود درست نیست.', 'error')
    return render_template('auth.html', mode='login')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    challenge = get_active_challenge(g.user['id'])
    if not challenge:
        with connect_db() as db:
            challenge = db.execute('SELECT * FROM challenges WHERE user_id=? ORDER BY id DESC LIMIT 1', (g.user['id'],)).fetchone()
    with connect_db() as db:
        trades = db.execute('SELECT * FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 8', (g.user['id'],)).fetchall()
    balance = challenge['balance'] if challenge else START_BALANCE
    profit = balance - START_BALANCE
    progress = max(0, min(100, (profit / (START_BALANCE * PROFIT_TARGET)) * 100))
    return render_template('dashboard.html', challenge=challenge, trades=trades, balance=balance, profit=profit, progress=progress,
                           target=START_BALANCE * PROFIT_TARGET, daily_limit=DAILY_LOSS_LIMIT, total_limit=TOTAL_LOSS_LIMIT)


@app.route('/trade', methods=['POST'])
@login_required
def trade():
    symbol = request.form.get('symbol', 'BTCUSDT').strip().upper()
    side = request.form.get('side', 'buy').lower()
    try:
        amount = float(request.form.get('amount', '0'))
    except ValueError:
        amount = 0
    allowed_symbols = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'}
    if symbol not in allowed_symbols or side not in {'buy', 'sell'} or amount <= 0 or amount > 10000:
        flash('اطلاعات معامله معتبر نیست. مقدار باید بین ۰ تا ۱۰٬۰۰۰ دلار باشد.', 'error')
        return redirect(url_for('dashboard'))
    challenge = get_active_challenge(g.user['id'])
    if not challenge:
        flash('چالش فعال نداری؛ یک چالش جدید شروع کن.', 'warning')
        return redirect(url_for('dashboard'))
    # Educational simulation only: a randomized outcome, not a real market execution.
    import random
    pct = random.uniform(-0.025, 0.035)
    pnl = round(amount * pct, 2)
    new_balance = round(challenge['balance'] + pnl, 2)
    new_high = max(challenge['high_water'], new_balance)
    status = 'active'
    if new_balance >= challenge['start_balance'] * (1 + PROFIT_TARGET):
        status = 'passed'
    elif new_balance <= challenge['start_balance'] - TOTAL_LOSS_LIMIT:
        status = 'failed'
    with connect_db() as db:
        db.execute('INSERT INTO trades(user_id,challenge_id,symbol,side,amount,pnl,created_at) VALUES(?,?,?,?,?,?,?)',
                   (g.user['id'], challenge['id'], symbol, side, amount, pnl, datetime.utcnow().isoformat()))
        db.execute('UPDATE challenges SET balance=?, high_water=?, status=? WHERE id=?', (new_balance, new_high, status, challenge['id']))
    flash(f"معامله آزمایشی ثبت شد؛ نتیجه: {'+' if pnl >= 0 else ''}{pnl:.2f} دلار.", 'success')
    if status == 'passed': flash('تبریک! هدف سود چالش آزمایشی را زدی.', 'success')
    if status == 'failed': flash('چالش به‌دلیل عبور از حد ضرر کل رد شد.', 'error')
    return redirect(url_for('dashboard'))


@app.route('/challenge/restart', methods=['POST'])
@login_required
def restart_challenge():
    create_challenge(g.user['id'])
    flash('چالش آزمایشی جدید شروع شد.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/health')
def health():
    return {'status': 'ok', 'mode': 'demo-only'}


init_db()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')
