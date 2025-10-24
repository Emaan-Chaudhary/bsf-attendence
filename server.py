from flask import Flask, request, render_template, redirect, session, url_for, send_file, make_response
from flask_session import Session
from datetime import datetime, timedelta
import pymysql
import atexit
import pandas as pd
from io import BytesIO
import os
from dotenv import load_dotenv
import pytz
import secrets  # For session tokens

# -------------------------
# LOAD ENV VARIABLES
# -------------------------
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "flask_mysql_db")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "yourpassword")
DB_NAME = os.getenv("DB_NAME", "bsfattendence")
DB_PORT = int(os.getenv("DB_PORT", 3306))
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

# -------------------------
# GLOBAL ADMIN LIST
# -------------------------
ADMIN_USERS = ["areeba_admin", "kaenat_admin", "shahzeb_admin"]

# -------------------------
# APP CONFIGURATION
# -------------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "./flask_sessions"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
Session(app)
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)

# -------------------------
# DB CONNECTION FUNCTION
# -------------------------
def get_db_connection():
    try:
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print("❌ DB Connection Failed:", e)
        return None

# -------------------------
# CLEANUP ON SERVER SHUTDOWN
# -------------------------
def reset_all_logins_and_clear_logs():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE loginstatus SET logged_in=0, session_token=NULL")
                conn.commit()
                print("✅ All loginstatus reset on shutdown.")
        except Exception as e:
            print(f"❌ Cleanup failed: {e}")
        finally:
            conn.close()

atexit.register(reset_all_logins_and_clear_logs)

# -------------------------
# SESSION INACTIVITY TRACKER
# -------------------------
@app.before_request
def track_last_active():
    username = session.get("username")
    token = session.get("session_token")
    if username and token:
        pakistan_tz = pytz.timezone("Asia/Karachi")
        now = datetime.now(pakistan_tz)
        last_active = session.get("last_active")

        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT session_token FROM loginstatus WHERE username=%s", (username,))
                    db_token = cur.fetchone()
                    if not db_token or db_token["session_token"] != token:
                        session.clear()
                        return redirect(url_for("login"))

                    # Auto-logout after 30 min inactivity
                    if last_active and (now - last_active).total_seconds() > 30*60:
                        cur.execute("UPDATE loginstatus SET logged_in=0, session_token=NULL WHERE username=%s", (username,))
                        conn.commit()
                        session.clear()
                        return redirect(url_for("login"))

            finally:
                conn.close()
        session["last_active"] = now

# -------------------------
# LOGIN PAGE
# -------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if "username" in session:
        username = session["username"]
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE loginstatus SET logged_in=0, session_token=NULL WHERE username=%s", (username,))
                conn.commit()
            conn.close()
        session.clear()

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db_connection()
        if not conn:
            return render_template("login.html", error="Database not connected.")

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username=%s", (username,))
                user = cur.fetchone()
                if not user or user["password"] != password:
                    error = "Invalid username or password."
                    return render_template("login.html", error=error)

                cur.execute("SELECT logged_in FROM loginstatus WHERE username=%s", (username,))
                status = cur.fetchone()
                if status and status["logged_in"] == 1:
                    error = f"User '{username}' is already logged in."
                    return render_template("login.html", error=error)

                # Generate session token
                token = secrets.token_hex(32)
                cur.execute("""
                    INSERT INTO loginstatus (username, logged_in, session_token)
                    VALUES (%s, 1, %s)
                    ON DUPLICATE KEY UPDATE logged_in=1, session_token=%s
                """, (username, token, token))
                conn.commit()
        finally:
            conn.close()

        # Set session
        session.permanent = True
        session["username"] = username
        session["session_token"] = token
        session["last_active"] = datetime.now(pytz.timezone("Asia/Karachi"))

        if username.lower() in ADMIN_USERS:
            resp = make_response(redirect(url_for("admin_logs")))
            resp.set_cookie("admin_token", "secureadmin", max_age=1800)
            return resp
        else:
            return redirect(url_for("user_dashboard"))

    return render_template("login.html", error=error)

# -------------------------
# USER DASHBOARD
# -------------------------
@app.route("/user-dashboard", methods=["GET", "POST"])
def user_dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    pakistan_tz = pytz.timezone("Asia/Karachi")
    username = session["username"]
    today = datetime.now(pakistan_tz).date()
    clicked_actions = {}

    conn = get_db_connection()
    if not conn:
        return "❌ Database connection failed."

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_actions WHERE username=%s AND action_date=%s", (username, today))
            existing = cursor.fetchone()

            if not existing:
                cursor.execute("INSERT INTO user_actions (username, action_date) VALUES (%s,%s)", (username, today))
                conn.commit()
                cursor.execute("SELECT * FROM user_actions WHERE username=%s AND action_date=%s", (username, today))
                existing = cursor.fetchone()

            clicked_actions = {
                "Start": bool(existing["start_time"]),
                "Break": bool(existing["break_time"]),
                "Back at Seat": bool(existing["onseat_time"]),
                "Leave": bool(existing["leave_time"])
            }

            if request.method == "POST":
                action = request.form.get("actionBtn")
                current_time = datetime.now(pakistan_tz).time()
                action_map = {
                    "Start": "start_time",
                    "Break 15 min": "break_time",
                    "Break 30 min": "break_time",
                    "Back at Seat": "onseat_time",
                    "Leave": "leave_time"
                }

                if action in action_map and not existing[action_map[action]]:
                    cursor.execute(f"UPDATE user_actions SET {action_map[action]}=%s WHERE id=%s", (current_time, existing["id"]))
                    cursor.execute(f"""
                        INSERT INTO logs (username, log_date, {action_map[action]})
                        VALUES (%s,%s,%s)
                        ON DUPLICATE KEY UPDATE {action_map[action]}=VALUES({action_map[action]})
                    """, (username, today, current_time))
                    conn.commit()

                    # Update clicked_actions
                    if action == "Start":
                        clicked_actions["Start"] = True
                    elif action in ["Break 15 min", "Break 30 min"]:
                        clicked_actions["Break"] = True
                    elif action == "Back at Seat":
                        clicked_actions["Back at Seat"] = True
                    elif action == "Leave":
                        clicked_actions["Leave"] = True

    finally:
        conn.close()

    return render_template("user_dashboard.html", username=username, clicked_actions=clicked_actions)

