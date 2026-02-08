# main.py - Complete version with authentication system
import os
import shutil
import uuid
import threading
import time
import random
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse
from functools import wraps
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, render_template, send_file, jsonify, session, redirect, url_for, flash, g
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
import yt_dlp

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    handlers=[logging.FileHandler('downloader.log'), logging.StreamHandler()]
)
log = logging.getLogger("yt-any")

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
COOKIES_DIR = os.path.join(BASE_DIR, "cookies")
FFMPEG_DIR = os.path.join(BASE_DIR, "bin")
DATABASE_PATH = os.path.join(BASE_DIR, "eliot_downloader.db")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(COOKIES_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# --- Flask/Socket ---
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- Platform Configuration ---
PLATFORM_CONFIGS = {
    'agasobanuyefilms.com': {
        'requires_cookies': True,
        'description': 'Rwandan movie streaming platform',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://agasobanuyefilms.com/',
        'headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    },
    'youtube.com': {
        'requires_cookies': False,
        'description': 'YouTube platform',
    },
    'vimeo.com': {
        'requires_cookies': False,
        'description': 'Vimeo platform',
    },
    'instagram.com': {
        'requires_cookies': False,
        'description': 'Instagram - Videos, Photos, Stories',
        'supports_photos': True
    },
    'pinterest.com': {
        'requires_cookies': False,
        'description': 'Pinterest - High-resolution Images',
        'supports_photos': True
    }
}


# --- Database Setup ---
def init_database():
    """Initialize the SQLite database with all required tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')

    # User activities table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            activity_type TEXT NOT NULL,
            url TEXT,
            format TEXT,
            quality TEXT,
            filename TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Contact submissions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contact_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            location TEXT,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            ip_address TEXT,
            status TEXT DEFAULT 'unread',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Traffic statistics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS traffic_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            user_agent TEXT,
            referrer TEXT,
            page TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create default admin user if doesn't exist
    cursor.execute("SELECT * FROM users WHERE username = ?", ("admin@eliot",))
    if not cursor.fetchone():
        default_admin_pw = os.environ.get('ADMIN_PASSWORD', 'changeme123')
        admin_password_hash = generate_password_hash(default_admin_pw)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, is_admin)
            VALUES (?, ?, ?, ?)
        ''', ("admin@eliot", "admin@eliot.com", admin_password_hash, True))

    conn.commit()
    conn.close()


def get_db():
    """Get database connection"""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    """Close database connection"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


@app.teardown_appcontext
def close_db_on_teardown(error):
    close_db()


# --- Authentication Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE id = ?", (session['user_id'],)
        ).fetchone()

        if not user or not user['is_admin']:
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


# --- Traffic Tracking ---
@app.before_request
def track_traffic():
    """Track page visits for analytics"""
    if request.endpoint not in ['static', 'download_file']:
        try:
            db = get_db()
            db.execute('''
                INSERT INTO traffic_stats (ip_address, user_agent, referrer, page)
                VALUES (?, ?, ?, ?)
            ''', (
                request.remote_addr,
                request.headers.get('User-Agent', ''),
                request.headers.get('Referer', ''),
                request.path
            ))
            db.commit()
        except Exception as e:
            log.warning(f"Traffic tracking error: {e}")


# --- Activity Logging ---
def log_user_activity(user_id, activity_type, **kwargs):
    """Log user activity to database"""
    try:
        db = get_db()
        db.execute('''
            INSERT INTO user_activities 
            (user_id, activity_type, url, format, quality, filename, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            activity_type,
            kwargs.get('url'),
            kwargs.get('format'),
            kwargs.get('quality'),
            kwargs.get('filename'),
            kwargs.get('status')
        ))
        db.commit()
    except Exception as e:
        log.warning(f"Activity logging error: {e}")


# --- Helper Functions ---
def get_platform_config(url):
    """Get platform-specific configuration based on URL"""
    if not url:
        return None

    domain = urlparse(url).netloc.lower()

    # Remove www. prefix if present
    if domain.startswith('www.'):
        domain = domain[4:]

    # Check for exact matches first
    if domain in PLATFORM_CONFIGS:
        return PLATFORM_CONFIGS[domain]

    # Check for subdomain matches
    for platform, config in PLATFORM_CONFIGS.items():
        if domain.endswith(platform):
            return config

    return None


# --- Cookie Management ---
ALLOWED_COOKIE_EXTENSIONS = {'txt'}


def allowed_cookie_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_COOKIE_EXTENSIONS


def cleanup_old_cookies():
    """Remove cookie files older than 24 hours"""
    try:
        for filename in os.listdir(COOKIES_DIR):
            file_path = os.path.join(COOKIES_DIR, filename)
            if os.path.isfile(file_path):
                file_age = datetime.now() - datetime.fromtimestamp(os.path.getctime(file_path))
                if file_age > timedelta(hours=24):
                    os.remove(file_path)
                    log.info(f"Removed old cookie file: {filename}")
    except Exception as e:
        log.warning(f"Error cleaning up cookies: {e}")


def get_available_cookies():
    """Get list of available cookie files"""
    cookies = []
    # Default cookies.txt in base directory
    default_cookies = os.path.join(BASE_DIR, "cookies.txt")
    if os.path.exists(default_cookies):
        cookies.append({"name": "default", "path": default_cookies, "uploaded": False})

    # Uploaded cookie files
    try:
        for filename in os.listdir(COOKIES_DIR):
            if filename.endswith('.txt'):
                file_path = os.path.join(COOKIES_DIR, filename)
                cookies.append({
                    "name": filename[:-4],  # Remove .txt extension
                    "path": file_path,
                    "uploaded": True,
                    "upload_time": datetime.fromtimestamp(os.path.getctime(file_path)).strftime("%Y-%m-%d %H:%M")
                })
    except Exception as e:
        log.warning(f"Error reading cookies directory: {e}")

    return cookies


# --- Sessions ---
class DownloadProgress:
    def __init__(self, sid: str):
        self.session_id = sid
        self.status = "queued"
        self.progress = 0.0
        self.speed = "N/A"
        self.eta = "N/A"
        self.file_size = "N/A"
        self.downloaded = "0 B"
        self.error = None
        self.filename = ""
        self.filepath = ""
        self.cookie_file = None


download_sessions = {}


# --- Utility Functions ---
def has_ffmpeg() -> bool:
    return (
            shutil.which("ffmpeg") is not None
            or os.path.exists(os.path.join(FFMPEG_DIR, "ffmpeg"))
            or os.path.exists(os.path.join(FFMPEG_DIR, "ffmpeg.exe"))
    )


def fmt_bytes(n: int | float | None) -> str:
    if not n or n <= 0:
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024.0:
            return f"{x:.1f} {u}"
        x /= 1024.0
    return f"{x:.1f} PB"


def progress_hook(d, session_id: str):
    prog = download_sessions.get(session_id)
    if not prog:
        return

    try:
        status = d.get("status", "")
        if status == "downloading":
            prog.status = "downloading"
            prog.filename = os.path.basename(d.get("filename") or prog.filename)
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes") or 0
            prog.progress = (downloaded / total * 100) if total else prog.progress
            prog.file_size = fmt_bytes(total)
            prog.downloaded = fmt_bytes(downloaded)
            prog.speed = d.get("_speed_str", "N/A")
            prog.eta = d.get("_eta_str", "N/A")

        elif status == "finished":
            prog.status = "processing"
            prog.progress = 100.0
            prog.filepath = d.get("filename") or prog.filepath

        elif status == "error":
            prog.status = "error"
            prog.error = "Download error"

    finally:
        socketio.emit("progress_update", {
            "session_id": session_id,
            "status": prog.status,
            "progress": round(prog.progress, 1),
            "speed": prog.speed,
            "eta": prog.eta,
            "file_size": prog.file_size,
            "downloaded": prog.downloaded,
            "filename": prog.filename,
            "error": prog.error
        })


def ydl_base_opts(cookie_file_path=None, url=None):
    """Enhanced options with platform-specific configurations"""
    # Get platform configuration
    platform_config = get_platform_config(url) if url else None

    # Base configuration
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "noplaylist": True,
        "restrictfilenames": False,
        "writesubtitles": False,
        "writethumbnail": False,
        "merge_output_format": "mp4",
        "outtmpl": {
            "default": os.path.join(DOWNLOAD_DIR, "%(title).150B-%(id)s.%(ext)s")
        },
        "concurrent_fragment_downloads": 5,
        "retries": 20,
        "fragment_retries": 20,
        "extractor_retries": 10,
        "retry_sleep_functions": {
            "http": "linexpbackoff",
            "fragment": "linexpbackoff",
            "extractor": "linexpbackoff",
        },
        "socket_timeout": 30,
    }

    # Add platform-specific configurations
    if platform_config:
        # Add user agent if specified
        if 'user_agent' in platform_config:
            base_opts['http_headers'] = base_opts.get('http_headers', {})
            base_opts['http_headers']['User-Agent'] = platform_config['user_agent']

        # Add custom headers
        if 'headers' in platform_config:
            base_opts['http_headers'] = base_opts.get('http_headers', {})
            base_opts['http_headers'].update(platform_config['headers'])

        # Add referer if specified
        if 'referer' in platform_config:
            base_opts['http_headers'] = base_opts.get('http_headers', {})
            base_opts['http_headers']['Referer'] = platform_config['referer']

    # Handle cookies
    cookie_part = {}
    if platform_config and platform_config.get('requires_cookies', False):
        # Platform requires cookies - use provided cookie file or show warning
        if cookie_file_path and os.path.exists(cookie_file_path):
            cookie_part = {"cookiefile": cookie_file_path}
            log.info(f"Using cookies for {urlparse(url).netloc}")
        else:
            # Check for default cookies
            default_cookies = os.path.join(BASE_DIR, "cookies.txt")
            if os.path.exists(default_cookies):
                cookie_part = {"cookiefile": default_cookies}
                log.info(f"Using default cookies for {urlparse(url).netloc}")
            else:
                log.warning(f"Platform {urlparse(url).netloc} may require cookies for full access")
    elif cookie_file_path and os.path.exists(cookie_file_path):
        # Cookie file provided, use it regardless
        cookie_part = {"cookiefile": cookie_file_path}

    # FFmpeg configuration
    ffmpeg_part = {"ffmpeg_location": FFMPEG_DIR} if has_ffmpeg() else {}

    # YouTube-specific extractor configuration
    if not platform_config or 'youtube.com' in (url or ''):
        base_opts["extractor_args"] = {
            "youtube": {
                "player_client": ["web", "android", "ios", "tv_embedded"],
                "max_comments": [0],
            }
        }
        base_opts["live_from_start"] = True
        base_opts["ignore_no_formats_error"] = False

    return {**base_opts, **cookie_part, **ffmpeg_part}


def check_platform_requirements(url):
    """Check if platform has specific requirements and return info"""
    platform_config = get_platform_config(url)

    if not platform_config:
        return {
            'requires_cookies': False,
            'message': 'Platform not specifically configured. Standard download will be attempted.',
            'level': 'info'
        }

    if platform_config.get('requires_cookies', False):
        # Check if cookies are available
        available_cookies = get_available_cookies()
        default_cookies = os.path.join(BASE_DIR, "cookies.txt")

        has_cookies = len(available_cookies) > 0 or os.path.exists(default_cookies)

        if has_cookies:
            return {
                'requires_cookies': True,
                'message': f'Platform: {platform_config.get("description", "Unknown")} - Cookies available for full access.',
                'level': 'success'
            }
        else:
            return {
                'requires_cookies': True,
                'message': f'Platform: {platform_config.get("description", "Unknown")} - Cookies recommended for full video access. You may only get trailers without authentication.',
                'level': 'warning'
            }

    return {
        'requires_cookies': False,
        'message': f'Platform: {platform_config.get("description", "Unknown")} - No special requirements.',
        'level': 'info'
    }


def build_video_format(quality: str) -> str:
    """Robust format selector that merges best video+audio, honoring a max height."""
    if quality == "best":
        return "bv*+ba/b"
    # quality like "1080p", "720p"
    h = "".join(ch for ch in quality if ch.isdigit())
    if not h:
        return "bv*+ba/b"
    # prefer mp4 where possible, fallback otherwise
    # pick best video up to height, then best audio
    return f"((bv*[height<={h}][ext=mp4]/bv*[height<={h}])+(ba[ext=m4a]/ba))/b[height<={h}]"


def build_audio_opts():
    return {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    }


def build_photo_opts():
    return {
        "format": "best",
        "writeinfojson": False,
        "writethumbnail": False,
        "extract_flat": False
    }


def extract_info_only(url: str, cookie_file_path=None) -> dict:
    opts = ydl_base_opts(cookie_file_path, url) | {"skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def download_job(url: str, media: str, quality: str, session_id: str, cookie_file_path=None):
    prog = download_sessions[session_id]
    prog.status = "starting"
    prog.cookie_file = cookie_file_path

    # Check platform requirements
    platform_info = check_platform_requirements(url)
    log.info(f"Platform check: {platform_info['message']}")

    # Small random delay to stagger repeated requests
    time.sleep(random.uniform(0.2, 0.9))

    opts = ydl_base_opts(cookie_file_path, url)
    if media == "audio":
        opts |= build_audio_opts()
    elif media == "photo":
        opts |= build_photo_opts()
    else:
        opts |= {"format": build_video_format(quality)}

    opts["progress_hooks"] = [lambda d: progress_hook(d, session_id)]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # Path resolution - updated for photos
            target = ydl.prepare_filename(info)
            base, ext = os.path.splitext(target)

            candidates = [
                target,
                f"{base}.mp4",
                f"{base}.mkv",
                f"{base}.webm",
                f"{base}.m4a",
                f"{base}.mp3",
                f"{base}.jpg",
                f"{base}.jpeg",
                f"{base}.png",
                f"{base}.gif",
                f"{base}.webp"
            ]
            for p in candidates:
                if os.path.exists(p):
                    prog.filepath = p
                    prog.filename = os.path.basename(p)
                    break

            if not prog.filepath:
                raise FileNotFoundError("Downloaded file not found.")

            prog.status = "completed"

            # Log successful download for logged-in users
            if 'user_id' in session and session['user_id']:
                log_user_activity(session['user_id'], 'download_completed',
                                  url=url, format=media, quality=quality,
                                  filename=prog.filename, status='completed')

            socketio.emit("download_complete", {
                "session_id": session_id,
                "filename": prog.filename
            })

    except Exception as e:
        prog.status = "error"
        err = str(e)

        # Platform-specific error handling
        platform_config = get_platform_config(url)
        if platform_config and platform_config.get('requires_cookies', False):
            if "age-restricted" in err.lower() or "sign in" in err.lower() or "private" in err.lower():
                prog.error = f"Authentication required for {platform_config.get('description', 'this platform')}. Please upload cookies from your browser session."
            elif "unavailable" in err.lower():
                prog.error = f"Content unavailable. Ensure you're logged in to {platform_config.get('description', 'this platform')} and have access to this content."
            else:
                prog.error = f"Download failed: {err}"
        else:
            # Standard error handling
            if "Sign in to confirm your age" in err or "age-restricted" in err:
                prog.error = "Age-restricted. Try uploading cookies from your browser."
            elif "This video is private" in err:
                prog.error = "Private content."
            elif "unavailable" in err.lower():
                prog.error = "Content unavailable or region-blocked. Try uploading cookies."
            else:
                prog.error = f"Download failed: {err}"

        # Log failed download for logged-in users
        if 'user_id' in session and session['user_id']:
            log_user_activity(session['user_id'], 'download_failed',
                              url=url, format=media, quality=quality,
                              status='failed')

        socketio.emit("download_error", {"session_id": session_id, "error": prog.error})


# --- Authentication Routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    try:
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({"success": False, "error": "Username and password are required"}), 400

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        ).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']

            # Update last login
            db.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user['id'],)
            )
            db.commit()

            log_user_activity(user['id'], 'login')

            if user['is_admin']:
                return jsonify({"success": True, "redirect": "/admin/dashboard"})
            else:
                return jsonify({"success": True, "redirect": "/dashboard"})
        else:
            return jsonify({"success": False, "error": "Invalid username or password"}), 401

    except Exception as e:
        log.error(f"Login error: {e}")
        return jsonify({"success": False, "error": "Login failed"}), 500


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    try:
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')

        # Validation
        errors = {}
        if not username:
            errors['username'] = 'Username is required'
        elif len(username) < 3:
            errors['username'] = 'Username must be at least 3 characters'

        if not email:
            errors['email'] = 'Email is required'
        elif '@' not in email:
            errors['email'] = 'Please enter a valid email'

        if not password:
            errors['password'] = 'Password is required'
        elif len(password) < 6:
            errors['password'] = 'Password must be at least 6 characters'

        if password != confirm_password:
            errors['confirm_password'] = 'Passwords do not match'

        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        db = get_db()

        # Check if username or email already exists
        existing_user = db.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?", (username, email)
        ).fetchone()

        if existing_user:
            if existing_user['username'] == username:
                errors['username'] = 'Username already taken'
            if existing_user['email'] == email:
                errors['email'] = 'Email already registered'
            return jsonify({"success": False, "errors": errors}), 400

        # Create new user
        password_hash = generate_password_hash(password)
        db.execute('''
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
        ''', (username, email, password_hash))
        db.commit()

        return jsonify({"success": True, "message": "Account created successfully! Please log in."})

    except Exception as e:
        log.error(f"Registration error: {e}")
        return jsonify({"success": False, "error": "Registration failed"}), 500


@app.route("/logout")
def logout():
    if 'user_id' in session:
        log_user_activity(session['user_id'], 'logout')
    session.clear()
    return redirect(url_for('index'))


# --- Dashboard Routes ---
@app.route("/dashboard")
@login_required
def user_dashboard():
    db = get_db()

    # Get user's recent activities
    activities = db.execute('''
        SELECT * FROM user_activities 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 50
    ''', (session['user_id'],)).fetchall()

    # Get user stats
    stats = db.execute('''
        SELECT 
            COUNT(*) as total_downloads,
            COUNT(CASE WHEN activity_type = 'download_completed' THEN 1 END) as successful_downloads,
            COUNT(CASE WHEN DATE(created_at) = DATE('now') THEN 1 END) as today_downloads
        FROM user_activities 
        WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()

    return render_template("user_dashboard.html", activities=activities, stats=stats)


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = get_db()

    # Get overall statistics
    stats = db.execute('''
        SELECT 
            (SELECT COUNT(*) FROM users WHERE is_admin = 0) as total_users,
            (SELECT COUNT(*) FROM user_activities) as total_downloads,
            (SELECT COUNT(*) FROM contact_submissions WHERE status = 'unread') as unread_messages,
            (SELECT COUNT(*) FROM traffic_stats WHERE DATE(created_at) = DATE('now')) as today_visits
    ''').fetchone()

    # Get recent activities
    recent_activities = db.execute('''
        SELECT ua.*, u.username 
        FROM user_activities ua 
        JOIN users u ON ua.user_id = u.id 
        ORDER BY ua.created_at DESC 
        LIMIT 20
    ''').fetchall()

    # Get traffic stats for last 7 days
    traffic_stats = db.execute('''
        SELECT DATE(created_at) as date, COUNT(*) as visits
        FROM traffic_stats 
        WHERE created_at >= date('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY date DESC
    ''').fetchall()

    return render_template("admin_dashboard.html",
                           stats=stats,
                           recent_activities=recent_activities,
                           traffic_stats=traffic_stats)


@app.route("/admin/users")
@admin_required
def admin_users():
    db = get_db()
    users = db.execute('''
        SELECT u.*, 
               COUNT(ua.id) as total_downloads,
               MAX(ua.created_at) as last_download
        FROM users u 
        LEFT JOIN user_activities ua ON u.id = ua.user_id 
        WHERE u.is_admin = 0
        GROUP BY u.id 
        ORDER BY u.created_at DESC
    ''').fetchall()

    return render_template("admin_users.html", users=users)


@app.route("/admin/inbox")
@admin_required
def admin_inbox():
    db = get_db()
    messages = db.execute('''
        SELECT * FROM contact_submissions 
        ORDER BY created_at DESC
    ''').fetchall()

    return render_template("admin_inbox.html", messages=messages)


@app.route("/admin/change_password", methods=["GET", "POST"])
@admin_required
def admin_change_password():
    if request.method == "GET":
        return render_template("admin_change_password.html")

    try:
        data = request.get_json()
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')

        if not current_password or not new_password:
            return jsonify({"success": False, "error": "All fields are required"}), 400

        if new_password != confirm_password:
            return jsonify({"success": False, "error": "New passwords do not match"}), 400

        if len(new_password) < 6:
            return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE id = ?", (session['user_id'],)
        ).fetchone()

        if not check_password_hash(user['password_hash'], current_password):
            return jsonify({"success": False, "error": "Current password is incorrect"}), 400

        new_password_hash = generate_password_hash(new_password)
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, session['user_id'])
        )
        db.commit()

        return jsonify({"success": True, "message": "Password updated successfully"})

    except Exception as e:
        log.error(f"Password change error: {e}")
        return jsonify({"success": False, "error": "Password change failed"}), 500


