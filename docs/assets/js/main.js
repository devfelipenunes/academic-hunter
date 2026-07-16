/* ═══════════════════════════════════════════════════════
   Academic Hunter — Shared Scripts
   ═══════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", () => {
  /* ── Theme Toggle ── */
  const toggle = document.getElementById("theme-toggle");
  const html = document.documentElement;

  // Restore saved theme, or use system preference
  const saved = localStorage.getItem("ah-theme");
  if (saved) {
    html.setAttribute("data-theme", saved);
  } else {
    const prefersDark = window.matchMedia(
      "(prefers-color-scheme: dark)",
    ).matches;
    html.setAttribute("data-theme", prefersDark ? "dark" : "light");
  }

  if (toggle) {
    toggle.addEventListener("click", () => {
      const current = html.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      html.setAttribute("data-theme", next);
      localStorage.setItem("ah-theme", next);
      toggle.setAttribute(
        "aria-label",
        `Switch to ${next === "dark" ? "light" : "dark"} mode`,
      );
    });
  }

  /* ── Mobile Nav Toggle ── */
  const navToggle = document.getElementById("nav-toggle");
  const navLinks = document.getElementById("nav-links");

  if (navToggle && navLinks) {
    navToggle.addEventListener("click", () => {
      const open = navLinks.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open);
    });

    // Close nav on link click
    navLinks.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        navLinks.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  /* ── Active navigation link ── */
  const currentPath = window.location.pathname;
  document.querySelectorAll(".navbar-links a").forEach((link) => {
    const href = link.getAttribute("href");
    if (href === "/" || href === "./") return;
    if (currentPath.startsWith(href) || currentPath.endsWith(href)) {
      link.classList.add("active");
    }
  });

  /* ── Copy code blocks ── */
  document.querySelectorAll("pre").forEach((block) => {
    const btn = document.createElement("button");
    btn.className = "copy-btn";
    btn.setAttribute("aria-label", "Copy code");
    btn.textContent = "Copy";
    block.style.position = "relative";
    block.appendChild(btn);

    btn.addEventListener("click", async () => {
      const code = block.querySelector("code");
      const text = code ? code.textContent : block.textContent;
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = "Copied!";
        setTimeout(() => {
          btn.textContent = "Copy";
        }, 2000);
      } catch {
        btn.textContent = "Failed";
        setTimeout(() => {
          btn.textContent = "Copy";
        }, 2000);
      }
    });
  });
});
