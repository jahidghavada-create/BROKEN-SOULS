# BROKEN SOULS

A responsive Flask and MySQL music-discovery and reflection website. The visual direction uses an original CSS-built nightscape rather than film stills or unlicensed artwork. Commercial songs are never downloaded or re-hosted: seed records contain no invented streaming links, and submitted music uses validated official links and provider embeds.

## Project structure

```text
broken_souls/
├── app.py
├── config.py
├── database.py
├── requirements.txt
├── .env.example
├── .gitignore
├── schema.sql
├── sqlite_schema.sql
├── seed_songs.py
├── templates/
│   ├── base.html
│   ├── _song_card.html
│   ├── home.html
│   ├── music.html
│   ├── song.html
│   ├── add_song.html
│   ├── auth.html
│   ├── profile.html
│   ├── playlists.html
│   ├── playlist_form.html
│   ├── playlist_detail.html
│   ├── shared_playlist.html
│   ├── journal.html
│   ├── heart_wall.html
│   ├── healing.html
│   ├── info.html
│   ├── contact.html
│   ├── admin.html
│   ├── admin_songs.html
│   ├── admin_song_form.html
│   └── error.html
├── static/
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       ├── music.js
│       ├── add-song.js
│       └── playlist.js
└── tests/test_app.py
```

## Database schema

`schema.sql` is the production MySQL schema. It creates the `broken_souls` database and these related tables:

- `users`: unique usernames/emails, password hashes, and user/admin roles.
- `songs` and `song_categories`: normalized song records with category-specific mood, time-category, and period assignments. Duplicate titles may have separate category assignments.
- `playlists` and `playlist_songs`: private-by-default playlists, share tokens, and persistent song ordering.
- `favorites`: unique per-user song favorites.
- `journal_entries`: private letters with user ownership.
- `stories`, `comments`, `story_reactions`, and `reports`: moderated anonymous stories and community actions.
- `mood_logs`: private check-ins.

The schema uses foreign keys, deletion rules, unique constraints, and indexes. `sqlite_schema.sql` is only for the automated tests; use MySQL for a regular local installation.

## Windows setup (Command Prompt)

1. Install Python 3.10+ and MySQL 8+, then create a MySQL user with access to create/use the application database.
2. Open Command Prompt in the project directory:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   py -m pip install -r requirements.txt
   copy .env.example .env
   ```

3. Edit `.env`. Generate a secret key, for example:

   ```bat
   py -c "import secrets; print(secrets.token_hex(32))"
   ```

   Put the generated value in `FLASK_SECRET_KEY`, and set the MySQL URL:

   ```ini
   FLASK_SECRET_KEY=paste-your-generated-value
   DATABASE_URL=mysql://broken_souls:your-password@127.0.0.1:3306/broken_souls
   TIMEZONE=Asia/Kolkata
   SESSION_COOKIE_SECURE=0
   ```

   URL-encode special characters in the database username/password. Keep `.env` private; it is ignored by Git.

4. Create the database and tables from Command Prompt:

   ```bat
   mysql -u root -p < schema.sql
   ```

   If your MySQL installation doesn't put `mysql.exe` on `PATH`, run it from the MySQL `bin` directory or use the full path to `mysql.exe`.
   For a dedicated local application user, connect to MySQL as an administrator and run:

   ```sql
   CREATE USER 'broken_souls'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
   GRANT ALL PRIVILEGES ON broken_souls.* TO 'broken_souls'@'localhost';
   ```

5. Seed the 33 provided category assignments:

   ```bat
   py seed_songs.py
   ```

   Seed records intentionally leave singer and external-link values blank unless verified. They do not contain fake playback links.

6. Start the website:

   ```bat
   py app.py
   ```

   Open `http://127.0.0.1:5000`. For development-only debug output, set `FLASK_DEBUG=1` in `.env`. Do not enable debug mode in a public deployment.

## Music metadata configuration

The application accepts validated HTTPS links from official YouTube (`youtube.com`, `youtu.be`) and Spotify (`open.spotify.com`) track or playlist URLs. The server does not fetch arbitrary URLs:

