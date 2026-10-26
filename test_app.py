import os
import tempfile
import unittest

from app import category_for_time, create_app, parse_music_url
from database import connect
from seed_songs import seed


class BrokenSoulsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.directory.name, "test.sqlite3")
        self.database_url = "sqlite:///" + db_path.replace("\\", "/")
        connection = connect(self.database_url)
        with open(os.path.join(os.path.dirname(__file__), "..", "sqlite_schema.sql"), encoding="utf-8") as schema:
            connection.executescript(schema.read())
        connection.close()
        seed(self.database_url)
        self.app = create_app({
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret-key",
            "DATABASE_URL": self.database_url,
            "YOUTUBE_API_KEY": "",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    def register(self, username="listener"):
        return self.client.post("/register", data={
            "username": username,
            "email": f"{username}@example.test",
            "password": "a sufficiently long test password",
        }, follow_redirects=True)

    def test_home_and_music_render_seeded_catalogue(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/music?category=Midnight&period=Night&mood=Loneliness")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Jiyein Kyun", response.data)
        self.assertEqual(response.data.count(b'<article class="song-card'), 1)
        combined = self.client.get(
            "/music?category=Morning&period=Day&mood=Missing%20Someone&movie=Rockstar"
        )
        self.assertIn(b"Tum Ho", combined.data)
        self.assertEqual(combined.data.count(b'<article class="song-card'), 1)
        connection = connect(self.database_url)
        assignments = connection.execute("SELECT COUNT(*) AS total FROM song_categories").fetchone()["total"]
        self.assertEqual(assignments, 33)
        connection.close()

    def test_exact_time_category_boundaries(self):
        self.assertEqual(category_for_time(5, 59), "Quiet Hours")
        self.assertEqual(category_for_time(6, 0), "Morning")
        self.assertEqual(category_for_time(11, 59), "Morning")
        self.assertEqual(category_for_time(12, 0), "Afternoon")
        self.assertEqual(category_for_time(17, 0), "Evening")
        self.assertEqual(category_for_time(21, 0), "Night")
        self.assertEqual(category_for_time(0, 0), "Midnight")
        self.assertEqual(category_for_time(3, 59), "Midnight")
        self.assertEqual(category_for_time(4, 0), "Quiet Hours")

    def test_supported_music_links_are_canonical_and_invalid_hosts_rejected(self):
        youtube = parse_music_url("https://youtu.be/abcdefghijk?t=15")
        self.assertEqual(youtube["url"], "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(youtube["embed"], "https://www.youtube-nocookie.com/embed/abcdefghijk")
        spotify = parse_music_url("https://open.spotify.com/track/0123456789012345678901")
        self.assertEqual(spotify["provider"], "Spotify")
        self.assertIsNone(parse_music_url("https://example.com/redirect?url=https://youtube.com"))
        self.assertIsNone(parse_music_url("https://youtube.com.evil.test/watch?v=abcdefghijk"))
        self.assertIsNone(parse_music_url("https://youtube.com:8080/watch?v=abcdefghijk"))

    def test_playlist_order_and_private_journal_ownership(self):
        self.register("first_listener")
        self.client.post("/playlists/create", data={"title": "Songs for 2 AM"})
        connection = connect(self.database_url)
        playlist = connection.execute("SELECT playlist_id FROM playlists").fetchone()
        songs = connection.execute("SELECT song_id FROM songs ORDER BY song_id LIMIT 2").fetchall()
        playlist_id = playlist["playlist_id"]
        self.client.post(f"/playlists/{playlist_id}/add-song", data={"song_id": songs[0]["song_id"]})
        self.client.post(f"/playlists/{playlist_id}/add-song", data={"song_id": songs[1]["song_id"]})
        response = self.client.post(
            f"/playlists/{playlist_id}/reorder",
            data={"song_ids": f"{songs[1]['song_id']},{songs[0]['song_id']}"},
        )
        self.assertEqual(response.status_code, 302)
        positions = connection.execute(
            "SELECT song_id, position FROM playlist_songs WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        self.assertEqual([row["song_id"] for row in positions], [songs[1]["song_id"], songs[0]["song_id"]])
        self.client.post("/journal", data={"title": "Private", "content": "This belongs to the first user."})
        entry = connection.execute("SELECT entry_id FROM journal_entries").fetchone()
        self.client.post("/logout")
        self.register("second_listener")
        self.client.post(
            f"/journal/{entry['entry_id']}/update",
            data={"title": "Changed", "content": "Attempted access from another account."},
        )
        saved = connection.execute("SELECT title FROM journal_entries").fetchone()
        self.assertEqual(saved["title"], "Private")
        connection.close()

    def test_public_submissions_require_admin_review(self):
        self.register("moderator")
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.client.post("/heart-wall", data={
            "title": "A quiet story",
            "content": "This is a long enough story to appear after an administrator reviews it.",
            "category": "Letting go",
        })
        connection = connect(self.database_url)
        story = connection.execute("SELECT story_id, status FROM stories").fetchone()
        self.assertEqual(story["status"], "pending")
        connection.execute("UPDATE users SET role = 'admin' WHERE username = 'moderator'")
        connection.commit()
        connection.close()
        dashboard = self.client.get("/admin")
        self.assertEqual(dashboard.status_code, 200)
        response = self.client.post(f"/admin/stories/{story['story_id']}/approve")
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"A quiet story", self.client.get("/heart-wall").data)

    def test_metadata_endpoint_rejects_untrusted_url(self):
        response = self.client.post("/songs/fetch-metadata", data={"url": "http://127.0.0.1/admin"})
        self.assertEqual(response.status_code, 400)

    def test_validated_external_song_can_be_added_privately(self):
        self.register("song_owner")
        url = "https://www.youtube.com/watch?v=abcdefghijk"
        metadata = self.client.post("/songs/fetch-metadata", data={"url": url})
        self.assertEqual(metadata.status_code, 200)
        self.assertEqual(metadata.json["provider"], "YouTube")
        self.assertEqual(metadata.json["embed_url"], "https://www.youtube-nocookie.com/embed/abcdefghijk")
        response = self.client.post("/songs/add", data={
            "external_url": url,
            "title": "My private song",
            "movie_name": "A memory",
            "singer": "",
            "language": "Hindi",
            "mood": "Longing",
            "time_category": "Night",
            "period": "Night",
            "visibility": "private",
        })
        self.assertEqual(response.status_code, 302)
        connection = connect(self.database_url)
        song = connection.execute(
            "SELECT * FROM songs WHERE title = 'My private song'"
        ).fetchone()
        self.assertEqual(song["approval_status"], "private")
        self.assertEqual(song["embed_url"], "https://www.youtube-nocookie.com/embed/abcdefghijk")
        connection.close()

    def test_authenticated_pages_playlist_sharing_and_admin_catalogue(self):
        self.register("site_tester")
        for path in ("/profile", "/playlists", "/journal", "/healing", "/songs/add", "/heart-wall", "/about", "/contact"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.client.post("/playlists/create", data={
            "title": "Night notes",
            "description": "A public read-only list.",
            "visibility": "public",
        })
        connection = connect(self.database_url)
        playlist = connection.execute("SELECT playlist_id, share_token FROM playlists").fetchone()
        song = connection.execute("SELECT song_id FROM songs ORDER BY song_id LIMIT 1").fetchone()
        connection.close()
        self.assertEqual(self.client.get(f"/playlists/{playlist['playlist_id']}").status_code, 200)
        self.client.post(
            f"/playlists/{playlist['playlist_id']}/add-song",
            data={"song_id": song["song_id"]},
        )
        self.assertEqual(
            self.client.get(f"/shared/{playlist['share_token']}").status_code,
            200,
        )
        self.assertEqual(self.client.get(f"/songs/{song['song_id']}").status_code, 200)
        connection = connect(self.database_url)
        connection.execute("UPDATE users SET role = 'admin' WHERE username = 'site_tester'")
        connection.commit()
        connection.close()
        self.assertEqual(self.client.get("/admin/songs").status_code, 200)
        created = self.client.post("/admin/songs/new", data={
            "title": "Admin-added example",
            "movie_name": "Test film",
            "singer": "",
            "language": "Hindi",
            "mood": "Longing",
            "time_category": "Night",
            "period": "Night",
        })
        self.assertEqual(created.status_code, 302)
        connection = connect(self.database_url)
        admin_song = connection.execute(
            "SELECT song_id FROM songs WHERE title = 'Admin-added example'"
        ).fetchone()
        connection.close()
        self.assertEqual(self.client.get(f"/admin/songs/{admin_song['song_id']}/edit").status_code, 200)


if __name__ == "__main__":
    unittest.main()
