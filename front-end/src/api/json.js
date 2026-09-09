export async function readApiJson(response, authenticationRequired = () => {}) {
  if (response.status === 401) {
    authenticationRequired();
    throw Object.assign(new Error("会话已失效，请重新登录 NAS"), {
      status: 401,
    });
  }
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    throw Object.assign(
      new Error(
        response.ok
          ? "服务返回了网页而非接口数据，请检查 NAS 版本和服务地址"
          : `NAS 请求失败（HTTP ${response.status}），请稍后重试或查看服务端日志`,
      ),
      { code: "NON_JSON_RESPONSE", status: response.status },
    );
  }
  if (!response.ok) {
    const message = Array.isArray(data?.detail)
      ? "请求参数无效"
      : typeof data?.detail === "string"
        ? data.detail.slice(0, 500)
        : `请求失败（HTTP ${response.status}）`;
    throw Object.assign(new Error(message), {
      detail: data?.detail,
      status: response.status,
    });
  }
  return data;
}