- YouTube embeds are created from validated video/playlist IDs. To fetch YouTube title, channel, and artwork metadata, create an authorized YouTube Data API key and set `YOUTUBE_API_KEY` in `.env`.
- Spotify links work as official embeds. To fetch Spotify track metadata, create an authorized Spotify application and set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`. Without credentials, enter details manually.
- Metadata failures and unavailable links are reported; a validated link can still be saved with manually entered fields.
- Public submissions remain pending until an administrator approves them. Personal additions are private to their owner. Direct audio upload and commercial audio hosting are not implemented.

Provider availability, playback controls, login requirements, and advertisements remain under the control of YouTube/Spotify. The site does not claim that a link is playing when no embedded player is available.

## Features

- Homepage, responsive navigation, accessible labels, reduced-motion preference, and a plain-background toggle.
- Six time tabs with exact windows: Morning 06:00–12:00; Afternoon 12:00–17:00; Evening 17:00–21:00; Night 21:00–00:00; Midnight 00:00–04:00; Quiet Hours 04:00–06:00. The initial zone is configurable (Asia/Kolkata by default), while browser-side display updates live.
- Combined search, mood, period, category, language, movie, and singer filters backed by database queries; search suggestions, recently added songs, and a Surprise Me action.
- Registration/login with password hashing, Flask sessions, CSRF protection, private playlists/favorites/journals/mood logs, and backend ownership checks.
- Playlist create/edit/delete, song management, persistent reorder, and read-only public share pages.
- Anonymous story submission with moderation queue, kind comments, hearts, reports, and admin actions.
- Admin access is granted only by changing the `users.role` column for a trusted registered account. Admins can manage song metadata/categories, review public song and story submissions, and process reports. No public hard-coded admin credential exists.

## Run tests

From the project directory with the virtual environment active:

```bat
py -m unittest discover -s tests -v
```

The tests use an isolated SQLite database and do not require a running MySQL server. The local site uses the MySQL URL from `.env`.

## Make an administrator

First register using the website. Then grant the role from a MySQL account with appropriate privileges:

```sql
USE broken_souls;
UPDATE users SET role = 'admin' WHERE email = 'trusted-admin@example.com';
```

Do not give admin access to an untrusted account. The admin dashboard is protected by a server-side role check.

## Troubleshooting

- **Can't connect to MySQL:** confirm the MySQL service is running, database/user credentials are correct, and the selected user can access `broken_souls`.
- **Unknown database/table:** apply `schema.sql` with `mysql -u root -p < schema.sql`.
- **`Access denied`:** grant the application account privileges on the `broken_souls` database and check URL-encoding for special characters.
- **No fetched title/artwork:** confirm the corresponding provider credentials and API access are enabled. Use manual metadata entry when a provider doesn't expose details.
- **CSRF token errors:** load or refresh the form page to receive a current session token; ensure the browser accepts session cookies.
- **Images are blank:** external artwork is optional. Cards use the built-in dark gradient fallback and do not download or mirror art.
- **Admin page returns 403:** grant the trusted account the `admin` role using the SQL above, then sign out and back in.

The contact form is a UI placeholder in this local build; configure a mail provider before relying on it to deliver messages. Use HTTPS, a production-grade secret, secure cookie settings, database backups, and operational rate limiting before public deployment.

Set `SESSION_COOKIE_SECURE=1` when serving the app over HTTPS in production.


## Local MP3 playback (licensed audio only)

To play an MP3 directly on the website, place an MP3 file that you own or are licensed to distribute in `static/audio/`. Commit that file to the repository, then sign in with an admin account and open **Admin → Song library → Add a song**. In the URL/path field, enter a path such as `/static/audio/my-track.mp3`. Save the song and its card/detail page will show an in-page audio player.

Use a simple filename containing letters, numbers, dots, underscores, or hyphens. Only MP3 paths under `/static/audio/` are accepted. Do not commit commercial songs unless you have the rights or permission to distribute them. Large audio files increase repository/deployment size; use an authorized audio host or object storage for larger catalogs.
