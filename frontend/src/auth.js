const AUTH_STORAGE_KEY = "tonghehui_auth";
const AUTH_EVENT = "tonghehui-auth-changed";

export function getAuth() {
  const rawValue = localStorage.getItem(AUTH_STORAGE_KEY);

  if (!rawValue) {
    return null;
  }

  try {
    return JSON.parse(rawValue);
  } catch (error) {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}

export function getToken() {
  return getAuth()?.token ?? null;
}

export function isAuthenticated() {
  return Boolean(getToken());
}

export function saveAuth(auth) {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function clearAuth() {
  localStorage.removeItem(AUTH_STORAGE_KEY);
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function subscribeAuthChange(callback) {
  function handleStorage(event) {
    if (event.key === AUTH_STORAGE_KEY) {
      callback();
    }
  }

  window.addEventListener(AUTH_EVENT, callback);
  window.addEventListener("storage", handleStorage);

  return () => {
    window.removeEventListener(AUTH_EVENT, callback);
    window.removeEventListener("storage", handleStorage);
  };
}
