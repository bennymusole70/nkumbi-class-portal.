import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, request, redirect, url_for, session, flash,
    render_template_string, abort
)

# ============================================================
# NKUMBI CLASS PORTAL - COMPLETE SYSTEM
# Single-file Flask + SQLite application for Pydroid 3 & Render
# ============================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "nkumbi_class_portal.db")

app = Flask(__name__)
app.secret_key = os.environ.get("NKUMBI_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)

# ---------------------------- Database ----------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            student_number TEXT UNIQUE,
            email TEXT NOT NULL UNIQUE,
            programme TEXT NOT NULL DEFAULT '',
            department TEXT NOT NULL DEFAULT '',
            year_of_study TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            course TEXT NOT NULL DEFAULT '',
            instructions TEXT NOT NULL,
            due_date TEXT NOT NULL DEFAULT '',
            resource_link TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS schedule_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT NOT NULL DEFAULT 'Timetable',
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            event_date TEXT NOT NULL DEFAULT '',
            event_time TEXT NOT NULL DEFAULT '',
            venue TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Present',
            note TEXT NOT NULL DEFAULT '',
            marked_by INTEGER,
            UNIQUE(user_id, attendance_date),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(marked_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            course TEXT NOT NULL DEFAULT '',
            programme TEXT NOT NULL DEFAULT '',
            year_of_study TEXT NOT NULL DEFAULT '',
            duration_minutes INTEGER NOT NULL DEFAULT 30,
            opens_at TEXT NOT NULL DEFAULT '',
            closes_at TEXT NOT NULL DEFAULT '',
            is_published INTEGER NOT NULL DEFAULT 0,
            results_released INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question_type TEXT NOT NULL DEFAULT 'mcq',
            question_text TEXT NOT NULL,
            option_a TEXT DEFAULT '',
            option_b TEXT DEFAULT '',
            option_c TEXT DEFAULT '',
            option_d TEXT DEFAULT '',
            correct_answer TEXT DEFAULT '',
            marks INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS test_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            score REAL DEFAULT 0,
            total_marks REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'in_progress',
            FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS student_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            student_answer TEXT DEFAULT '',
            marks_awarded REAL DEFAULT 0,
            FOREIGN KEY(attempt_id) REFERENCES test_attempts(id) ON DELETE CASCADE,
            FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
        );
        """)
        
        user_cols = {r["name"] for r in db.execute("PRAGMA table_info(users)").fetchall()}
        for name, definition in [
            ("department", "TEXT NOT NULL DEFAULT ''"),
            ("year_of_study", "TEXT NOT NULL DEFAULT ''"),
            ("role", "TEXT NOT NULL DEFAULT 'student'"),
            ("created_at", "TEXT NOT NULL DEFAULT ''"),
        ]:
            if name not in user_cols:
                db.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

init_db()

def admin_exists():
    with get_db() as db:
        return db.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone() is not None

SETUP_KEY = secrets.token_urlsafe(18)
if not admin_exists():
    print("\n" + "=" * 58)
    print("NKUMBI CLASS PORTAL: FIRST-TIME ADMIN SETUP")
    print("Open the portal in your browser and visit /setup")
    print("Your one-time setup key is:")
    print(SETUP_KEY)
    print("Keep this key private. It will stop working after admin setup.")
    print("=" * 58 + "\n")

# ---------------------------- Security helpers ----------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    with get_db() as db:
        return db.execute(
            "SELECT id, full_name, student_number, email, programme, department, year_of_study, role, created_at "
            "FROM users WHERE id=?", (user_id,)
        ).fetchone()

# ---------------------------- Page design ----------------------------

BASE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#123b72">
<title>{{ title }} | Nkumbi Class Portal</title>
<style>
:root{--navy:#123b72;--blue:#2164c5;--sky:#eaf3ff;--gold:#ffbf47;--ink:#182230;--muted:#637083;--paper:#f5f7fb;--white:#fff;--line:#e1e7f0;--green:#137a4b;--red:#a92727}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:var(--paper);color:var(--ink);line-height:1.5}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
header{background:linear-gradient(120deg,#102f5e,#2164c5);color:#fff;padding:15px 0;box-shadow:0 4px 16px #0a2b551a}
.nav{max-width:1100px;margin:auto;padding:0 16px;display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.brand{font-weight:850;font-size:1.1rem;letter-spacing:.2px;color:#fff}.brand small{display:block;font-size:.72rem;font-weight:500;opacity:.82}
.navlinks{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.navlinks a{color:#fff;font-size:.92rem}
main{max-width:1100px;margin:24px auto;padding:0 16px 40px}
.hero{background:linear-gradient(125deg,#153b75,#2c78d7);color:white;padding:28px;border-radius:22px;position:relative;overflow:hidden;box-shadow:0 12px 28px #153b7520}
.hero:after{content:"";position:absolute;width:210px;height:210px;border-radius:50%;right:-55px;top:-85px;background:#ffffff12;border:25px solid #ffffff0c}
.hero h1{font-size:clamp(1.7rem,5vw,2.8rem);line-height:1.12;margin:0 0 12px;max-width:720px}.hero p{max-width:690px;color:#e4efff;margin:0 0 18px}
.btn{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:11px;padding:11px 16px;background:var(--blue);color:#fff;font-weight:700;font-size:.94rem;cursor:pointer;text-decoration:none}
.btn:hover{filter:brightness(.95);text-decoration:none}.btn.gold{background:var(--gold);color:#28200d}.btn.light{background:#fff;color:var(--navy)}.btn.danger{background:var(--red)}.btn.small{padding:7px 10px;font-size:.82rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,245px),1fr));gap:16px;margin-top:18px}
.card{background:#fff;border:1px solid var(--line);border-radius:17px;padding:19px;box-shadow:0 5px 18px #17335a08;min-width:0}
.card h2,.card h3{margin-top:0}.card h2{font-size:1.18rem}.card h3{font-size:1.02rem}
.muted{color:var(--muted);font-size:.92rem}.pill{display:inline-block;padding:4px 9px;border-radius:999px;background:var(--sky);color:var(--navy);font-size:.78rem;font-weight:750}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-top:18px}.stat{background:white;border:1px solid var(--line);border-radius:15px;padding:16px}.stat strong{display:block;font-size:1.7rem;color:var(--navy)}
.form-card{max-width:700px;margin:0 auto}.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:13px}
label{display:block;font-size:.9rem;font-weight:700;margin:10px 0 5px}input,textarea,select{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:10px;background:white;font:inherit;color:var(--ink)}textarea{min-height:105px;resize:vertical}input:focus,textarea:focus,select:focus{outline:2px solid #8dbaff;border-color:var(--blue)}
form .btn{margin-top:14px}.flash{padding:12px 14px;border-radius:10px;margin:0 0 12px;background:#eaf3ff;border:1px solid #c9ddff}.flash.success{background:#e9f8ef;border-color:#b9e8ca}.flash.warning{background:#fff5df;border-color:#f5d995}.flash.error{background:#ffeded;border-color:#f2bcbc}
.section-title{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;margin:25px 0 10px}.section-title h2{margin:0;font-size:1.35rem}
.item{border-bottom:1px solid var(--line);padding:13px 0}.item:last-child{border-bottom:0}.item h3{margin:0 0 5px}.item p{margin:5px 0;overflow-wrap:anywhere}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:620px;background:white}th,td{text-align:left;padding:11px;border-bottom:1px solid var(--line);font-size:.9rem}th{background:#eef4fc;color:#18365f}
.empty{padding:22px;text-align:center;color:var(--muted);background:#f8faff;border:1px dashed #cbd5e1;border-radius:12px}
footer{text-align:center;padding:22px 15px;color:var(--muted);font-size:.85rem}
hr{border:0;border-top:1px solid var(--line);margin:20px 0}
@media(max-width:540px){main{margin-top:16px}.hero{padding:22px 19px;border-radius:17px}.nav{align-items:flex-start}.navlinks{gap:9px}.navlinks a{font-size:.84rem}.card{padding:16px}}
</style>
</head>
<body>
<header><div class="nav">
<a class="brand" href="{{ url_for('home') }}">🎓 NKUMBI CLASS PORTAL<small>Nkumbi International College</small></a>
<nav class="navlinks">
{% if session.get('user_id') %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('tests_page') }}">Tests & Exams</a>
{% if session.get('role') == 'admin' %}<a href="{{ url_for('admin_dashboard') }}">Administration</a>{% endif %}
<a href="{{ url_for('profile') }}">My profile</a>
<a href="{{ url_for('logout') }}">Log out</a>
{% else %}
<a href="{{ url_for('login') }}">Log in</a><a href="{{ url_for('register') }}">Register</a>
{% endif %}
</nav></div></header>
<main>
{% with messages = get_flashed_messages(with_categories=true) %}
{% for category, message in messages %}<div class="flash {{ category }}">{{ message }}</div>{% endfor %}
{% endwith %}
{{ body|safe }}
</main>
<footer>Nkumbi Class Portal · A student information project · Keep your password private.</footer>
</body></html>
"""

def page(title, body, **context):
    body_html = render_template_string(body, **context)
    return render_template_string(BASE, title=title, body=body_html)

# ---------------------------- Public pages ----------------------------

@app.route("/")
def home():
    body = """
    <section class="hero">
      <span class="pill">ONE COLLEGE · ONE PORTAL</span>
      <h1>Your learning journey, organised in one place.</h1>
      <p>Welcome to the Nkumbi Class Portal for students across all programmes, departments and years of study at Nkumbi International College.</p>
      {% if session.get('user_id') %}
        <a class="btn gold" href="{{ url_for('dashboard') }}">Open my dashboard →</a>
      {% else %}
        <a class="btn gold" href="{{ url_for('register') }}">Create student account</a>
        <a class="btn light" href="{{ url_for('login') }}">Log in</a>
      {% endif %}
    </section>
    <div class="grid">
      <section class="card"><h2>📢 College announcements</h2><p class="muted">Read notices published by the portal administrator.</p></section>
      <section class="card"><h2>📝 Online tests & exams</h2><p class="muted">Take timed assessments and check your examination results.</p></section>
      <section class="card"><h2>📚 Learning materials</h2><p class="muted">Find course resources and learning links shared through the portal.</p></section>
    </div>
    <div class="section-title"><h2>Latest announcements</h2></div>
    {% if announcements %}
      <section class="card">{% for item in announcements %}
      <div class="item"><h3>{{ item['title'] }}</h3><p>{{ item['body'] }}</p><p class="muted">Posted {{ item['created_at'] }}</p></div>
      {% endfor %}</section>
    {% else %}<div class="empty">There are no announcements yet.</div>{% endif %}
    """
    with get_db() as db:
        announcements = db.execute("SELECT * FROM announcements ORDER BY id DESC LIMIT 5").fetchall()
    return page("Welcome", body, announcements=announcements)

@app.route("/setup", methods=["GET", "POST"])
def setup_admin():
    global SETUP_KEY
    if admin_exists():
        return page("Setup complete", """<div class=\"card\"><h2>Administrator already set up</h2><p>For safety, first-time setup is now closed.</p><a class=\"btn\" href=\"{{ url_for('login') }}\">Go to login</a></div>""")
    if request.method == "POST":
        key = request.form.get("setup_key", "")
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not secrets.compare_digest(key, SETUP_KEY):
            flash("The setup key is incorrect. Check the Pydroid console.", "error")
        elif not name or not email or len(password) < 10:
            flash("Enter your name and email. Use an administrator password of at least 10 characters.", "warning")
        else:
            try:
                with get_db() as db:
                    db.execute("""INSERT INTO users(full_name, student_number, email, programme, department, year_of_study, password_hash, role, created_at)
                                  VALUES(?, NULL, ?, '', '', '', ?, 'admin', ?)""",
                               (name, email, generate_password_hash(password), now_text()))
                SETUP_KEY = ""
                flash("Administrator account created. Log in with your email and password.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email address is already in use.", "error")
    body = """
    <section class="card form-card"><h1>First-time administrator setup</h1>
    <p class="muted">Use the one-time key printed in the Pydroid console. This page closes after an administrator is created.</p>
    <form method="post">
      <label>One-time setup key</label><input name="setup_key" required autocomplete="off">
      <label>Administrator full name</label><input name="full_name" required maxlength="100">
      <label>Administrator email</label><input type="email" name="email" required maxlength="160">
      <label>Create password (at least 10 characters)</label><input type="password" name="password" required minlength="10" autocomplete="new-password">
      <button class="btn" type="submit">Create administrator</button>
    </form></section>
    """
    return page("Administrator setup", body)

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        student_no = request.form.get("student_number", "").strip().upper()
        email = request.form.get("email", "").strip().lower()
        programme = request.form.get("programme", "").strip()
        department = request.form.get("department", "").strip()
        year = request.form.get("year_of_study", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not all([name, student_no, email, programme, password, confirm]):
            flash("Please complete all required fields.", "warning")
        elif len(name) > 100 or len(student_no) > 50 or len(email) > 160:
            flash("One of the fields is too long. Please shorten it.", "warning")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "warning")
        elif password != confirm:
            flash("The passwords do not match.", "error")
        else:
            try:
                with get_db() as db:
                    db.execute("""INSERT INTO users(full_name, student_number, email, programme, department, year_of_study, password_hash, role, created_at)
                                  VALUES(?,?,?,?,?,?,?,'student',?)""",
                               (name, student_no, email, programme, department, year,
                                generate_password_hash(password), now_text()))
                flash("Registration successful. You can now log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That student number or email is already registered.", "error")
    body = """
    <section class="card form-card"><h1>Create your student account</h1>
    <p class="muted">Open to students from every programme, department and year at Nkumbi International College.</p>
    <form method="post">
      <div class="form-grid">
        <div><label>Full name *</label><input name="full_name" required maxlength="100" autocomplete="name"></div>
        <div><label>Student number *</label><input name="student_number" required maxlength="50" autocomplete="off"></div>
        <div><label>Email address *</label><input type="email" name="email" required maxlength="160" autocomplete="email"></div>
        <div><label>Programme *</label><input name="programme" required maxlength="120" placeholder="e.g. Diploma in Secondary Teaching"></div>
        <div><label>Department (optional)</label><input name="department" maxlength="120" placeholder="e.g. Education"></div>
        <div><label>Year of study (optional)</label><select name="year_of_study"><option value="">Choose year</option><option>Year 1</option><option>Year 2</option><option>Year 3</option><option>Year 4</option><option>Other</option></select></div>
        <div><label>Password (at least 8 characters) *</label><input type="password" name="password" required minlength="8" autocomplete="new-password"></div>
        <div><label>Confirm password *</label><input type="password" name="confirm_password" required minlength="8" autocomplete="new-password"></div>
      </div>
      <button class="btn" type="submit">Register account</button>
    </form><p class="muted">Already registered? <a href="{{ url_for('login') }}">Log in</a>.</p></section>
    """
    return page("Student registration", body)

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]
            flash("Welcome back, " + user["full_name"] + ".", "success")
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    body = """
    <section class="card form-card"><h1>Log in</h1><p class="muted">Enter the email and password connected to your account.</p>
    <form method="post"><label>Email address</label><input type="email" name="email" required autocomplete="username">
    <label>Password</label><input type="password" name="password" required autocomplete="current-password">
    <button class="btn" type="submit">Log in</button></form>
    <p class="muted">New student? <a href="{{ url_for('register') }}">Create an account</a>.</p></section>
    """
    return page("Log in", body)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("home"))

