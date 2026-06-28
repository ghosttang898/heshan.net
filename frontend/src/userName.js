export function formatUserName(displayName, username, fallback = "匿名用户") {
  if (displayName && username) {
    return `${displayName}（${username}）`;
  }

  return displayName || username || fallback;
}
