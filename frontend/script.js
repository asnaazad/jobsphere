/* ==========================================
   JOBSPHERE FRONTEND
   MICROSERVICES + JWT + RBAC INTEGRATION
========================================== */

const JOB_SERVICE = "/api/jobs";
const AUTH_SERVICE = "/api/auth";
const APPLICATION_SERVICE = "/api/applications";

let authMode = "register";
let currentUser = null;
let authToken = null;
let allJobs = [];
let userApplications = [];

const APPLICATION_STATUSES = [
    "Applied",
    "Under Review",
    "Shortlisted",
    "Interview Scheduled",
    "Rejected",
    "Hired"
];

/* ==========================================
   SESSION INITIALIZATION
========================================== */

function restoreSession() {
    const savedToken = localStorage.getItem("jobsphere_token");
    const savedUser = localStorage.getItem("jobsphere_user");

    if (savedToken && savedUser) {
        try {
            authToken = savedToken;
            currentUser = JSON.parse(savedUser);
        } catch (e) {
            clearSession();
        }
    }
    updateUIForAuthState();
}

function saveSession(token, user) {
    authToken = token;
    currentUser = user;
    localStorage.setItem("jobsphere_token", token);
    localStorage.setItem("jobsphere_user", JSON.stringify(user));
    updateUIForAuthState();
}

function clearSession() {
    authToken = null;
    currentUser = null;
    userApplications = [];
    localStorage.removeItem("jobsphere_token");
    localStorage.removeItem("jobsphere_user");
    updateUIForAuthState();
    displayJobs(allJobs);
}

function authHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (authToken) {
        headers["Authorization"] = `Bearer ${authToken}`;
    }
    return headers;
}

/* ==========================================
   AUTH UI & SUBMISSION
========================================== */

function switchAuthMode(mode) {
    authMode = mode;
    const isRegister = mode === "register";

    document.getElementById("tabRegister").classList.toggle("active", isRegister);
    document.getElementById("tabLogin").classList.toggle("active", !isRegister);

    const nameField = document.getElementById("authName");
    const roleField = document.getElementById("authRole");
    const submitBtn = document.getElementById("authSubmitBtn");

    nameField.style.display = isRegister ? "block" : "none";
    nameField.required = isRegister;
    roleField.style.display = isRegister ? "block" : "none";

    submitBtn.textContent = isRegister ? "Create Account →" : "Sign In →";
    document.getElementById("authMessage").textContent = "";
}