# ---------------------------- Student pages ----------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    with get_db() as db:
        announcements = db.execute("SELECT * FROM announcements ORDER BY id DESC LIMIT 5").fetchall()
        materials = db.execute("SELECT * FROM materials ORDER BY id DESC LIMIT 5").fetchall()
        assignments = db.execute("SELECT * FROM assignments ORDER BY id DESC LIMIT 5").fetchall()
        tests = db.execute("SELECT * FROM tests WHERE is_published=1 ORDER BY id DESC LIMIT 5").fetchall()
        schedule = db.execute("SELECT * FROM schedule_items ORDER BY CASE WHEN event_date='' THEN 1 ELSE 0 END, event_date, event_time LIMIT 8").fetchall()
        attendance_count = db.execute("SELECT COUNT(*) AS n FROM attendance WHERE user_id=?", (user["id"],)).fetchone()["n"]
    body = """
    <section class="hero"><span class="pill">{% if user['role']=='admin' %}ADMINISTRATOR{% else %}STUDENT DASHBOARD{% endif %}</span>
    <h1>Hello, {{ user['full_name'] }} 👋</h1><p>Your Nkumbi Class Portal overview. Check tests, new notices, learning resources and academic dates here.</p>
    {% if user['role']=='admin' %}<a class="btn gold" href="{{ url_for('admin_dashboard') }}">Open administration →</a>{% endif %}</section>
    <div class="stats">
      <div class="stat"><span class="muted">Published tests</span><strong>{{ tests|length }}</strong></div>
      <div class="stat"><span class="muted">Learning resources</span><strong>{{ materials|length }}</strong></div>
      <div class="stat"><span class="muted">Assignments shown</span><strong>{{ assignments|length }}</strong></div>
      <div class="stat"><span class="muted">Attendance entries</span><strong>{{ attendance_count }}</strong></div>
    </div>
    <div class="section-title"><h2>📝 Available Tests & Exams</h2><a href="{{ url_for('tests_page') }}">View all tests</a></div>
    <section class="card">{% if tests %}{% for t in tests %}<div class="item"><h3>{{ t['title'] }}</h3><p class="muted">Course: {{ t['course'] or 'General' }} · Duration: {{ t['duration_minutes'] }} mins</p><a class="btn small" href="{{ url_for('take_test', test_id=t['id']) }}">Open test →</a></div>{% endfor %}{% else %}<div class="empty">No tests available right now.</div>{% endif %}</section>
    <div class="section-title"><h2>📢 Announcements</h2><a href="{{ url_for('announcements_page') }}">View all</a></div>
    <section class="card">{% if announcements %}{% for x in announcements %}<div class="item"><h3>{{ x['title'] }}</h3><p>{{ x['body'] }}</p><p class="muted">{{ x['created_at'] }}</p></div>{% endfor %}{% else %}<div class="empty">No announcements yet.</div>{% endif %}</section>
    <div class="section-title"><h2>📚 Learning materials</h2><a href="{{ url_for('materials_page') }}">View all</a></div>
    <section class="card">{% if materials %}{% for x in materials %}<div class="item"><h3>{{ x['title'] }}</h3><p class="muted">{{ x['subject'] }} · {{ x['description'] }}</p>{% if x['link'] %}<a href="{{ x['link'] }}" target="_blank" rel="noopener">Open resource ↗</a>{% endif %}</div>{% endfor %}{% else %}<div class="empty">No learning materials yet.</div>{% endif %}</section>
    <div class="section-title"><h2>🗓️ Timetable and exam information</h2><a href="{{ url_for('schedule_page') }}">View all</a></div>
    <section class="card">{% if schedule %}{% for x in schedule %}<div class="item"><span class="pill">{{ x['item_type'] }}</span><h3>{{ x['title'] }}</h3><p>{{ x['details'] }}</p><p class="muted">{{ x['event_date'] or 'Date not set' }} · {{ x['event_time'] or 'Time not set' }} · {{ x['venue'] or 'Venue not set' }}</p></div>{% endfor %}{% else %}<div class="empty">No schedule information posted yet.</div>{% endif %}</section>
    """
    return page("Dashboard", body, user=user, announcements=announcements, materials=materials,
                assignments=assignments, tests=tests, schedule=schedule, attendance_count=attendance_count)

