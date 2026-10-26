(() => {
  const clock = document.getElementById("local-clock");
  if (!clock) return;

  const zone = clock.dataset.timezone || "Asia/Kolkata";
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
      clock.querySelector("span").textContent = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
      clock.dataset.active = current;
      const intro = document.getElementById("music-intro");
      if (intro) {
        intro.dataset.category = current;
        intro.textContent = `${current} hours: ${introductions[current]}`;
      }
      document.querySelectorAll(".time-tab").forEach((tab) => {
        const active = tab.querySelector("span").textContent === current;
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
