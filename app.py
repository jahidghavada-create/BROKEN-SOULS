import os
import re
import secrets
import sqlite3
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from pymysql.err import IntegrityError as MySQLIntegrityError
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from database import all_rows, connect, execute, is_sqlite

MOODS = [
    "Broken Heart", "One-Sided Love", "Betrayal", "Missing Someone", "Lost Love",
    "Incomplete Love", "Loneliness", "Old Memories", "Separation", "Regret",
    "Moving On", "Unspoken Feelings", "Deep Love", "Emotional Pain", "Acceptance",
    "Emotional", "Heartbreak", "Pain", "Emotional Love", "Longing", "Goodbye",
    "Inner Struggle", "Unforgettable Love", "Love Memories",
]
CATEGORIES = ["Morning", "Afternoon", "Evening", "Night", "Midnight", "Quiet Hours"]
PERIODS = ["All", "Day", "Night", "Quiet Hours"]
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{22}$")
YOUTUBE_PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]{10,80}$")


def category_for_time(hour, minute):
    minute_of_day = hour * 60 + minute
    if 360 <= minute_of_day < 720:
        return "Morning"
    if 720 <= minute_of_day < 1020:
        return "Afternoon"
    if 1020 <= minute_of_day < 1260:
        return "Evening"
    if minute_of_day >= 1260:
        return "Night"
    if minute_of_day < 240:
        return "Midnight"
    return "Quiet Hours"