@app.route("/tests")
@login_required
def tests_page():
    user = current_user()
    with get_db() as db:
        tests = db.execute("SELECT * FROM tests WHERE is_published=1 ORDER BY id DESC").fetchall()
        attempts = db.execute("SELECT * FROM test_attempts WHERE user_id=?", (user["id"],)).fetchall()
        attempt_map = {a["test_id"]: a for a in attempts}
    body = """
    <div class="section-title"><h1>📝 Online Tests & Examinations</h1></div>
    {% if tests %}
      <section class="card">
        {% for t in tests %}
          {% set att = attempt_map.get(t['id']) %}
          <div class="item">
            <h3>{{ t['title'] }}</h3>
            <p class="muted">Course: {{ t['course'] or 'General' }} · Duration: {{ t['duration_minutes'] }} minutes</p>
            {% if att %}
              <p><strong>Status:</strong> 
                {% if att['status'] == 'in_progress' %}In Progress <a class="btn small" href="{{ url_for('take_test', test_id=t['id']) }}">Continue test</a>
                {% elif att['status'] == 'submitted' %}Submitted (Waiting for grading / results release)
                {% elif att['status'] == 'graded' %}Graded — Score: {{ att['score'] }} / {{ att['total_marks'] }}
                {% endif %}
              </p>
            {% else %}
              <a class="btn small" href="{{ url_for('take_test', test_id=t['id']) }}">Start Test</a>
            {% endif %}
          </div>
        {% endfor %}
      </section>
    {% else %}
      <div class="empty">No tests are currently published.</div>
    {% endif %}
    """
    return page("Tests", body, tests=tests, attempt_map=attempt_map)