async function handleAuthSubmit(event) {
    event.preventDefault();

    const name = document.getElementById("authName").value.trim();
    const role = document.getElementById("authRole").value;
    const email = document.getElementById("authEmail").value.trim();
    const password = document.getElementById("authPassword").value;
    const message = document.getElementById("authMessage");

    const endpoint = authMode === "register" ? "/register" : "/login";
    const payload = authMode === "register"
        ? { name, email, password, role }
        : { email, password };

    try {
        message.textContent = "Authenticating...";
        message.style.color = "#64748b";

        const response = await fetch(`${AUTH_SERVICE}${endpoint}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Authentication failed.");
        }

        saveSession(data.token, data.user);
        document.getElementById("authForm").reset();
        message.textContent = "";

        showToast(`Welcome, ${data.user.name}!`, `Signed in as ${data.user.role}.`, "success");
        await refreshWorkspace();
        await loadJobs();
    } catch (error) {
        message.textContent = error.message;
        message.style.color = "#dc2626";
    }
}

function updateUIForAuthState() {
    const navActions = document.getElementById("navActions");
    const navWorkspaceLink = document.getElementById("navWorkspaceLink");
    const authSection = document.getElementById("authSection");
    const workspaceSection = document.getElementById("workspace");
    const recruiterPostBox = document.getElementById("recruiterPostBox");

    if (currentUser && authToken) {
        const isRecruiter = currentUser.role === "recruiter";

        navActions.innerHTML = `
            <span class="user-pill">
                ${escapeHtml(currentUser.name)} (${escapeHtml(currentUser.role)})
            </span>
            <button class="outline-btn" onclick="logoutUser()">Logout</button>
        `;

        navWorkspaceLink.classList.remove("hidden");
        authSection.classList.add("hidden");
        workspaceSection.classList.remove("hidden");

        document.getElementById("workspaceRoleLabel").textContent =
            isRecruiter ? "RECRUITER CONSOLE" : "CANDIDATE DASHBOARD";
        document.getElementById("workspaceTitle").textContent =
            `Welcome back, ${currentUser.name}`;
        document.getElementById("workspaceSubtitle").textContent = isRecruiter
            ? "Publish job openings and review incoming candidate applications."
            : "Track the real-time status of your submitted job applications.";
        document.getElementById("applicationsHeading").textContent = isRecruiter
            ? "Candidate Applications Pipeline"
            : "My Submitted Applications";

        recruiterPostBox.classList.toggle("hidden", !isRecruiter);
    } else {
        navActions.innerHTML = `
            <button class="nav-btn" onclick="scrollToAuth()">Sign In / Register</button>
        `;
        navWorkspaceLink.classList.add("hidden");
        authSection.classList.remove("hidden");
        workspaceSection.classList.add("hidden");
    }
}

function logoutUser() {
    clearSession();
    showToast("Signed out", "Your session has been cleared.", "success");
}

/* ==========================================
   JOBS: LOAD, SEARCH & DISPLAY
========================================== */

async function loadJobs(queryString = "") {
    const container = document.getElementById("jobsContainer");
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">⏳</div>
            <h3>Loading opportunities...</h3>
            <p>Querying JobSphere Job Service.</p>
        </div>
    `;

    try {
        const response = await fetch(`${JOB_SERVICE}/jobs${queryString}`);
        if (!response.ok) throw new Error("Job Service returned an error.");

        const data = await response.json();
        allJobs = Array.isArray(data) ? data : data.jobs || [];

        const statCount = document.getElementById("statJobCount");
        if (statCount && !queryString) {
            statCount.textContent = allJobs.length;
        }

        displayJobs(allJobs);
    } catch (error) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <h3>Unable to load jobs</h3>
                <p>${escapeHtml(error.message)}</p>
                <br>
                <button class="primary-btn" onclick="loadJobs()">Try Again</button>
            </div>
        `;
    }
}

function searchJobs() {
    const search = document.getElementById("searchInput").value.trim();
    const location = document.getElementById("locationFilter").value;
    const type = document.getElementById("typeFilter").value;

    const params = new URLSearchParams();
    if (search) params.append("search", search);
    if (location) params.append("location", location);
    if (type) params.append("type", type);

    const qs = params.toString() ? `?${params.toString()}` : "";
    loadJobs(qs);

    document.getElementById("jobs").scrollIntoView({ behavior: "smooth" });
}

function resetAndLoadJobs() {
    document.getElementById("searchInput").value = "";
    document.getElementById("locationFilter").value = "";
    document.getElementById("typeFilter").value = "";
    loadJobs();
}

function displayJobs(jobs) {
    const container = document.getElementById("jobsContainer");

    if (!jobs || jobs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🔍</div>
                <h3>No matching jobs found</h3>
                <p>Try clearing filters or refreshing the job board.</p>
            </div>
        `;
        return;
    }

    const appliedJobIds = new Set(userApplications.map(app => Number(app.job_id)));
    const isRecruiter = currentUser && currentUser.role === "recruiter";

    container.innerHTML = "";

    jobs.forEach(job => {
        const card = document.createElement("article");
        card.className = "job-card";

        const jobId = Number(job.id);
        const company = escapeHtml(job.company || "Company");
        const title = escapeHtml(job.title || "Job Opportunity");
        const location = escapeHtml(job.location || "Remote");
        const type = escapeHtml(job.type || "Full-Time");
        const companyLetter = escapeHtml((job.company || "J").charAt(0).toUpperCase());
        const alreadyApplied = appliedJobIds.has(jobId);

        let actionButtonHtml = "";
        if (isRecruiter) {
            actionButtonHtml = `
                <button class="delete-btn" onclick="deleteJob(${jobId})">
                    Delete Listing
                </button>
            `;
        } else if (alreadyApplied) {
            actionButtonHtml = `
                <button class="apply-btn applied" disabled>
                    ✓ Applied
                </button>
            `;
        } else {
            actionButtonHtml = `
                <button class="apply-btn" onclick="applyForJob(${jobId})">
                    Apply Now →
                </button>
            `;
        }

        card.innerHTML = `
            <div class="job-card-top">
                <div class="company-icon">${companyLetter}</div>
                <span class="job-type">${type}</span>
            </div>
            <h3>${title}</h3>
            <div class="company-name">${company}</div>
            <div class="job-details">
                <span>📍 ${location}</span>
                <span>💼 ${type}</span>
            </div>
            ${actionButtonHtml}
        `;

        container.appendChild(card);
    });
}

/* ==========================================
   RECRUITER: CREATE & DELETE JOBS
========================================== */

async function handleCreateJob(event) {
    event.preventDefault();

    const title = document.getElementById("jobTitle").value.trim();
    const company = document.getElementById("jobCompany").value.trim();
    const location = document.getElementById("jobLocation").value.trim();
    const type = document.getElementById("jobType").value;

    try {
        const response = await fetch(`${JOB_SERVICE}/jobs`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ title, company, location, type })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Failed to create job.");

        document.getElementById("createJobForm").reset();
        showToast("Job Published", `${title} at ${company} is now live.`, "success");
        await loadJobs();
    } catch (error) {
        showToast("Error", error.message, "error");
    }
}

