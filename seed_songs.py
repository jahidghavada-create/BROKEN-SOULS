import os

from dotenv import load_dotenv

from database import execute, is_sqlite, transaction

load_dotenv()

SONGS = [
    ("Agar Tum Saath Ho", "Tamasha", "Emotional", "Morning", "Day"),
    ("Phir Le Aya Dil (Reprise)", "Barfi!", "Lost Love", "Morning", "Day"),
    ("Tum Ho", "Rockstar", "Missing Someone", "Morning", "Day"),
    ("Channa Mereya", "Ae Dil Hai Mushkil", "One-Sided Love", "Morning", "Day"),
    ("Tujhe Bhula Diya", "Anjaana Anjaani", "Moving On", "Morning", "Day"),
    ("Hamari Adhuri Kahani", "Hamari Adhuri Kahani", "Incomplete Love", "Morning", "Day"),
    ("Bekhayali", "Kabir Singh", "Heartbreak", "Afternoon", "Day"),
    ("Bhula Dena", "Aashiqui 2", "Separation", "Afternoon", "Day"),
    ("Zaroorat", "Ek Villain", "Loneliness", "Afternoon", "Day"),
    ("Humnava", "Hamari Adhuri Kahani", "Missing Someone", "Afternoon", "Day"),
    ("Tujhe Kitna Chahne Lage", "Kabir Singh", "Unforgettable Love", "Afternoon", "Day"),
    ("Judaai", "Badlapur", "Separation", "Afternoon", "Day"),
    ("Sunn Raha Hai (Male Version)", "Aashiqui 2", "Pain", "Evening", "Day"),
    ("Humdard", "Ek Villain", "Emotional Love", "Evening", "Day"),
    ("Saaiyaan", "Gunday", "Longing", "Evening", "Day"),
    ("Lo Maan Liya", "Raaz Reboot", "Acceptance", "Evening", "Day"),
    ("Phir Bhi Tumko Chaahunga", "Half Girlfriend", "One-Sided Love", "Evening", "Day"),
    ("Kaise Hua", "Kabir Singh", "Love Memories", "Evening", "Day"),
    ("Channa Mereya", "Ae Dil Hai Mushkil", "One-Sided Love", "Night", "Night"),
    ("Tum Hi Ho", "Aashiqui 2", "Deep Love", "Night", "Night"),
    ("Tera Ban Jaunga", "Kabir Singh", "Longing", "Night", "Night"),
    ("Sach Keh Raha Hai", "Rehnaa Hai Terre Dil Mein", "Betrayal", "Night", "Night"),
    ("Dil Ibaadat", "Tum Mile", "Emotional Love", "Night", "Night"),
    ("Tere Bin", "Bas Ek Pal", "Loneliness", "Night", "Night"),
    ("Tanhayee", "Dil Chahta Hai", "Loneliness", "Night", "Night"),
    ("Agar Tum Saath Ho", "Tamasha", "Emotional Pain", "Midnight", "Night"),
    ("Nadaan Parindey", "Rockstar", "Inner Struggle", "Midnight", "Night"),
    ("Tune Jo Na Kaha", "New York", "Unspoken Feelings", "Midnight", "Night"),
    ("Alvida", "Life in... Metro", "Goodbye", "Midnight", "Night"),
    ("Woh Lamhe Woh Baatein", "Zeher", "Old Memories", "Midnight", "Night"),
    ("Jiyein Kyun", "Dum Maaro Dum", "Loneliness", "Midnight", "Night"),
    ("Main Dhoondne Ko Zamaane Mein", "Heartless", "Betrayal", "Midnight", "Night"),
    ("Tadap Tadap", "Hum Dil De Chuke Sanam", "Intense Heartbreak", "Midnight", "Night"),
]


def seed(database_url):
    with transaction(database_url) as connection:
        for title, movie, mood, category, period in SONGS:
            row = execute(
                connection,
                database_url,
                "SELECT song_id FROM songs WHERE title = %s AND movie_name = %s LIMIT 1",
                (title, movie),
            ).fetchone()
            if row:
                song_id = row["song_id"]
            else:
                cursor = execute(
                    connection,
                    database_url,
                    """INSERT INTO songs
                       (title, movie_name, singer, language, provider, approval_status)
                       VALUES (%s, %s, NULL, 'Hindi', NULL, 'approved')""",
                    (title, movie),
                )
                song_id = cursor.lastrowid
            insert_prefix = "INSERT OR IGNORE" if is_sqlite(database_url) else "INSERT IGNORE"
            execute(
                connection,
                database_url,
                f"""{insert_prefix} INTO song_categories
                   (song_id, mood, time_category, period, language, is_featured)
                   VALUES (%s, %s, %s, %s, 'Hindi', 1)""",
                (song_id, mood, category, period),
            )


if __name__ == "__main__":
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL before running the song seed script.")
    seed(database_url)
    print(f"Seeded {len(SONGS)} song-category assignments.")