@app.route("/tests/<int:test_id>", methods=["GET", "POST"])
@login_required
def take_test(test_id):
    user = current_user()
    with get_db() as db:
        test = db.execute("SELECT * FROM tests WHERE id=? AND is_published=1", (test_id,)).fetchone()
        if not test:
            abort(404)
        
        questions = db.execute("SELECT * FROM questions WHERE test_id=?", (test_id,)).fetchall()
        attempt = db.execute("SELECT * FROM test_attempts WHERE test_id=? AND user_id=?", (test_id, user["id"])).fetchone()

        if request.method == "POST":
            if not attempt or attempt["status"] != "in_progress":
                flash("This test is already submitted or closed.", "error")
                return redirect(url_for("tests_page"))
            
            total_score = 0
            max_marks = sum(q["marks"] for q in questions)

            for q in questions:
                ans_key = f"q_{q['id']}"
                student_ans = request.form.get(ans_key, "").strip()
                
                marks_awarded = 0
                if q["question_type"] in {"mcq", "true_false"}:
                    if student_ans.upper() == q["correct_answer"].upper():
                        marks_awarded = q["marks"]
                
                total_score += marks_awarded

                db.execute("""INSERT INTO student_answers(attempt_id, question_id, student_answer, marks_awarded)
                              VALUES(?,?,?,?)""",
                           (attempt["id"], q["id"], student_ans, marks_awarded))

            db.execute("""UPDATE test_attempts SET submitted_at=?, score=?, total_marks=?, status='submitted' WHERE id=?""",
                       (now_text(), total_score, max_marks, attempt["id"]))
            
            flash("Test submitted successfully!", "success")
            return redirect(url_for("tests_page"))

        if not attempt:
            cursor = db.execute("""INSERT INTO test_attempts(test_id, user_id, started_at, status)
                                   VALUES(?,?,?, 'in_progress')""",
                                (test_id, user["id"], now_text()))
            attempt = db.execute("SELECT * FROM test_attempts WHERE id=?", (cursor.lastrowid,)).fetchone()
        elif attempt["status"] != "in_progress":
            body = """
            <div class="card">
              <h2>Test already submitted</h2>
              <p>You submitted this test on {{ attempt['submitted_at'] }}.</p>
              {% if test['results_released'] == 1 %}
                <p><strong>Your Score:</strong> {{ attempt['score'] }} / {{ attempt['total_marks'] }}</p>
              {% else %}
                <p>Results have not been released by the lecturer yet.</p>
              {% endif %}
              <a class="btn" href="{{ url_for('tests_page') }}">Back to tests</a>
            </div>
            """
            return page("Test Submitted", body, attempt=attempt, test=test)

    body = """
    <section class="card">
      <h1>{{ test['title'] }}</h1>
      <p class="muted">Course: {{ test['course'] }} · Duration: {{ test['duration_minutes'] }} minutes</p>
      <hr>
      <form method="post">
        {% for q in questions %}
          <div class="item" style="margin-bottom: 20px;">
            <p><strong>Q{{ loop.index }}. ({{ q['marks'] }} mark{% if q['marks']>1 %}s{% endif %})</strong> {{ q['question_text'] }}</p>
            {% if q['question_type'] == 'mcq' %}
              <div><label><input type="radio" name="q_{{ q['id'] }}" value="A"> A) {{ q['option_a'] }}</label></div>
              <div><label><input type="radio" name="q_{{ q['id'] }}" value="B"> B) {{ q['option_b'] }}</label></div>
              <div><label><input type="radio" name="q_{{ q['id'] }}" value="C"> C) {{ q['option_c'] }}</label></div>
              <div><label><input type="radio" name="q_{{ q['id'] }}" value="D"> D) {{ q['option_d'] }}</label></div>
            {% elif q['question_type'] == 'true_false' %}
              <div><label><input type="radio" name="q_{{ q['id'] }}" value="True"> True</label></div>
              <div><label><input type="radio" name="q_{{ q['id'] }}" value="False"> False</label></div>
            {% elif q['question_type'] == 'written' %}
              <textarea name="q_{{ q['id'] }}" placeholder="Type your answer here..." required></textarea>
            {% endif %}
          </div>
        {% endfor %}
        <button class="btn gold" type="submit" onclick="return confirm('Are you sure you want to submit your test?');">Submit Test</button>
      </form>
    </section>
    """
    return page(test["title"], body, test=test, questions=questions)

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        programme = request.form.get("programme", "").strip()
        department = request.form.get("department", "").strip()
        year = request.form.get("year_of_study", "").strip()
        if not name or not programme:
            flash("Full name and programme are required.", "warning")
        else:
            with get_db() as db:
                db.execute("UPDATE users SET full_name=?, programme=?, department=?, year_of_study=? WHERE id=?",
                           (name, programme, department, year, user["id"]))
            session["full_name"] = name
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    body = """
    <section class="card form-card"><h1>My profile</h1><p class="muted">Your account email and student number cannot be changed here.</p>
    <form method="post"><label>Full name</label><input name="full_name" required value="{{ user['full_name'] }}">
    <label>Email</label><input value="{{ user['email'] }}" disabled>
    <label>Student number</label><input value="{{ user['student_number'] or 'Administrator account' }}" disabled>
    <label>Programme</label><input name="programme" required value="{{ user['programme'] }}">
    <label>Department</label><input name="department" value="{{ user['department'] }}">
    <label>Year of study</label><select name="year_of_study"><option value="">Not specified</option>{% for y in ['Year 1','Year 2','Year 3','Year 4','Other'] %}<option {% if user['year_of_study']==y %}selected{% endif %}>{{ y }}</option>{% endfor %}</select>
    <button class="btn" type="submit">Save profile</button></form></section>
    """
    return page("My profile", body, user=user)

