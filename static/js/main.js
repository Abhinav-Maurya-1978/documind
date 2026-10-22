document.addEventListener("DOMContentLoaded", function () {
    const fileInput = document.getElementById("fileInput");
    const dropZone = document.getElementById("dropZone");
    const fileList = document.getElementById("fileList");
    const fileCount = document.getElementById("fileCount");
    const selectedFilesContainer = document.getElementById("selectedFilesContainer");
    const startAuditBtn = document.getElementById("startAuditBtn");
    const demoSampleBtn = document.getElementById("demoSampleBtn");
    const progressWrapper = document.getElementById("progressWrapper");
    const progressBar = document.getElementById("progressBar");
    const progressStatus = document.getElementById("progressStatus");
    const progressPercent = document.getElementById("progressPercent");
    const errorAlert = document.getElementById("errorAlert");
    const errorMessage = document.getElementById("errorMessage");

    let selectedFiles = [];

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

    function updateFileList() {
        fileList.innerHTML = "";
        selectedFiles.forEach((file, index) => {
            const li = document.createElement("li");
            li.className = "list-group-item d-flex justify-content-between align-items-center py-2";
            li.innerHTML = `
                <div class="d-flex align-items-center gap-2 text-truncate me-2">
                    <i class="fa-solid fa-file-pdf text-danger fs-5"></i>
                    <div>
                        <strong class="d-block text-truncate small" style="max-width: 320px;">${file.name}</strong>
                        <span class="text-muted small">${formatBytes(file.size)}</span>
                    </div>
                </div>
                <button type="button" class="btn btn-sm btn-link text-danger p-0" data-index="${index}">
                    <i class="fa-solid fa-xmark fs-5"></i>
                </button>
            `;
            li.querySelector("button").addEventListener("click", function (e) {
                e.stopPropagation();
                removeFile(index);
            });
            fileList.appendChild(li);
        });

        fileCount.textContent = selectedFiles.length;
        if (selectedFiles.length > 0) {
            selectedFilesContainer.classList.remove("d-none");
        } else {
            selectedFilesContainer.classList.add("d-none");
        }

        startAuditBtn.disabled = selectedFiles.length < 2;
    }

    function addFiles(files) {
        clearError();
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            if (!file.name.toLowerCase().endsWith(".pdf")) {
                showError(`File '${file.name}' is not a PDF.`);
                continue;
            }
            if (file.size > 32 * 1024 * 1024) {
                showError(`File '${file.name}' exceeds the 32 MB limit.`);
                continue;
            }
            if (!selectedFiles.some(f => f.name === file.name && f.size === file.size)) {
                selectedFiles.push(file);
            }
        }
        updateFileList();
    }

    function removeFile(index) {
        selectedFiles.splice(index, 1);
        updateFileList();
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
        if (e.dataTransfer.files) {
            addFiles(e.dataTransfer.files);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files) {
            addFiles(e.target.files);
        }
    });

    // Run Contradiction Audit Submission
    startAuditBtn.addEventListener("click", async function () {
        if (selectedFiles.length < 2) {
            showError("Please upload at least 2 PDF documents to run a cross-document audit.");
            return;
        }

        clearError();
        startAuditBtn.disabled = true;
        progressWrapper.classList.remove("d-none");

        const stages = [
            { pct: 15, msg: "Uploading documents securely..." },
            { pct: 35, msg: "Extracting page content & running OCR fallback..." },
            { pct: 60, msg: "Normalizing structured claims (dates, amounts, terms)..." },
            { pct: 85, msg: "Cross-matching claims and grounding verifiable evidence..." },
            { pct: 95, msg: "Compiling audit summary report..." }
        ];

        let stageIdx = 0;
        const timer = setInterval(() => {
            if (stageIdx < stages.length) {
                progressBar.style.width = stages[stageIdx].pct + "%";
                progressPercent.textContent = stages[stageIdx].pct + "%";
                progressStatus.textContent = stages[stageIdx].msg;
                stageIdx++;
            }
        }, 600);

        const formData = new FormData();
        selectedFiles.forEach(file => {
            formData.append("documents", file);
        });

        try {
            const resp = await fetch("/api/audit", {
                method: "POST",
                body: formData
            });

            clearInterval(timer);

            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.error || "Audit processing failed.");
            }

            progressBar.style.width = "100%";
            progressPercent.textContent = "100%";
            progressStatus.textContent = "Audit complete! Redirecting to report...";

            setTimeout(() => {
                window.location.href = data.redirect_url;
            }, 500);

        } catch (err) {
            clearInterval(timer);
            progressWrapper.classList.add("d-none");
            startAuditBtn.disabled = false;
            showError(err.message || "An unexpected error occurred during processing.");
        }
    });

    // Demo Sample Loader (Generates synthetic test documents on-the-fly)
    if (demoSampleBtn) {
        demoSampleBtn.addEventListener("click", async function () {
            demoSampleBtn.disabled = true;
            demoSampleBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Loading Synthetic Test Pair...';
            clearError();

            try {
                // Fetch pre-generated test documents from scripts/api endpoint
                const resp = await fetch("/api/demo-samples");
                if (!resp.ok) {
                    throw new Error("Could not load pre-generated demo samples.");
                }
                const sampleBlobData = await resp.json();

                // Convert base64 samples to File objects
                function b64toBlob(b64Data, contentType) {
                    const byteCharacters = atob(b64Data);
                    const byteArrays = [];
                    for (let offset = 0; offset < byteCharacters.length; offset += 512) {
                        const slice = byteCharacters.slice(offset, offset + 512);
                        const byteNumbers = new Array(slice.length);
                        for (let i = 0; i < slice.length; i++) {
                            byteNumbers[i] = slice.charCodeAt(i);
                        }
                        const byteArray = new Uint8Array(byteNumbers);
                        byteArrays.push(byteArray);
                    }
                    return new Blob(byteArrays, { type: contentType });
                }

                selectedFiles = [];
                sampleBlobData.samples.forEach(s => {
                    const blob = b64toBlob(s.data, "application/pdf");
                    const file = new File([blob], s.filename, { type: "application/pdf" });
                    selectedFiles.push(file);
                });

                updateFileList();
                demoSampleBtn.innerHTML = '<i class="fa-solid fa-check text-success me-2"></i>Loaded Demo Pair!';
                setTimeout(() => {
                    demoSampleBtn.disabled = false;
                    demoSampleBtn.innerHTML = '<i class="fa-solid fa-vial me-2"></i> Load Demo Test Pair';
                }, 2000);

            } catch (err) {
                demoSampleBtn.disabled = false;
                demoSampleBtn.innerHTML = '<i class="fa-solid fa-vial me-2"></i> Load Demo Test Pair';
                showError("Error loading sample documents: " + err.message);
            }
        });
    }
});
