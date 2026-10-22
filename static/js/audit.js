document.addEventListener("DOMContentLoaded", function () {
    const filterButtons = document.querySelectorAll(".filter-btn");
    const searchInput = document.getElementById("searchInput");
    const cards = document.querySelectorAll(".finding-card");
    const exportBtn = document.getElementById("exportJsonBtn");

    let currentFilter = "all";
    let currentSearch = "";

    function applyFilters() {
        cards.forEach(card => {
            const status = card.getAttribute("data-status");
            const cardText = card.textContent.toLowerCase();

            const matchesFilter = (currentFilter === "all") || (status === currentFilter);
            const matchesSearch = (!currentSearch) || cardText.includes(currentSearch);

            if (matchesFilter && matchesSearch) {
                card.classList.remove("d-none");
            } else {
                card.classList.add("d-none");
            }
        });
    }

    filterButtons.forEach(btn => {
        btn.addEventListener("click", function () {
            filterButtons.forEach(b => b.classList.remove("active"));
            this.classList.add("active");
            currentFilter = this.getAttribute("data-filter");
            applyFilters();
        });
    });

    if (searchInput) {
        searchInput.addEventListener("input", function (e) {
            currentSearch = e.target.value.toLowerCase().trim();
            applyFilters();
        });
    }

    if (exportBtn && window.DOCUMIND_AUDIT) {
        exportBtn.addEventListener("click", function () {
            const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(window.DOCUMIND_AUDIT, null, 2));
            const downloadAnchor = document.createElement("a");
            downloadAnchor.setAttribute("href", dataStr);
            downloadAnchor.setAttribute("download", `documind-audit-${window.DOCUMIND_AUDIT.session_id}.json`);
            document.body.appendChild(downloadAnchor);
            downloadAnchor.click();
            downloadAnchor.remove();
        });
    }
});