@app.route("/announcements")
@login_required
def announcements_page():
    with get_db() as db:
        items = db.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()
    body = """<div class="section-title"><h1>📢 Announcements</h1></div>
    {% if items %}<section class="card">{% for x in items %}<div class="item"><h3>{{ x['title'] }}</h3><p>{{ x['body'] }}</p><p class="muted">Posted {{ x['created_at'] }}</p></div>{% endfor %}</section>{% else %}<div class="empty">No announcements yet.</div>{% endif %}"""
    return page("Announcements", body, items=items)

@app.route("/materials")
@login_required
def materials_page():
    with get_db() as db:
        items = db.execute("SELECT * FROM materials ORDER BY id DESC").fetchall()
    body = """<div class="section-title"><h1>📚 Learning materials</h1></div>
    {% if items %}<section class="card">{% for x in items %}<div class="item"><h3>{{ x['title'] }}</h3><p class="muted">{{ x['subject'] }} · {{ x['description'] }}</p>{% if x['link'] %}<a href="{{ x['link'] }}" target="_blank" rel="noopener">Open resource ↗</a>{% endif %}</div>{% endfor %}</section>{% else %}<div class="empty">No materials have been added yet.</div>{% endif %}"""
    return page("Learning materials", body, items=items)

@app.route("/schedule")
@login_required
def schedule_page():
    with get_db() as db:
        items = db.execute("SELECT * FROM schedule_items ORDER BY CASE WHEN event_date='' THEN 1 ELSE 0 END, event_date, event_time").fetchall()
    body = """<div class="section-title"><h1>🗓️ Timetable and examinations</h1></div>
    {% if items %}<section class="card">{% for x in items %}<div class="item"><span class="pill">{{ x['item_type'] }}</span><h3>{{ x['title'] }}</h3><p>{{ x['details'] }}</p><p class="muted">{{ x['event_date'] or 'Date not set' }} · {{ x['event_time'] or 'Time not set' }} · {{ x['venue'] or 'Venue not set' }}</p></div>{% endfor %}</section>{% else %}<div class="empty">No timetable or examination information has been posted.</div>{% endif %}"""
    return page("Schedule", body, items=items)