# -------------------------
# ADMIN LOGS
# -------------------------
@app.route("/logs")
def admin_logs():
    username = session.get("username")
    admin_cookie = request.cookies.get("admin_token")

    if not username or username.lower() not in ADMIN_USERS or admin_cookie != "secureadmin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    logs = []
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM logs ORDER BY id DESC")
            logs = cur.fetchall()
        conn.close()

    # ===== Calculate Status Counts =====
    started_count = 0
    break_count = 0
    for log in logs:
        if log["start_time"] and not log["leave_time"]:
            started_count += 1
        if log["break_time"] and not log["onseat_time"]:
            break_count += 1
    active_count = started_count - break_count

    return render_template(
        "admin_logs.html",
        logs=logs,
        started_count=started_count,
        break_count=break_count,
        active_count=active_count
    )

# -------------------------
# LIVE STATUS COUNTS (AJAX)
# -------------------------
@app.route("/live-status")
def live_status():
    username = session.get("username")
    admin_cookie = request.cookies.get("admin_token")
    if not username or username.lower() not in ADMIN_USERS or admin_cookie != "secureadmin":
        return {"error": "Unauthorized"}, 401

    conn = get_db_connection()
    counts = {"started": 0, "break": 0, "active": 0}
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM logs")
                logs = cur.fetchall()
                started_count = 0
                break_count = 0
                for log in logs:
                    if log["start_time"] and not log["leave_time"]:
                        started_count += 1
                    if log["break_time"] and not log["onseat_time"]:
                        break_count += 1
                counts["started"] = started_count
                counts["break"] = break_count
                counts["active"] = started_count - break_count
        finally:
            conn.close()
    return counts

# -------------------------
# DOWNLOAD LOGS
# -------------------------
@app.route("/download-logs")
def download_logs():
    pakistan_tz = pytz.timezone("Asia/Karachi")
    username = session.get("username")
    admin_cookie = request.cookies.get("admin_token")
    if not username or username.lower() not in ADMIN_USERS or admin_cookie != "secureadmin":
        return redirect(url_for("login"))

    conn = get_db_connection()
    if not conn:
        return "❌ Database not connected."

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM logs ORDER BY log_date DESC, username ASC")
            logs = cur.fetchall()

        if not logs:
            return "⚠️ No logs to export."

        df = pd.DataFrame(logs)
        for col in ["start_time", "break_time", "onseat_time", "leave_time"]:
            df[col] = df[col].apply(lambda x: (pd.Timestamp("1900-01-01") + x).strftime("%I:%M %p") if pd.notnull(x) else "")
        df["log_date"] = df["log_date"].apply(lambda x: x.strftime("%Y-%m-%d"))

        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Logs")
            workbook = writer.book
            worksheet = writer.sheets["Logs"]
            header_format = workbook.add_format({"bold": True, "text_wrap": True, "valign": "center", "align": "center", "fg_color": "#4CAF50", "font_color": "white", "border": 1})
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            for i, col in enumerate(df.columns):
                max_len = df[col].astype(str).map(len).max()
                worksheet.set_column(i, i, max_len + 5)
            time_columns = ["start_time", "break_time", "onseat_time", "leave_time"]
            for i, col in enumerate(df.columns):
                if col in time_columns:
                    worksheet.conditional_format(1, i, len(df), i, {"type": "blanks", "format": workbook.add_format({"bg_color": "#FF9999"})})
            worksheet.autofilter(0, 0, len(df), len(df.columns)-1)

        output.seek(0)
        filename = f"logs_{datetime.now(pakistan_tz).strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(output, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    finally:
        conn.close()

# -------------------------
# ADD EMPLOYEE
# -------------------------
@app.route("/add-employee", methods=["GET", "POST"])
def add_employee():
    username = session.get("username")
    admin_cookie = request.cookies.get("admin_token")
    if not username or username.lower() not in ADMIN_USERS or admin_cookie != "secureadmin":
        return redirect(url_for("login"))

    message = None
    if request.method == "POST":
        new_username = request.form.get("username", "").strip()
        new_password = request.form.get("password", "").strip()
        if not new_username or not new_password:
            message = "⚠️ Please fill all fields."
        else:
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM users WHERE username=%s", (new_username,))
                    existing = cur.fetchone()
                    if existing:
                        message = f"⚠️ Username '{new_username}' already exists!"
                    else:
                        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (new_username, new_password))
                        conn.commit()
                        message = f"✅ Employee '{new_username}' added successfully!"
                conn.close()
    return render_template("add_employee.html", message=message)

# -------------------------
# LOGOUT
# -------------------------
@app.route("/logout")
def logout():
    username = session.get("username")
    if username:
        conn = get_db_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE loginstatus SET logged_in=0, session_token=NULL WHERE username=%s", (username,))
                conn.commit()
            conn.close()

    session.clear()
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie("admin_token")
    return resp

# -------------------------
# RUN APP
# -------------------------
#if __name__ == "__main__":
 #   print("🚀 Flask server running on http://0.0.0.0:5000")
  #  app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)

