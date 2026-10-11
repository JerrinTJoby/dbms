/**
 * Agriculture Management System - Complete Frontend Application Controller
 * Pure Vanilla JavaScript (ES6)
 * Supports all 19 entities/tables from the DBMS schema and ER diagram.
 */

const API_BASE_URL = window.location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

const ROLE_PAGES = {
  FARMER: {
    login: "./farmer_login.html",
    dashboard: "./farmer_dashboard.html",
  },
  OFFICER: {
    login: "./officer_login.html",
    dashboard: "./officer_dashboard.html",
  },
};

// =========================================================================
// Session & Navigation Helpers
// =========================================================================

function readUser() {
  try {
    const user = JSON.parse(localStorage.getItem("user"));
    return user && typeof user === "object" ? user : null;
  } catch {
    return null;
  }
}

function clearSession() {
  localStorage.removeItem("authToken");
  localStorage.removeItem("user");
}

function redirectForUser(user) {
  const role = String(user.role || "").toUpperCase();
  const routes = ROLE_PAGES[role];

  if (!routes) {
    clearSession();
    window.location.replace("./index.html");
    return;
  }

  window.location.replace(
    user.is_profile_complete ? routes.dashboard : "./setup_profile.html",
  );
}

function requireSession(expectedRole) {
  const token = localStorage.getItem("authToken");
  const user = readUser();

  if (!token || !user) {
    clearSession();
    window.location.replace("./index.html");
    return null;
  }

  const role = String(user.role || "").toUpperCase();

  if (expectedRole && role !== expectedRole) {
    redirectForUser(user);
    return null;
  }

  const isSetupPage = window.location.pathname.endsWith("setup_profile.html");

  if (!user.is_profile_complete && !isSetupPage) {
    window.location.replace("./setup_profile.html");
    return null;
  }

  if (user.is_profile_complete && isSetupPage) {
    window.location.replace(ROLE_PAGES[role]?.dashboard || "./index.html");
    return null;
  }

  return { token, user };
}

function showStatus(element, message, isError = false) {
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

// =========================================================================
// API Request Helper
// =========================================================================

async function apiRequest(path, { method = "GET", body, token } = {}) {
  if (window.location.protocol === "file:") {
    throw new Error(
      "Open this application from http://127.0.0.1:8000 or a local web server.",
    );
  }

  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Unable to reach the server. Ensure the backend is running at http://127.0.0.1:8000.");
  }

  const contentType = response.headers.get("content-type") || "";
  const result = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof result === "object" && result
        ? result.message || result.error
        : result;
    throw new Error(message || `Request failed (${response.status}).`);
  }

  return result;
}

function extractList(result, keys) {
  if (Array.isArray(result)) return result;
  for (const key of keys) {
    if (Array.isArray(result?.[key])) return result[key];
  }
  return [];
}

function fillSelect(select, items, idKey, labelKey, placeholder) {
  if (!select) return;
  select.replaceChildren(new Option(placeholder, ""));
  (items || []).forEach((item) => {
    const id = item[idKey];
    const label = item[labelKey];
    if (id !== undefined && label !== undefined) {
      select.add(new Option(label, id));
    }
  });
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function setupFormToggles() {
  document.querySelectorAll("[data-toggle-form]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.toggleForm;
      const form = document.getElementById(targetId);
      if (form) {
        form.hidden = !form.hidden;
        if (!form.hidden) {
          form.querySelector("input, select")?.focus();
        }
      }
    });
  });

  document.querySelectorAll("[data-cancel-form]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.dataset.cancelForm;
      const form = document.getElementById(targetId);
      if (form) {
        form.hidden = true;
        form.reset();
      }
    });
  });
}

function attachLogoutListeners() {
  document.querySelectorAll("[data-logout]").forEach((button) => {
    button.addEventListener("click", () => {
      clearSession();
      window.location.replace("./index.html");
    });
  });
}

// =========================================================================
// Phase 1: Authentication Pages (Login & Register)
// =========================================================================

function initializeAuthPages() {
  const pages = document.querySelectorAll("[data-auth-page]");
  if (!pages.length) return;

  const existingUser = readUser();
  const token = localStorage.getItem("authToken");
  if (existingUser && token) {
    redirectForUser(existingUser);
    return;
  }

  pages.forEach((page) => {
    const tabs = page.querySelectorAll("[data-auth-mode]");
    const forms = page.querySelectorAll("[data-auth-form]");
    const status = page.querySelector(".auth-status");
    const role = page.dataset.role;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const mode = tab.dataset.authMode;
        tabs.forEach((item) => {
          item.setAttribute("aria-pressed", String(item === tab));
        });
        forms.forEach((form) => {
          form.hidden = form.dataset.authForm !== mode;
        });
        showStatus(status, "");
      });
    });

    // Populate registration dropdowns if present
    const regPanchSel = page.querySelector("#register-officer-panchayath");
    const regOffSel = page.querySelector("#register-officer-office");

    if (regPanchSel || regOffSel) {
      Promise.all([
        apiRequest("/api/panchayaths").catch(() => null),
        apiRequest("/api/offices").catch(() => null),
      ]).then(([panchRes, offRes]) => {
        const pList = extractList(panchRes, ["panchayaths", "data"]);
        const oList = extractList(offRes, ["offices", "data"]);

        if (regPanchSel) {
          fillSelect(regPanchSel, pList, "panchayath_id", "panchayath_name", "Select Governing Gram Panchayath…");
          if (regOffSel) {
            regPanchSel.addEventListener("change", () => {
              const selected = pList.find((p) => Number(p.panchayath_id) === Number(regPanchSel.value));
              if (selected && selected.office_id) {
                regOffSel.value = String(selected.office_id);
              }
            });
          }
        }
        if (regOffSel) {
          fillSelect(regOffSel, oList, "office_id", "office_name", "Select Agriculture Office / Krishi Bhavan…");
        }
      });
    }

    forms.forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const submit = form.querySelector('[type="submit"]');
        const mode = form.dataset.authForm;
        const formData = new FormData(form);
        const credentials = {
          email: formData.get("email"),
          password: formData.get("password"),
        };

        submit.disabled = true;
        showStatus(status, mode === "login" ? "Signing in…" : "Registering account in database…");

        try {
          if (mode === "register") {
            const regPayload = Object.fromEntries(formData.entries());
            regPayload.role = role;
            if (regPayload.panchayath_id) regPayload.panchayath_id = parseInt(regPayload.panchayath_id, 10);
            if (regPayload.office_id) regPayload.office_id = parseInt(regPayload.office_id, 10);

            const result = await apiRequest("/api/auth/register", {
              method: "POST",
              body: regPayload,
            });

            tabs.forEach((tab) => {
              const isLogin = tab.dataset.authMode === "login";
              tab.setAttribute("aria-pressed", String(isLogin));
            });
            forms.forEach((item) => {
              item.hidden = item.dataset.authForm !== "login";
            });
            const loginForm = page.querySelector('[data-auth-form="login"]');
            if (loginForm && regPayload.email) {
              const emailInput = loginForm.querySelector('[name="email"]');
              if (emailInput) emailInput.value = regPayload.email;
              const pwdInput = loginForm.querySelector('[name="password"]');
              if (pwdInput) pwdInput.focus();
            }
            form.reset();
            showStatus(status, result?.message || "Officer account registered successfully in database! Please log in.");
            return;
          }

          const result = await apiRequest("/api/auth/login", {
            method: "POST",
            body: credentials,
          });

          if (!result || typeof result.token !== "string" || !result.user) {
            throw new Error("Invalid response received from server.");
          }

          if (String(result.user.role || "").toUpperCase() !== role) {
            throw new Error(`This account is not registered as an ${role.toLowerCase()}.`);
          }

          localStorage.setItem("authToken", result.token);
          localStorage.setItem("user", JSON.stringify(result.user));

          showStatus(status, "Login successful. Redirecting…");
          redirectForUser(result.user);
        } catch (error) {
          showStatus(status, error.message, true);
        } finally {
          submit.disabled = false;
        }
      });
    });
  });
}

// =========================================================================
// Phase 2: Role-Based Profile Setup
// =========================================================================

async function initializeProfileSetup() {
  const page = document.querySelector("[data-profile-page]");
  if (!page) return;

  const session = requireSession();
  if (!session) return;

  const { user, token } = session;
  const role = String(user.role || "").toUpperCase();

  const roleBadge = page.querySelector("#profile-role-badge");
  if (roleBadge) {
    roleBadge.textContent = role === "FARMER" ? "Farmer Profile Setup" : "Officer Profile Setup";
  }

  page.querySelectorAll("[data-profile-role]").forEach((group) => {
    const isActiveRole = group.dataset.profileRole === role;
    group.hidden = !isActiveRole;
    group.querySelectorAll("input, select, textarea").forEach((field) => {
      field.disabled = !isActiveRole;
    });
  });

  const status = page.querySelector(".auth-status");

  try {
    if (role === "FARMER") {
      const farmerPanchayathSelect = page.querySelector("#panchayath-id");
      const panchRes = await apiRequest("/api/panchayaths", { token });
      const panchList = extractList(panchRes, ["panchayaths", "data"]);
      fillSelect(farmerPanchayathSelect, panchList, "panchayath_id", "panchayath_name", "Select your Gram Panchayath");
    } else {
      const officerPanchayathSelect = page.querySelector("#officer-panchayath-id");
      const officeSelect = page.querySelector("#office-id");
      const [panchRes, offRes] = await Promise.all([
        apiRequest("/api/panchayaths", { token }),
        apiRequest("/api/offices", { token }),
      ]);
      const panchList = extractList(panchRes, ["panchayaths", "data"]);
      const offList = extractList(offRes, ["offices", "data"]);
      fillSelect(officerPanchayathSelect, panchList, "panchayath_id", "panchayath_name", "Select Governing Gram Panchayath");
      fillSelect(officeSelect, offList, "office_id", "office_name", "Select Agriculture Office");

      officerPanchayathSelect?.addEventListener("change", () => {
        const selected = panchList.find((p) => Number(p.panchayath_id) === Number(officerPanchayathSelect.value));
        if (selected && officeSelect) {
          officeSelect.value = String(selected.office_id || "");
        }
      });
    }
  } catch (error) {
    showStatus(status, error.message, true);
  }

  const form = page.querySelector("#profile-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('[type="submit"]');
    const data = new FormData(form);

    const profile = {
      full_name: data.get("full_name"),
      phone: data.get("phone"),
      role,
    };

    if (role === "FARMER") {
      profile.address = data.get("address");
      profile.panchayath_id = parseInt(data.get("panchayath_id"), 10);
    } else {
      profile.designation = data.get("designation");
      profile.panchayath_id = parseInt(data.get("panchayath_id"), 10);
      profile.office_id = parseInt(data.get("office_id"), 10);
    }

    submit.disabled = true;
    showStatus(status, "Saving profile details…");

    try {
      const result = await apiRequest("/api/users/complete-profile", {
        method: "POST",
        body: profile,
        token,
      });

      if (!result?.user || !result.user.is_profile_complete) {
        throw new Error("Unable to save completed profile.");
      }

      localStorage.setItem("user", JSON.stringify(result.user));
      showStatus(status, "Profile setup complete. Redirecting to dashboard…");
      window.location.replace(ROLE_PAGES[role].dashboard);
    } catch (error) {
      showStatus(status, error.message, true);
    } finally {
      submit.disabled = false;
    }
  });
}

