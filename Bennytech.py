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

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "nkumbi_class_portal.db")

app = Flask(__name__)
app.secret_key = os.environ.get("NKUMBI_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)

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
        """)

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

init_db()

def admin_exists():
    with get_db() as db:
        return db.execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone() is not None

SETUP_KEY = "bennytechsolution"

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

BASE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | Nkumbi Class Portal</title>
<style>
:root{--navy:#123b72;--blue:#2164c5;--sky:#eaf3ff;--gold:#ffbf47;--ink:#182230;--muted:#637083;--white:#fff;--line:#e1e7f0;--red:#a92727}
*{box-sizing:border-box}
body{
    margin:0; font-family:system-ui,-apple-system,sans-serif;
    background: linear-gradient(270deg, #0f2027, #203a43, #2c5364, #123b72, #2164c5);
    background-size: 600% 600%;
    animation: techBackground 18s ease infinite;
    color: var(--ink); line-height: 1.5; min-height: 100vh; display: flex; flex-direction: column;
}
@keyframes techBackground {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
header{background:rgba(16, 47, 94, 0.95); backdrop-filter: blur(10px); color:#fff;padding:15px 0; border-bottom: 1px solid rgba(255,255,255,0.1)}
.nav{max-width:1100px;margin:auto;padding:0 16px;display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.brand{font-weight:850;font-size:1.1rem;color:#fff}.brand small{display:block;font-size:.72rem;font-weight:500;opacity:.82}
.navlinks{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.navlinks a{color:#fff;font-size:.92rem}
main{max-width:1100px;width:100%;margin:24px auto;padding:0 16px 40px;flex:1}
.card{background:rgba(255, 255, 255, 0.96); backdrop-filter: blur(12px); border:1px solid var(--line);border-radius:17px;padding:20px;box-shadow:0 8px 32px rgba(0,0,0,0.15);margin-bottom:16px}
.btn{display:inline-flex;align-items:center;justify-content:center;border:0;border-radius:11px;padding:10px 15px;background:var(--blue);color:#fff;font-weight:700;cursor:pointer;text-decoration:none;font-size:.9rem}
.btn.gold{background:var(--gold);color:#28200d}
label{display:block;font-size:.9rem;font-weight:700;margin:10px 0 5px}input,textarea,select{width:100%;padding:11px;border:1px solid #cbd5e1;border-radius:10px;background:white;font:inherit}
.flash{padding:12px 14px;border-radius:10px;margin:0 0 12px;background:#eaf3ff;border:1px solid #c9ddff}
.flash.success{background:#e9f8ef;border-color:#b9e8ca}.flash.error{background:#ffeded;border-color:#f2bcbc}
.form-card{max-width:700px;margin:0 auto}
.grid-2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
footer{text-align:center;padding:22px;color:#fff;font-size:.85rem;background:rgba(0,0,0,0.2); margin-top: auto;}
</style>
</head>
<body>
<header><div class="nav">
<a class="brand" href="{{ url_for('home') }}">🎓 NKUMBI CLASS PORTAL<small>Powered by Benny Tech Solution</small></a>
<nav class="navlinks">
{% if session.get('user_id') %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
{% if session.get('role') == 'admin' %}<a href="{{ url_for('admin_dashboard') }}">Administration</a>{% endif %}
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
<footer>Nkumbi Class Portal &copy; 2026 · Benny Tech Solution</footer>
</body></html>
"""

def page(title, body, **context):
    body_html = render_template_string(body, **context)
    return render_template_string(BASE, title=title, body=body_html)

@app.route("/")
def home():
    body = """
    <div class="card" style="background:linear-gradient(125deg,#153b75,#2c78d7);color:white;padding:32px;">
      <h1>Welcome to Nkumbi Class Portal</h1>
      <p style="font-size:1.1rem; opacity:0.9;">Comprehensive academic management system for students and staff.</p>
      {% if not session.get('user_id') %}
        <div style="margin-top:20px;">
          <a class="btn gold" href="{{ url_for('login') }}">Log in to Portal</a>
          <a class="btn" style="background:#fff;color:#123b72;margin-left:10px;" href="{{ url_for('register') }}">Student Registration</a>
        </div>
      {% endif %}
    </div>
    """
    return page("Welcome", body)

@app.route("/setup", methods=["GET", "POST"])
def setup_admin():
    if admin_exists():
        return page("Setup complete", '<div class="card"><h2>Administrator already set up</h2><p><a class="btn" href="' + url_for('login') + '">Go to login</a></p></div>')
    
    if request.method == "POST":
        key = request.form.get("setup_key", "")
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        
        if not secrets.compare_digest(key, SETUP_KEY):
            flash("Incorrect setup key. Use: bennytechsolution", "error")
        elif not name or not email or len(password) < 10:
            flash("Provide a name, valid email, and a password of at least 10 characters.", "error")
        else:
            try:
                with get_db() as db:
                    db.execute("INSERT INTO users(full_name, email, password_hash, role, created_at) VALUES(?, ?, ?, 'admin', ?)",
                               (name, email, generate_password_hash(password), now_text()))
                flash("Administrator account created successfully! Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email address is already in use.", "error")
                
    body = f"""
    <div class="card form-card">
      <h1>First-time administrator setup</h1>
      <div style="background:#eaf3ff; border:1px solid #2164c5; padding:12px; border-radius:10px; margin-bottom:15px;">
        <strong>Your Permanent Setup Key:</strong> <code style="background:#fff; padding:3px 6px; font-weight:bold; color:#123b72;">{SETUP_KEY}</code>
      </div>
      <form method="post">
        <label>Setup Key</label><input name="setup_key" required autocomplete="off" placeholder="Enter key here">
        <label>Full Name</label><input name="full_name" required>
        <label>Email Address</label><input type="email" name="email" required>
        <label>Password (at least 10 characters)</label><input type="password" name="password" required minlength="10">
        <button class="btn" type="submit" style="margin-top:14px;">Create administrator</button>
      </form>
    </div>
    """
    return page("Administrator Setup", body)

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        student_no = request.form.get("student_number", "").strip().upper()
        email = request.form.get("email", "").strip().lower()
        programme = request.form.get("programme", "").strip()
        password = request.form.get("password", "")
        if not all([name, student_no, email, programme, password]):
            flash("Please complete all required fields.", "error")
        else:
            try:
                with get_db() as db:
                    db.execute("INSERT INTO users(full_name, student_number, email, programme, password_hash, role, created_at) VALUES(?,?,?,?,?,'student',?)",
                               (name, student_no, email, programme, generate_password_hash(password), now_text()))
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Student number or email already registered.", "error")
    body = """
    <div class="card form-card">
      <h1>Student Registration</h1>
      <form method="post">
        <label>Full Name</label><input name="full_name" required>
        <label>Student Number</label><input name="student_number" required>
        <label>Email Address</label><input type="email" name="email" required>
        <label>Programme</label><input name="programme" required>
        <label>Password</label><input type="password" name="password" required>
        <button class="btn" type="submit" style="margin-top:14px;">Register Account</button>
      </form>
    </div>
    """
    return page("Register", body)

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
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "dashboard"))
        flash("Invalid email or password.", "error")
    body = """
    <div class="card form-card">
      <h1>Portal Login</h1>
      <form method="post">
        <label>Email Address</label><input type="email" name="email" required>
        <label>Password</label><input type="password" name="password" required>
        <button class="btn" type="submit" style="margin-top:14px;">Log In</button>
      </form>
    </div>
    """
    return page("Login", body)

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))
    
    with get_db() as db:
        announcements = db.execute("SELECT * FROM announcements ORDER BY id DESC LIMIT 5").fetchall()
        materials = db.execute("SELECT * FROM materials ORDER BY id DESC LIMIT 5").fetchall()
        assignments = db.execute("SELECT * FROM assignments ORDER BY id DESC LIMIT 5").fetchall()
        schedule = db.execute("SELECT * FROM schedule_items ORDER BY id DESC LIMIT 5").fetchall()
        
    body = f"""
    <div class="card" style="background:linear-gradient(120deg,#123b72,#2164c5); color:#fff;">
      <h1>Student Dashboard</h1>
      <p>Welcome back, <strong>{user['full_name']}</strong> ({user['student_number']}) — Programme: {user['programme']}</p>
    </div>
    
    <div class="grid-2">
      <div class="card">
        <h3>📢 Recent Announcements</h3>
        {% if announcements %}
          <ul style="padding-left:18px;">
          {% for a in announcements %}
            <li style="margin-bottom:10px;"><strong>{a['title']}</strong><br><small style="color:var(--muted);">{a['created_at']}</small><p style="margin:4px 0 0 0;">{a['body']}</p></li>
          {% endfor %}
          </ul>
        {% else %}
          <p style="color:var(--muted);">No announcements posted yet.</p>
        {% endif %}
      </div>
      
      <div class="card">
        <h3>📚 Course Materials</h3>
        {% if materials %}
          <ul style="padding-left:18px;">
          {% for m in materials %}
            <li style="margin-bottom:10px;"><strong>{m['title']}</strong> ({m['subject']})<br><a href="{m['link']}" target="_blank">Download / View Resource</a></li>
          {% endfor %}
          </ul>
        {% else %}
          <p style="color:var(--muted);">No learning materials uploaded yet.</p>
        {% endif %}
      </div>
    </div>
    
    <div class="grid-2" style="margin-top:16px;">
      <div class="card">
        <h3>📝 Assignments</h3>
        {% if assignments %}
          <ul style="padding-left:18px;">
          {% for ass in assignments %}
            <li style="margin-bottom:10px;"><strong>{ass['title']}</strong> ({ass['course']})<br><small style="color:var(--muted);">Due: {ass['due_date']}</small><p style="margin:4px 0 0 0;">{ass['instructions']}</p></li>
          {% endfor %}
          </ul>
        {% else %}
          <p style="color:var(--muted);">No pending assignments.</p>
        {% endif %}
      </div>
      
      <div class="card">
        <h3>📅 Class Timetable & Schedule</h3>
        {% if schedule %}
          <ul style="padding-left:18px;">
          {% for s in schedule %}
            <li style="margin-bottom:10px;"><strong>{s['title']}</strong> ({s['item_type']})<br><small style="color:var(--muted);">Venue: {s['venue']} | Time: {s['event_date']}</small></li>
          {% endfor %}
          </ul>
        {% else %}
          <p style="color:var(--muted);">No schedule items posted.</p>
        {% endif %}
      </div>
    </div>
    """
    return page("Student Dashboard", body)

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    action = request.args.get("action", "announcements")
    
    if request.method == "POST":
        form_type = request.form.get("form_type")
        if form_type == "announcement":
            title = request.form.get("title", "").strip()
            body_text = request.form.get("body", "").strip()
            if title and body_text:
                with get_db() as db:
                    db.execute("INSERT INTO announcements(title, body, created_by, created_at) VALUES(?, ?, ?, ?)",
                               (title, body_text, session.get("user_id"), now_text()))
                flash("Announcement posted successfully!", "success")
        elif form_type == "material":
            title = request.form.get("title", "").strip()
            subject = request.form.get("subject", "").strip()
            description = request.form.get("description", "").strip()
            link = request.form.get("link", "").strip()
            if title:
                with get_db() as db:
                    db.execute("INSERT INTO materials(title, subject, description, link, created_by, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                               (title, subject, description, link, session.get("user_id"), now_text()))
                flash("Learning material added successfully!", "success")
        elif form_type == "assignment":
            title = request.form.get("title", "").strip()
            course = request.form.get("course", "").strip()
            instructions = request.form.get("instructions", "").strip()
            due_date = request.form.get("due_date", "").strip()
            if title:
                with get_db() as db:
                    db.execute("INSERT INTO assignments(title, course, instructions, due_date, created_by, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                               (title, course, instructions, due_date, session.get("user_id"), now_text()))
                flash("Assignment posted successfully!", "success")
        elif form_type == "schedule":
            item_type = request.form.get("item_type", "Timetable")
            title = request.form.get("title", "").strip()
            venue = request.form.get("venue", "").strip()
            event_date = request.form.get("event_date", "").strip()
            if title:
                with get_db() as db:
                    db.execute("INSERT INTO schedule_items(item_type, title, venue, event_date, created_by, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                               (item_type, title, venue, event_date, session.get("user_id"), now_text()))
                flash("Schedule item added successfully!", "success")
        return redirect(url_for("admin_dashboard", action=form_type or "announcements"))
        
    body = f"""
    <div class="card" style="background:linear-gradient(120deg,#102f5e,#2164c5); color:#fff;">
      <h1>Administration Dashboard</h1>
      <p>Manage college announcements, learning materials, assignments, and timetables.</p>
      <div style="margin-top:15px; display:flex; gap:10px; flex-wrap:wrap;">
        <a class="btn gold" href="{url_for('admin_dashboard', action='announcements')}">Announcements</a>
        <a class="btn" style="background:#fff;color:#123b72;" href="{url_for('admin_dashboard', action='materials')}">Upload Materials</a>
        <a class="btn" style="background:#fff;color:#123b72;" href="{url_for('admin_dashboard', action='assignments')}">Post Assignments</a>
        <a class="btn" style="background:#fff;color:#123b72;" href="{url_for('admin_dashboard', action='schedule')}">Timetable / Schedule</a>
      </div>
    </div>
    """
    
    if action == "announcements" or action == "":
        body += """
        <div class="card form-card">
          <h2>Post New Announcement</h2>
          <form method="post">
            <input type="hidden" name="form_type" value="announcement">
            <label>Title</label><input name="title" required>
            <label>Body</label><textarea name="body" required style="min-height:90px;"></textarea>
            <button class="btn" type="submit" style="margin-top:14px;">Publish Announcement</button>
          </form>
        </div>"""
    elif action == "materials":
        body += """
        <div class="card form-card">
          <h2>Upload Learning Material</h2>
          <form method="post">
            <input type="hidden" name="form_type" value="material">
            <label>Material Title</label><input name="title" required>
            <label>Subject / Course</label><input name="subject" required>
            <label>Resource Link (URL)</label><input name="link" placeholder="https://..." required>
            <label>Description</label><textarea name="description"></textarea>
            <button class="btn" type="submit" style="margin-top:14px;">Save Material</button>
          </form>
        </div>"""
    elif action == "assignments":
        body += """
        <div class="card form-card">
          <h2>Post Assignment</h2>
          <form method="post">
            <input type="hidden" name="form_type" value="assignment">
            <label>Assignment Title</label><input name="title" required>
            <label>Course Name</label><input name="course" required>
            <label>Due Date</label><input type="date" name="due_date" required>
            <label>Instructions</label><textarea name="instructions" required></textarea>
            <button class="btn" type="submit" style="margin-top:14px;">Publish Assignment</button>
          </form>
        </div>"""
    elif action == "schedule":
        body += """
        <div class="card form-card">
          <h2>Add Schedule / Timetable Item</h2>
          <form method="post">
            <input type="hidden" name="form_type" value="schedule">
            <label>Type</label><select name="item_type"><option>Timetable</option><option>Exam Schedule</option><option>Event</option></select>
            <label>Title</label><input name="title" required>
            <label>Venue</label><input name="venue">
            <label>Date & Time</label><input name="event_date" placeholder="e.g. Monday 10:00 AM">
            <button class="btn" type="submit" style="margin-top:14px;">Add to Schedule</button>
          </form>
        </div>"""
        
    return page("Administration Dashboard", body)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
