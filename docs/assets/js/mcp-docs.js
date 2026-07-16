/* ═══════════════════════════════════════════════════════
   Academic Hunter — MCP Docs: Filter & Search
   ═══════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("tool-search");
  const filterBtns = document.querySelectorAll(".filter-btn");
  const toolCards = document.querySelectorAll(".tool-card");
  let activeCategory = "all";

  /* ── Category Filter ── */
  filterBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      filterBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeCategory = btn.dataset.category;
      applyFilters();
    });
  });

  /* ── Search Filter ── */
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      applyFilters();
    });
  }

  function applyFilters() {
    const query = searchInput ? searchInput.value.toLowerCase().trim() : "";
    let visibleCount = 0;

    toolCards.forEach((card) => {
      const category = card.dataset.category;
      const name = card.dataset.name ? card.dataset.name.toLowerCase() : "";
      const desc = card.dataset.description
        ? card.dataset.description.toLowerCase()
        : "";

      const catMatch = activeCategory === "all" || category === activeCategory;
      const textMatch = !query || name.includes(query) || desc.includes(query);
      const visible = catMatch && textMatch;

      card.style.display = visible ? "" : "none";
      if (visible) visibleCount++;
    });

    // Show "no results" message if nothing matched
    const noResults = document.getElementById("no-results");
    if (noResults) {
      noResults.style.display = visibleCount === 0 ? "block" : "none";
    }
  }
});
