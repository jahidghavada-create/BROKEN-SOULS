document.addEventListener("DOMContentLoaded", () => {
  const readPreference = (key) => window.localStorage.getItem(key) === "1";
  const backgroundButton = document.getElementById("background-toggle");
  if (backgroundButton) {
    document.body.classList.toggle("plain-background", readPreference("plain-background"));
    backgroundButton.addEventListener("click", () => {
      const plain = document.body.classList.toggle("plain-background");
      window.localStorage.setItem("plain-background", plain ? "1" : "0");
    });
  }
  const motionButton = document.getElementById("motion-toggle");
  if (motionButton) {
    document.documentElement.classList.toggle("reduce-motion", readPreference("reduce-motion"));
    motionButton.addEventListener("click", () => {
      const reduced = document.documentElement.classList.toggle("reduce-motion");
      window.localStorage.setItem("reduce-motion", reduced ? "1" : "0");
    });
  }

  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".main-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      nav.classList.toggle("nav-open", !open);
    });
  }

  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reducedMotion && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    document.querySelectorAll(".reveal, .feature-card, .song-card").forEach((item) => observer.observe(item));
  } else {
    document.querySelectorAll(".reveal, .feature-card, .song-card").forEach((item) => item.classList.add("is-visible"));
  }
});