@app.route("/attendance")
@login_required
def attendance_page():
    user = current_user()
    with get_db() as db:
        if user["role"] == "admin":
            rows = db.execute("""SELECT a.*, u.full_name, u.student_number FROM attendance a
                                 JOIN users u ON u.id=a.user_id ORDER BY a.attendance_date DESC, u.full_name LIMIT 300""").fetchall()
        else:
            rows = db.execute("SELECT * FROM attendance WHERE user_id=? ORDER BY attendance_date DESC", (user["id"],)).fetchall()
    body = """<div class="section-title"><h1>🟢 Attendance records</h1>{% if user['role']=='admin' %}<a class="btn small" href="{{ url_for('admin_dashboard') }}">Manage attendance</a>{% endif %}</div>
    {% if rows %}<div class="card table-wrap"><table><thead><tr>{% if user['role']=='admin' %}<th>Student</th><th>Student number</th>{% endif %}<th>Date</th><th>Status</th><th>Note</th></tr></thead><tbody>
    {% for x in rows %}<tr>{% if user['role']=='admin' %}<td>{{ x['full_name'] }}</td><td>{{ x['student_number'] }}</td>{% endif %}<td>{{ x['attendance_date'] }}</td><td>{{ x['status'] }}</td><td>{{ x['note'] }}</td></tr>{% endfor %}
    </tbody></table></div>{% else %}<div class="empty">No attendance records found.</div>{% endif %}"""
    return page("Attendance", body, user=user, rows=rows)

# ---------------------------- Administrator pages ----------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    with get_db() as db:
        counts = {
            "students": db.execute("SELECT COUNT(*) n FROM users WHERE role='student'").fetchone()["n"],
            "tests": db.execute("SELECT COUNT(*) n FROM tests").fetchone()["n"],
            "materials": db.execute("SELECT COUNT(*) n FROM materials").fetchone()["n"],
            "assignments": db.execute("SELECT COUNT(*) n FROM assignments").fetchone()["n"],
        }
        students = db.execute("SELECT id, full_name, student_number, email, programme, department, year_of_study FROM users WHERE role='student' ORDER BY full_name LIMIT 100").fetchall()
        tests = db.execute("SELECT * FROM tests ORDER BY id DESC").fetchall()
    body = """
    <section class="hero"><span class="pill">ADMINISTRATION</span><h1>Portal management</h1><p>Manage student accounts, tests, and publish information for the whole college.</p></section>
    <div class="stats">
      <div class="stat"><span class="muted">Student accounts</span><strong>{{ counts['students'] }}</strong></div>
      <div class="stat"><span class="muted">Tests created</span><strong>{{ counts['tests'] }}</strong></div>
      <div class="stat"><span class="muted">Materials</span><strong>{{ counts['materials'] }}</strong></div>
      <div class="stat"><span class="muted">Assignments</span><strong>{{ counts['assignments'] }}</strong></div>
    </div>
    
    <div class="section-title"><h2>📝 Test & Examination Management</h2><a class="btn small gold" href="{{ url_for('admin_create_test') }}">Create New Test</a></div>
    <section class="card">
      {% if tests %}
        <div class="table-wrap"><table><thead><tr><th>Title</th><th>Course</th><th>Duration</th><th>Published</th><th>Results</th><th>Actions</th></tr></thead><tbody>
        {% for t in tests %}
          <tr>
            <td>{{ t['title'] }}</td>
            <td>{{ t['course'] }}</td>
            <td>{{ t['duration_minutes'] }}m</td>
            <td>{% if t['is_published'] %}Yes{% else %}No{% endif %}</td>
            <td>{% if t['results_released'] %}Released{% else %}Hidden{% endif %}</td>
            <td>
              <a class="btn small" href="{{ url_for('admin_questions', test_id=t['id']) }}">Questions</a>
              <a class="btn small light" href="{{ url_for('admin_submissions', test_id=t['id']) }}">Submissions</a>
              <a class="btn small" href="{{ url_for('admin_edit_test', test_id=t['id']) }}">Settings</a>
            </td>
          </tr>
        {% endfor %}
        </tbody></table></div>
      {% else %}
        <div class="empty">No tests created yet. Click "Create New Test" above.</div>
      {% endif %}
    </section>

    <div class="grid">
      <section class="card"><h2>📢 Publish announcement</h2><form method="post" action="{{ url_for('admin_announcement') }}"><label>Title</label><input name="title" required maxlength="180"><label>Message</label><textarea name="body" required maxlength="5000"></textarea><button class="btn" type="submit">Publish</button></form></section>
      <section class="card"><h2>📚 Add learning material</h2><form method="post" action="{{ url_for('admin_material') }}"><label>Title</label><input name="title" required maxlength="180"><label>Subject / course</label><input name="subject" maxlength="180"><label>Description</label><textarea name="description" maxlength="3000"></textarea><label>Resource URL (optional)</label><input type="url" name="link" placeholder="https://..."><button class="btn" type="submit">Add material</button></form></section>
    </div>
    """
    return page("Administration", body, counts=counts, students=students, tests=tests)

