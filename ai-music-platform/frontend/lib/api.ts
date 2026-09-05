// 前端 API 客户端：统一封装后端请求 + token 注入。
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// 带 HTTP 状态码的错误，便于上层按状态码区分处理（如 401 引导重新登录）
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export type SongView = {
  id: number;
  title: string;
  status: string;
  audio_url?: string | null;
  cover_url?: string | null;
  lyric?: string | null;
  task_type?: string;
  is_public?: boolean;
  is_owner?: boolean;
  play_count?: number;
  // Freemium 试听门控：未订阅时后端只下发「前 N 秒片段」链接，完整音频 URL 不下发。
  preview_audio_url?: string | null;
  preview_seconds?: number | null;
  can_play_full?: boolean;   // 订阅后可播放完整版
  can_download?: boolean;    // 订阅后可下载完整音频
};

export type AdminSongView = SongView & {
  user_email?: string | null;
  moderation_status?: string;
  moderation_note?: string | null;
  style?: string | null;
  prompt?: string | null;
  model_version?: string | null;
  duration?: number;
  created_at?: string;
  content_category?: string | null;
  engine_name?: string | null;
  cost_cny?: number | null;
  price_cny?: number | null;
  margin_cny?: number | null;
  tier_key?: string | null;
};

export type AdminStats = {
  total: number;
  by_status: Record<string, number>;
  by_moderation: Record<string, number>;
  total_cost_cny?: number;
  total_revenue_cny?: number;
  total_margin_cny?: number;
};

// —— 用户侧用量/账单（GAP-005）：本人歌曲范围内的单位经济汇总 ——
export type MyBillingSong = {
  id: number;
  title: string;
  status: string;
  cost_cny: number;
  price_cny: number;
  margin_cny: number;
  tier_key: string | null;
  created_at: string | null;
};

export type MyBilling = {
  tier_key: string | null;
  total_songs: number;
  total_cost_cny: number;
  total_revenue_cny: number;
  total_margin_cny: number;
  daily_quota_used: number;
  daily_quota_limit: number;
  recent: MyBillingSong[];
};

// —— 订阅/套餐：真实支付基座（GAP-004）——
// SubscribeResp 为旧 mock 切换接口（后端 billing_mode=live 时返回 410 废弃），保留以兼容历史调用。
export type SubscribeResp = {
  tier_key: string | null;
  limits: Record<string, unknown>;
};

// 真实支付流程（/api/billing/*）数据结构，与 backend/app/routers/billing.py 对齐。
export type CheckoutResp = {
  order_id: number;
  checkout_url: string; // manual 模式为平台内 /api/billing/orders/{id}/confirm；外部供应商为收银台 URL
  amount_cny: number;   // 结算等价人民币
  amount: number;       // 实际计费金额(按 currency)
  currency: string;     // CNY | USD | KRW
  tier_key: string;
  provider: string;
  // kakao(모바일 딥링크/앱 스킴) / naver(JS SDK 파라미터) / wechat(Native QR) 등
  // checkout_url 하나로 표현 안 되는 PG 별 handoff 정보. 없으면 null.
  provider_params?: Record<string, unknown> | null;
};

// GET /api/billing/providers 返回的单条(前端支付方式选择器 source of truth).
export type BillingProvider = {
  provider: string;
  flow: "redirect" | "qr" | "sdk" | "internal";
  settle: "webhook" | "approve" | "confirm";
  currency: string | null; // 该 PG 只受理的结算币种(None = 多币种)
  approve_endpoint: string | null; // approve 型才有
  is_default: boolean;
};

export type ProvidersResp = {
  providers: BillingProvider[];
  default: string;
  mode: string;
};

export type BillingOrder = {
  order_id: number;
  tier_key: string;
  amount_cny: number;
  amount: number;
  currency: string;
  status: string;
  provider: string;
  created_at: string;
};

export type BillingSubscription = {
  active: boolean;
  tier_key: string | null;
  provider?: string | null;
  status?: string | null;
  current_period_end?: string | null;
  cancel_at_period_end?: boolean | null;
};

// 已启用套餐(真实价格 source of truth = 后端 pricing_tiers)，与 /api/billing/plans 对齐。
export type BillingPlan = {
  tier_key: string;
  tier_name: string | null;
  price_cny: number;
  price_usd: number;
  price_krw: number;
  credits_per_song: number;
  description: string | null;
  enabled: boolean;
};

// —— 后台控制（多引擎路由 + 分层计费）数据结构，与后端 schemas.py 对齐 ——
export type EngineConfig = {
  provider: string;
  display_name?: string | null;
  enabled: boolean;
  is_default: boolean;
  api_base?: string | null;
  api_key_set: boolean; // 仅表示是否配置，不返回明文
  cost_per_song_cny: number;
  priority: number;
  notes?: string | null;
};

export type RoutingRule = {
  id: number;
  category: string;
  provider: string;
  priority: number;
  enabled: boolean;
};

