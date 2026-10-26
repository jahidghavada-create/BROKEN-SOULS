document.addEventListener("DOMContentLoaded", () => {
  const list = document.getElementById("ordered-songs");
  const form = document.getElementById("reorder-form");
  const idField = document.getElementById("song-ids");
  if (!list || !form || !idField) return;

  list.addEventListener("click", (event) => {
    const button = event.target.closest(".move-song");
    if (!button) return;
    const row = button.closest("li");
    const sibling = button.dataset.direction === "-1" ? row.previousElementSibling : row.nextElementSibling;
    if (!sibling) return;
    if (button.dataset.direction === "-1") list.insertBefore(row, sibling);
    else list.insertBefore(sibling, row);
    [...list.children].forEach((item, index) => {
      item.querySelector(".position").textContent = String(index + 1);
    });
    idField.value = [...list.children].map((item) => item.dataset.songId).join(",");
  });

  form.addEventListener("submit", () => {
    idField.value = [...list.children].map((item) => item.dataset.songId).join(",");
  });
});