// =========================================================================
// Phase 3: Officer Dashboard & Subsidy Verification Desk
// =========================================================================

async function initializeOfficerDashboard() {
  const page = document.querySelector("[data-officer-dashboard]");
  if (!page) return;

  const session = requireSession("OFFICER");
  if (!session) return;

  const status = page.querySelector(".dashboard-status");
  const officeFilter = page.querySelector("#office-filter");
  const filterSelect = page.querySelector("#panchayath-filter");
  const farmerTbody = page.querySelector("#farmer-directory");
  const subsidiesTbody = page.querySelector("#officer-subsidies-body");
  const inspectionPanel = page.querySelector("#farmer-inspection-panel");
  const closeInspectionBtn = page.querySelector("#close-inspection-btn");

  if (closeInspectionBtn && inspectionPanel) {
    closeInspectionBtn.addEventListener("click", () => {
      inspectionPanel.style.display = "none";
    });
  }

  // 0. Top Navigation Pills
  const officerNavPills = page.querySelectorAll("#officer-nav-pills .nav-pill");
  officerNavPills.forEach((pill) => {
    pill.addEventListener("click", (e) => {
      e.preventDefault();
      officerNavPills.forEach((p) => p.classList.remove("is-active"));
      pill.classList.add("is-active");
      const targetId = pill.getAttribute("href");
      const targetEl = page.querySelector(targetId);
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  // Inspection Drawer Switchable Tabs
  const inspectTabs = page.querySelectorAll("#inspect-sub-tabs .sub-tab-btn");
  const inspectPanels = page.querySelectorAll("[data-inspect-panel]");

  function showInspectTab(tabKey) {
    inspectTabs.forEach((btn) => {
      if (btn.dataset.inspectTab === tabKey) {
        btn.classList.add("is-active");
      } else {
        btn.classList.remove("is-active");
      }
    });

    inspectPanels.forEach((panel) => {
      if (tabKey === "all" || panel.dataset.inspectPanel === tabKey) {
        panel.style.display = "block";
      } else {
        panel.style.display = "none";
      }
    });
  }

  inspectTabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      showInspectTab(btn.dataset.inspectTab);
    });
  });

  // Officer Profile Edit Modal
  const officerModal = page.querySelector("#officer-edit-modal");
  const officerModalForm = page.querySelector("#officer-profile-form");
  const officerModalClose = page.querySelector("#officer-modal-close");
  const officerModalCancel = page.querySelector("#officer-modal-cancel");

  function closeOfficerModal() {
    if (officerModal) officerModal.style.display = "none";
  }
  officerModalClose?.addEventListener("click", closeOfficerModal);
  officerModalCancel?.addEventListener("click", closeOfficerModal);

  function updateOfficerHeaderUI() {
    const officerName = session.user.full_name || session.user.email || "Officer";
    const officerDesignation = session.user.designation || "Agricultural Officer";
    const officerOffice = session.user.office_name || "Assigned Office";
    const officerPanchayath = session.user.panchayath_name || "Assigned Panchayath";

    page.querySelector("[data-officer-name]").textContent = officerName;
    page.querySelector("[data-officer-designation]").textContent = officerDesignation;
    page.querySelector("[data-officer-office]").textContent = officerOffice;
    page.querySelector("[data-stat-office]").textContent = officerOffice;
    const panchEl = page.querySelector("[data-officer-panchayath]");
    if (panchEl) panchEl.textContent = officerPanchayath;
    const statPanchEl = page.querySelector("[data-stat-panchayath]");
    if (statPanchEl) statPanchEl.textContent = officerPanchayath;
  }
  updateOfficerHeaderUI();

  page.querySelector("#edit-officer-profile-btn")?.addEventListener("click", () => {
    if (!officerModal) return;
    page.querySelector("#officer-edit-name").value = session.user.full_name || "";
    page.querySelector("#officer-edit-phone").value = session.user.phone || "";
    page.querySelector("#officer-edit-desig").value = session.user.designation || "";

    const panchSel = page.querySelector("#officer-edit-panchayath");
    const officeSel = page.querySelector("#officer-edit-office");

    if (panchSel) {
      fillSelect(panchSel, allPanchayaths, "panchayath_id", "panchayath_name", "Select Governing Panchayath…");
      panchSel.value = String(session.user.panchayath_id || "");
      panchSel.onchange = () => {
        const selected = allPanchayaths.find((p) => Number(p.panchayath_id) === Number(panchSel.value));
        if (selected && officeSel) {
          officeSel.value = String(selected.office_id || "");
        }
      };
    }
    if (officeSel) {
      fillSelect(officeSel, allOffices, "office_id", "office_name", "Select Agriculture Office…");
      officeSel.value = String(session.user.office_id || "");
    }
    officerModal.style.display = "flex";
  });

  officerModalForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(officerModalForm);
    try {
      const res = await apiRequest("/api/users/profile", {
        method: "PUT",
        body: {
          full_name: fd.get("full_name"),
          phone: fd.get("phone"),
          designation: fd.get("designation"),
          panchayath_id: parseInt(fd.get("panchayath_id")),
          office_id: parseInt(fd.get("office_id")),
        },
        token: session.token,
      });
      session.user = { ...session.user, ...res.user };
      localStorage.setItem("user", JSON.stringify(session.user));
      updateOfficerHeaderUI();
      closeOfficerModal();
      showStatus(status, "Officer profile updated successfully!");
      await loadOfficerStats();
      await loadOfficerSubsidies();
      await reloadAllOfficerData();
    } catch (err) {
      alert("Error updating profile: " + err.message);
    }
  });

  // 1. Fetch Stats
  async function loadOfficerStats() {
    try {
      const stats = await apiRequest("/api/officer/stats", { token: session.token });
      page.querySelector("#stat-panchayaths-count").textContent = String(stats.panchayaths_count || 0);
      page.querySelector("#stat-farmers-count").textContent = String(stats.farmers_count || 0);
      page.querySelector("#stat-farms-count").textContent = String(stats.farms_count || 0);
      page.querySelector("#stat-pending-subsidies").textContent = String(stats.pending_subsidies || 0);
      if (stats.panchayath_name) {
        const statPanchEl = page.querySelector("[data-stat-panchayath]");
        if (statPanchEl) statPanchEl.textContent = stats.panchayath_name;
      }
    } catch {
      // Non-blocking
    }
  }

  // 2. Fetch Offices & Panchayaths for Filter
  let allOffices = [];
  let allPanchayaths = [];

  function updatePanchayathFilterOptions() {
    const selectedOffice = officeFilter ? officeFilter.value : "";
    let filteredP = allPanchayaths;
    if (selectedOffice && selectedOffice !== "all") {
      filteredP = allPanchayaths.filter((p) => Number(p.office_id) === Number(selectedOffice));
    }
    fillSelect(filterSelect, filteredP, "panchayath_id", "panchayath_name", "All Gram Panchayaths");
  }

  try {
    const [officesRes, panchayathsRes] = await Promise.all([
      apiRequest("/api/offices", { token: session.token }),
      apiRequest("/api/panchayaths", { token: session.token }),
    ]);
    allOffices = extractList(officesRes, ["offices", "data"]);
    allPanchayaths = extractList(panchayathsRes, ["panchayaths", "data"]);

    if (officeFilter) {
      officeFilter.replaceChildren();

      // Default: Assigned Office
      if (session.user.office_id) {
        const assignedOpt = document.createElement("option");
        assignedOpt.value = String(session.user.office_id);
        assignedOpt.textContent = `📍 Assigned: ${session.user.office_name || 'Assigned Office'}`;
        assignedOpt.selected = true;
        officeFilter.append(assignedOpt);
      }

      // Statewide option
      const statewideOpt = document.createElement("option");
      statewideOpt.value = "all";
      statewideOpt.textContent = "🌐 All Offices (Statewide Directory)";
      if (!session.user.office_id) statewideOpt.selected = true;
      officeFilter.append(statewideOpt);

      // Other offices
      allOffices.forEach((off) => {
        if (Number(off.office_id) !== Number(session.user.office_id)) {
          const opt = document.createElement("option");
          opt.value = String(off.office_id);
          opt.textContent = `🏢 ${off.office_name}`;
          officeFilter.append(opt);
        }
      });

      officeFilter.addEventListener("change", () => {
        updatePanchayathFilterOptions();
        reloadAllOfficerData();
      });
    }

    updatePanchayathFilterOptions();
  } catch (err) {
    showStatus(status, "Error loading offices: " + err.message, true);
  }

  // 3. Load Farmers with Farms & Crops Aggregates
  async function loadFarmers() {
    const params = new URLSearchParams();
    if (officeFilter && officeFilter.value) {
      params.set("office_id", officeFilter.value);
    }
    if (filterSelect && filterSelect.value) {
      params.set("panchayath_id", filterSelect.value);
    }
    const query = params.toString() ? `?${params.toString()}` : "";

    try {
      const result = await apiRequest(`/api/officer/farmers${query}`, { token: session.token });
      const farmers = extractList(result, ["farmers", "data"]);
      farmerTbody.replaceChildren();

      if (!farmers.length) {
        const row = farmerTbody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 6;
        cell.className = "table-empty";
        cell.textContent = "No registered farmers found for the selected jurisdiction.";
        return;
      }

      farmers.forEach((farmer) => {
        const row = farmerTbody.insertRow();

        // 1. Farmer Name
        const nameCell = row.insertCell();
        nameCell.innerHTML = `<strong>${escapeHtml(farmer.farmer_name)}</strong><br><small style="color:#687067;">ID #${farmer.farmer_id} • Reg: ${farmer.registration_date || '—'}</small>`;

        // 2. Contact
        const contactCell = row.insertCell();
        contactCell.innerHTML = `<div>${escapeHtml(farmer.farmer_email)}</div><small style="color:#687067;">📞 ${escapeHtml(farmer.farmer_phone || 'None')}</small>`;

        // 3. Office & Panchayath
        const locCell = row.insertCell();
        locCell.innerHTML = `<div><strong>${escapeHtml(farmer.panchayath_name)}</strong></div><small style="color:#687067;">${escapeHtml(farmer.office_name)}</small>`;

        // 4. Farms & Acreage
        const farmsCell = row.insertCell();
        const fCount = Number(farmer.farms_count || 0);
        const acres = parseFloat(farmer.total_acres || 0);
        if (fCount > 0) {
          farmsCell.innerHTML = `<div><strong>${fCount} Farm(s)</strong> (${acres.toFixed(2)} acres)</div><small style="color:#287647;">🌱 ${escapeHtml(farmer.farms_summary || '')}</small>`;
        } else {
          farmsCell.innerHTML = `<span class="status-badge badge--pending">No Farms Added</span>`;
        }

        // 5. Cultivated Crops
        const cropsCell = row.insertCell();
        const cCount = Number(farmer.crops_count || 0);
        if (cCount > 0) {
          cropsCell.innerHTML = `<div><strong>${cCount} Active Crop(s)</strong></div><small style="color:#795331;">🌾 ${escapeHtml(farmer.crops_summary || '')}</small>`;
        } else {
          cropsCell.innerHTML = `<span style="color:#888;">— None —</span>`;
        }

        // 6. Action button (Inspection drawer)
        const actionCell = row.insertCell();
        const inspectBtn = document.createElement("button");
        inspectBtn.type = "button";
        inspectBtn.className = "action-btn action-btn--inspect";
        inspectBtn.innerHTML = "🔍 View Full Details";
        inspectBtn.addEventListener("click", () => inspectFarmer(farmer));
        actionCell.append(inspectBtn);
      });
    } catch (err) {
      farmerTbody.replaceChildren();
      const row = farmerTbody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 6;
      cell.className = "table-empty";
      cell.textContent = "Unable to load farmer directory: " + err.message;
    }
  }

  // Farmer Inspection Drilldown
  async function inspectFarmer(farmer) {
    if (!inspectionPanel) return;
    inspectionPanel.style.display = "block";
    inspectionPanel.scrollIntoView({ behavior: "smooth", block: "start" });

    page.querySelector("#inspect-farmer-name").textContent = `${farmer.farmer_name} (Farmer #${farmer.farmer_id})`;
    page.querySelector("#inspect-farmer-meta").textContent = `Email: ${farmer.farmer_email} | Phone: ${farmer.farmer_phone || 'None'} | Panchayath: ${farmer.panchayath_name} (${farmer.office_name}) | Address: ${farmer.farmer_address || '—'}`;

    const farmsTbody = page.querySelector("#inspect-farms-tbody");
    const cropsTbody = page.querySelector("#inspect-crops-tbody");
    const expensesTbody = page.querySelector("#inspect-expenses-tbody");
    const incomeTbody = page.querySelector("#inspect-income-tbody");
    const fertTbody = page.querySelector("#inspect-fert-tbody");
    const labourTbody = page.querySelector("#inspect-labour-tbody");
    const subsidiesTbody = page.querySelector("#inspect-subsidies-tbody");

    [farmsTbody, cropsTbody, expensesTbody, incomeTbody, fertTbody, labourTbody, subsidiesTbody].forEach((tb) => {
      if (tb) {
        tb.replaceChildren();
        const r = tb.insertRow();
        const c = r.insertCell();
        c.colSpan = 10;
        c.className = "table-empty";
        c.textContent = "Loading farmer records…";
      }
    });

    try {
      const details = await apiRequest(`/api/officer/farmer-details?farmer_id=${farmer.farmer_id}`, { token: session.token });

      // 1. Farms
      const farms = details.farms || [];
      const fcTab = page.querySelector("#inspect-farms-count");
      if (fcTab) fcTab.textContent = String(farms.length);
      const fcHdr = page.querySelector("#inspect-farms-count-header");
      if (fcHdr) fcHdr.textContent = String(farms.length);
      farmsTbody.replaceChildren();
      if (!farms.length) {
        const r = farmsTbody.insertRow();
        const c = r.insertCell();
        c.colSpan = 5;
        c.className = "table-empty";
        c.textContent = "No registered farms.";
      } else {
        farms.forEach((f) => {
          const r = farmsTbody.insertRow();
          [f.farm_name, f.location, `${f.area_acres} acres`, f.soil_type, f.irrigation_type].forEach((v) => {
            r.insertCell().textContent = v || "—";
          });
        });
      }

      // 2. Crops
      const crops = details.crops || [];
      const ccTab = page.querySelector("#inspect-crops-count");
      if (ccTab) ccTab.textContent = String(crops.length);
      const ccHdr = page.querySelector("#inspect-crops-count-header");
      if (ccHdr) ccHdr.textContent = String(crops.length);
      cropsTbody.replaceChildren();
      if (!crops.length) {
        const r = cropsTbody.insertRow();
        const c = r.insertCell();
        c.colSpan = 7;
        c.className = "table-empty";
        c.textContent = "No crop cultivation records.";
      } else {
        crops.forEach((c) => {
          const r = cropsTbody.insertRow();
          r.insertCell().textContent = c.farm_name;
          r.insertCell().textContent = c.crop_name;
          r.insertCell().textContent = c.crop_category || "—";
          r.insertCell().textContent = c.season || "—";
          r.insertCell().textContent = c.planting_date || "—";
          r.insertCell().textContent = `${c.cultivated_area_acres || '0'} acres`;

          const statusCell = r.insertCell();
          const badge = document.createElement("span");
          const st = String(c.status || "PLANNED").toUpperCase();
          badge.className = `status-badge badge--${st.toLowerCase()}`;
          badge.textContent = st;
          statusCell.append(badge);
        });
      }

      // 3. Expenses
      const expenses = details.expenses || [];
      const ecTab = page.querySelector("#inspect-expenses-count");
      if (ecTab) ecTab.textContent = String(expenses.length);
      const ecHdr = page.querySelector("#inspect-expenses-count-header");
      if (ecHdr) ecHdr.textContent = String(expenses.length);
      expensesTbody.replaceChildren();
      if (!expenses.length) {
        const r = expensesTbody.insertRow();
        const c = r.insertCell();
        c.colSpan = 6;
        c.className = "table-empty";
        c.textContent = "No expense entries recorded.";
      } else {
        expenses.forEach((e) => {
          const r = expensesTbody.insertRow();
          r.insertCell().textContent = e.farm_name;
          r.insertCell().textContent = e.expense_category;
          r.insertCell().textContent = e.rental_name || e.energy_name || "—";
          r.insertCell().textContent = `₹${parseFloat(e.amount || 0).toLocaleString()}`;
          r.insertCell().textContent = e.expense_date || "—";
          r.insertCell().textContent = e.description || "—";
        });
      }

      // 4. Harvest Sales / Income
      const income = details.income || [];
      const icTab = page.querySelector("#inspect-income-count");
      if (icTab) icTab.textContent = String(income.length);
      const icHdr = page.querySelector("#inspect-income-count-header");
      if (icHdr) icHdr.textContent = String(income.length);
      incomeTbody.replaceChildren();
      if (!income.length) {
        const r = incomeTbody.insertRow();
        const c = r.insertCell();
        c.colSpan = 6;
        c.className = "table-empty";
        c.textContent = "No harvest produce sales recorded.";
      } else {
        income.forEach((inc) => {
          const r = incomeTbody.insertRow();
          r.insertCell().textContent = `${inc.farm_name} (${inc.crop_name})`;
          r.insertCell().textContent = inc.sale_date || "—";
          r.insertCell().textContent = `${inc.quantity_sold} ${inc.unit || 'kg'}`;
          r.insertCell().textContent = `₹${parseFloat(inc.price_per_unit || 0).toLocaleString()}`;
          r.insertCell().textContent = `₹${parseFloat(inc.total_income || 0).toLocaleString()}`;
          r.insertCell().textContent = inc.buyer_name || "—";
        });
      }

      // 5. Fertilizers
      const fertilizers = details.fertilizers || [];
      const ftTab = page.querySelector("#inspect-fert-count");
      if (ftTab) ftTab.textContent = String(fertilizers.length);
      const ftHdr = page.querySelector("#inspect-fert-count-header");
      if (ftHdr) ftHdr.textContent = String(fertilizers.length);
      fertTbody.replaceChildren();
      if (!fertilizers.length) {
        const r = fertTbody.insertRow();
        const c = r.insertCell();
        c.colSpan = 5;
        c.className = "table-empty";
        c.textContent = "No fertilizer application logs.";
      } else {
        fertilizers.forEach((f) => {
          const r = fertTbody.insertRow();
          r.insertCell().textContent = `${f.farm_name} (${f.crop_name})`;
          r.insertCell().textContent = f.fertilizer_name;
          r.insertCell().textContent = f.application_date || "—";
          r.insertCell().textContent = `${f.quantity} ${f.unit || 'kg'}`;
          r.insertCell().textContent = `₹${parseFloat(f.total_cost || 0).toLocaleString()}`;
        });
      }

      // 6. Labour
      const labour = details.labour || [];
      const lcTab = page.querySelector("#inspect-labour-count");
      if (lcTab) lcTab.textContent = String(labour.length);
      const lcHdr = page.querySelector("#inspect-labour-count-header");
      if (lcHdr) lcHdr.textContent = String(labour.length);
      labourTbody.replaceChildren();
      if (!labour.length) {
        const r = labourTbody.insertRow();
        const c = r.insertCell();
        c.colSpan = 6;
        c.className = "table-empty";
        c.textContent = "No labour activity records.";
      } else {
        labour.forEach((l) => {
          const r = labourTbody.insertRow();
          r.insertCell().textContent = `${l.farm_name} (${l.crop_name})`;
          r.insertCell().textContent = l.labour_name;
          r.insertCell().textContent = l.work_date || "—";
          r.insertCell().textContent = `${l.worker_count} workers`;
          r.insertCell().textContent = `${l.days_worked} days`;
          r.insertCell().textContent = `₹${parseFloat(l.total_cost || 0).toLocaleString()}`;
        });
      }

      // 7. Subsidies
      const subsidies = details.subsidies || [];
      const scTab = page.querySelector("#inspect-subsidies-count");
      if (scTab) scTab.textContent = String(subsidies.length);
      const scHdr = page.querySelector("#inspect-subsidies-count-header");
      if (scHdr) scHdr.textContent = String(subsidies.length);
      subsidiesTbody.replaceChildren();
      if (!subsidies.length) {
        const r = subsidiesTbody.insertRow();
        const c = r.insertCell();
        c.colSpan = 7;
        c.className = "table-empty";
        c.textContent = "No subsidy applications submitted.";
      } else {
        subsidies.forEach((s) => {
          const r = subsidiesTbody.insertRow();
          r.insertCell().textContent = `#${s.farmer_subsidy_id}`;
          r.insertCell().textContent = s.subsidy_name;
          r.insertCell().textContent = s.application_date || "—";

          const statusCell = r.insertCell();
          const badge = document.createElement("span");
          const st = String(s.status || "PENDING").toUpperCase();
          badge.className = `status-badge badge--${st.toLowerCase()}`;
          badge.textContent = st;
          statusCell.append(badge);

          r.insertCell().textContent = `₹${parseFloat(s.amount || 0).toLocaleString()}`;
          r.insertCell().textContent = s.approved_amount ? `₹${parseFloat(s.approved_amount).toLocaleString()}` : "—";
          r.insertCell().textContent = s.remarks || "—";
        });
      }

      showInspectTab("farms");
    } catch (err) {
      showStatus(status, "Error retrieving farmer details: " + err.message, true);
    }
  }

  // 4. Load Subsidy Applications for Review Desk
  async function loadOfficerSubsidies() {
    try {
      const result = await apiRequest("/api/officer/subsidies", { token: session.token });
      const subsidies = extractList(result, ["subsidies", "data"]);
      subsidiesTbody.replaceChildren();

      const badge = page.querySelector("#officer-jurisdiction-badge");
      if (badge) {
        if (result.officer_panchayath_name) {
          badge.textContent = `📍 ${result.officer_panchayath_name} Jurisdiction`;
          badge.style.display = "inline-block";
        } else {
          badge.textContent = "🏢 Office Jurisdiction";
          badge.style.display = "inline-block";
        }
      }

      if (!subsidies.length) {
        const row = subsidiesTbody.insertRow();
        const cell = row.insertCell();
        cell.colSpan = 10;
        cell.className = "table-empty";
        cell.textContent = result.officer_panchayath_name
          ? `No pending or active subsidy applications from farmers in ${result.officer_panchayath_name}.`
          : "No farmer subsidy applications recorded for this office.";
        return;
      }

      subsidies.forEach((sub) => {
        const row = subsidiesTbody.insertRow();
        row.insertCell().textContent = `#${sub.farmer_subsidy_id}`;
        row.insertCell().textContent = `${sub.farmer_name} (${sub.farmer_phone || '—'})`;
        row.insertCell().textContent = sub.panchayath_name || "—";
        row.insertCell().textContent = sub.subsidy_name || "—";
        row.insertCell().textContent = sub.application_date || "—";
        row.insertCell().textContent = `₹${parseFloat(sub.amount || 0).toLocaleString()}`;

        // Status badge
        const statusCell = row.insertCell();
        const badge = document.createElement("span");
        const st = String(sub.status || "PENDING").toUpperCase();
        badge.className = `status-badge badge--${st.toLowerCase()}`;
        badge.textContent = st;
        statusCell.append(badge);

        row.insertCell().textContent = sub.approved_amount ? `₹${parseFloat(sub.approved_amount).toLocaleString()}` : "—";
        row.insertCell().textContent = sub.remarks || "—";

        // Action cell (Approve / Reject)
        const actionCell = row.insertCell();
        if (st === "PENDING") {
          const btnGroup = document.createElement("div");
          btnGroup.className = "table-actions";

          const approveBtn = document.createElement("button");
          approveBtn.className = "action-btn action-btn--approve";
          approveBtn.textContent = "Approve";
          approveBtn.addEventListener("click", async () => {
            const amtStr = prompt(`Enter Approved Grant Amount (₹) for ${sub.farmer_name}:`, sub.amount);
            if (amtStr === null) return;
            const amt = parseFloat(amtStr);
            if (isNaN(amt) || amt <= 0) {
              alert("Please enter a valid amount.");
              return;
            }
            const remarks = prompt("Enter verification remarks:", "Approved after field inspection.") || "Approved";
            try {
              await apiRequest("/api/officer/subsidies/review", {
                method: "POST",
                body: { farmer_subsidy_id: sub.farmer_subsidy_id, status: "APPROVED", approved_amount: amt, remarks },
                token: session.token,
              });
              showStatus(status, `Subsidy #${sub.farmer_subsidy_id} approved.`);
              await loadOfficerSubsidies();
              await loadOfficerStats();
            } catch (error) {
              alert(error.message);
            }
          });

          const rejectBtn = document.createElement("button");
          rejectBtn.className = "action-btn action-btn--reject";
          rejectBtn.textContent = "Reject";
          rejectBtn.addEventListener("click", async () => {
            const remarks = prompt("Enter rejection reason:", "Criteria not fulfilled.");
            if (remarks === null) return;
            try {
              await apiRequest("/api/officer/subsidies/review", {
                method: "POST",
                body: { farmer_subsidy_id: sub.farmer_subsidy_id, status: "REJECTED", remarks },
                token: session.token,
              });
              showStatus(status, `Subsidy #${sub.farmer_subsidy_id} rejected.`);
              await loadOfficerSubsidies();
              await loadOfficerStats();
            } catch (error) {
              alert(error.message);
            }
          });

          btnGroup.append(approveBtn, rejectBtn);
          actionCell.append(btnGroup);
        } else {
          actionCell.textContent = "Reviewed";
        }
      });
    } catch {
      subsidiesTbody.replaceChildren();
      const row = subsidiesTbody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 10;
      cell.className = "table-empty";
      cell.textContent = "Unable to load subsidy applications.";
    }
  }

  // 5. Reference Catalog Explorer
  const catalogSelect = page.querySelector("#catalog-select");
  const catalogThead = page.querySelector("#catalog-thead");
  const catalogTbody = page.querySelector("#catalog-tbody");
  const catalogTabBtns = page.querySelectorAll("#catalog-tab-buttons .sub-tab-btn");

  let refDataCache = null;
  async function loadCatalog(type) {
    catalogTabBtns.forEach((btn) => {
      if (btn.dataset.catalogTab === type) {
        btn.classList.add("is-active");
      } else {
        btn.classList.remove("is-active");
      }
    });

    if (!refDataCache) {
      try {
        refDataCache = await apiRequest("/api/reference-data", { token: session.token });
      } catch {
        return;
      }
    }

    catalogThead.replaceChildren();
    catalogTbody.replaceChildren();
    const hRow = catalogThead.insertRow();

    if (type === "crops") {
      ["ID", "Crop Name", "Category", "Season", "Growth (Days)", "Exp. Yield / Acre"].forEach((h) => {
        const th = document.createElement("th");
        th.textContent = h;
        hRow.append(th);
      });
      (refDataCache.crops || []).forEach((c) => {
        const r = catalogTbody.insertRow();
        [c.crop_id, c.crop_name, c.crop_category, c.season, `${c.growth_duration_days} days`, `${c.expected_yield_per_acre} kg`].forEach((v) => {
          r.insertCell().textContent = v || "—";
        });
      });
    } else if (type === "fertilizers") {
      ["ID", "Fertilizer Name", "Type", "Unit"].forEach((h) => {
        const th = document.createElement("th");
        th.textContent = h;
        hRow.append(th);
      });
      (refDataCache.fertilizers || []).forEach((f) => {
        const r = catalogTbody.insertRow();
        [f.fertilizer_id, f.fertilizer_name, f.fertilizer_type, f.unit].forEach((v) => r.insertCell().textContent = v || "—");
      });
    } else if (type === "labour_types") {
      ["ID", "Labour Activity", "Standard Daily Rate (₹)"].forEach((h) => {
        const th = document.createElement("th");
        th.textContent = h;
        hRow.append(th);
      });
      (refDataCache.labour_types || []).forEach((l) => {
        const r = catalogTbody.insertRow();
        [l.labour_id, l.labour_name, `₹${l.standard_daily_rate}`].forEach((v) => r.insertCell().textContent = v || "—");
      });
    } else if (type === "rental_types") {
      ["ID", "Rental Machinery", "Description"].forEach((h) => {
        const th = document.createElement("th");
        th.textContent = h;
        hRow.append(th);
      });
      (refDataCache.rental_types || []).forEach((rt) => {
        const r = catalogTbody.insertRow();
        [rt.rental_id, rt.rental_name, rt.description].forEach((v) => r.insertCell().textContent = v || "—");
      });
    } else if (type === "energy_types") {
      ["ID", "Energy Source"].forEach((h) => {
        const th = document.createElement("th");
        th.textContent = h;
        hRow.append(th);
      });
      (refDataCache.energy_types || []).forEach((et) => {
        const r = catalogTbody.insertRow();
        [et.energy_id, et.energy_name].forEach((v) => r.insertCell().textContent = v || "—");
      });
    } else if (type === "subsidies") {
      ["ID", "Scheme Name", "Eligible Amount (₹)", "Period", "Eligibility"].forEach((h) => {
        const th = document.createElement("th");
        th.textContent = h;
        hRow.append(th);
      });
      (refDataCache.subsidies || []).forEach((s) => {
        const r = catalogTbody.insertRow();
        [s.subsidy_id, s.subsidy_name, `₹${s.amount}`, `${s.start_date || '—'} to ${s.end_date || '—'}`, s.eligibility_criteria].forEach((v) => r.insertCell().textContent = v || "—");
      });
    }
  }

  catalogTabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const catKey = btn.dataset.catalogTab;
      if (catalogSelect) catalogSelect.value = catKey;
      loadCatalog(catKey);
    });
  });

  if (catalogSelect) {
    catalogSelect.addEventListener("change", () => loadCatalog(catalogSelect.value));
  }

  // 6. Jurisdiction-Wide ER Records (Farms, Crops, Expenses, Income, Fertilizers, Labour)
  const officerFarmsBody = page.querySelector("#officer-farms-body");
  const officerCropsBody = page.querySelector("#officer-crops-body");
  const officerExpensesBody = page.querySelector("#officer-expenses-body");
  const officerIncomeBody = page.querySelector("#officer-income-body");
  const officerFertBody = page.querySelector("#officer-fert-body");
  const officerLabourBody = page.querySelector("#officer-labour-body");

  async function loadJurisdictionRecords() {
    const params = new URLSearchParams();
    if (officeFilter && officeFilter.value) {
      params.set("office_id", officeFilter.value);
    }
    if (filterSelect && filterSelect.value) {
      params.set("panchayath_id", filterSelect.value);
    }
    const q = params.toString() ? `&${params.toString()}` : "";

    try {
      const [fRes, cRes, eRes, iRes, ftRes, lRes] = await Promise.all([
        apiRequest(`/api/officer/records?type=farms${q}`, { token: session.token }),
        apiRequest(`/api/officer/records?type=crops${q}`, { token: session.token }),
        apiRequest(`/api/officer/records?type=expenses${q}`, { token: session.token }),
        apiRequest(`/api/officer/records?type=income${q}`, { token: session.token }),
        apiRequest(`/api/officer/records?type=fertilizers${q}`, { token: session.token }),
        apiRequest(`/api/officer/records?type=labour${q}`, { token: session.token }),
      ]);

      // 1. Farms
      if (officerFarmsBody) {
        officerFarmsBody.replaceChildren();
        const records = fRes.records || [];
        if (!records.length) {
          const r = officerFarmsBody.insertRow();
          const c = r.insertCell();
          c.colSpan = 7;
          c.className = "table-empty";
          c.textContent = "No registered farms found in the selected jurisdiction.";
        } else {
          records.forEach((f) => {
            const r = officerFarmsBody.insertRow();
            r.insertCell().innerHTML = `<strong>${escapeHtml(f.farm_name)}</strong>`;
            r.insertCell().innerHTML = `<div>${escapeHtml(f.farmer_name)}</div><small style="color:#687067;">${escapeHtml(f.farmer_phone || f.farmer_email || '')}</small>`;
            r.insertCell().textContent = f.location || "—";
            r.insertCell().textContent = `${f.area_acres} acres`;
            r.insertCell().textContent = f.soil_type || "—";
            r.insertCell().textContent = f.irrigation_type || "—";
            r.insertCell().innerHTML = `<strong>${escapeHtml(f.panchayath_name)}</strong><br><small style="color:#687067;">${escapeHtml(f.office_name)}</small>`;
          });
        }
      }

      // 2. Crops
      if (officerCropsBody) {
        officerCropsBody.replaceChildren();
        const records = cRes.records || [];
        if (!records.length) {
          const r = officerCropsBody.insertRow();
          const c = r.insertCell();
          c.colSpan = 9;
          c.className = "table-empty";
          c.textContent = "No crop cultivation records found in the selected jurisdiction.";
        } else {
          records.forEach((c) => {
            const r = officerCropsBody.insertRow();
            r.insertCell().innerHTML = `<strong>${escapeHtml(c.farmer_name)}</strong>`;
            r.insertCell().textContent = c.farm_name;
            r.insertCell().innerHTML = `<strong>${escapeHtml(c.crop_name)}</strong> <small>(${escapeHtml(c.crop_category || 'Cereal')})</small>`;
            r.insertCell().textContent = c.season || "—";
            r.insertCell().textContent = c.planting_date || "—";
            r.insertCell().textContent = c.expected_harvest_date || c.actual_harvest_date || "—";
            r.insertCell().textContent = `${c.cultivated_area_acres || '0'} acres`;

            const statusCell = r.insertCell();
            const badge = document.createElement("span");
            const st = String(c.status || "GROWING").toUpperCase();
            badge.className = `status-badge badge--${st.toLowerCase()}`;
            badge.textContent = st;
            statusCell.append(badge);

            r.insertCell().textContent = c.panchayath_name || "—";
          });
        }
      }

      // 3. Expenses
      if (officerExpensesBody) {
        officerExpensesBody.replaceChildren();
        const records = eRes.records || [];
        if (!records.length) {
          const r = officerExpensesBody.insertRow();
          const c = r.insertCell();
          c.colSpan = 8;
          c.className = "table-empty";
          c.textContent = "No operational expenses recorded in the selected jurisdiction.";
        } else {
          records.forEach((e) => {
            const r = officerExpensesBody.insertRow();
            r.insertCell().textContent = e.expense_date || "—";
            r.insertCell().innerHTML = `<strong>${escapeHtml(e.farmer_name)}</strong>`;
            r.insertCell().textContent = `${e.farm_name}${e.crop_name ? ' (' + e.crop_name + ')' : ''}`;
            r.insertCell().innerHTML = `<span class="status-badge badge--info">${escapeHtml(e.expense_category)}</span>`;
            r.insertCell().textContent = e.rental_name || e.energy_name || "—";
            r.insertCell().innerHTML = `<strong>₹${parseFloat(e.amount || 0).toLocaleString()}</strong>`;
            r.insertCell().textContent = e.description || "—";
            r.insertCell().textContent = e.panchayath_name || "—";
          });
        }
      }

      // 4. Harvest Sales / Income
      if (officerIncomeBody) {
        officerIncomeBody.replaceChildren();
        const records = iRes.records || [];
        if (!records.length) {
          const r = officerIncomeBody.insertRow();
          const c = r.insertCell();
          c.colSpan = 8;
          c.className = "table-empty";
          c.textContent = "No harvest sales recorded in the selected jurisdiction.";
        } else {
          records.forEach((inc) => {
            const r = officerIncomeBody.insertRow();
            r.insertCell().textContent = inc.sale_date || "—";
            r.insertCell().innerHTML = `<strong>${escapeHtml(inc.farmer_name)}</strong>`;
            r.insertCell().textContent = `${inc.farm_name} (${inc.crop_name})`;
            r.insertCell().textContent = `${inc.quantity_sold} ${inc.unit || 'kg'}`;
            r.insertCell().textContent = `₹${parseFloat(inc.price_per_unit || 0).toLocaleString()}`;
            r.insertCell().innerHTML = `<strong style="color:#287647;">₹${parseFloat(inc.total_income || 0).toLocaleString()}</strong>`;
            r.insertCell().textContent = inc.buyer_name || "—";
            r.insertCell().textContent = inc.panchayath_name || "—";
          });
        }
      }

      // 5. Fertilizers
      if (officerFertBody) {
        officerFertBody.replaceChildren();
        const records = ftRes.records || [];
        if (!records.length) {
          const r = officerFertBody.insertRow();
          const c = r.insertCell();
          c.colSpan = 8;
          c.className = "table-empty";
          c.textContent = "No fertilizer application logs found in the selected jurisdiction.";
        } else {
          records.forEach((f) => {
            const r = officerFertBody.insertRow();
            r.insertCell().textContent = f.application_date || "—";
            r.insertCell().innerHTML = `<strong>${escapeHtml(f.farmer_name)}</strong>`;
            r.insertCell().textContent = `${f.farm_name} (${f.crop_name})`;
            r.insertCell().innerHTML = `<strong>${escapeHtml(f.fertilizer_name)}</strong>`;
            r.insertCell().textContent = f.fertilizer_type || "—";
            r.insertCell().textContent = `${f.quantity} ${f.unit || 'kg'}`;
            r.insertCell().textContent = `₹${parseFloat(f.total_cost || 0).toLocaleString()}`;
            r.insertCell().textContent = f.panchayath_name || "—";
          });
        }
      }

      // 6. Labour
      if (officerLabourBody) {
        officerLabourBody.replaceChildren();
        const records = lRes.records || [];
        if (!records.length) {
          const r = officerLabourBody.insertRow();
          const c = r.insertCell();
          c.colSpan = 8;
          c.className = "table-empty";
          c.textContent = "No labour activity logged in the selected jurisdiction.";
        } else {
          records.forEach((l) => {
            const r = officerLabourBody.insertRow();
            r.insertCell().textContent = l.work_date || "—";
            r.insertCell().innerHTML = `<strong>${escapeHtml(l.farmer_name)}</strong>`;
            r.insertCell().textContent = `${l.farm_name} (${l.crop_name})`;
            r.insertCell().innerHTML = `<strong>${escapeHtml(l.labour_name)}</strong>`;
            r.insertCell().textContent = `${l.worker_count} workers`;
            r.insertCell().textContent = `${l.days_worked} days`;
            r.insertCell().textContent = `₹${parseFloat(l.total_cost || 0).toLocaleString()}`;
            r.insertCell().textContent = l.panchayath_name || "—";
          });
        }
      }
    } catch (err) {
      console.error("Error loading jurisdiction records:", err);
    }
  }

  async function reloadAllOfficerData() {
    await Promise.all([
      loadFarmers(),
      loadJurisdictionRecords(),
    ]);
  }

  filterSelect.addEventListener("change", reloadAllOfficerData);
  await loadCatalog("crops");
  await loadOfficerStats();
  await reloadAllOfficerData();
  await loadOfficerSubsidies();
}

