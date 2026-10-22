document.addEventListener("DOMContentLoaded", function () {
    const fileInput = document.getElementById("fileInput");
    const dropZone = document.getElementById("dropZone");
    const selectedFileContainer = document.getElementById("selectedFileContainer");
    const selectedFileName = document.getElementById("selectedFileName");
    const selectedFileSize = document.getElementById("selectedFileSize");
    const removeFileBtn = document.getElementById("removeFileBtn");
    const startFactCheckBtn = document.getElementById("startFactCheckBtn");
    const progressWrapper = document.getElementById("progressWrapper");
    const progressBar = document.getElementById("progressBar");
    const progressStatus = document.getElementById("progressStatus");
    const progressPercent = document.getElementById("progressPercent");
    const errorAlert = document.getElementById("errorAlert");
    const errorMessage = document.getElementById("errorMessage");
    const resultsSection = document.getElementById("resultsSection");
    const claimsContainer = document.getElementById("claimsContainer");

    const statTotal = document.getElementById("statTotal");
    const statSupported = document.getElementById("statSupported");
    const statContradicted = document.getElementById("statContradicted");
    const statUnverifiable = document.getElementById("statUnverifiable");

    let currentFile = null;
    let counts = { total: 0, Supported: 0, Contradicted: 0, Unverifiable: 0 };

    function formatBytes(bytes) {
        if (bytes === 0) return "0 Bytes";
        const k = 1024;
        const sizes = ["Bytes", "KB", "MB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorAlert.classList.remove("d-none");
    }

    function clearError() {
        errorAlert.classList.add("d-none");
        errorMessage.textContent = "";
    }

    function setSelectedFile(file) {
        clearError();
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            showError(`File '${file.name}' is not a PDF. Please select a valid PDF document.`);
            return;
        }
        if (file.size > 32 * 1024 * 1024) {
            showError(`File '${file.name}' exceeds the 32 MB upload limit.`);
            return;
        }
        currentFile = file;
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = formatBytes(file.size);
        selectedFileContainer.classList.remove("d-none");
        startFactCheckBtn.disabled = false;
    }

    function clearSelectedFile() {
        currentFile = null;
        fileInput.value = "";
        selectedFileContainer.classList.add("d-none");
        startFactCheckBtn.disabled = true;
    }

    // Drag and Drop
    dropZone.addEventListener("click", () => fileInput.click());
    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            setSelectedFile(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
            setSelectedFile(e.target.files[0]);
        }
    });

    removeFileBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        clearSelectedFile();
    });

    // Run AI Fact Check
    startFactCheckBtn.addEventListener("click", async function () {
        if (!currentFile) {
            showError("Please select a PDF document first.");
            return;
        }

        clearError();
        startFactCheckBtn.disabled = true;
        progressWrapper.classList.remove("d-none");
        resultsSection.classList.add("d-none");
        claimsContainer.innerHTML = "";
        counts = { total: 0, Supported: 0, Contradicted: 0, Unverifiable: 0 };
        updateStats();

        // Step 1: Extract claims from PDF
        progressBar.style.width = "20%";
        progressPercent.textContent = "20%";
        progressStatus.textContent = "Reading PDF and extracting verifiable factual claims...";

        const formData = new FormData();
        formData.append("document", currentFile);

        let claims = [];
        try {
            const extractResp = await fetch("/api/factcheck/extract", {
                method: "POST",
                body: formData,
            });

            const extractData = await extractResp.json();
            if (!extractResp.ok) {
                throw new Error(extractData.error || "Failed to extract factual claims from document.");
            }

            claims = extractData.claims || [];
            if (claims.length === 0) {
                throw new Error("No verifiable factual claims could be extracted from this document.");
            }

        } catch (err) {
            progressWrapper.classList.add("d-none");
            startFactCheckBtn.disabled = false;
            showError(err.message || "An unexpected error occurred during claim extraction.");
            return;
        }

        // Show results section
        resultsSection.classList.remove("d-none");
        const totalClaims = claims.length;

        // Step 2: Verify claims in sequence (client-driven architecture)
        for (let i = 0; i < totalClaims; i++) {
            const claim = claims[i];
            const currentIdx = i + 1;
            const progressPct = Math.round(20 + ((currentIdx / totalClaims) * 80));

            progressBar.style.width = progressPct + "%";
            progressPercent.textContent = progressPct + "%";
            progressStatus.textContent = `Fact-checking claim ${currentIdx} of ${totalClaims}...`;

            try {
                const verifyResp = await fetch("/api/factcheck/verify", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(claim),
                });

                const result = await verifyResp.json();
                if (!verifyResp.ok) {
                    throw new Error(result.error || "Claim verification error.");
                }

                renderClaimCard(result);
                counts.total++;
                if (counts[result.verdict] !== undefined) {
                    counts[result.verdict]++;
                } else {
                    counts.Unverifiable++;
                }
                updateStats();

            } catch (err) {
                // Render claim as unverifiable on error
                renderClaimCard({
                    id: claim.id,
                    claim: claim.claim,
                    page_number: claim.page_number,
                    quote: claim.quote,
                    verdict: "Unverifiable",
                    reason: `Verification notice: ${err.message}`,
                    sources: [],
                });
                counts.total++;
                counts.Unverifiable++;
                updateStats();
            }
        }

        // Complete
        progressBar.style.width = "100%";
        progressPercent.textContent = "100%";
        progressStatus.textContent = "Fact checking complete!";
        startFactCheckBtn.disabled = false;
    });

    function updateStats() {
        statTotal.textContent = counts.total;
        statSupported.textContent = counts.Supported;
        statContradicted.textContent = counts.Contradicted;
        statUnverifiable.textContent = counts.Unverifiable;
    }

    // Safe DOM construction using textContent to prevent XSS
    function renderClaimCard(item) {
        const card = document.createElement("div");
        card.className = `card border-0 shadow-sm rounded-4 finding-card status-${item.verdict.toLowerCase()}`;
        card.setAttribute("data-verdict", item.verdict);

        // Header
        const header = document.createElement("div");
        header.className = "card-header bg-white py-3 border-bottom d-flex justify-content-between align-items-center";

        const badgeWrapper = document.createElement("div");
        badgeWrapper.className = "d-flex align-items-center gap-2";

        const verdictBadge = document.createElement("span");
        if (item.verdict === "Supported") {
            verdictBadge.className = "badge bg-success px-3 py-2 rounded-pill";
            verdictBadge.textContent = " Supported";
        } else if (item.verdict === "Contradicted") {
            verdictBadge.className = "badge bg-danger px-3 py-2 rounded-pill";
            verdictBadge.textContent = " Contradicted";
        } else {
            verdictBadge.className = "badge bg-secondary px-3 py-2 rounded-pill";
            verdictBadge.textContent = " Unverifiable";
        }
        badgeWrapper.appendChild(verdictBadge);

        const pageBadge = document.createElement("span");
        pageBadge.className = "badge bg-light text-muted border";
        pageBadge.textContent = `Page ${item.page_number}`;
        badgeWrapper.appendChild(pageBadge);

        header.appendChild(badgeWrapper);
        card.appendChild(header);

        // Body
        const body = document.createElement("div");
        body.className = "card-body p-4";

        // Claim
        const claimTitle = document.createElement("h6");
        claimTitle.className = "fw-bold text-dark mb-2";
        claimTitle.textContent = item.claim;
        body.appendChild(claimTitle);

        // Source quote from PDF
        const quoteBox = document.createElement("div");
        quoteBox.className = "p-2 px-3 rounded bg-light border-start border-3 border-primary mb-3 small text-muted";
        const quoteLabel = document.createElement("strong");
        quoteLabel.className = "d-block text-dark small mb-1";
        quoteLabel.textContent = "Supporting Quote from PDF:";
        quoteBox.appendChild(quoteLabel);
        const quoteText = document.createElement("span");
        quoteText.className = "font-monospace";
        quoteText.textContent = `"${item.quote}"`;
        quoteBox.appendChild(quoteText);
        body.appendChild(quoteBox);

        // Reason
        const reasonBox = document.createElement("div");
        reasonBox.className = "mb-3 small text-secondary";
        const reasonLabel = document.createElement("strong");
        reasonLabel.className = "text-dark me-1";
        reasonLabel.textContent = "Reason:";
        reasonBox.appendChild(reasonLabel);
        const reasonSpan = document.createElement("span");
        reasonSpan.textContent = item.reason;
        reasonBox.appendChild(reasonSpan);
        body.appendChild(reasonBox);

        // Verified Sources
        if (item.sources && item.sources.length > 0) {
            const sourcesDiv = document.createElement("div");
            sourcesDiv.className = "pt-2 border-top";
            const sourcesLabel = document.createElement("small");
            sourcesLabel.className = "text-muted fw-semibold d-block mb-2";
            sourcesLabel.textContent = "Evidence Sources:";
            sourcesDiv.appendChild(sourcesLabel);

            const sourcesList = document.createElement("div");
            sourcesList.className = "d-flex flex-column gap-2";

            item.sources.forEach(src => {
                const srcLink = document.createElement("a");
                srcLink.className = "d-flex align-items-start gap-2 p-2 rounded bg-light border text-decoration-none text-dark small";
                srcLink.setAttribute("href", src.url);
                srcLink.setAttribute("target", "_blank");
                srcLink.setAttribute("rel", "noopener noreferrer");

                const icon = document.createElement("i");
                if (src.source_type === "google_factcheck") {
                    icon.className = "fa-solid fa-square-check text-primary mt-1";
                } else if (src.source_type === "wikipedia") {
                    icon.className = "fa-brands fa-wikipedia-w text-secondary mt-1";
                } else {
                    icon.className = "fa-solid fa-arrow-up-right-from-square text-info mt-1";
                }
                srcLink.appendChild(icon);

                const srcDetails = document.createElement("div");
                const srcTitle = document.createElement("strong");
                srcTitle.className = "d-block text-primary";
                srcTitle.textContent = src.title;
                srcDetails.appendChild(srcTitle);

                const srcSnippet = document.createElement("span");
                srcSnippet.className = "text-muted small";
                srcSnippet.textContent = src.snippet;
                srcDetails.appendChild(srcSnippet);

                srcLink.appendChild(srcDetails);
                sourcesList.appendChild(srcLink);
            });

            sourcesDiv.appendChild(sourcesList);
            body.appendChild(sourcesDiv);
        }

        card.appendChild(body);
        claimsContainer.appendChild(card);
    }

    // Filter Buttons
    const filterButtons = document.querySelectorAll(".filter-btn");
    filterButtons.forEach(btn => {
        btn.addEventListener("click", function () {
            filterButtons.forEach(b => b.classList.remove("active"));
            this.classList.add("active");
            const filter = this.getAttribute("data-filter");

            const cards = claimsContainer.querySelectorAll(".finding-card");
            cards.forEach(card => {
                const verdict = card.getAttribute("data-verdict");
                if (filter === "all" || verdict === filter) {
                    card.classList.remove("d-none");
                } else {
                    card.classList.add("d-none");
                }
            });
        });
    });
});
