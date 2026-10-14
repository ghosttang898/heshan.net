export function validateFields(values, rules) {
  for (const [field, label, limit, required] of rules) {
    const value = values[field] ?? "";
    if (required && !value.trim()) return `请填写${label}。`;
    if ([...value].length > limit) return `${label}不能超过${limit}个字符。`;
  }
  return "";
}

export function validateRegistration(values) {
  const error = validateFields(values, [
    ["username", "用户名", 255, true],
    ["displayName", "显示名", 255, true],
    ["password", "密码", 72, true],
  ]);
  if (error) return error;
  return new TextEncoder().encode(values.password).length > 72
    ? "密码过长，最多72字节（中文等字符会占用多个字节）。" : "";
}

export function validatePost(values) {
  return validateFields(values, [
    ["title", "标题", 255, true], ["content", "内容", 4000, true],
    ["nickname", "昵称", 255, false], ["location", "地点", 255, false],
    ["yearRange", "年份范围", 255, false],
  ]);
}

export function submissionError(error, fallback) {
  const status = error?.response?.status;
  if (!error?.response) return "无法连接服务器，请检查网络后重试。";
  if (status === 400) return "输入不符合要求，请检查必填项及长度。";
  if (status === 401 || status === 403) return "登录已失效或没有操作权限，请重新登录。";
  if (status === 409) return "用户名已存在，请换一个用户名。";
  if (status === 404) return "帖子不存在或已不可访问。";
  return fallback;
}
