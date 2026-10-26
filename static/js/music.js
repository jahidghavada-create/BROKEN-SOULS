(() => {
  const clock = document.getElementById("local-clock");
  const zone = clock?.dataset.timezone || "Asia/Kolkata";

  // Only accept official embed URLs from providers this website supports.
  const safeEmbedUrl = (value) => {
    try {
      const url = new URL(value);
      const youtubeHost = ["www.youtube-nocookie.com", "youtube-nocookie.com", "www.youtube.com", "youtube.com"].includes(url.hostname);
      const spotifyHost = ["open.spotify.com", "www.open.spotify.com"].includes(url.hostname);
      if (url.protocol !== "https:") return null;
      if (youtubeHost && url.pathname.startsWith("/embed/")) return url.href;
      if (spotifyHost && url.pathname.startsWith("/embed/")) return url.href;
    } catch (_) {}
    return null;
  };

  document.querySelectorAll("[data-inline-play]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".song-card, .song-detail");
      const playerBox = card?.querySelector("[data-inline-player]");
      if (!playerBox) return;

      const alreadyOpen = !playerBox.hidden;
      document.querySelectorAll("[data-inline-player]").forEach((box) => {
        box.replaceChildren();
        box.hidden = true;
      });
      document.querySelectorAll("[data-inline-play]").forEach((item) => {
        item.setAttribute("aria-expanded", "false");
        item.textContent = "▶ Play here";
      });
      if (alreadyOpen) return;

      const embedUrl = safeEmbedUrl(button.dataset.embedUrl);
      if (!embedUrl) {
        playerBox.textContent = "This player link is not supported. Please ask the site admin to update it.";
        playerBox.hidden = false;
        return;
      }
      const frame = document.createElement("iframe");
      frame.src = embedUrl;
      frame.title = "Play " + (button.dataset.songTitle || "song") + " on this page";
      frame.loading = "lazy";
      frame.allow = "autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture";
      frame.referrerPolicy = "strict-origin-when-cross-origin";
      frame.allowFullscreen = true;
      playerBox.replaceChildren(frame);
      playerBox.hidden = false;
      button.setAttribute("aria-expanded", "true");
      button.textContent = "■ Stop player";
    });
  });

  if (!clock) return;
  const categoryAt = (hour, minute) => {
    const minutes = hour * 60 + minute;
    if (minutes >= 360 && minutes < 720) return "Morning";
    if (minutes >= 720 && minutes < 1020) return "Afternoon";
    if (minutes >= 1020 && minutes < 1260) return "Evening";
    if (minutes >= 1260) return "Night";
    if (minutes < 240) return "Midnight";
    return "Quiet Hours";
  };
  const introductions = {
    Morning: "soft sadness, memories, and a little peace.",
    Afternoon: "for the moments of regret and remembering.",
    Evening: "nostalgia, old memories, and emotional love.",
    Night: "for loneliness and the feelings that deepen after dark.",
    Midnight: "for deep thoughts and memories that stay.",
    "Quiet Hours": "a quiet pause between night and morning. Choose what feels gentle."
  };
  const update = () => {
    try {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23"
      }).formatToParts(new Date());
      const hour = Number(parts.find((part) => part.type === "hour").value);
      const minute = Number(parts.find((part) => part.type === "minute").value);
      const current = categoryAt(hour, minute);
      const timeText = clock.querySelector("span");
      if (timeText) timeText.textContent = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
      clock.dataset.active = current;
      const intro = document.getElementById("music-intro");
      if (intro) {
        intro.dataset.category = current;
        intro.textContent = `${current} hours: ${introductions[current]}`;
      }
      document.querySelectorAll(".time-tab").forEach((tab) => {
        const active = tab.querySelector("span")?.textContent === current;
        tab.classList.toggle("is-current", active);
        tab.setAttribute("aria-selected", String(active));
      });
    } catch (error) {
      console.error("Unable to update Music Room clock for timezone:", error);
    }
  };
  update();
  window.setInterval(update, 30000);
})();