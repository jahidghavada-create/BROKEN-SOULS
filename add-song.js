document.addEventListener("DOMContentLoaded", () => {
  const button = document.getElementById("fetch-metadata");
  if (!button) return;
  const form = document.getElementById("add-song-form");
  const status = document.getElementById("metadata-status");
  const fields = {
    title: document.getElementById("song-title"),
    singer: document.getElementById("singer"),
    cover_image_url: document.getElementById("cover-url")
  };

  button.addEventListener("click", async () => {
    const url = document.getElementById("music-url").value.trim();
    status.textContent = "Checking the official provider link…";
    button.disabled = true;
    try {
      const response = await fetch("/songs/fetch-metadata", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content
        },
        body: new URLSearchParams({ url })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not retrieve details.");
      Object.entries(fields).forEach(([key, field]) => {
        if (!field.value && data[key]) field.value = data[key];
      });
      const external = form.querySelector('[name="external_url"]');
      external.value = data.external_url || url;
      status.textContent = data.title
        ? `Details found from ${data.provider}. Check them and complete the remaining fields.`
        : `Link validated for ${data.provider}. Metadata isn't available here; enter the details below.`;
    } catch (error) {
      status.textContent = `${error.message} You can still enter details manually after correcting the URL.`;
    } finally {
      button.disabled = false;
    }
  });
});