async function deleteJob(jobId) {
    try {
        const response = await fetch(`${JOB_SERVICE}/jobs/${jobId}`, {
            method: "DELETE",
            headers: authHeaders()
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Failed to delete job.");

        showToast("Job Removed", "The listing has been deleted.", "success");
        await loadJobs();
        await refreshWorkspace();
    } catch (error) {
        showToast("Error", error.message, "error");
    }
}

/* ==========================================
   APPLICATIONS: APPLY, LOAD & UPDATE STATUS
========================================== */

async function applyForJob(jobId) {
    if (!currentUser || !authToken) {
        showToast("Sign In Required", "Create a candidate account to apply.", "error");
        scrollToAuth();
        return;
    }

    try {
        const response = await fetch(`${APPLICATION_SERVICE}/applications`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ job_id: Number(jobId) })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Application failed.");

        showToast("✓ Application Submitted", "Recorded in your dashboard.", "success");
        await refreshWorkspace();
        displayJobs(allJobs);
    } catch (error) {
        showToast("Application Failed", error.message, "error");
    }
}

async function refreshWorkspace() {
    if (!currentUser || !authToken) return;

    const container = document.getElementById("applicationsContainer");
    try {
        const response = await fetch(`${APPLICATION_SERVICE}/applications`, {
            headers: authHeaders()
        });

        if (response.status === 401) {
            clearSession();
            return;
        }

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not fetch applications.");

        userApplications = Array.isArray(data) ? data : [];
        renderApplications(userApplications);
        displayJobs(allJobs);
    } catch (error) {
        container.innerHTML = `<p class="muted-text">${escapeHtml(error.message)}</p>`;
    }
}

function renderApplications(applications) {
    const container = document.getElementById("applicationsContainer");

    if (!applications.length) {
        container.innerHTML = `
            <div class="empty-inline">
                No applications found yet.
            </div>
        `;
        return;
    }

    const isRecruiter = currentUser.role === "recruiter";

    container.innerHTML = applications.map(app => {
        const statusBadge = `<span class="status-badge status-${app.status.toLowerCase().replace(/\s+/g, "-")}">${escapeHtml(app.status)}</span>`;

        const recruiterControls = isRecruiter ? `
            <select class="status-select" onchange="updateApplicationStatus(${Number(app.id)}, this.value)">
                ${APPLICATION_STATUSES.map(st => `
                    <option value="${st}" ${st === app.status ? "selected" : ""}>${st}</option>
                `).join("")}
            </select>
        ` : "";

        return `
            <div class="application-row">
                <div>
                    <strong>${escapeHtml(app.job_title)}</strong>
                    <div class="app-meta">
                        ${escapeHtml(app.company)} • 📍 ${escapeHtml(app.location)}
                        ${isRecruiter ? `• 👤 ${escapeHtml(app.candidate_name)} (${escapeHtml(app.candidate_email)})` : ""}
                    </div>
                </div>
                <div class="app-actions">
                    ${statusBadge}
                    ${recruiterControls}
                </div>
            </div>
        `;
    }).join("");
}

async function updateApplicationStatus(applicationId, newStatus) {
    try {
        const response = await fetch(`${APPLICATION_SERVICE}/applications/${applicationId}`, {
            method: "PUT",
            headers: authHeaders(),
            body: JSON.stringify({ status: newStatus })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Failed to update status.");

        showToast("Status Updated", `Application marked as "${newStatus}".`, "success");
        await refreshWorkspace();
    } catch (error) {
        showToast("Update Failed", error.message, "error");
    }
}

/* ==========================================
   HELPERS & EVENT LISTENERS
========================================== */

function showToast(title, text, type = "success") {
    const toast = document.createElement("div");
    toast.className = `success-notification ${type === "error" ? "error-toast" : ""}`;
    toast.innerHTML = `
        <div class="success-title">${escapeHtml(title)}</div>
        <div class="success-text">${escapeHtml(text)}</div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3800);
}

function scrollToAuth() {
    const section = document.getElementById("authSection");
    if (section && !section.classList.contains("hidden")) {
        section.scrollIntoView({ behavior: "smooth" });
    }
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

document.addEventListener("DOMContentLoaded", async () => {
    restoreSession();

    const searchInput = document.getElementById("searchInput");
    if (searchInput) {
        searchInput.addEventListener("keydown", e => {
            if (e.key === "Enter") searchJobs();
        });
    }

    await loadJobs();
    if (currentUser && authToken) {
        await refreshWorkspace();
    }
});