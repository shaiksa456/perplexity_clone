import os
import re
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    flash,
)
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

import db  # noqa: E402
from rag.pipeline import run_query  # noqa: E402  (import after load_dotenv)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")

db.init_db()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- helpers --

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please log in first."}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def current_user():
    user_id = session.get("user_id")
    return db.get_user_by_id(user_id) if user_id else None


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


# ------------------------------------------------------------------- auth --

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        error = None
        if not username or len(username) < 3:
            error = "Username must be at least 3 characters."
        elif not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif db.get_user_by_username(username):
            error = "That username is already taken."
        elif db.get_user_by_email(email):
            error = "An account with that email already exists."

        if error:
            flash(error, "error")
            return render_template("register.html", username=username, email=email)

        user_id = db.create_user(username, email, generate_password_hash(password))
        session["user_id"] = user_id
        flash("Welcome! Your account has been created.", "success")
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password = request.form.get("password") or ""

        user = db.get_user_by_login(identifier.lower()) or db.get_user_by_login(identifier)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['username']}.", "success")
            next_url = request.form.get("next") or request.args.get("next")
            return redirect(next_url or url_for("index"))

        flash("Invalid username/email or password.", "error")
        return render_template("login.html", identifier=identifier)

    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for("login"))


# -------------------------------------------------------------- main app --

@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/api/ask", methods=["POST"])
@login_required
def ask():
    user_id = session["user_id"]
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    thread_id = data.get("thread_id")

    if not question:
        return jsonify({"error": "Please enter a question."}), 400

    if not thread_id or not db.thread_belongs_to_user(thread_id, user_id):
        title = question[:60] + ("…" if len(question) > 60 else "")
        thread_id = db.create_thread(user_id, title=title)

    history = db.get_history_pairs(thread_id)
    try:
        result = run_query(question, history)
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}", "thread_id": thread_id}), 500

    if "error" in result:
        return jsonify({"error": result["error"], "thread_id": thread_id}), 502

    db.add_message(thread_id, question, result)
    db.touch_thread(thread_id)

    result["thread_id"] = thread_id
    result["question"] = question
    return jsonify(result)


@app.route("/api/new_thread", methods=["POST"])
@login_required
def new_thread():
    thread_id = db.create_thread(session["user_id"])
    return jsonify({"thread_id": thread_id})


# ----------------------------------------------------------------- history --

@app.route("/api/history", methods=["GET"])
@login_required
def api_history():
    threads = db.list_threads_for_user(session["user_id"])
    return jsonify({"threads": threads})


@app.route("/api/history/<thread_id>", methods=["GET"])
@login_required
def api_history_thread(thread_id):
    if not db.thread_belongs_to_user(thread_id, session["user_id"]):
        return jsonify({"error": "Not found."}), 404
    messages = db.get_messages_for_thread(thread_id)
    return jsonify({"thread_id": thread_id, "messages": messages})


@app.route("/api/history/<thread_id>", methods=["DELETE"])
@login_required
def api_history_delete(thread_id):
    if not db.thread_belongs_to_user(thread_id, session["user_id"]):
        return jsonify({"error": "Not found."}), 404
    db.delete_thread(thread_id, session["user_id"])
    return jsonify({"ok": True})


@app.route("/history")
@login_required
def history_page():
    threads = db.list_threads_for_user(session["user_id"])
    return render_template("history.html", threads=threads)


# ----------------------------------------------------------------- profile --

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()

        error = None
        if not username or len(username) < 3:
            error = "Username must be at least 3 characters."
        elif not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        else:
            clash = db.get_user_by_username(username)
            if clash and clash["id"] != user["id"]:
                error = "That username is already taken."
            clash = db.get_user_by_email(email)
            if clash and clash["id"] != user["id"]:
                error = "An account with that email already exists."

        if error:
            flash(error, "error")
        else:
            db.update_user_profile(user["id"], username, email)
            flash("Profile updated.", "success")

        return redirect(url_for("profile"))

    return render_template("profile.html", user=user)


@app.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    user = current_user()
    current_pw = request.form.get("current_password") or ""
    new_pw = request.form.get("new_password") or ""
    confirm_pw = request.form.get("confirm_new_password") or ""

    if not check_password_hash(user["password_hash"], current_pw):
        flash("Current password is incorrect.", "error")
    elif len(new_pw) < 8:
        flash("New password must be at least 8 characters.", "error")
    elif new_pw != confirm_pw:
        flash("New passwords do not match.", "error")
    else:
        db.update_user_password(user["id"], generate_password_hash(new_pw))
        flash("Password changed.", "success")

    return redirect(url_for("profile"))


# ---------------------------------------------------------------- settings --

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user = current_user()

    if request.method == "POST":
        theme = request.form.get("theme", "dark")
        if theme not in ("dark", "light"):
            theme = "dark"
        db.update_user_theme(user["id"], theme)
        session["theme"] = theme
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", user=user)


@app.route("/settings/delete_account", methods=["POST"])
@login_required
def delete_account():
    user = current_user()
    password = request.form.get("password") or ""
    if not check_password_hash(user["password_hash"], password):
        flash("Incorrect password. Account not deleted.", "error")
        return redirect(url_for("settings"))

    db.delete_user(user["id"])
    session.clear()
    flash("Your account has been deleted.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, port=port)