@app.route("/admin/tests/create", methods=["GET", "POST"])
@admin_required
def admin_create_test():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        course = request.form.get("course", "").strip()
        programme = request.form.get("programme", "").strip()
        year = request.form.get("year_of_study", "").strip()
        duration = int(request.form.get("duration_minutes", 30))
        is_published = 1 if request.form.get("is_published") else 0
        
        with get_db() as db:
            cur = db.execute("""INSERT INTO tests(title, course, programme, year_of_study, duration_minutes, is_published, created_by, created_at)
                                VALUES(?,?,?,?,?,?,?,?)""",
                             (title, course, programme, year, duration, is_published, session["user_id"], now_text()))
            test_id = cur.lastrowid
        flash("Test created. Now add questions.", "success")
        return redirect(url_for("admin_questions", test_id=test_id))
    
    body = """
    <section class="card form-card">
      <h1>Create Online Test</h1>
      <form method="post">
        <label>Test Title *</label><input name="title" required placeholder="e.g. Mid-Term Examination">
        <label>Course / Subject</label><input name="course" placeholder="e.g. Mathematics">
        <label>Programme</label><input name="programme" placeholder="e.g. Diploma in Secondary Teaching">
        <label>Year of Study</label><select name="year_of_study"><option value="">All years</option><option>Year 1</option><option>Year 2</option><option>Year 3</option><option>Year 4</option></select>
        <label>Duration (minutes)</label><input type="number" name="duration_minutes" value="30" required min="5">
        <label><input type="checkbox" name="is_published" value="1"> Publish immediately for students</label>
        <button class="btn" type="submit">Save and Add Questions</button>
      </form>
    </section>
    """
    return page("Create Test", body)