// =========================================================================
// Phase 3: Farmer Dashboard & All 7 Subsystems
// =========================================================================

async function initializeFarmerDashboard() {
  const page = document.querySelector("[data-farmer-dashboard]");
  if (!page) return;

  const session = requireSession("FARMER");
  if (!session) return;

  const { user } = session;
  const status = page.querySelector(".dashboard-status");

  // Profile credentials display helper
  function updateFarmerProfileDisplay(u) {
    page.querySelector("[data-farmer-name]").textContent = u.full_name || u.email || "Farmer";
    page.querySelector("[data-farmer-fullname]").textContent = u.full_name || "—";
    page.querySelector("[data-farmer-email]").textContent = u.email || "—";
    page.querySelector("[data-farmer-phone]").textContent = u.phone || "—";
    page.querySelector("[data-farmer-panchayath]").textContent = u.panchayath_name || "—";
    page.querySelector("[data-farmer-address]").textContent = u.address || "—";
  }
  updateFarmerProfileDisplay(session.user);

  // Reusable Edit Modal Handler
  function openEditModal(title, fields, onSubmit) {
    const modal = page.querySelector("#edit-modal");
    const modalTitle = page.querySelector("#edit-modal-title");
    const modalForm = page.querySelector("#edit-modal-form");
    const modalFields = page.querySelector("#edit-modal-fields");
    if (!modal || !modalForm || !modalFields) return;

    modalTitle.textContent = title;
    modalFields.replaceChildren();

    fields.forEach((field) => {
      const label = document.createElement("label");
      label.className = "form-field";
      if (field.span) {
        label.style.gridColumn = `span ${field.span}`;
      }
      label.textContent = field.label;

      let input;
      if (field.type === "select") {
        input = document.createElement("select");
        input.className = "form-select";
        (field.options || []).forEach((opt) => {
          const o = document.createElement("option");
          o.value = opt.value;
          o.textContent = opt.text;
          if (String(opt.value) === String(field.value)) o.selected = true;
          input.append(o);
        });
      } else {
        input = document.createElement("input");
        input.type = field.type || "text";
        if (field.step) input.step = field.step;
        if (field.min !== undefined) input.min = field.min;
        if (field.readonly) input.readOnly = true;
        input.value = field.value !== undefined && field.value !== null ? field.value : "";
        if (field.placeholder) input.placeholder = field.placeholder;
      }
      input.name = field.name;
      if (field.required) input.required = true;
      label.append(input);
      modalFields.append(label);
    });

    const closeBtn = page.querySelector("#edit-modal-close");
    const cancelBtn = page.querySelector("#edit-modal-cancel");
    function closeModal() {
      modal.style.display = "none";
      modalForm.onsubmit = null;
    }
    if (closeBtn) closeBtn.onclick = closeModal;
    if (cancelBtn) cancelBtn.onclick = closeModal;

    modalForm.onsubmit = async (e) => {
      e.preventDefault();
      const submitBtn = page.querySelector("#edit-modal-submit");
      if (submitBtn) submitBtn.disabled = true;
      try {
        const formData = new FormData(modalForm);
        await onSubmit(formData);
        closeModal();
      } catch (err) {
        alert("Error updating record: " + err.message);
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    };

    modal.style.display = "flex";
  }

  function createEditButton(onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "action-btn action-btn--edit";
    btn.innerHTML = "✏️ Edit";
    btn.addEventListener("click", onClick);
    return btn;
  }

  // Cache master lookup data for dropdowns
  let refData = {};
  try {
    refData = await apiRequest("/api/reference-data", { token: session.token });
  } catch (err) {
    showStatus(status, "Error loading master catalogs: " + err.message, true);
  }

  // 8. Farmer Profile Record Editor
  page.querySelector("#edit-profile-btn")?.addEventListener("click", () => {
    const panchOptions = (refData.panchayaths || []).map((p) => ({
      value: p.panchayath_id,
      text: `${p.panchayath_name} (${p.district || ''})`,
    }));
    openEditModal(
      "Edit Farmer Profile Record",
      [
        { name: "full_name", label: "Full Name", type: "text", required: true, value: session.user.full_name || "" },
        { name: "phone", label: "Phone Number", type: "text", required: true, value: session.user.phone || "" },
        { name: "panchayath_id", label: "Governing Gram Panchayath", type: "select", required: true, value: session.user.panchayath_id || "", options: panchOptions },
        { name: "address", label: "Residential Address", type: "text", span: 2, required: true, value: session.user.address || "" },
      ],
      async (fd) => {
        const res = await apiRequest("/api/users/profile", {
          method: "PUT",
          body: {
            full_name: fd.get("full_name"),
            phone: fd.get("phone"),
            panchayath_id: parseInt(fd.get("panchayath_id")),
            address: fd.get("address"),
          },
          token: session.token,
        });
        session.user = { ...session.user, ...res.user };
        localStorage.setItem("user", JSON.stringify(session.user));
        updateFarmerProfileDisplay(session.user);
        showStatus(status, "Farmer profile updated successfully!");
        await loadOverview();
      }
    );
  });

  // Populate static dropdowns from reference data (Enforce Rice & Wheat Only)
  const allowedCrops = (refData.crops || []).filter((c) =>
    ["rice", "wheat"].includes(c.crop_name.toLowerCase())
  );
  fillSelect(page.querySelector("#select-crop-type"), allowedCrops, "crop_id", "crop_name", "Select crop (Rice or Wheat)…");
  fillSelect(page.querySelector("#select-expense-rental"), refData.rental_types, "rental_id", "rental_name", "None (No Machinery Rental)");
  fillSelect(page.querySelector("#select-expense-energy"), refData.energy_types, "energy_id", "energy_name", "None (No Energy/Fuel)");
  fillSelect(page.querySelector("#select-fert-type"), refData.fertilizers, "fertilizer_id", "fertilizer_name", "Select a fertilizer…");
  fillSelect(page.querySelector("#select-labour-type"), refData.labour_types, "labour_id", "labour_name", "Select labour activity…");
  fillSelect(page.querySelector("#select-subsidy-type"), refData.subsidies, "subsidy_id", "subsidy_name", "Select a government scheme…");

  // Auto-calculation: Harvest sale total
  const incomeQty = page.querySelector("#income-qty");
  const incomePrice = page.querySelector("#income-price");
  const incomeTotal = page.querySelector("#income-total");
  function recalcIncome() {
    const q = parseFloat(incomeQty?.value || 0);
    const p = parseFloat(incomePrice?.value || 0);
    if (incomeTotal) incomeTotal.value = (q * p).toFixed(2);
  }
  incomeQty?.addEventListener("input", recalcIncome);
  incomePrice?.addEventListener("input", recalcIncome);

  // Auto-calculation: Labour rate
  const labourWorkers = page.querySelector("#labour-workers");
  const labourDays = page.querySelector("#labour-days");
  const labourSelect = page.querySelector("#select-labour-type");
  const labourCost = page.querySelector("#labour-cost");
  function recalcLabour() {
    const selectedId = parseInt(labourSelect?.value || 0);
    const item = (refData.labour_types || []).find((l) => l.labour_id === selectedId);
    const rate = item ? parseFloat(item.standard_daily_rate) : 850;
    const w = parseInt(labourWorkers?.value || 1);
    const d = parseFloat(labourDays?.value || 1);
    if (labourCost) labourCost.value = (w * d * rate).toFixed(2);
  }
  labourWorkers?.addEventListener("input", recalcLabour);
  labourDays?.addEventListener("input", recalcLabour);
  labourSelect?.addEventListener("change", recalcLabour);

  // Load and render all 7 tables
  async function loadOverview() {
    try {
      const data = await apiRequest("/api/farmer/overview", { token: session.token });

      // 1. KPI Stats
      const stats = data.stats || {};
      page.querySelector("#stat-farmer-farms").textContent = String(stats.total_farms || 0);
      page.querySelector("#stat-farmer-crops").textContent = String(stats.total_crops || 0);
      page.querySelector("#stat-farmer-expenses").textContent = `₹${parseFloat(stats.total_expenses || 0).toLocaleString()}`;
      page.querySelector("#stat-farmer-income").textContent = `₹${parseFloat(stats.total_income || 0).toLocaleString()}`;
      page.querySelector("#stat-farmer-subsidies").textContent = `₹${parseFloat(stats.approved_subsidies || 0).toLocaleString()}`;

      const profitEl = page.querySelector("#stat-farmer-profit");
      const profit = parseFloat(stats.net_balance || 0);
      profitEl.textContent = `₹${profit.toLocaleString()}`;
      profitEl.className = `stat-value ${profit >= 0 ? 'stat-value--positive' : 'stat-value--negative'}`;

      // Update farm dropdowns for crop, expense, and subsidy forms
      const farms = data.farms || [];
      fillSelect(page.querySelector("#select-crop-farm"), farms, "farm_id", "farm_name", "Select a farm plot…");
      fillSelect(page.querySelector("#select-expense-farm"), farms, "farm_id", "farm_name", "Select a farm plot…");
      const subFarmSelect = page.querySelector("#select-subsidy-farm");
      if (subFarmSelect) {
        fillSelect(subFarmSelect, farms, "farm_id", "farm_name", "Select target farm plot (optional)…");
        subFarmSelect.onchange = () => {
          const selectedF = farms.find((f) => Number(f.farm_id) === Number(subFarmSelect.value));
          const remInput = page.querySelector("#subsidy-remarks-input");
          if (selectedF && remInput && (!remInput.value || remInput.value.startsWith("Holding:"))) {
            remInput.value = `Holding: ${selectedF.farm_name} (${selectedF.location}, ${selectedF.area_acres} acres, ${selectedF.soil_type})`;
          }
        };
      }

      // Update crop dropdowns for expense, income, fertilizer, labour forms
      const crops = data.crops || [];
      const cropOptions = crops.map((c) => ({
        id: c.farm_crop_id,
        label: `${c.crop_name} (${c.farm_name} • ${c.season})`,
      }));
      fillSelect(page.querySelector("#select-expense-crop"), cropOptions, "id", "label", "None (General Farm Cost)");
      fillSelect(page.querySelector("#select-income-crop"), cropOptions, "id", "label", "Select harvested crop cycle…");
      fillSelect(page.querySelector("#select-fert-crop"), cropOptions, "id", "label", "Select crop cycle…");
      fillSelect(page.querySelector("#select-labour-crop"), cropOptions, "id", "label", "Select crop cycle…");

      // --- Render Table 1: Farms ---
      const farmsBody = page.querySelector("#farmer-farms-body");
      farmsBody.replaceChildren();
      if (!farms.length) {
        farmsBody.innerHTML = `<tr><td class="table-empty" colspan="7">No farm plots registered yet. Click "+ Register New Farm" above.</td></tr>`;
      } else {
        farms.forEach((f) => {
          const row = farmsBody.insertRow();
          row.insertCell().textContent = `#${f.farm_id}`;
          row.insertCell().textContent = f.farm_name;
          row.insertCell().textContent = f.location;
          row.insertCell().textContent = `${f.area_acres} Acres`;
          row.insertCell().textContent = f.soil_type || "—";
          row.insertCell().textContent = f.irrigation_type || "—";

          const actionCell = row.insertCell();
          const editBtn = createEditButton(() => {
            openEditModal(
              `Edit Farm Plot #${f.farm_id}`,
              [
                { name: "farm_name", label: "Farm Name", type: "text", required: true, value: f.farm_name },
                { name: "location", label: "Location / Village", type: "text", required: true, value: f.location },
                { name: "area_acres", label: "Area (Acres)", type: "number", step: "0.01", min: 0.05, required: true, value: f.area_acres },
                {
                  name: "soil_type",
                  label: "Soil Type",
                  type: "select",
                  value: f.soil_type || "Clay Loam",
                  options: ["Clay Loam", "Alluvial", "Laterite", "Sandy Loam", "Red Soil"].map((v) => ({ value: v, text: v })),
                },
                {
                  name: "irrigation_type",
                  label: "Irrigation System",
                  type: "select",
                  span: 2,
                  value: f.irrigation_type || "Canal Irrigation",
                  options: ["Canal Irrigation", "Borewell & Pump", "Drip Irrigation", "Sprinkler Irrigation", "Rainfed"].map((v) => ({ value: v, text: v })),
                },
              ],
              async (fd) => {
                await apiRequest("/api/farmer/farms", {
                  method: "PUT",
                  body: {
                    farm_id: f.farm_id,
                    farm_name: fd.get("farm_name"),
                    location: fd.get("location"),
                    area_acres: parseFloat(fd.get("area_acres")),
                    soil_type: fd.get("soil_type"),
                    irrigation_type: fd.get("irrigation_type"),
                  },
                  token: session.token,
                });
                showStatus(status, `Farm #${f.farm_id} updated successfully!`);
                await loadOverview();
              }
            );
          });
          actionCell.append(editBtn);
        });
      }

      // --- Render Table 2: Crops ---
      const cropsBody = page.querySelector("#farmer-crops-body");
      cropsBody.replaceChildren();
      if (!crops.length) {
        cropsBody.innerHTML = `<tr><td class="table-empty" colspan="9">No active crop plantings recorded. Click "+ Plant New Crop" above.</td></tr>`;
      } else {
        crops.forEach((c) => {
          const row = cropsBody.insertRow();
          row.insertCell().textContent = `#${c.farm_crop_id}`;
          row.insertCell().textContent = c.crop_name;
          row.insertCell().textContent = c.farm_name;
          row.insertCell().textContent = c.season || "—";
          row.insertCell().textContent = `${c.cultivated_area_acres || '—'} Acres`;
          row.insertCell().textContent = c.planting_date || "—";
          row.insertCell().textContent = c.expected_harvest_date || "—";

          const statusCell = row.insertCell();
          const badge = document.createElement("span");
          const st = String(c.status || "GROWING").toUpperCase();
          badge.className = `status-badge badge--${st.toLowerCase()}`;
          badge.textContent = st;
          statusCell.append(badge);

          const actionCell = row.insertCell();
          const editBtn = createEditButton(() => {
            openEditModal(
              `Edit Crop Cycle #${c.farm_crop_id}`,
              [
                {
                  name: "farm_id",
                  label: "Target Farm Plot",
                  type: "select",
                  required: true,
                  value: c.farm_id,
                  options: farms.map((fm) => ({ value: fm.farm_id, text: fm.farm_name })),
                },
                {
                  name: "crop_id",
                  label: "Crop Variety (Rice & Wheat Only)",
                  type: "select",
                  required: true,
                  value: c.crop_id,
                  options: allowedCrops.map((cr) => ({ value: cr.crop_id, text: cr.crop_name })),
                },
                {
                  name: "season",
                  label: "Agricultural Season",
                  type: "select",
                  value: c.season || "Kharif",
                  options: ["Kharif", "Rabi", "Mundakan", "Virippu", "Puncha"].map((v) => ({ value: v, text: v })),
                },
                {
                  name: "cultivated_area_acres",
                  label: "Cultivated Area (Acres)",
                  type: "number",
                  step: "0.01",
                  min: 0.05,
                  required: true,
                  value: c.cultivated_area_acres,
                },
                {
                  name: "planting_date",
                  label: "Planting Date",
                  type: "date",
                  required: true,
                  value: c.planting_date,
                },
                {
                  name: "expected_harvest_date",
                  label: "Expected Harvest Date",
                  type: "date",
                  value: c.expected_harvest_date || "",
                },
                {
                  name: "actual_harvest_date",
                  label: "Actual Harvest Date (Optional)",
                  type: "date",
                  value: c.actual_harvest_date || "",
                },
                {
                  name: "status",
                  label: "Crop Status",
                  type: "select",
                  value: c.status || "GROWING",
                  options: ["GROWING", "PLANNED", "HARVESTED", "FAILED"].map((v) => ({ value: v, text: v })),
                },
              ],
              async (fd) => {
                await apiRequest("/api/farmer/crops", {
                  method: "PUT",
                  body: {
                    farm_crop_id: c.farm_crop_id,
                    farm_id: parseInt(fd.get("farm_id")),
                    crop_id: parseInt(fd.get("crop_id")),
                    season: fd.get("season"),
                    planting_date: fd.get("planting_date"),
                    expected_harvest_date: fd.get("expected_harvest_date") || null,
                    actual_harvest_date: fd.get("actual_harvest_date") || null,
                    cultivated_area_acres: parseFloat(fd.get("cultivated_area_acres")),
                    status: fd.get("status"),
                  },
                  token: session.token,
                });
                showStatus(status, `Crop Cycle #${c.farm_crop_id} updated successfully!`);
                await loadOverview();
              }
            );
          });
          actionCell.append(editBtn);
        });
      }

      // --- Render Table 3: Expenses ---
      const expensesBody = page.querySelector("#farmer-expenses-body");
      expensesBody.replaceChildren();
      const expenses = data.expenses || [];
      if (!expenses.length) {
        expensesBody.innerHTML = `<tr><td class="table-empty" colspan="7">No expenses recorded yet. Click "+ Record Expense" to log costs.</td></tr>`;
      } else {
        expenses.forEach((e) => {
          const row = expensesBody.insertRow();
          row.insertCell().textContent = e.expense_date || "—";
          row.insertCell().textContent = e.crop_name ? `${e.farm_name} (${e.crop_name})` : e.farm_name;
          row.insertCell().textContent = e.expense_category;
          row.insertCell().textContent = e.rental_name || e.energy_name || "Standard";
          row.insertCell().textContent = `₹${parseFloat(e.amount).toLocaleString()}`;
          row.insertCell().textContent = e.description || "—";

          const actionCell = row.insertCell();
          const editBtn = createEditButton(() => {
            openEditModal(
              `Edit Farm Expense #${e.expense_id}`,
              [
                {
                  name: "farm_id",
                  label: "Farm Plot",
                  type: "select",
                  required: true,
                  value: e.farm_id,
                  options: farms.map((fm) => ({ value: fm.farm_id, text: fm.farm_name })),
                },
                {
                  name: "farm_crop_id",
                  label: "Linked Crop Cycle (Optional)",
                  type: "select",
                  value: e.farm_crop_id || "",
                  options: [{ value: "", text: "None (General Farm Expense)" }, ...cropOptions.map((co) => ({ value: co.id, text: co.label }))],
                },
                {
                  name: "expense_category",
                  label: "Expense Category",
                  type: "select",
                  value: e.expense_category || "OTHER",
                  options: ["SEEDS", "RENTAL", "ENERGY", "IRRIGATION", "TRANSPORT", "OTHER"].map((v) => ({ value: v, text: v })),
                },
                {
                  name: "rental_id",
                  label: "Rental Machinery (Optional)",
                  type: "select",
                  value: e.rental_id || "",
                  options: [{ value: "", text: "None" }, ...(refData.rental_types || []).map((r) => ({ value: r.rental_id, text: r.rental_name }))],
                },
                {
                  name: "energy_id",
                  label: "Energy Source (Optional)",
                  type: "select",
                  value: e.energy_id || "",
                  options: [{ value: "", text: "None" }, ...(refData.energy_types || []).map((en) => ({ value: en.energy_id, text: en.energy_name }))],
                },
                {
                  name: "amount",
                  label: "Amount (₹)",
                  type: "number",
                  step: "0.01",
                  min: 1,
                  required: true,
                  value: e.amount,
                },
                {
                  name: "expense_date",
                  label: "Expense Date",
                  type: "date",
                  required: true,
                  value: e.expense_date,
                },
                {
                  name: "description",
                  label: "Description / Details",
                  type: "text",
                  span: 2,
                  required: true,
                  value: e.description || "",
                },
              ],
              async (fd) => {
                await apiRequest("/api/farmer/expenses", {
                  method: "PUT",
                  body: {
                    expense_id: e.expense_id,
                    farm_id: parseInt(fd.get("farm_id")),
                    farm_crop_id: fd.get("farm_crop_id") ? parseInt(fd.get("farm_crop_id")) : null,
                    expense_category: fd.get("expense_category"),
                    rental_id: fd.get("rental_id") ? parseInt(fd.get("rental_id")) : null,
                    energy_id: fd.get("energy_id") ? parseInt(fd.get("energy_id")) : null,
                    amount: parseFloat(fd.get("amount")),
                    expense_date: fd.get("expense_date"),
                    description: fd.get("description"),
                  },
                  token: session.token,
                });
                showStatus(status, "Expense record updated successfully!");
                await loadOverview();
              }
            );
          });
          actionCell.append(editBtn);
        });
      }

      // --- Render Table 4: Income ---
      const incomeBody = page.querySelector("#farmer-income-body");
      incomeBody.replaceChildren();
      const incomeList = data.income || [];
      if (!incomeList.length) {
        incomeBody.innerHTML = `<tr><td class="table-empty" colspan="8">No harvest sales recorded yet. Click "+ Record Produce Sale" to log revenues.</td></tr>`;
      } else {
        incomeList.forEach((inc) => {
          const row = incomeBody.insertRow();
          row.insertCell().textContent = inc.sale_date || "—";
          row.insertCell().textContent = inc.crop_name;
          row.insertCell().textContent = inc.farm_name;
          row.insertCell().textContent = `${inc.quantity_sold} ${inc.unit}`;
          row.insertCell().textContent = `₹${parseFloat(inc.price_per_unit).toLocaleString()} / ${inc.unit}`;
          row.insertCell().textContent = `₹${parseFloat(inc.total_income).toLocaleString()}`;
          row.insertCell().textContent = inc.buyer_name || "—";

          const actionCell = row.insertCell();
          const editBtn = createEditButton(() => {
            openEditModal(
              `Edit Produce Sale #${inc.income_id}`,
              [
                {
                  name: "farm_crop_id",
                  label: "Harvested Crop Cycle",
                  type: "select",
                  required: true,
                  value: inc.farm_crop_id,
                  options: cropOptions.map((co) => ({ value: co.id, text: co.label })),
                },
                {
                  name: "sale_date",
                  label: "Sale Date",
                  type: "date",
                  required: true,
                  value: inc.sale_date,
                },
                {
                  name: "buyer_name",
                  label: "Buyer / Market Name",
                  type: "text",
                  required: true,
                  value: inc.buyer_name || "",
                },
                {
                  name: "quantity_sold",
                  label: "Quantity Sold",
                  type: "number",
                  step: "0.01",
                  min: 0.1,
                  required: true,
                  value: inc.quantity_sold,
                },
                {
                  name: "unit",
                  label: "Unit of Measurement",
                  type: "select",
                  value: inc.unit || "kg",
                  options: ["kg", "quintal", "ton", "bunches"].map((v) => ({ value: v, text: v })),
                },
                {
                  name: "price_per_unit",
                  label: "Price per Unit (₹)",
                  type: "number",
                  step: "0.01",
                  min: 0.1,
                  required: true,
                  value: inc.price_per_unit,
                },
              ],
              async (fd) => {
                await apiRequest("/api/farmer/income", {
                  method: "PUT",
                  body: {
                    income_id: inc.income_id,
                    farm_crop_id: parseInt(fd.get("farm_crop_id")),
                    sale_date: fd.get("sale_date"),
                    quantity_sold: parseFloat(fd.get("quantity_sold")),
                    unit: fd.get("unit"),
                    price_per_unit: parseFloat(fd.get("price_per_unit")),
                    buyer_name: fd.get("buyer_name"),
                  },
                  token: session.token,
                });
                showStatus(status, "Harvest sale record updated!");
                await loadOverview();
              }
            );
          });
          actionCell.append(editBtn);
        });
      }

      // --- Render Table 5: Fertilizers ---
      const fertBody = page.querySelector("#farmer-fert-body");
      fertBody.replaceChildren();
      const fertList = data.fertilizers || [];
      if (!fertList.length) {
        fertBody.innerHTML = `<tr><td class="table-empty" colspan="8">No fertilizer applications logged. Click "+ Log Fertilizer Application" above.</td></tr>`;
      } else {
        fertList.forEach((f) => {
          const row = fertBody.insertRow();
          row.insertCell().textContent = f.application_date || "—";
          row.insertCell().textContent = f.crop_name;
          row.insertCell().textContent = f.farm_name;
          row.insertCell().textContent = f.fertilizer_name;
          row.insertCell().textContent = f.fertilizer_type || "—";
          row.insertCell().textContent = `${f.quantity} ${f.unit || 'kg'}`;
          row.insertCell().textContent = `₹${parseFloat(f.total_cost).toLocaleString()}`;

          const actionCell = row.insertCell();
          const editBtn = createEditButton(() => {
            openEditModal(
              `Edit Fertilizer Application #${f.application_id}`,
              [
                {
                  name: "farm_crop_id",
                  label: "Crop Cycle",
                  type: "select",
                  required: true,
                  value: f.farm_crop_id,
                  options: cropOptions.map((co) => ({ value: co.id, text: co.label })),
                },
                {
                  name: "fertilizer_id",
                  label: "Fertilizer Type",
                  type: "select",
                  required: true,
                  value: f.fertilizer_id,
                  options: (refData.fertilizers || []).map((ft) => ({ value: ft.fertilizer_id, text: `${ft.fertilizer_name} (${ft.unit || 'kg'})` })),
                },
                {
                  name: "application_date",
                  label: "Application Date",
                  type: "date",
                  required: true,
                  value: f.application_date,
                },
                {
                  name: "quantity",
                  label: "Quantity Applied",
                  type: "number",
                  step: "0.1",
                  min: 0.1,
                  required: true,
                  value: f.quantity,
                },
                {
                  name: "total_cost",
                  label: "Total Nutrient Cost (₹)",
                  type: "number",
                  step: "0.01",
                  min: 0,
                  required: true,
                  value: f.total_cost,
                },
              ],
              async (fd) => {
                await apiRequest("/api/farmer/fertilizers", {
                  method: "PUT",
                  body: {
                    application_id: f.application_id,
                    farm_crop_id: parseInt(fd.get("farm_crop_id")),
                    fertilizer_id: parseInt(fd.get("fertilizer_id")),
                    application_date: fd.get("application_date"),
                    quantity: parseFloat(fd.get("quantity")),
                    total_cost: parseFloat(fd.get("total_cost")),
                  },
                  token: session.token,
                });
                showStatus(status, "Fertilizer application record updated!");
                await loadOverview();
              }
            );
          });
          actionCell.append(editBtn);
        });
      }

      // --- Render Table 6: Labour ---
      const labourBody = page.querySelector("#farmer-labour-body");
      labourBody.replaceChildren();
      const labourList = data.labour || [];
      if (!labourList.length) {
        labourBody.innerHTML = `<tr><td class="table-empty" colspan="8">No farm labour operations logged. Click "+ Log Labour Work" above.</td></tr>`;
      } else {
        labourList.forEach((l) => {
          const row = labourBody.insertRow();
          row.insertCell().textContent = l.work_date || "—";
          row.insertCell().textContent = l.crop_name;
          row.insertCell().textContent = l.farm_name;
          row.insertCell().textContent = l.labour_name;
          row.insertCell().textContent = `${l.worker_count} workers`;
          row.insertCell().textContent = `${l.days_worked} days`;
          row.insertCell().textContent = `₹${parseFloat(l.total_cost).toLocaleString()}`;

          const actionCell = row.insertCell();
          const editBtn = createEditButton(() => {
            openEditModal(
              `Edit Labour Operation #${l.labour_usage_id}`,
              [
                {
                  name: "farm_crop_id",
                  label: "Crop Cycle",
                  type: "select",
                  required: true,
                  value: l.farm_crop_id,
                  options: cropOptions.map((co) => ({ value: co.id, text: co.label })),
                },
                {
                  name: "labour_id",
                  label: "Labour Activity",
                  type: "select",
                  required: true,
                  value: l.labour_id,
                  options: (refData.labour_types || []).map((lt) => ({ value: lt.labour_id, text: `${lt.labour_name} (₹${lt.standard_daily_rate}/day)` })),
                },
                {
                  name: "work_date",
                  label: "Work Date",
                  type: "date",
                  required: true,
                  value: l.work_date,
                },
                {
                  name: "worker_count",
                  label: "Worker Count",
                  type: "number",
                  min: 1,
                  required: true,
                  value: l.worker_count,
                },
                {
                  name: "days_worked",
                  label: "Days Worked",
                  type: "number",
                  step: "0.5",
                  min: 0.5,
                  required: true,
                  value: l.days_worked,
                },
                {
                  name: "total_cost",
                  label: "Total Wage Cost (₹)",
                  type: "number",
                  step: "0.01",
                  min: 0,
                  required: true,
                  value: l.total_cost,
                },
              ],
              async (fd) => {
                await apiRequest("/api/farmer/labour", {
                  method: "PUT",
                  body: {
                    labour_usage_id: l.labour_usage_id,
                    farm_crop_id: parseInt(fd.get("farm_crop_id")),
                    labour_id: parseInt(fd.get("labour_id")),
                    work_date: fd.get("work_date"),
                    worker_count: parseInt(fd.get("worker_count")),
                    days_worked: parseFloat(fd.get("days_worked")),
                    total_cost: parseFloat(fd.get("total_cost")),
                  },
                  token: session.token,
                });
                showStatus(status, "Labour operation updated!");
                await loadOverview();
              }
            );
          });
          actionCell.append(editBtn);
        });
      }

      // --- Render Table 7: Subsidies ---
      const subsidiesBody = page.querySelector("#farmer-subsidies-body");
      subsidiesBody.replaceChildren();
      const subsidiesList = data.subsidies || [];
      if (!subsidiesList.length) {
        subsidiesBody.innerHTML = `<tr><td class="table-empty" colspan="8">No government subsidy applications recorded. Click "+ Apply for Scheme" above.</td></tr>`;
      } else {
        subsidiesList.forEach((s) => {
          const row = subsidiesBody.insertRow();
          row.insertCell().textContent = s.subsidy_name;
          row.insertCell().textContent = s.application_date || "—";
          row.insertCell().textContent = `₹${parseFloat(s.amount).toLocaleString()}`;

          const statusCell = row.insertCell();
          const badge = document.createElement("span");
          const st = String(s.status || "PENDING").toUpperCase();
          badge.className = `status-badge badge--${st.toLowerCase()}`;
          badge.textContent = st;
          statusCell.append(badge);

          const grantCell = row.insertCell();
          if (st === "APPROVED" || st === "PAID") {
            grantCell.innerHTML = `<strong>₹${parseFloat(s.approved_amount).toLocaleString()}</strong> <small style="color:#176532;">(Disbursed)</small>`;
          } else {
            grantCell.innerHTML = `<span style="color:#8f6805; font-style:italic;">₹0.00 (Pending Officer Approval)</span>`;
          }

          let officerDisplay = "Assigned Officer";
          if (s.officer_name) {
            officerDisplay = `${s.officer_name} (${s.panchayath_name || 'Governing AO'})`;
          } else if (st === "PENDING") {
            officerDisplay = `Awaiting AO (${s.panchayath_name || 'Your Panchayath'})`;
          }
          row.insertCell().textContent = officerDisplay;
          row.insertCell().textContent = s.remarks || "—";

          const actionCell = row.insertCell();
          if (st === "PENDING") {
            const editBtn = createEditButton(() => {
              openEditModal(
                `Edit Subsidy Application #${s.farmer_subsidy_id}`,
                [
                  {
                    name: "subsidy_id",
                    label: "State Government Scheme",
                    type: "select",
                    required: true,
                    value: s.subsidy_id,
                    options: (refData.subsidies || []).map((sub) => ({ value: sub.subsidy_id, text: `${sub.subsidy_name} (Max ₹${sub.amount})` })),
                  },
                  {
                    name: "application_date",
                    label: "Application Date",
                    type: "date",
                    required: true,
                    value: s.application_date,
                  },
                  {
                    name: "remarks",
                    label: "Remarks / Land Eligibility Note",
                    type: "text",
                    span: 2,
                    required: true,
                    value: s.remarks || "",
                  },
                ],
                async (fd) => {
                  await apiRequest("/api/farmer/subsidies", {
                    method: "PUT",
                    body: {
                      farmer_subsidy_id: s.farmer_subsidy_id,
                      subsidy_id: parseInt(fd.get("subsidy_id")),
                      application_date: fd.get("application_date"),
                      remarks: fd.get("remarks"),
                    },
                    token: session.token,
                  });
                  showStatus(status, `Subsidy application #${s.farmer_subsidy_id} updated!`);
                  await loadOverview();
                }
              );
            });
            actionCell.append(editBtn);
          } else {
            actionCell.innerHTML = `<span style="color:#687067; font-size:0.82rem;">🔒 Approved</span>`;
          }
        });
      }
    } catch (err) {
      showStatus(status, "Error loading farm data: " + err.message, true);
    }
  }

  // --- Form 1: Add Farm Submission ---
  page.querySelector("#add-farm-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submit = form.querySelector('[type="submit"]');
    const fd = new FormData(form);
    submit.disabled = true;
    try {
      await apiRequest("/api/farmer/farms", {
        method: "POST",
        body: {
          farm_name: fd.get("farm_name"),
          location: fd.get("location"),
          area_acres: parseFloat(fd.get("area_acres")),
          soil_type: fd.get("soil_type"),
          irrigation_type: fd.get("irrigation_type"),
        },
        token: session.token,
      });
      form.reset();
      form.hidden = true;
      showStatus(status, "Farm plot registered successfully!");
      await loadOverview();
    } catch (err) {
      showStatus(status, err.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  // --- Form 2: Plant Crop Submission ---
  page.querySelector("#add-crop-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submit = form.querySelector('[type="submit"]');
    const fd = new FormData(form);
    submit.disabled = true;
    try {
      await apiRequest("/api/farmer/crops", {
        method: "POST",
        body: {
          farm_id: parseInt(fd.get("farm_id")),
          crop_id: parseInt(fd.get("crop_id")),
          season: fd.get("season"),
          cultivated_area_acres: parseFloat(fd.get("cultivated_area_acres")),
          planting_date: fd.get("planting_date"),
          expected_harvest_date: fd.get("expected_harvest_date") || null,
          status: fd.get("status"),
        },
        token: session.token,
      });
      form.reset();
      form.hidden = true;
      showStatus(status, "Crop cycle planted successfully!");
      await loadOverview();
    } catch (err) {
      showStatus(status, err.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  // --- Form 3: Add Expense Submission ---
  page.querySelector("#add-expense-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submit = form.querySelector('[type="submit"]');
    const fd = new FormData(form);
    submit.disabled = true;
    try {
      await apiRequest("/api/farmer/expenses", {
        method: "POST",
        body: {
          farm_id: parseInt(fd.get("farm_id")),
          farm_crop_id: fd.get("farm_crop_id") ? parseInt(fd.get("farm_crop_id")) : null,
          expense_category: fd.get("expense_category"),
          rental_id: fd.get("rental_id") ? parseInt(fd.get("rental_id")) : null,
          energy_id: fd.get("energy_id") ? parseInt(fd.get("energy_id")) : null,
          amount: parseFloat(fd.get("amount")),
          expense_date: fd.get("expense_date"),
          description: fd.get("description"),
        },
        token: session.token,
      });
      form.reset();
      form.hidden = true;
      showStatus(status, "Expense recorded successfully!");
      await loadOverview();
    } catch (err) {
      showStatus(status, err.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  // --- Form 4: Add Income Submission ---
  page.querySelector("#add-income-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submit = form.querySelector('[type="submit"]');
    const fd = new FormData(form);
    submit.disabled = true;
    try {
      await apiRequest("/api/farmer/income", {
        method: "POST",
        body: {
          farm_crop_id: parseInt(fd.get("farm_crop_id")),
          sale_date: fd.get("sale_date"),
          quantity_sold: parseFloat(fd.get("quantity_sold")),
          unit: fd.get("unit"),
          price_per_unit: parseFloat(fd.get("price_per_unit")),
          total_income: parseFloat(fd.get("total_income")),
          buyer_name: fd.get("buyer_name"),
        },
        token: session.token,
      });
      form.reset();
      form.hidden = true;
      showStatus(status, "Produce sale recorded successfully!");
      await loadOverview();
    } catch (err) {
      showStatus(status, err.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  // --- Form 5: Add Fertilizer Submission ---
  page.querySelector("#add-fertilizer-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submit = form.querySelector('[type="submit"]');
    const fd = new FormData(form);
    submit.disabled = true;
    try {
      await apiRequest("/api/farmer/fertilizers", {
        method: "POST",
        body: {
          farm_crop_id: parseInt(fd.get("farm_crop_id")),
          fertilizer_id: parseInt(fd.get("fertilizer_id")),
          application_date: fd.get("application_date"),
          quantity: parseFloat(fd.get("quantity")),
          total_cost: parseFloat(fd.get("total_cost")),
        },
        token: session.token,
      });
      form.reset();
      form.hidden = true;
      showStatus(status, "Fertilizer application logged!");
      await loadOverview();
    } catch (err) {
      showStatus(status, err.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  // --- Form 6: Add Labour Submission ---
  page.querySelector("#add-labour-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submit = form.querySelector('[type="submit"]');
    const fd = new FormData(form);
    submit.disabled = true;
    try {
      await apiRequest("/api/farmer/labour", {
        method: "POST",
        body: {
          farm_crop_id: parseInt(fd.get("farm_crop_id")),
          labour_id: parseInt(fd.get("labour_id")),
          work_date: fd.get("work_date"),
          worker_count: parseInt(fd.get("worker_count")),
          days_worked: parseFloat(fd.get("days_worked")),
          total_cost: parseFloat(fd.get("total_cost")),
        },
        token: session.token,
      });
      form.reset();
      form.hidden = true;
      showStatus(status, "Farm labour logged successfully!");
      await loadOverview();
    } catch (err) {
      showStatus(status, err.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  // --- Form 7: Apply Subsidy Submission ---
  page.querySelector("#apply-subsidy-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submit = form.querySelector('[type="submit"]');
    const fd = new FormData(form);
    submit.disabled = true;
    try {
      await apiRequest("/api/farmer/subsidies", {
        method: "POST",
        body: {
          subsidy_id: parseInt(fd.get("subsidy_id")),
          farm_id: fd.get("farm_id") ? parseInt(fd.get("farm_id")) : undefined,
          application_date: fd.get("application_date"),
          remarks: fd.get("remarks"),
        },
        token: session.token,
      });
      form.reset();
      form.hidden = true;
      showStatus(status, "Subsidy application submitted to Agriculture Office!");
      await loadOverview();
    } catch (err) {
      showStatus(status, err.message, true);
    } finally {
      submit.disabled = false;
    }
  });

  await loadOverview();
}

// =========================================================================
// Initialization Entry Point
// =========================================================================

function init() {
  attachLogoutListeners();
  setupFormToggles();
  initializeAuthPages();
  initializeProfileSetup();
  initializeOfficerDashboard();
  initializeFarmerDashboard();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