def parse_music_url(value):
    if not value or len(value) > 1000:
        return None
    try:
        parsed = urlparse(value.strip())
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443):
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        query = {
            key: val
            for key, val in (part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
        }
        if parsed.path == "/watch":
            video_id = query.get("v", "")
            if YOUTUBE_ID.fullmatch(video_id):
                clean_url = f"https://www.youtube.com/watch?v={video_id}"
                return {
                    "provider": "YouTube", "kind": "video", "id": video_id,
                    "url": clean_url, "embed": f"https://www.youtube-nocookie.com/embed/{video_id}",
                }
        if parsed.path == "/playlist":
            playlist_id = query.get("list", "")
            if YOUTUBE_PLAYLIST_ID.fullmatch(playlist_id):
                clean_url = f"https://www.youtube.com/playlist?list={playlist_id}"
                return {
                    "provider": "YouTube", "kind": "playlist", "id": playlist_id,
                    "url": clean_url,
                    "embed": f"https://www.youtube-nocookie.com/embed/videoseries?list={playlist_id}",
                }
    if host in ("youtu.be", "www.youtu.be"):
        video_id = parsed.path.strip("/")
        if YOUTUBE_ID.fullmatch(video_id):
            return {
                "provider": "YouTube", "kind": "video", "id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "embed": f"https://www.youtube-nocookie.com/embed/{video_id}",
            }
    if host in ("open.spotify.com", "www.open.spotify.com"):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 2 and parts[0] in ("track", "playlist") and SPOTIFY_ID.fullmatch(parts[1]):
            kind, spotify_id = parts
            return {
                "provider": "Spotify", "kind": kind, "id": spotify_id,
                "url": f"https://open.spotify.com/{kind}/{spotify_id}",
                "embed": f"https://open.spotify.com/embed/{kind}/{spotify_id}",
            }
    return None


def parse_local_audio(value):
    """Accept only MP3 files stored in this site's static/audio directory."""
    value = (value or "").strip()
    if not value:
        return None
    if re.fullmatch(r"/static/audio/[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.mp3", value, re.IGNORECASE):
        return {"provider": "Local MP3", "url": value, "embed": None}
    return None


def create_app(test_config=None):
    app = Flask(__name__, template_folder=".")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    CSRFProtect(app)

    def login_required(view):
        from functools import wraps
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please sign in to continue.", "error")
                return redirect(url_for("login", next=request.path))
            if not current_user():
                session.clear()
                flash("Your session expired. Please sign in again.", "error")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        from functools import wraps
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or user["role"] != "admin":
                abort(403)
            return view(*args, **kwargs)
        return wrapped

    @app.before_request
    def open_database():
        g.db = connect(app.config["DATABASE_URL"])
        if is_sqlite(app.config["DATABASE_URL"]):
            schema_path = os.path.join(os.path.dirname(__file__), "sqlite_schema.sql")
            with open(schema_path, encoding="utf-8") as schema_file:
                g.db.executescript(schema_file.read())

        # Ensure the starter song catalog is added to whichever database is
        # configured. A hosted MySQL database is required for persistent data;
        # SQLite on Vercel is only a temporary demo fallback.
        if not app.extensions.get("starter_catalog_seeded"):
            from seed_songs import seed
            seed(app.config["DATABASE_URL"])
            app.extensions["starter_catalog_seeded"] = True

    @app.teardown_request
    def close_database(error=None):
        connection = g.pop("db", None)
        if connection is not None:
            if error:
                connection.rollback()
            connection.close()

    @app.context_processor
    def template_context():
        user = current_user()
        user_playlists = []
        if user:
            user_playlists = all_rows(
                g.db,
                app.config["DATABASE_URL"],
                "SELECT playlist_id, title FROM playlists WHERE user_id = %s ORDER BY title",
                (user["user_id"],),
            )
        return {
            "current_user": user,
            "user_playlists": user_playlists,
            "moods": MOODS,
            "categories": CATEGORIES,
        }

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="That page could not be found."), 404

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="You do not have permission to view this page."), 403

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("error.html", code=500, message="Something went wrong. Please try again."), 500

    @app.route("/")
    def home():
        featured = all_rows(
            g.db,
            app.config["DATABASE_URL"],
            """SELECT s.*, c.mood, c.time_category, c.period
               FROM songs s JOIN song_categories c ON c.song_id = s.song_id
               WHERE s.approval_status = 'approved'
               ORDER BY c.is_featured DESC, s.song_id DESC LIMIT 6""",
        )
        return render_template("home.html", featured=featured)

    @app.route("/music")
    @app.route("/songs")
    def music():
        now = local_now()
        active_category = category_for_time(now.hour, now.minute)
        period = request.args.get("period", "All")
        category = request.args.get("category", "")
        mood = request.args.get("mood", "")
        language = request.args.get("language", "")
        movie = request.args.get("movie", "").strip()[:200]
        singer = request.args.get("singer", "").strip()[:200]
        search = request.args.get("q", "").strip()[:100]
        if period not in PERIODS:
            period = "All"
        if category not in CATEGORIES:
            category = ""
        if mood not in MOODS:
            mood = ""
        clauses = ["s.approval_status = 'approved'"]
        params = []
        if period != "All":
            clauses.append("c.period = %s")
            params.append(period)
        if category:
            clauses.append("c.time_category = %s")
            params.append(category)
        if mood:
            clauses.append("c.mood = %s")
            params.append(mood)
        if language:
            clauses.append("c.language = %s")
            params.append(language[:80])
        if movie:
            clauses.append("s.movie_name = %s")
            params.append(movie)
        if singer:
            clauses.append("s.singer = %s")
            params.append(singer)
        if search:
            clauses.append("(s.title LIKE %s OR s.movie_name LIKE %s OR s.singer LIKE %s OR c.mood LIKE %s)")
            params.extend([f"%{search}%"] * 4)
        rows = all_rows(
            g.db,
            app.config["DATABASE_URL"],
            """SELECT s.*, c.assignment_id, c.mood, c.time_category, c.period, c.language,
                      CASE WHEN f.user_id IS NULL THEN 0 ELSE 1 END AS is_favorite
               FROM songs s JOIN song_categories c ON c.song_id = s.song_id
               LEFT JOIN favorites f ON f.song_id = s.song_id AND f.user_id = %s
               WHERE """ + " AND ".join(clauses) + " ORDER BY s.song_id DESC LIMIT 200",
            [session.get("user_id", -1), *params],
        )
        languages = all_rows(
            g.db, app.config["DATABASE_URL"],
            "SELECT DISTINCT language FROM song_categories ORDER BY language",
        )
        suggestions = all_rows(
            g.db, app.config["DATABASE_URL"],
            "SELECT DISTINCT title FROM songs WHERE approval_status = 'approved' ORDER BY title LIMIT 40",
        )
        movies = all_rows(
            g.db, app.config["DATABASE_URL"],
            "SELECT DISTINCT movie_name FROM songs WHERE approval_status = 'approved' AND movie_name IS NOT NULL ORDER BY movie_name",
        )
        singers = all_rows(
            g.db, app.config["DATABASE_URL"],
            "SELECT DISTINCT singer FROM songs WHERE approval_status = 'approved' AND singer IS NOT NULL ORDER BY singer",
        )
        recent_songs = []
        if not any((search, category, mood, language, movie, singer)) and period == "All":
            recent_songs = all_rows(
                g.db,
                app.config["DATABASE_URL"],
                """SELECT s.*, c.mood, c.time_category, c.period,
                          CASE WHEN f.user_id IS NULL THEN 0 ELSE 1 END AS is_favorite
                   FROM songs s JOIN song_categories c ON c.song_id = s.song_id
                   LEFT JOIN favorites f ON f.song_id = s.song_id AND f.user_id = %s
                   WHERE s.approval_status = 'approved'
                   ORDER BY s.created_at DESC, s.song_id DESC LIMIT 6""",
                (session.get("user_id", -1),),
            )
        return render_template(
            "music.html",
            songs=rows,
            active_category=active_category,
            period=period,
            selected_category=category,
            selected_mood=mood,
            selected_language=language,
            selected_movie=movie,
            selected_singer=singer,
            search=search,
            languages=languages,
            suggestions=suggestions,
            movies=movies,
            singers=singers,
            recent_songs=recent_songs,
            now=now,
        )

    @app.route("/songs/surprise")
    def surprise_song():
        random_order = "RANDOM()" if is_sqlite(app.config["DATABASE_URL"]) else "RAND()"
        song = one(
            f"SELECT song_id FROM songs WHERE approval_status = 'approved' ORDER BY {random_order} LIMIT 1"
        )
        if not song:
            flash("The Music Room is still waiting for its first song.", "error")
            return redirect(url_for("music"))
        return redirect(url_for("song_detail", song_id=song["song_id"]))

    @app.route("/songs/<int:song_id>")
    def song_detail(song_id):
        song = one(
            "SELECT * FROM songs WHERE song_id = %s AND (approval_status = 'approved' OR created_by = %s)",
            (song_id, session.get("user_id", -1)),
        )
        if not song:
            abort(404)
        assignments = all_rows(
            g.db, app.config["DATABASE_URL"],
            "SELECT * FROM song_categories WHERE song_id = %s ORDER BY time_category",
            (song_id,),
        )
        return render_template("song.html", song=song, assignments=assignments)

    @app.route("/songs/fetch-metadata", methods=["POST"])
    def fetch_metadata():
        target = parse_music_url(request.form.get("url", ""))
        if not target:
            return jsonify(error="Enter a supported YouTube or Spotify track/playlist URL."), 400
        metadata = {"provider": target["provider"], "external_url": target["url"], "embed_url": target["embed"]}
        try:
            if target["provider"] == "YouTube" and app.config["YOUTUBE_API_KEY"]:
                metadata.update(fetch_youtube_metadata(target, app.config["YOUTUBE_API_KEY"]))
            elif target["provider"] == "Spotify":
                metadata.update(fetch_spotify_metadata(target))
        except requests.RequestException:
            return jsonify(error="The provider could not be reached. Enter the song details manually."), 502
        return jsonify(metadata)

    @app.route("/songs/add", methods=["GET", "POST"])
    @login_required
    def add_song():
        if request.method == "POST":
            target = parse_music_url(request.form.get("external_url", ""))
            if not target:
                flash("Use a valid YouTube or Spotify track/playlist link.", "error")
                return render_template("add_song.html", form=request.form)
            title = request.form.get("title", "").strip()[:200]
            if not title:
                flash("Song title is required.", "error")
                return render_template("add_song.html", form=request.form)
            category = request.form.get("time_category", "")
            period = request.form.get("period", "")
            mood = request.form.get("mood", "")
            if category not in CATEGORIES or period not in PERIODS[1:] or mood not in MOODS:
                flash("Choose a valid mood, time category, and period.", "error")
                return render_template("add_song.html", form=request.form)
            if (category in ("Morning", "Afternoon", "Evening") and period != "Day") or (
                category in ("Night", "Midnight") and period != "Night"
            ) or (category == "Quiet Hours" and period != "Quiet Hours"):
                flash("The selected period does not match the time category.", "error")
                return render_template("add_song.html", form=request.form)
            cover = valid_image_url(request.form.get("cover_image_url", ""))
            if request.form.get("cover_image_url", "").strip() and not cover:
                flash("Cover image must be a valid HTTPS URL.", "error")
                return render_template("add_song.html", form=request.form)
            visibility = request.form.get("visibility", "private")
            if visibility not in ("private", "public"):
                visibility = "private"
            status = "pending" if visibility == "public" else "private"
            cursor = execute(
                g.db, app.config["DATABASE_URL"],
                """INSERT INTO songs
                   (title, movie_name, singer, language, cover_image_url, provider, external_url,
                    embed_url, created_by, approval_status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    title, optional(request.form.get("movie_name"), 200),
                    optional(request.form.get("singer"), 200),
                    optional(request.form.get("language"), 80) or "Hindi",
                    cover, target["provider"], target["url"], target["embed"],
                    session["user_id"], status,
                ),
            )
            song_id = cursor.lastrowid
            execute(
                g.db, app.config["DATABASE_URL"],
                """INSERT INTO song_categories (song_id, mood, time_category, period, language)
                   VALUES (%s, %s, %s, %s, %s)""",
                (song_id, mood, category, period, optional(request.form.get("language"), 80) or "Hindi"),
            )
            g.db.commit()
            flash("Song saved to your collection." if status == "private" else "Song submitted for admin review.", "success")
            return redirect(url_for("song_detail", song_id=song_id))
        return render_template("add_song.html", form={})

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not re.fullmatch(r"[A-Za-z0-9_]{3,40}", username):
                flash("Username must be 3–40 letters, numbers, or underscores.", "error")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                flash("Enter a valid email address.", "error")
            elif len(password) < 10:
                flash("Use a password with at least 10 characters.", "error")
            else:
                existing = one("SELECT user_id FROM users WHERE username = %s OR email = %s", (username, email))
                if existing:
                    flash("That username or email is already registered.", "error")
                else:
                    cursor = execute(
                        g.db, app.config["DATABASE_URL"],
                        "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                        (username, email, generate_password_hash(password)),
                    )
                    g.db.commit()
                    session.clear()
                    session["user_id"] = cursor.lastrowid
                    flash("Your account is ready.", "success")
                    return redirect(url_for("profile"))
            return render_template("auth.html", mode="register")
        return render_template("auth.html", mode="register")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = one("SELECT * FROM users WHERE email = %s", (email,))
            if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
                session.clear()
                session["user_id"] = user["user_id"]
                flash("Welcome back.", "success")
                next_url = request.args.get("next", "")
                if next_url.startswith("/") and not next_url.startswith("//") and not urlparse(next_url).netloc:
                    return redirect(next_url)
                return redirect(url_for("profile"))
            flash("Email or password was not recognized.", "error")
        return render_template("auth.html", mode="login")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("home"))

    @app.route("/profile")
    @login_required
    def profile():
        playlists = all_rows("SELECT * FROM playlists WHERE user_id = %s ORDER BY created_at DESC", (session["user_id"],))
        favorites = all_rows(
            """SELECT s.* FROM favorites f JOIN songs s ON s.song_id = f.song_id
               WHERE f.user_id = %s AND
               (s.approval_status = 'approved' OR (s.approval_status = 'private' AND s.created_by = f.user_id))
               ORDER BY f.created_at DESC""",
            (session["user_id"],),
        )
        return render_template("profile.html", playlists=playlists, favorites=favorites)

    @app.route("/favorites/<int:song_id>", methods=["POST"])
    @login_required
    def toggle_favorite(song_id):
        song = one("SELECT song_id FROM songs WHERE song_id = %s AND approval_status IN ('approved', 'private') AND (approval_status = 'approved' OR created_by = %s)", (song_id, session["user_id"]))
        if not song:
            abort(404)
        favorite = one("SELECT user_id FROM favorites WHERE user_id = %s AND song_id = %s", (session["user_id"], song_id))
        if favorite:
            execute("DELETE FROM favorites WHERE user_id = %s AND song_id = %s", (session["user_id"], song_id))
            flash("Removed from favorites.", "success")
        else:
            execute("INSERT INTO favorites (user_id, song_id) VALUES (%s, %s)", (session["user_id"], song_id))
            flash("Added to favorites.", "success")
        g.db.commit()
        return redirect(request.referrer or url_for("music"))

    @app.route("/playlists")
    @login_required
    def playlists():
        items = all_rows(
            """SELECT p.*, COUNT(ps.song_id) AS song_count
               FROM playlists p LEFT JOIN playlist_songs ps ON ps.playlist_id = p.playlist_id
               WHERE p.user_id = %s GROUP BY p.playlist_id ORDER BY p.created_at DESC""",
            (session["user_id"],),
        )
        return render_template("playlists.html", playlists=items)

    @app.route("/playlists/create", methods=["GET", "POST"])
    @login_required
    def create_playlist():
        if request.method == "POST":
            title = request.form.get("title", "").strip()[:120]
            cover_input = request.form.get("cover_image_url", "")
            cover = valid_image_url(cover_input)
            mood_value = request.form.get("mood", "")
            category_value = request.form.get("time_category", "")
            period_value = request.form.get("period", "")
            preferences_valid = (
                (not mood_value or mood_value in MOODS)
                and (not category_value or category_value in CATEGORIES)
                and (not period_value or period_value in PERIODS[1:])
                and (
                    not category_value or not period_value
                    or (category_value in ("Morning", "Afternoon", "Evening") and period_value == "Day")
                    or (category_value in ("Night", "Midnight") and period_value == "Night")
                    or (category_value == "Quiet Hours" and period_value == "Quiet Hours")
                )
            )
            if not title:
                flash("Playlist title is required.", "error")
            elif not preferences_valid:
                flash("Choose valid playlist preferences with matching time category and period.", "error")
            elif cover_input.strip() and not cover:
                flash("Cover image must be a valid HTTPS URL.", "error")
            else:
                visibility = request.form.get("visibility", "private")
                if visibility not in ("private", "public"):
                    visibility = "private"
                share_token = secrets.token_hex(16) if visibility == "public" else None
                execute(
                    g.db, app.config["DATABASE_URL"],
                    """INSERT INTO playlists (user_id, title, description, cover_image_url, mood,
                       time_category, period, visibility, share_token)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        session["user_id"], title, optional(request.form.get("description"), 500),
                        cover, valid_choice(mood_value, MOODS),
                        valid_choice(category_value, CATEGORIES),
                        valid_choice(period_value, PERIODS[1:]), visibility, share_token,
                    ),
                )
                g.db.commit()
                flash("Playlist created.", "success")
                return redirect(url_for("playlists"))
            return render_template("playlist_form.html", playlist=None)
        return render_template("playlist_form.html", playlist=None)

    @app.route("/playlists/<int:playlist_id>", methods=["GET", "POST"])
    @login_required
    def playlist_detail(playlist_id):
        playlist = one("SELECT * FROM playlists WHERE playlist_id = %s AND user_id = %s", (playlist_id, session["user_id"]))
        if not playlist:
            abort(404)
        if request.method == "POST" and request.form.get("action") == "edit":
            title = request.form.get("title", "").strip()[:120]
            cover_input = request.form.get("cover_image_url", "")
            cover = valid_image_url(cover_input)
            mood_value = request.form.get("mood", "")
            category_value = request.form.get("time_category", "")
            period_value = request.form.get("period", "")
            preferences_valid = (
                (not mood_value or mood_value in MOODS)
                and (not category_value or category_value in CATEGORIES)
                and (not period_value or period_value in PERIODS[1:])
                and (
                    not category_value or not period_value
                    or (category_value in ("Morning", "Afternoon", "Evening") and period_value == "Day")
                    or (category_value in ("Night", "Midnight") and period_value == "Night")
                    or (category_value == "Quiet Hours" and period_value == "Quiet Hours")
                )
            )
            if not title:
                flash("Playlist title is required.", "error")
            elif not preferences_valid:
                flash("Choose valid playlist preferences with matching time category and period.", "error")
            elif cover_input.strip() and not cover:
                flash("Cover image must be a valid HTTPS URL.", "error")
            else:
                visibility = request.form.get("visibility", "private")
                if visibility not in ("private", "public"):
                    visibility = "private"
                token = playlist["share_token"]
                if visibility == "public" and not token:
                    token = secrets.token_hex(16)
                if visibility == "private":
                    token = None
                execute(
                    g.db, app.config["DATABASE_URL"],
                    """UPDATE playlists SET title = %s, description = %s, mood = %s, time_category = %s,
                       period = %s, visibility = %s, share_token = %s, cover_image_url = %s
                       WHERE playlist_id = %s AND user_id = %s""",
                    (
                        title, optional(request.form.get("description"), 500),
                        valid_choice(mood_value, MOODS),
                        valid_choice(category_value, CATEGORIES),
                        valid_choice(period_value, PERIODS[1:]), visibility, token, cover,
                        playlist_id, session["user_id"],
                    ),
                )
                g.db.commit()
                flash("Playlist updated.", "success")
            return redirect(url_for("playlist_detail", playlist_id=playlist_id))
        songs = all_rows(
            """SELECT s.*, ps.position,
                      (SELECT mood FROM song_categories WHERE song_id = s.song_id LIMIT 1) AS mood,
                      (SELECT time_category FROM song_categories WHERE song_id = s.song_id LIMIT 1) AS time_category,
                      (SELECT period FROM song_categories WHERE song_id = s.song_id LIMIT 1) AS period
               FROM playlist_songs ps JOIN songs s ON s.song_id = ps.song_id
               WHERE ps.playlist_id = %s ORDER BY ps.position""",
            (playlist_id,),
        )
        available = all_rows(
            """SELECT song_id, title, movie_name FROM songs
               WHERE approval_status = 'approved' OR (approval_status = 'private' AND created_by = %s)
               ORDER BY title LIMIT 300""",
            (session["user_id"],),
        )
        return render_template("playlist_detail.html", playlist=playlist, songs=songs, available=available)

    @app.route("/playlists/<int:playlist_id>/add-song", methods=["POST"])
    @login_required
    def add_playlist_song(playlist_id):
        playlist_owner(playlist_id)
        song_id = request.form.get("song_id", type=int)
        song = one(
            """SELECT song_id FROM songs WHERE song_id = %s AND
               (approval_status = 'approved' OR (approval_status = 'private' AND created_by = %s))""",
            (song_id, session["user_id"]),
        )
        if not song:
            abort(404)
        position_row = one("SELECT COALESCE(MAX(position), 0) AS max_position FROM playlist_songs WHERE playlist_id = %s", (playlist_id,))
        try:
            execute(
                g.db, app.config["DATABASE_URL"],
                "INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (%s, %s, %s)",
                (playlist_id, song_id, position_row["max_position"] + 1),
            )
        except (sqlite3.IntegrityError, MySQLIntegrityError):
            g.db.rollback()
            flash("That song is already in this playlist.", "error")
        else:
            g.db.commit()
            flash("Song added to playlist.", "success")
        return redirect(url_for("playlist_detail", playlist_id=playlist_id))

    @app.route("/playlists/add-song/<int:song_id>", methods=["POST"])
    @login_required
    def add_song_to_playlist_quick(song_id):
        playlist_id = request.form.get("playlist_id", type=int)
        if not playlist_id:
            flash("Choose one of your playlists first.", "error")
            return redirect(request.referrer or url_for("music"))
        playlist_owner(playlist_id)
        song = one(
            """SELECT song_id FROM songs WHERE song_id = %s AND
               (approval_status = 'approved' OR (approval_status = 'private' AND created_by = %s))""",
            (song_id, session["user_id"]),
        )
        if not song:
            abort(404)
        position_row = one(
            "SELECT COALESCE(MAX(position), 0) AS max_position FROM playlist_songs WHERE playlist_id = %s",
            (playlist_id,),
        )
        try:
            execute(
                g.db, app.config["DATABASE_URL"],
                "INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (%s, %s, %s)",
                (playlist_id, song_id, position_row["max_position"] + 1),
            )
        except (sqlite3.IntegrityError, MySQLIntegrityError):
            g.db.rollback()
            flash("That song is already in this playlist.", "error")
        else:
            g.db.commit()
            flash("Song added to playlist.", "success")
        return redirect(request.referrer or url_for("playlist_detail", playlist_id=playlist_id))

    @app.route("/playlists/<int:playlist_id>/remove-song", methods=["POST"])
    @login_required
    def remove_playlist_song(playlist_id):
        playlist_owner(playlist_id)
        song_id = request.form.get("song_id", type=int)
        execute("DELETE FROM playlist_songs WHERE playlist_id = %s AND song_id = %s", (playlist_id, song_id))
        g.db.commit()
        reorder_positions(playlist_id)
        flash("Song removed.", "success")
        return redirect(url_for("playlist_detail", playlist_id=playlist_id))

    @app.route("/playlists/<int:playlist_id>/reorder", methods=["POST"])
    @login_required
    def reorder_playlist(playlist_id):
        playlist_owner(playlist_id)
        try:
            song_ids = [int(value) for value in request.form.get("song_ids", "").split(",") if value]
        except ValueError:
            abort(400)
        current = [row["song_id"] for row in all_rows(
            "SELECT song_id FROM playlist_songs WHERE playlist_id = %s ORDER BY position", (playlist_id,)
        )]
        if len(song_ids) != len(current) or set(song_ids) != set(current):
            abort(400)
        execute("UPDATE playlist_songs SET position = position + 100000 WHERE playlist_id = %s", (playlist_id,))
        for position, song_id in enumerate(song_ids, 1):
            execute("UPDATE playlist_songs SET position = %s WHERE playlist_id = %s AND song_id = %s", (position, playlist_id, song_id))
        g.db.commit()
        flash("Playlist order saved.", "success")
        return redirect(url_for("playlist_detail", playlist_id=playlist_id))

    @app.route("/playlists/<int:playlist_id>/delete", methods=["POST"])
    @login_required
    def delete_playlist(playlist_id):
        playlist_owner(playlist_id)
        execute("DELETE FROM playlists WHERE playlist_id = %s AND user_id = %s", (playlist_id, session["user_id"]))
        g.db.commit()
        flash("Playlist deleted.", "success")
        return redirect(url_for("playlists"))

    @app.route("/shared/<token>")
    def shared_playlist(token):
        playlist = one("SELECT * FROM playlists WHERE share_token = %s AND visibility = 'public'", (token,))
        if not playlist:
            abort(404)
        songs = all_rows(
            """SELECT s.*, ps.position,
                      (SELECT mood FROM song_categories WHERE song_id = s.song_id LIMIT 1) AS mood,
                      (SELECT time_category FROM song_categories WHERE song_id = s.song_id LIMIT 1) AS time_category,
                      (SELECT period FROM song_categories WHERE song_id = s.song_id LIMIT 1) AS period
               FROM playlist_songs ps JOIN songs s ON s.song_id = ps.song_id
               WHERE ps.playlist_id = %s AND s.approval_status = 'approved' ORDER BY ps.position""",
            (playlist["playlist_id"],),
        )
        return render_template("shared_playlist.html", playlist=playlist, songs=songs)

    @app.route("/journal", methods=["GET", "POST"])
    @login_required
    def journal():
        if request.method == "POST":
            title = request.form.get("title", "").strip()[:200]
            content = request.form.get("content", "").strip()
            if not title or not content:
                flash("A title and letter are both required.", "error")
            else:
                execute(
                    g.db, app.config["DATABASE_URL"],
                    "INSERT INTO journal_entries (user_id, title, content, mood) VALUES (%s, %s, %s, %s)",
                    (session["user_id"], title, content[:20000], valid_choice(request.form.get("mood"), MOODS)),
                )
                g.db.commit()
                flash("Your private letter has been saved.", "success")
            return redirect(url_for("journal"))
        entries = all_rows(
            "SELECT * FROM journal_entries WHERE user_id = %s ORDER BY updated_at DESC",
            (session["user_id"],),
        )
        return render_template("journal.html", entries=entries)

    @app.route("/journal/<int:entry_id>/update", methods=["POST"])
    @login_required
    def update_journal(entry_id):
        title = request.form.get("title", "").strip()[:200]
        content = request.form.get("content", "").strip()[:20000]
        if not title or not content:
            flash("A title and letter are both required.", "error")
        else:
            execute(
                g.db, app.config["DATABASE_URL"],
                """UPDATE journal_entries SET title = %s, content = %s, mood = %s,
                   updated_at = CURRENT_TIMESTAMP WHERE entry_id = %s AND user_id = %s""",
                (title, content, valid_choice(request.form.get("mood"), MOODS), entry_id, session["user_id"]),
            )
            g.db.commit()
            flash("Your letter was updated.", "success")
        return redirect(url_for("journal"))

    @app.route("/journal/<int:entry_id>/delete", methods=["POST"])
    @login_required
    def delete_journal(entry_id):
        execute(
            g.db, app.config["DATABASE_URL"],
            "DELETE FROM journal_entries WHERE entry_id = %s AND user_id = %s",
            (entry_id, session["user_id"]),
        )
        g.db.commit()
        flash("Your letter was deleted.", "success")
        return redirect(url_for("journal"))

    @app.route("/heart-wall", methods=["GET", "POST"])
    def heart_wall():
        if request.method == "POST":
            key = "last_story_submission"
            from datetime import timezone as utc
            if session.get(key) and (datetime.now(utc.utc).timestamp() - session[key] < 60):
                flash("Please wait a minute before sharing another story.", "error")
            else:
                title = request.form.get("title", "").strip()[:200] or "A story from the heart"
                content = request.form.get("content", "").strip()
                if len(content) < 20:
                    flash("Share at least 20 characters so others can understand your story.", "error")
                else:
                    execute(
                        g.db, app.config["DATABASE_URL"],
                        "INSERT INTO stories (user_id, title, content, category, status) VALUES (%s, %s, %s, %s, 'pending')",
                        (session.get("user_id"), title, content[:5000], optional(request.form.get("category"), 80)),
                    )
                    g.db.commit()
                    session[key] = datetime.now(utc.utc).timestamp()
                    flash("Your story was sent for review. Your identity will not appear publicly.", "success")
            return redirect(url_for("heart_wall"))
        stories = all_rows(
            """SELECT s.story_id, s.title, s.content, s.category, s.created_at,
                      (SELECT COUNT(*) FROM comments c WHERE c.story_id = s.story_id) AS comment_count
               FROM stories s WHERE s.status = 'published' ORDER BY s.created_at DESC LIMIT 50"""
        )
        for story in stories:
            story["comments"] = all_rows(
                """SELECT c.content, u.username, c.created_at FROM comments c
                   JOIN users u ON u.user_id = c.user_id WHERE c.story_id = %s
                   ORDER BY c.created_at LIMIT 20""",
                (story["story_id"],),
            )
            story["heart_count"] = one(
                "SELECT COUNT(*) AS total FROM story_reactions WHERE story_id = %s",
                (story["story_id"],),
            )["total"]
            story["hearted"] = bool(
                session.get("user_id")
                and one(
                    "SELECT story_id FROM story_reactions WHERE story_id = %s AND user_id = %s",
                    (story["story_id"], session["user_id"]),
                )
            )
        return render_template("heart_wall.html", stories=stories)

    @app.route("/heart-wall/<int:story_id>/comment", methods=["POST"])
    @login_required
    def add_comment(story_id):
        content = request.form.get("content", "").strip()[:1000]
        if not content:
            flash("Write a kind comment first.", "error")
        elif not one("SELECT story_id FROM stories WHERE story_id = %s AND status = 'published'", (story_id,)):
            abort(404)
        else:
            execute(
                g.db, app.config["DATABASE_URL"],
                "INSERT INTO comments (story_id, user_id, content) VALUES (%s, %s, %s)",
                (story_id, session["user_id"], content),
            )
            g.db.commit()
            flash("Your comment was shared.", "success")
        return redirect(url_for("heart_wall"))

    @app.route("/heart-wall/<int:story_id>/heart", methods=["POST"])
    @login_required
    def react_story(story_id):
        if not one("SELECT story_id FROM stories WHERE story_id = %s AND status = 'published'", (story_id,)):
            abort(404)
        existing = one(
            "SELECT story_id FROM story_reactions WHERE story_id = %s AND user_id = %s AND reaction = 'heart'",
            (story_id, session["user_id"]),
        )
        if existing:
            execute(
                g.db, app.config["DATABASE_URL"],
                "DELETE FROM story_reactions WHERE story_id = %s AND user_id = %s AND reaction = 'heart'",
                (story_id, session["user_id"]),
            )
        else:
            execute(
                g.db, app.config["DATABASE_URL"],
                "INSERT INTO story_reactions (story_id, user_id, reaction) VALUES (%s, %s, 'heart')",
                (story_id, session["user_id"]),
            )
        g.db.commit()
        return redirect(url_for("heart_wall"))

    @app.route("/heart-wall/<int:story_id>/report", methods=["POST"])
    @login_required
    def report_story(story_id):
        reason = request.form.get("reason", "").strip()[:500]
        if not reason or not one("SELECT story_id FROM stories WHERE story_id = %s AND status = 'published'", (story_id,)):
            abort(400)
        execute(
            g.db, app.config["DATABASE_URL"],
            "INSERT INTO reports (reporter_id, story_id, reason) VALUES (%s, %s, %s)",
            (session["user_id"], story_id, reason),
        )
        g.db.commit()
        flash("Thank you. The story has been reported for review.", "success")
        return redirect(url_for("heart_wall"))

    @app.route("/healing", methods=["GET", "POST"])
    @login_required
    def healing():
        prompts = [
            "What is one thing you wish you could say without fear?",
            "Which small moment brought you a little peace today?",
            "What would you tell a friend feeling the way you do?",
            "What are you ready to release, even just for today?",
            "What is one gentle thing you can do for yourself now?",
        ]
        if request.method == "POST":
            mood = valid_choice(request.form.get("mood"), MOODS)
            if not mood:
                flash("Choose a mood to save today's reflection.", "error")
            else:
                execute(
                    g.db, app.config["DATABASE_URL"],
                    "INSERT INTO mood_logs (user_id, mood, note) VALUES (%s, %s, %s)",
                    (session["user_id"], mood, optional(request.form.get("note"), 500)),
                )
                g.db.commit()
                flash("Your private check-in was saved.", "success")
            return redirect(url_for("healing"))
        mood_logs = all_rows(
            "SELECT mood, note, created_at FROM mood_logs WHERE user_id = %s ORDER BY created_at DESC LIMIT 14",
            (session["user_id"],),
        )
        day_number = local_now().timetuple().tm_yday
        return render_template(
            "healing.html", prompt=prompts[day_number % len(prompts)], mood_logs=mood_logs
        )

    @app.route("/about")
    def about():
        return render_template("info.html", title="About", intro="A quiet corner for words left unsaid, songs that understand, and people finding their own pace.", body="BROKEN SOULS is a community and music discovery space. It is not a substitute for professional mental-health care.")

    @app.route("/contact", methods=["GET", "POST"])
    def contact():
        if request.method == "POST":
            email = request.form.get("email", "").strip()
            message = request.form.get("message", "").strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or not message:
                flash("Enter a valid email address and a message.", "error")
            else:
                flash("This local build has no mail delivery configured; your message was not sent.", "error")
            return redirect(url_for("contact"))
        return render_template("contact.html")

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        pending_songs = all_rows(
            """SELECT s.*, u.username FROM songs s LEFT JOIN users u ON u.user_id = s.created_by
               WHERE s.approval_status = 'pending' ORDER BY s.created_at"""
        )
        pending_stories = all_rows(
            "SELECT story_id, title, content, category, created_at FROM stories WHERE status = 'pending' ORDER BY created_at"
        )
        reports = all_rows(
            """SELECT r.*, s.title AS story_title FROM reports r
               JOIN stories s ON s.story_id = r.story_id WHERE r.status = 'open' ORDER BY r.created_at"""
        )
        counts = {
            "users": one("SELECT COUNT(*) AS total FROM users")["total"],
            "songs": one("SELECT COUNT(*) AS total FROM songs")["total"],
            "playlists": one("SELECT COUNT(*) AS total FROM playlists")["total"],
        }
        return render_template("admin.html", songs=pending_songs, stories=pending_stories, reports=reports, counts=counts)

    @app.route("/admin/songs")
    @admin_required
    def admin_songs():
        songs = all_rows(
            """SELECT s.song_id, s.title, s.movie_name, s.approval_status, s.created_at,
                      (SELECT mood FROM song_categories c WHERE c.song_id = s.song_id LIMIT 1) AS mood,
                      (SELECT time_category FROM song_categories c WHERE c.song_id = s.song_id LIMIT 1) AS time_category
               FROM songs s ORDER BY s.created_at DESC LIMIT 500"""
        )
        return render_template("admin_songs.html", songs=songs)

    @app.route("/admin/songs/new", methods=["GET", "POST"])
    @admin_required
    def admin_song_create():
        if request.method == "POST":
            title = request.form.get("title", "").strip()[:200]
            mood = valid_choice(request.form.get("mood"), MOODS)
            category = valid_choice(request.form.get("time_category"), CATEGORIES)
            period = valid_choice(request.form.get("period"), PERIODS[1:])
            external_url = request.form.get("external_url", "").strip()
            target = (parse_music_url(external_url) or parse_local_audio(external_url)) if external_url else None
            cover_input = request.form.get("cover_image_url", "")
            cover = valid_image_url(cover_input)
            category_valid = (
                category in ("Morning", "Afternoon", "Evening") and period == "Day"
            ) or (category in ("Night", "Midnight") and period == "Night") or (
                category == "Quiet Hours" and period == "Quiet Hours"
            )
            if not title or not mood or not category_valid:
                flash("Provide a title, a valid mood, and a matching category/period.", "error")
            elif external_url and not target:
                flash("Use a validated YouTube/Spotify URL or a local MP3 path under /static/audio/.", "error")
            elif cover_input.strip() and not cover:
                flash("Cover image must be a valid HTTPS URL.", "error")
            else:
                cursor = execute(
                    g.db, app.config["DATABASE_URL"],
                    """INSERT INTO songs (title, movie_name, singer, language, cover_image_url,
                       provider, external_url, embed_url, approval_status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'approved')""",
                    (
                        title, optional(request.form.get("movie_name"), 200),
                        optional(request.form.get("singer"), 200),
                        optional(request.form.get("language"), 80) or "Hindi",
                        cover,
                        target["provider"] if target else None,
                        target["url"] if target else None,
                        target["embed"] if target else None,
                    ),
                )
                execute(
                    g.db, app.config["DATABASE_URL"],
                    """INSERT INTO song_categories (song_id, mood, time_category, period, language)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (cursor.lastrowid, mood, category, period, optional(request.form.get("language"), 80) or "Hindi"),
                )
                g.db.commit()
                flash("Song added to the public library.", "success")
                return redirect(url_for("admin_songs"))
            return render_template("admin_song_form.html", song=None)
        return render_template("admin_song_form.html", song=None)

    @app.route("/admin/songs/<int:song_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_song_edit(song_id):
        song = one("SELECT * FROM songs WHERE song_id = %s", (song_id,))
        if not song:
            abort(404)
        assignment = one(
            "SELECT * FROM song_categories WHERE song_id = %s ORDER BY assignment_id LIMIT 1",
            (song_id,),
        )
        if request.method == "POST":
            title = request.form.get("title", "").strip()[:200]
            external_url = request.form.get("external_url", "").strip()
            target = (parse_music_url(external_url) or parse_local_audio(external_url)) if external_url else None
            cover_input = request.form.get("cover_image_url", "")
            cover = valid_image_url(cover_input)
            mood = valid_choice(request.form.get("mood"), MOODS)
            category = valid_choice(request.form.get("time_category"), CATEGORIES)
            period = valid_choice(request.form.get("period"), PERIODS[1:])
            selected_assignment_valid = (
                category in ("Morning", "Afternoon", "Evening") and period == "Day"
            ) or (category in ("Night", "Midnight") and period == "Night") or (
                category == "Quiet Hours" and period == "Quiet Hours"
            )
            if not title:
                flash("Song title is required.", "error")
            elif external_url and not target:
                flash("The link must be a validated YouTube or Spotify URL.", "error")
            elif cover_input.strip() and not cover:
                flash("Cover image must be a valid HTTPS URL.", "error")
            elif assignment and (not mood or not selected_assignment_valid):
                flash("Choose a valid mood and matching time category/period.", "error")
            else:
                execute(
                    g.db, app.config["DATABASE_URL"],
                    """UPDATE songs SET title = %s, movie_name = %s, singer = %s, language = %s,
                       cover_image_url = %s, provider = %s, external_url = %s, embed_url = %s
                       WHERE song_id = %s""",
                    (
                        title, optional(request.form.get("movie_name"), 200),
                        optional(request.form.get("singer"), 200),
                        optional(request.form.get("language"), 80) or "Hindi",
                        cover,
                        target["provider"] if target else None,
                        target["url"] if target else None,
                        target["embed"] if target else None,
                        song_id,
                    ),
                )
                if assignment:
                    execute(
                        g.db, app.config["DATABASE_URL"],
                        """UPDATE song_categories SET mood = %s, time_category = %s, period = %s,
                           language = %s WHERE assignment_id = %s""",
                        (
                            mood or assignment["mood"],
                            category or assignment["time_category"],
                            period or assignment["period"],
                            optional(request.form.get("language"), 80) or assignment["language"],
                            assignment["assignment_id"],
                        ),
                    )
                g.db.commit()
                flash("Song metadata updated.", "success")
                return redirect(url_for("admin_songs"))
        return render_template("admin_song_form.html", song=song, assignment=assignment)

    @app.route("/admin/songs/<int:song_id>/delete", methods=["POST"])
    @admin_required
    def admin_song_remove(song_id):
        execute(
            g.db, app.config["DATABASE_URL"],
            "UPDATE songs SET approval_status = 'removed' WHERE song_id = %s",
            (song_id,),
        )
        g.db.commit()
        flash("Song removed from the public library.", "success")
        return redirect(url_for("admin_songs"))

    @app.route("/admin/songs/<int:song_id>/<action>", methods=["POST"])
    @admin_required
    def admin_song_review(song_id, action):
        if action not in ("approve", "reject"):
            abort(404)
        status = "approved" if action == "approve" else "removed"
        execute(
            g.db, app.config["DATABASE_URL"],
            "UPDATE songs SET approval_status = %s WHERE song_id = %s AND approval_status = 'pending'",
            (status, song_id),
        )
        g.db.commit()
        flash(f"Song {action}d.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/stories/<int:story_id>/<action>", methods=["POST"])
    @admin_required
    def admin_story_review(story_id, action):
        if action not in ("approve", "remove"):
            abort(404)
        status = "published" if action == "approve" else "removed"
        execute(
            g.db, app.config["DATABASE_URL"],
            "UPDATE stories SET status = %s WHERE story_id = %s AND status IN ('pending', 'published')",
            (status, story_id),
        )
        g.db.commit()
        flash(f"Story {action}d.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/reports/<int:report_id>/<action>", methods=["POST"])
    @admin_required
    def admin_report_action(report_id, action):
        if action not in ("resolved", "dismissed"):
            abort(404)
        execute(
            g.db, app.config["DATABASE_URL"],
            "UPDATE reports SET status = %s WHERE report_id = %s",
            (action, report_id),
        )
        g.db.commit()
        flash("Report updated.", "success")
        return redirect(url_for("admin_dashboard"))

    def db_arguments(args):
        if args and args[0] is g.db:
            query = args[2]
            params = args[3] if len(args) > 3 else ()
            return query, params
        return args[0], args[1] if len(args) > 1 else ()

    def one(*args):
        from database import one as fetch_one
        query, params = db_arguments(args)
        return fetch_one(g.db, app.config["DATABASE_URL"], query, params)

    def execute(*args):
        query, params = db_arguments(args)
        return globals()["execute"](g.db, app.config["DATABASE_URL"], query, params)

    def all_rows(*args):
        query, params = db_arguments(args)
        return globals()["all_rows"](g.db, app.config["DATABASE_URL"], query, params)

    def playlist_owner(playlist_id):
        if not one("SELECT playlist_id FROM playlists WHERE playlist_id = %s AND user_id = %s", (playlist_id, session["user_id"])):
            abort(404)

    def reorder_positions(playlist_id):
        rows = all_rows("SELECT song_id FROM playlist_songs WHERE playlist_id = %s ORDER BY position", (playlist_id,))
        execute("UPDATE playlist_songs SET position = position + 100000 WHERE playlist_id = %s", (playlist_id,))
        for position, row in enumerate(rows, 1):
            execute(
                "UPDATE playlist_songs SET position = %s WHERE playlist_id = %s AND song_id = %s",
                (position, playlist_id, row["song_id"]),
            )
        g.db.commit()

    def current_user():
        user_id = session.get("user_id")
        if not user_id or not hasattr(g, "db"):
            return None
        return one("SELECT user_id, username, email, role FROM users WHERE user_id = %s", (user_id,))

    def local_now():
        try:
            timezone = ZoneInfo(app.config["TIMEZONE"])
        except ZoneInfoNotFoundError:
            app.logger.error("Invalid TIMEZONE configured: %s", app.config["TIMEZONE"])
            timezone = ZoneInfo("UTC")
        from datetime import timezone as utc
        return datetime.now(utc.utc).astimezone(timezone)

    def fetch_youtube_metadata(target, api_key):
        if target["kind"] == "playlist":
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/playlists",
                params={"part": "snippet", "id": target["id"], "key": api_key},
                timeout=5,
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            if items:
                snippet = items[0]["snippet"]
                return {
                    "title": snippet.get("title", ""),
                    "singer": snippet.get("channelTitle", ""),
                    "cover_image_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                }
            return {}
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet", "id": target["id"], "key": api_key},
            timeout=5,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        if not items:
            return {}
        snippet = items[0]["snippet"]
        return {
            "title": snippet.get("title", ""),
            "singer": snippet.get("channelTitle", ""),
            "cover_image_url": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        }

    def fetch_spotify_metadata(target):
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        if not client_id or not client_secret or target["kind"] != "track":
            return {}
        token_response = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=5,
        )
        token_response.raise_for_status()
        token = token_response.json().get("access_token")
        if not token:
            return {}
        response = requests.get(
            f"https://api.spotify.com/v1/tracks/{target['id']}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "title": data.get("name", ""),
            "singer": ", ".join(artist["name"] for artist in data.get("artists", [])),
            "cover_image_url": data.get("album", {}).get("images", [{}])[0].get("url", ""),
        }

    def valid_image_url(value):
        value = (value or "").strip()
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        return value[:1000]

    def optional(value, limit):
        value = (value or "").strip()
        return value[:limit] if value else None

    def valid_choice(value, choices):
        return value if value in choices else None

    app.jinja_env.globals["category_for_time"] = category_for_time
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