# --- Main Routes ---
@app.route("/")
def index():
    cleanup_old_cookies()
    available_cookies = get_available_cookies()
    return render_template("index.html", cookies=available_cookies)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", current_date=datetime.now().strftime("%B %d, %Y"))


@app.route("/terms")
def terms():
    return render_template("terms.html", current_date=datetime.now().strftime("%B %d, %Y"))


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html")

    try:
        data = request.get_json(force=True)

        # Validation
        errors = {}
        required_fields = ['name', 'email', 'subject', 'message', 'privacy']

        for field in required_fields:
            if not data.get(field):
                errors[field] = f"{field.replace('_', ' ').title()} is required"

        email = data.get('email', '').strip()
        if email and '@' not in email:
            errors['email'] = "Please enter a valid email address"

        message = data.get('message', '').strip()
        if message and len(message) > 2000:
            errors['message'] = "Message must be less than 2000 characters"
        elif message and len(message) < 10:
            errors['message'] = "Message must be at least 10 characters"

        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        # Save to database
        db = get_db()
        db.execute('''
            INSERT INTO contact_submissions (name, email, location, subject, message, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data.get('name', '').strip(),
            email,
            data.get('location', '').strip(),
            data.get('subject'),
            message,
            request.remote_addr
        ))
        db.commit()

        return jsonify({"success": True, "message": "Your message has been sent successfully!"})

    except Exception as e:
        log.error(f"Contact form error: {e}")
        return jsonify({"success": False, "error": "Failed to send message. Please try again."}), 500


# --- Download Routes ---
@app.route("/upload_cookies", methods=["POST"])
def upload_cookies():
    if 'cookie_file' not in request.files:
        return jsonify({"error": "No file selected"}), 400

    file = request.files['cookie_file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not allowed_cookie_file(file.filename):
        return jsonify({"error": "Only .txt files are allowed"}), 400

    try:
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = secure_filename(file.filename).rsplit('.', 1)[0]
        filename = f"{original_name}_{timestamp}.txt"
        file_path = os.path.join(COOKIES_DIR, filename)

        file.save(file_path)

        # Validate cookie file format (basic check)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                os.remove(file_path)
                return jsonify({"error": "Cookie file is empty"}), 400

        log.info(f"Cookie file uploaded: {filename}")
        return jsonify({
            "success": True,
            "message": f"Cookie file '{original_name}' uploaded successfully",
            "filename": filename[:-4]  # Remove .txt extension for display
        })

    except Exception as e:
        log.error(f"Cookie upload error: {e}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@app.route("/delete_cookies/<cookie_name>", methods=["POST"])
def delete_cookies(cookie_name):
    try:
        file_path = os.path.join(COOKIES_DIR, f"{cookie_name}.txt")
        if os.path.exists(file_path):
            os.remove(file_path)
            log.info(f"Cookie file deleted: {cookie_name}")
            return jsonify({"success": True, "message": "Cookie file deleted"})
        else:
            return jsonify({"error": "Cookie file not found"}), 404
    except Exception as e:
        log.error(f"Cookie deletion error: {e}")
        return jsonify({"error": f"Deletion failed: {str(e)}"}), 500


@app.route("/get_video_info", methods=["POST"])
def get_video_info_route():
    try:
        data = request.get_json(force=True)
        url = data.get("url", "").strip()
        cookie_name = data.get("cookie_file", "")

        if not url:
            return jsonify({"error": "URL is required"}), 400

        # Check platform requirements
        platform_info = check_platform_requirements(url)

        # Get cookie file path if specified
        cookie_file_path = None
        if cookie_name:
            if cookie_name == "default":
                cookie_file_path = os.path.join(BASE_DIR, "cookies.txt")
            else:
                cookie_file_path = os.path.join(COOKIES_DIR, f"{cookie_name}.txt")

            if not os.path.exists(cookie_file_path):
                return jsonify({"error": f"Cookie file '{cookie_name}' not found"}), 400

        info_raw = extract_info_only(url, cookie_file_path)

        # Format information
        fmts = []
        seen = set()
        for f in (info_raw.get("formats") or []):
            if f.get("vcodec") == "none":
                continue
            h = f.get("height")
            if not h:
                continue
            if h < 144:
                continue
            if h in seen:
                continue
            seen.add(h)
            fmts.append({
                "format_id": f.get("format_id"),
                "quality": f"{h}p",
                "ext": f.get("ext") or "mp4",
                "filesize": fmt_bytes(f.get("filesize") or f.get("filesize_approx"))
            })
        fmts.sort(key=lambda x: int(x["quality"][:-1]), reverse=True)

        payload = {
            "title": info_raw.get("title") or "Unknown",
            "duration": info_raw.get("duration") or 0,
            "uploader": info_raw.get("uploader") or "Unknown",
            "thumbnail": info_raw.get("thumbnail") or "",
            "description": (info_raw.get("description") or "")[:200] + ("..." if info_raw.get("description") else ""),
            "formats": fmts[:10],
            "platform_info": platform_info
        }
        return jsonify({"success": True, "info": payload})

    except Exception as e:
        error_msg = str(e)
        platform_config = get_platform_config(data.get("url", "")) if 'data' in locals() else None

        if platform_config and platform_config.get('requires_cookies', False):
            if "age" in error_msg.lower() or "restricted" in error_msg.lower() or "private" in error_msg.lower():
                error_msg = f"Authentication required for {platform_config.get('description', 'this platform')}. Please upload and select cookies from your browser session."

        return jsonify({"error": error_msg}), 400


@app.route("/start_download", methods=["POST"])
def start_download():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    media = data.get("format", "video")
    quality = data.get("quality", "best")
    cookie_name = data.get("cookie_file", "")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Log activity for logged-in users
    user_id = session.get('user_id')
    if user_id:
        log_user_activity(user_id, 'download_started', url=url, format=media, quality=quality, status='started')

    cookie_file_path = None
    if cookie_name:
        if cookie_name == "default":
            cookie_file_path = os.path.join(BASE_DIR, "cookies.txt")
        else:
            cookie_file_path = os.path.join(COOKIES_DIR, f"{cookie_name}.txt")

        if not os.path.exists(cookie_file_path):
            return jsonify({"error": f"Cookie file '{cookie_name}' not found"}), 400

    session_id = str(uuid.uuid4())
    download_sessions[session_id] = DownloadProgress(session_id)

    t = threading.Thread(target=download_job, args=(url, media, quality, session_id, cookie_file_path), daemon=True)
    t.start()

    return jsonify({"success": True, "session_id": session_id, "message": "Download started"})


@app.route("/download_file/<session_id>")
def download_file(session_id):
    prog = download_sessions.get(session_id)
    if not prog:
        return "Session not found", 404
    if prog.status != "completed" or not prog.filepath or not os.path.exists(prog.filepath):
        return "File not ready", 400
    return send_file(prog.filepath, as_attachment=True, download_name=os.path.basename(prog.filepath))


@app.route("/cancel_download/<session_id>", methods=["POST"])
def cancel_download(session_id):
    if session_id in download_sessions:
        download_sessions[session_id].status = "cancelled"
        socketio.emit("download_cancelled", {"session_id": session_id})
        return jsonify({"success": True})
    return jsonify({"error": "Session not found"}), 404


@app.route("/get_available_cookies")
def get_available_cookies_route():
    return jsonify({"cookies": get_available_cookies()})


@app.route("/bypass-status")
def bypass_status():
    available_cookies = get_available_cookies()
    return jsonify({
        "cookies_available": len(available_cookies) > 0,
        "available_cookies": available_cookies,
        "ffmpeg_available": has_ffmpeg(),
        "notes": [
            "Supports watch links, Shorts, Music, and live replays.",
            "Upload cookies.txt from your browser to access age/region restricted videos.",
            "Cookie files are automatically deleted after 24 hours.",
            "Platform-specific configurations for optimal compatibility."
        ]
    })


# --- Socket Events ---
@socketio.on("connect")
def _on_connect():
    log.info("Client connected")


@socketio.on("disconnect")
def _on_disconnect():
    log.info("Client disconnected")


# --- Main ---
if __name__ == "__main__":
    init_database()
    log.info("Starting Eliot Downloader with authentication system")
    log.info(f"FFmpeg available: {has_ffmpeg()}")
    log.info(
        f"Supported platforms with cookie requirements: {[k for k, v in PLATFORM_CONFIGS.items() if v.get('requires_cookies')]}")
    log.info("Open: http://127.0.0.1:5000")
    socketio.run(app, host="127.0.0.1", port=5000, debug=True, allow_unsafe_werkzeug=True)
