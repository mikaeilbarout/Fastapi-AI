// Shared auth helpers. The access token lives in localStorage; the refresh
// token lives server-side in an httpOnly cookie the browser sends
// automatically, so JS never touches it directly.
const TOKEN_KEY = "access_token";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
window.getToken = getToken;

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// Calls POST /refresh, which reads the refresh_token cookie automatically.
// On success, stores the new access token and returns it; on failure (no
// cookie, expired, or already used), clears the stale token and returns null.
async function refreshAccessToken() {
  try {
    const res = await fetch("/refresh", { method: "POST", credentials: "same-origin" });
    if (!res.ok) {
      clearToken();
      return null;
    }
    const data = await res.json();
    setToken(data.access_token);
    return data.access_token;
  } catch (err) {
    return null;
  }
}

// Authenticated fetch: attaches the access token, and if it's expired (401),
// refreshes once via the cookie and retries the request automatically.
async function authFetch(url, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;

  let res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    const freshToken = await refreshAccessToken();
    if (freshToken) {
      res = await fetch(url, {
        ...options,
        headers: { ...(options.headers || {}), Authorization: `Bearer ${freshToken}` },
      });
    }
  }

  return res;
}
window.authFetch = authFetch;

async function logout() {
  try {
    await fetch("/logout", { method: "POST", credentials: "same-origin" });
  } catch (err) {
    // Best-effort server-side revoke; clear the local token regardless.
  }
  clearToken();
  window.location.href = "/";
}
window.logout = logout;

// FastAPI returns `detail` as a plain string for our own HTTPExceptions, but
// as a list of {msg, loc, ...} objects for Pydantic validation errors (422).
function extractErrorDetail(data) {
  if (!data) return null;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((e) => e.msg).join(" ");
  }
  return null;
}

function getNextParam() {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next") || "/";
  // Only allow internal paths, otherwise /login?next=https://evil.com would
  // bounce the user to an attacker's site right after they log in.
  if (!next.startsWith("/") || next.startsWith("//")) {
    return "/";
  }
  return next;
}

function showFormError(box, message) {
  box.textContent = message;
  box.style.display = "block";
}

async function handleLogin(event) {
  event.preventDefault();
  const form = event.target;
  const errorBox = document.getElementById("form-error");
  errorBox.style.display = "none";

  const payload = {
    email: form.email.value.trim(),
    password: form.password.value,
  };

  const submitBtn = form.querySelector("button[type=submit]");
  submitBtn.disabled = true;
  submitBtn.textContent = "Logging in...";

  try {
    const res = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showFormError(errorBox, extractErrorDetail(data) || "Log in failed.");
      return;
    }

    setToken(data.access_token);
    window.location.href = getNextParam();
  } catch (err) {
    showFormError(errorBox, "Could not reach the server. Please try again.");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Log in";
  }
}

async function handleSignup(event) {
  event.preventDefault();
  const form = event.target;
  const errorBox = document.getElementById("form-error");
  errorBox.style.display = "none";

  if (form.password.value !== form.confirm_password.value) {
    showFormError(errorBox, "Passwords do not match.");
    return;
  }

  // Backend's UserCreate schema calls this field "username" (it's stored as
  // the user's full_name), while the form input is labeled "Full name".
  const payload = {
    username: form.full_name.value.trim(),
    email: form.email.value.trim(),
    password: form.password.value,
  };

  const submitBtn = form.querySelector("button[type=submit]");
  submitBtn.disabled = true;
  submitBtn.textContent = "Creating...";

  try {
    const res = await fetch("/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showFormError(errorBox, extractErrorDetail(data) || "Sign up failed.");
      return;
    }

    setToken(data.access_token);
    window.location.href = getNextParam();
  } catch (err) {
    showFormError(errorBox, "Could not reach the server. Please try again.");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Create account";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("login-form");
  if (loginForm) loginForm.addEventListener("submit", handleLogin);

  const signupForm = document.getElementById("signup-form");
  if (signupForm) signupForm.addEventListener("submit", handleSignup);
});
