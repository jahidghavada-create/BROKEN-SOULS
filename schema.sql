CREATE DATABASE IF NOT EXISTS broken_souls CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE broken_souls;

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(40) NOT NULL UNIQUE,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('user', 'admin') NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS songs (
    song_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    movie_name VARCHAR(200) NULL,
    singer VARCHAR(200) NULL,
    language VARCHAR(80) NOT NULL DEFAULT 'Hindi',
    cover_image_url VARCHAR(1000) NULL,
    provider VARCHAR(40) NULL,
    external_url VARCHAR(1000) NULL,
    embed_url VARCHAR(1000) NULL,
    created_by BIGINT UNSIGNED NULL,
    approval_status ENUM('approved', 'pending', 'private', 'removed') NOT NULL DEFAULT 'approved',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_songs_creator FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_songs_status (approval_status),
    INDEX idx_songs_title (title)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS song_categories (
    assignment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    song_id BIGINT UNSIGNED NOT NULL,
    mood VARCHAR(80) NOT NULL,
    time_category ENUM('Morning', 'Afternoon', 'Evening', 'Night', 'Midnight', 'Quiet Hours') NOT NULL,
    period ENUM('Day', 'Night', 'Quiet Hours') NOT NULL,
    language VARCHAR(80) NOT NULL DEFAULT 'Hindi',
    is_featured BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_categories_song FOREIGN KEY (song_id) REFERENCES songs(song_id) ON DELETE CASCADE,
    UNIQUE KEY uq_song_assignment (song_id, mood, time_category, period),
    INDEX idx_categories_filter (time_category, period, mood, language)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS playlists (
    playlist_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(120) NOT NULL,
    description VARCHAR(500) NULL,
    cover_image_url VARCHAR(1000) NULL,
    mood VARCHAR(80) NULL,
    time_category VARCHAR(40) NULL,
    period ENUM('Day', 'Night', 'Quiet Hours') NULL,
    visibility ENUM('private', 'public') NOT NULL DEFAULT 'private',
    share_token CHAR(32) NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_playlists_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_playlists_owner (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS playlist_songs (
    playlist_id BIGINT UNSIGNED NOT NULL,
    song_id BIGINT UNSIGNED NOT NULL,
    position INT UNSIGNED NOT NULL,
    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (playlist_id, song_id),
    UNIQUE KEY uq_playlist_position (playlist_id, position),
    CONSTRAINT fk_playlist_songs_playlist FOREIGN KEY (playlist_id) REFERENCES playlists(playlist_id) ON DELETE CASCADE,
    CONSTRAINT fk_playlist_songs_song FOREIGN KEY (song_id) REFERENCES songs(song_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS favorites (
    user_id BIGINT UNSIGNED NOT NULL,
    song_id BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, song_id),
    CONSTRAINT fk_favorites_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_favorites_song FOREIGN KEY (song_id) REFERENCES songs(song_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS journal_entries (
    entry_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    mood VARCHAR(80) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_journal_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_journal_owner (user_id, updated_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS stories (
    story_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(80) NULL,
    status ENUM('pending', 'published', 'removed') NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_stories_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    INDEX idx_stories_status (status, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS comments (
    comment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    story_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    content VARCHAR(1000) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_comments_story FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
    CONSTRAINT fk_comments_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS story_reactions (
    story_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    reaction VARCHAR(20) NOT NULL DEFAULT 'heart',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (story_id, user_id, reaction),
    CONSTRAINT fk_reactions_story FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
    CONSTRAINT fk_reactions_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reports (
    report_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    reporter_id BIGINT UNSIGNED NOT NULL,
    story_id BIGINT UNSIGNED NOT NULL,
    reason VARCHAR(500) NOT NULL,
    status ENUM('open', 'resolved', 'dismissed') NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reports_user FOREIGN KEY (reporter_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_reports_story FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
    INDEX idx_reports_status (status, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mood_logs (
    log_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    mood VARCHAR(80) NOT NULL,
    note VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mood_logs_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_mood_logs_owner (user_id, created_at)
) ENGINE=InnoDB;