export type PricingTier = {
  id: number;
  tier_key: string;
  tier_name?: string | null;
  engine_provider?: string | null;
  price_cny: number;
  credits_per_song: number;
  description?: string | null;
  enabled: boolean;
};

export type ConfigDashboard = {
  engines: EngineConfig[];
  routing_rules: RoutingRule[];
  pricing_tiers: PricingTier[];
  cost_by_engine: Record<string, number>;
  cost_by_category: Record<string, number>;
  revenue_by_tier: Record<string, number>;
  margin_by_tier: Record<string, number>;
  revenue_by_category: Record<string, number>;
  margin_by_category: Record<string, number>;
  total_cost_cny: number;
  total_revenue_cny: number;
  total_margin_cny: number;
  margin_rate: number;
  pending_moderation: number;
};

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("token") || "";
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new ApiError((err as any).detail || "请求失败", res.status);
  }
  return res.json();
}

function getAdminToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("admin_token") || "";
}

async function requestAdmin<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAdminToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["X-Admin-Token"] = token;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new ApiError((err as any).detail || "管理请求失败", res.status);
  }
  return res.json();
}

export const api = {
  register: (email: string, password: string): Promise<{ access_token: string }> =>
    request("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string): Promise<{ access_token: string }> =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<{ id: number; email: string }>("/api/auth/me"),
  meBilling: () => request<MyBilling>("/api/songs/me/billing"),
  subscribe: (tier: string) =>
    request<SubscribeResp>("/api/auth/subscribe", {
      method: "POST",
      body: JSON.stringify({ tier_key: tier }),
    }),
  // —— 真实支付基座（GAP-004 step-2）：账户页升级走此流程，不再直接切档 ——
  checkout: (tierKey: string, idempotencyKey?: string, currency?: string) =>
    request<CheckoutResp>("/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({
        tier_key: tierKey,
        ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
        ...(currency ? { currency } : {}),
      }),
    }),
  confirmOrder: (orderId: number) =>
    request<{ status: string; tier_key: string; order_id: number }>(
      `/api/billing/orders/${orderId}/confirm`,
      { method: "POST" }
    ),
  myOrders: () => request<BillingOrder[]>("/api/billing/orders"),
  mySubscription: () => request<BillingSubscription>("/api/billing/subscription"),
  // —— 套餐列表(各币种真实标价) + 自助取消/恢复 ——
  plans: () => request<BillingPlan[]>("/api/billing/plans"),
  cancelSubscription: () =>
    request("/api/billing/subscription/cancel", { method: "POST" }),
  reactivateSubscription: () =>
    request("/api/billing/subscription/reactivate", { method: "POST" }),
  // —— approve 型 PG(kakao / naver): 无 webhook, 需前端回跳后把 pg_token / paymentId 送回服务端 승인 ——
  // 注意: 这两个端点绝不以客户端自述升档, 而是服务端向各自供应商发起 approve 调用成功后才 승격.
  approveKakao: (orderId: number, pgToken: string) =>
    request<{ status: string; tier_key: string; order_id: number }>(
      "/api/billing/kakao/approve",
      { method: "POST", body: JSON.stringify({ order_id: orderId, pg_token: pgToken }) }
    ),
  approveNaver: (orderId: number, paymentId: string) =>
    request<{ status: string; tier_key: string; order_id: number }>(
      "/api/billing/naver/approve",
      { method: "POST", body: JSON.stringify({ order_id: orderId, payment_id: paymentId }) }
    ),
  // 可用支付方式清单(前端选择器 + 币种硬约束 source of truth, 与后端 require_currency 同一份 PROVIDER_CURRENCY).
  providers: () => request<ProvidersResp>("/api/billing/providers"),
  generate: (body: Record<string, unknown>) =>
    request("/api/songs/generate", { method: "POST", body: JSON.stringify(body) }),
  getSong: (id: number) => request<SongView>(`/api/songs/${id}`),
  listSongs: (limit?: number, offset?: number) => {
    const qs =
      limit != null || offset != null
        ? "?" +
          new URLSearchParams({
            ...(limit != null ? { limit: String(limit) } : {}),
            ...(offset != null ? { offset: String(offset) } : {}),
          }).toString()
        : "";
    return request<SongView[]>(`/api/songs${qs}`);
  },
  syncFlow: (id: number) => request(`/api/songs/${id}/sync-flow`, { method: "POST" }),
  downloadSong: async (id: number) => {
    // 订阅者下载完整音频。必须带 token，故不能用 <a href> 直连；
    // 取 blob 后用本地 URL 触发下载，文件名由后端 Content-Disposition 决定。
    const token = getToken();
    const res = await fetch(`${API_BASE}/api/songs/${id}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new ApiError((err as any).detail || "下载失败", res.status);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  previewObjectUrl: async (id: number): Promise<string | null> => {
    // 未订阅者的试听片段。对象存储未配置时后端走 /api/songs/{id}/preview（需鉴权），
    // 而 <audio src> 无法携带 Authorization 头 → 取 blob 转成本地 object URL 播放。
    // 返回 null 表示试听片段暂不可用（fail-closed，前端提示而非回退完整音频）。
    const token = getToken();
    const res = await fetch(`${API_BASE}/api/songs/${id}/preview`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return null;
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
  extendSong: (id: number, body: Record<string, unknown> = {}) =>
    request(`/api/songs/${id}/extend`, { method: "POST", body: JSON.stringify(body) }),
  coverSong: (id: number, body: Record<string, unknown> = {}) =>
    request(`/api/songs/${id}/cover`, { method: "POST", body: JSON.stringify(body) }),
  remixSong: (id: number, body: Record<string, unknown> = {}) =>
    request(`/api/songs/${id}/remix`, { method: "POST", body: JSON.stringify(body) }),
  explore: (limit?: number, offset?: number, q?: string) => {
    const params: Record<string, string> = {};
    if (limit != null) params.limit = String(limit);
    if (offset != null) params.offset = String(offset);
    if (q != null && q.trim() !== "") params.q = q.trim();
    const qs = Object.keys(params).length
      ? "?" + new URLSearchParams(params).toString()
      : "";
    return request<SongView[]>(`/api/songs/explore${qs}`);
  },
  play: (id: number) =>
    request<SongView>(`/api/songs/${id}/play`, { method: "POST" }),
  deleteSong: (id: number) =>
    request(`/api/songs/${id}`, { method: "DELETE" }),
  updateVisibility: (id: number, isPublic: boolean) =>
    request<SongView>(`/api/songs/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_public: isPublic }),
    }),
  // —— 管理后台（X-Admin-Token 鉴权）——
  adminStats: () => requestAdmin<AdminStats>("/api/admin/stats"),
  adminSongs: (moderationStatus?: string, status?: string, limit?: number, offset?: number) => {
    const params: Record<string, string> = {};
    if (moderationStatus) params.moderation_status = moderationStatus;
    if (status) params.status = status;
    if (limit != null) params.limit = String(limit);
    if (offset != null) params.offset = String(offset);
    const qs = Object.keys(params).length
      ? "?" + new URLSearchParams(params).toString()
      : "";
    return requestAdmin<AdminSongView[]>(`/api/admin/songs${qs}`);
  },
  adminApprove: (id: number) =>
    requestAdmin(`/api/admin/songs/${id}/approve`, { method: "POST" }),
  adminReject: (id: number, note?: string) =>
    requestAdmin(`/api/admin/songs/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ note: note || "" }),
    }),
  // —— 后台控制：引擎 / 路由 / 计费（X-Admin-Token 鉴权）——
  adminEngines: () => requestAdmin<EngineConfig[]>("/api/admin/engines"),
  adminGetEngine: (provider: string) =>
    requestAdmin<EngineConfig>(`/api/admin/engines/${encodeURIComponent(provider)}`),
  adminCreateEngine: (body: Record<string, unknown>) =>
    requestAdmin<EngineConfig>("/api/admin/engines", { method: "POST", body: JSON.stringify(body) }),
  adminUpdateEngine: (provider: string, body: Record<string, unknown>) =>
    requestAdmin<EngineConfig>(`/api/admin/engines/${encodeURIComponent(provider)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  adminDeleteEngine: (provider: string) =>
    requestAdmin(`/api/admin/engines/${encodeURIComponent(provider)}`, { method: "DELETE" }),
  adminRoutingRules: () => requestAdmin<RoutingRule[]>("/api/admin/routing-rules"),
  adminCreateRoutingRule: (body: Record<string, unknown>) =>
    requestAdmin<RoutingRule>("/api/admin/routing-rules", { method: "POST", body: JSON.stringify(body) }),
  adminUpdateRoutingRule: (ruleId: number, body: Record<string, unknown>) =>
    requestAdmin<RoutingRule>(`/api/admin/routing-rules/${ruleId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  adminDeleteRoutingRule: (ruleId: number) =>
    requestAdmin(`/api/admin/routing-rules/${ruleId}`, { method: "DELETE" }),
  adminPricingTiers: () => requestAdmin<PricingTier[]>("/api/admin/pricing-tiers"),
  adminCreatePricingTier: (body: Record<string, unknown>) =>
    requestAdmin<PricingTier>("/api/admin/pricing-tiers", { method: "POST", body: JSON.stringify(body) }),
  adminUpdatePricingTier: (tierKey: string, body: Record<string, unknown>) =>
    requestAdmin<PricingTier>(`/api/admin/pricing-tiers/${encodeURIComponent(tierKey)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  adminDeletePricingTier: (tierKey: string) =>
    requestAdmin(`/api/admin/pricing-tiers/${encodeURIComponent(tierKey)}`, { method: "DELETE" }),
  adminDashboard: () => requestAdmin<ConfigDashboard>("/api/admin/config/dashboard"),
  adminSeedConfig: () => requestAdmin<ConfigDashboard>("/api/admin/config/seed", { method: "POST" }),
};