@app.route("/admin/tests/<int:test_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_test(test_id):
    with get_db() as db:
        test = db.execute("SELECT * FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            abort(404)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            course = request.form.get("course", "").strip()
            duration = int(request.form.get("duration_minutes", 30))
            is_published = 1 if request.form.get("is_published") else 0
            results_released = 1 if request.form.get("results_released") else 0
            
            db.execute("""UPDATE tests SET title=?, course=?, duration_minutes=?, is_published=?, results_released=? WHERE id=?""",
                       (title, course, duration, is_published, results_released, test_id))
            flash("Test settings updated.", "success")
            return redirect(url_for("admin_dashboard"))
    
    body = """
    <section class="card form-card">
      <h1>Edit Test Settings</h1>
      <form method="post">
        <label>Test Title</label><input name="title" required value="{{ test['title'] }}">
        <label>Course</label><input name="course" value="{{ test['course'] }}">
        <label>Duration (minutes)</label><input type="number" name="duration_minutes" value="{{ test['duration_minutes'] }}" required>
        <label><input type="checkbox" name="is_published" value="1" {% if test['is_published'] %}checked{% endif %}> Published to students</label>
        <label><input type="checkbox" name="results_released" value="1" {% if test['results_released'] %}checked{% endif %}> Release results to students</label>
        <button class="btn" type="submit">Update Test</button>
      </form>
    </section>
    """
    return page("Edit Test", body, test=test)

@app.route("/admin/tests/<int:test_id>/questions", methods=["GET", "POST"])
@admin_required
def admin_questions(test_id):
    with get_db() as db:
        test = db.execute("SELECT * FROM tests WHERE id=?", (test_id,)).fetchone()
        if not test:
            abort(404)
        
        if request.method == "POST":
            q_type = request.form.get("question_type", "mcq")
            q_text = request.form.get("question_text", "").strip()
            marks = int(request.form.get("marks", 1))
            
            opt_a = request.form.get("option_a", "")
            opt_b = request.form.get("option_b", "")
            opt_c = request.form.get("option_c", "")
            opt_d = request.form.get("option_d", "")
            correct = request.form.get("correct_answer", "").strip()
            
            db.execute("""INSERT INTO questions(test_id, question_type, question_text, option_a, option_b, option_c, option_d, correct_answer, marks)
                          VALUES(?,?,?,?,?,?,?,?,?)""",
                       (test_id, q_type, q_text, opt_a, opt_b, opt_c, opt_d, correct, marks))
            flash("Question added successfully.", "success")
            return redirect(url_for("admin_questions", test_id=test_id))
        
        questions = db.execute("SELECT * FROM questions WHERE test_id=?", (test_id,)).fetchall()

    body = """
    <section class="card">
      <h1>Add Questions: {{ test['title'] }}</h1>
      <form method="post">
        <label>Question Type</label>
        <select name="question_type" onchange="toggleOptions(this.value)">
          <option value="mcq">Multiple Choice (A, B, C, D)</option>
          <option value="true_false">True or False</option>
          <option value="written">Written Answer (Manual grading)</option>
        </select>
        
        <label>Question Text *</label><textarea name="question_text" required></textarea>
        
        <div id="mcq_options">
          <label>Option A</label><input name="option_a">
          <label>Option B</label><input name="option_b">
          <label>Option C</label><input name="option_c">
          <label>Option D</label><input name="option_d">
          <label>Correct Answer (A, B, C, or D)</label><input name="correct_answer" maxlength="1">
        </div>

        <label>Marks</label><input type="number" name="marks" value="1" required min="1">
        <button class="btn" type="submit" style="margin-top:15px;">Add Question</button>
      </form>
    </section>

    <div class="section-title"><h2>Current Questions ({{ questions|length }})</h2></div>
    <section class="card">
      {% if questions %}
        {% for q in questions %}
          <div class="item">
            <p><strong>Q{{ loop.index }}. [{{ q['question_type']|upper }}]</strong> {{ q['question_text'] }} (Marks: {{ q['marks'] }})</p>
            {% if q['question_type'] == 'mcq' %}
              <p class="muted">A) {{ q['option_a'] }} | B) {{ q['option_b'] }} | C) {{ q['option_c'] }} | D) {{ q['option_d'] }} — <strong>Correct: {{ q['correct_answer'] }}</strong></p>
            {% elif q['question_type'] == 'true_false' %}
              <p class="muted"><strong>Correct: {{ q['correct_answer'] }}</strong></p>
            {% endif %}
          </div>
        {% endfor %}
      {% else %}
        <div class="empty">No questions added to this test yet.</div>
      {% endif %}
    </section>
    <p><a class="btn light" href="{{ url_for('admin_dashboard') }}">← Return to Admin Dashboard</a></p>

    <script>
    function toggleOptions(val) {
        document.getElementById('mcq_options').style.display = (val === 'mcq') ? 'block' : 'none';
    }
    </script>
    """
    return page("Manage Questions", body, test=test, questions=questions)

@app.route("/admin/tests/<int:test_id>/submissions")
@admin_required
def admin_submissions(test_id):
    with get_db() as db:
        test = db.execute("SELECT * FROM tests WHERE id=?", (test_id,)).fetchone()
        attempts = db.execute("""SELECT ta.*, u.full_name, u.student_number FROM test_attempts ta
                                 JOIN users u ON u.id=ta.user_id WHERE ta.test_id=? ORDER BY ta.submitted_at DESC""", (test_id,)).fetchall()
    body = """
    <section class="card">
      <h1>Submissions: {{ test['title'] }}</h1>
      {% if attempts %}
        <div class="table-wrap"><table><thead><tr><th>Student</th><th>Number</th><th>Submitted At</th><th>Score</th><th>Status</th><th>Action</th></tr></thead><tbody>
        {% for a in attempts %}
          <tr>
            <td>{{ a['full_name'] }}</td>
            <td>{{ a['student_number'] }}</td>
            <td>{{ a['submitted_at'] or 'In progress' }}</td>
            <td>{{ a['score'] }} / {{ a['total_marks'] }}</td>
            <td>{{ a['status'] }}</td>
            <td><a class="btn small" href="{{ url_for('admin_grade_attempt', attempt_id=a['id']) }}">Review & Grade</a></td>
          </tr>
        {% endfor %}
        </tbody></table></div>
      {% else %}
        <div class="empty">No student submissions yet.</div>
      {% endif %}
    </section>
    <p><a class="btn light" href="{{ url_for('admin_dashboard') }}">← Return to Dashboard</a></p>
    """
    return page("Submissions", body, test=test, attempts=attempts)

@app.route("/admin/attempt/<int:attempt_id>/grade", methods=["GET", "POST"])
@admin_required
def admin_grade_attempt(attempt_id):
    with get_db() as db:
        attempt = db.execute("SELECT ta.*, u.full_name, u.student_number, t.title FROM test_attempts ta JOIN users u ON u.id=ta.user_id JOIN tests t ON t.id=ta.test_id WHERE ta.id=?", (attempt_id,)).fetchone()
        if not attempt:
            abort(404)
        
        if request.method == "POST":
            total_score = 0
            answers = db.execute("SELECT sa.*, q.marks FROM student_answers sa JOIN questions q ON q.id=sa.question_id WHERE sa.attempt_id=?", (attempt_id,)).fetchall()
            
            for ans in answers:
                awarded = float(request.form.get(f"marks_{ans['id']}", ans["marks_awarded"]))
                db.execute("UPDATE student_answers SET marks_awarded=? WHERE id=?", (awarded, ans["id"]))
                total_score += awarded
            
            db.execute("UPDATE test_attempts SET score=?, status='graded' WHERE id=?", (total_score, attempt_id))
            flash("Grades updated successfully.", "success")
            return redirect(url_for('admin_submissions', test_id=attempt["test_id"]))

        answers = db.execute("""SELECT sa.*, q.question_text, q.question_type, q.correct_answer, q.marks 
                                FROM student_answers sa JOIN questions q ON q.id=sa.question_id WHERE sa.attempt_id=?""", (attempt_id,)).fetchall()

    body = """
    <section class="card">
      <h1>Grading: {{ attempt['full_name'] }} ({{ attempt['student_number'] }})</h1>
      <p class="muted">Test: {{ attempt['title'] }}</p>
      <form method="post">
        {% for a in answers %}
          <div class="item">
            <p><strong>{{ a['question_text'] }}</strong> (Max marks: {{ a['marks'] }})</p>
            <p><strong>Student Answer:</strong> {{ a['student_answer'] }}</p>
            {% if a['question_type'] == 'written' %}
              <label>Marks Awarded</label>
              <input type="number" step="0.5" name="marks_{{ a['id'] }}" value="{{ a['marks_awarded'] }}" max="{{ a['marks'] }}" min="0" required>
            {% else %}
              <p class="muted">Auto-graded marks: {{ a['marks_awarded'] }} / {{ a['marks'] }}</p>
            {% endif %}
          </div>
        {% endfor %}
        <button class="btn gold" type="submit">Save Grades</button>
      </form>
    </section>
    """
    return page("Grade Student Attempt", body, attempt=attempt, answers=answers)

@app.route("/admin/announcement", methods=["POST"])
@admin_required
def admin_announcement():
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    if not title or not body:
        flash("Enter both the announcement title and message.", "warning")
    else:
        with get_db() as db:
            db.execute("INSERT INTO announcements(title, body, created_by, created_at) VALUES(?,?,?,?)",
                       (title, body, session["user_id"], now_text()))
        flash("Announcement published.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/material", methods=["POST"])
@admin_required
def admin_material():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    description = request.form.get("description", "").strip()
    link = request.form.get("link", "").strip()
    if not title:
        flash("Enter a title for the material.", "warning")
    else:
        with get_db() as db:
            db.execute("INSERT INTO materials(title, subject, description, link, created_by, created_at) VALUES(?,?,?,?,?,?)",
                       (title, subject, description, link, session["user_id"], now_text()))
        flash("Learning material added.", "success")
    return redirect(url_for("admin_dashboard"))

@app.errorhandler(403)
def forbidden(_error):
    return page("Access denied", """<section class=\"card\"><h1>403 — Access denied</h1><p>This page is only available to the portal administrator.</p><a class=\"btn\" href=\"{{ url_for('dashboard') }}\">Return to dashboard</a></section>"""), 403

@app.errorhandler(404)
def not_found(_error):
    return page("Page not found", """<section class=\"card\"><h1>404 — Page not found</h1><p>The page you requested does not exist.</p><a class=\"btn\" href=\"{{ url_for('home') }}\">Go home</a></section>"""), 404

if __name__ == "__main__":
    print("Nkumbi Class Portal is starting...")
    print("On this phone, open: http://127.0.0.1:5000")
    print("Keep Pydroid running while using the portal.")
    app.run(host="127.0.0.1", port=5000, debug=False)
