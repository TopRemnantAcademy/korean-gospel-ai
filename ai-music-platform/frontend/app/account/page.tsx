"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  type BillingOrder,
  type BillingPlan,
  type BillingProvider,
  type BillingSubscription,
  type MyBilling,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { QRCodeSVG } from "qrcode.react";

// 네이버페이 JS SDK 를 동적으로 로드.
// ⚠ 공식 스크립트 주소는 **https://nsp.pay.naver.com/sdk/js/naverpay.min.js** 이다.
//   (공식 문서 명시: "script include 시 https://nsp.pay.naver.com/sdk/js/naverpay.min.js 는
//    반드시 해당 링크를 통해 서비스에 적용하여야 합니다.")
//   출처: https://docs.pay.naver.com/docs/onetime-payment/payment/payment-auth-window
//   pay.naver.com/sdk/... 는 공식 주소가 아니므로 SDK 로드가 실패한다.
const NAVER_SDK_URL = "https://nsp.pay.naver.com/sdk/js/naverpay.min.js";

// oPay.open(...) 이 호출되면 네이버가 결제창을 띄우고, 완료 시 returnUrl(landing) 으로
// `?resultCode=Success&paymentId=...` 를 붙여 리다이렉트한다(실패 시 resultCode/resultMessage/reserveId).
function loadNaverSdk(scriptUrl?: string): Promise<any> {
  return new Promise((resolve, reject) => {
    if (typeof window !== "undefined" && (window as any).NaverPay) {
      return resolve((window as any).NaverPay);
    }
    const s = document.createElement("script");
    s.src = scriptUrl || NAVER_SDK_URL;
    s.async = true;
    s.onload = () => {
      if ((window as any).NaverPay) resolve((window as any).NaverPay);
      else reject(new Error("네이버페이 SDK 초기화 실패"));
    };
    s.onerror = () => reject(new Error("네이버페이 SDK 로드 실패(네트워크/차단)"));
    document.body.appendChild(s);
  });
}

export default function AccountPage() {
  const { isAuthed, email } = useAuth();
  const [data, setData] = useState<MyBilling | null>(null);
  const [sub, setSub] = useState<BillingSubscription | null>(null);
  const [orders, setOrders] = useState<BillingOrder[]>([]);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [providers, setProviders] = useState<BillingProvider[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tier, setTier] = useState("standard");
  const [currency, setCurrency] = useState("CNY");
  const [upgrading, setUpgrading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [qr, setQr] = useState<{ url: string; orderId: number } | null>(null);
  const [naverParams, setNaverParams] = useState<Record<string, unknown> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 单一 active provider(settings.billing_provider)가 결정하는 결제/币种硬约束.
  // kakao/naver 는 KRW 단일, stripe/alipay/wechat 은 다币种. backend require_currency 와 동일 source of truth.
  const defaultProvider = providers.find((p) => p.is_default) || null;
  const allowedCurrency = defaultProvider?.currency || null; // null = 多币种(请求에서 결정)

  async function refreshAll() {
    const [billing, subscription, myOrders, plansResp] = await Promise.all([
      api.meBilling(),
      api.mySubscription(),
      api.myOrders(),
      api.plans(),
    ]);
    setData(billing);
    setSub(subscription);
    setOrders(myOrders);
    setPlans(plansResp);
  }

  function clearPoll() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  // webhook 型(stripe/alipay/wechat): 跳转/扫码后 서버가 비동기 승격 → 프론트는 구독 상태를 폴링.
  async function pollUntilPaid(orderId: number) {
    clearPoll();
    let attempts = 0;
    pollRef.current = setInterval(async () => {
      attempts += 1;
      try {
        const s = await api.mySubscription();
        setSub(s);
        if (s.active) {
          clearPoll();
          setQr(null);
          await refreshAll();
        } else if (attempts >= 40) {
          // 약 2분(3s×40) 내 미도착: 무한 폴링 방지 + 사용자 안내.
          clearPoll();
          setError("支付结果尚未到账，请稍后刷新账户页查看；若已扣款仍未升级，请联系客服。");
        }
      } catch {
        // 轮询실패는 조용히 재시도(일시적 네트워크 등).
      }
    }, 3000);
  }

  // approve 型(kakao/naver): 回跳 쿼리의 pg_token / paymentId 를 서버 approve 엔드포인트로 전달.
  async function finalizeApprove(kind: "kakao" | "naver", orderId: number, token: string) {
    setApproving(true);
    setError("");
    try {
      if (kind === "kakao") {
        await api.approveKakao(orderId, token);
      } else {
        await api.approveNaver(orderId, token);
      }
      await refreshAll();
      setNaverParams(null);
      setQr(null);
    } catch (e: any) {
      setError(e?.message || "결제 승인 실패");
    } finally {
      setApproving(false);
    }
  }

  // 挂载时: kakao/naver 回跳 처리(approve 型은 webhook 이 없으므로 프론트가 토큰을 서버로 넘겨야 승격됨).
  // BILLING_RETURN_URL 이 이 계정 페이지(/account) 를 가리켜야 함(后端 kakao/naver 가 approval/cancel/fail/return 로 쿼리 붙여 리다이렉트).
  useEffect(() => {
    if (!isAuthed) return;
    const q = new URLSearchParams(window.location.search);
    const prov = q.get("provider");
    const orderId = Number(q.get("order_id") || "");
    const cleanUrl = () => window.history.replaceState({}, "", window.location.pathname);

    if (q.get("canceled") === "1" || q.get("failed") === "1") {
      setError("결제가 취소되었거나 실패했습니다. 다시 시도해 주세요.");
      cleanUrl();
      return;
    }
    // --- 공식 회귀 파라미터(실증됨) ---
    //  kakao : approval_url 뒤에 **pg_token** 이 query string 으로 붙어 온다.
    //          (공식: "approval_url로 redirection 해줄 때 pg_token을 query string으로 전달")
    //  naver : returnUrl 로 `?resultCode=Success&paymentId=...` 가 온다.
    //          실패/취소는 `?resultCode=UserCancel&resultMessage=...&reserveId=...` 이므로
    //          **resultCode 를 먼저 검증하지 않으면 paymentId 없이 승인을 시도하게 된다.**
    if (prov === "naver" && orderId) {
      const resultCode = q.get("resultCode");
      const paymentId = q.get("paymentId") || "";
      cleanUrl();
      if (resultCode && resultCode !== "Success") {
        const reason = q.get("resultMessage") || resultCode;
        setError(
          resultCode === "UserCancel"
            ? "결제가 취소되었습니다. 다시 시도해 주세요."
            : `네이버페이 결제 실패(${reason}). 다시 시도해 주세요.`
        );
        setNaverParams(null);
        return;
      }
      if (paymentId) {
        finalizeApprove("naver", orderId, paymentId);
        return;
      }
      // resultCode 도 paymentId 도 없다 → 정상 진입(회귀 아님). 아래 공통 처리를 타지 않게 종료.
      return;
    }

    if (prov === "kakao" && orderId && q.get("pg_token")) {
      cleanUrl();
      finalizeApprove("kakao", orderId, q.get("pg_token") as string);
      return;
    }

    // stripe/alipay(webhook 型): 回跳带 order_id(无 token) → 启动轮询, 待 서버 승격后自动반영.
    // (kakao/naver 는 위에서 approve 를 처리하므로 제외)
    if (orderId && prov !== "kakao" && prov !== "naver") {
      cleanUrl();
      pollUntilPaid(orderId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthed]);

  // 초기 로드 + providers(币种/결제방식 제약 source of truth)
  useEffect(() => {
    if (!isAuthed) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.all([
      api.meBilling(),
      api.mySubscription(),
      api.myOrders(),
      api.plans(),
      // providers 는 선택적: 실패해도 나머지 로드는 유지.
      api.providers().catch(() => ({ providers: [], default: "", mode: "" })),
    ])
      .then(([billing, subscription, myOrders, plansResp, provResp]) => {
        if (cancelled) return;
        setData(billing);
        setSub(subscription);
        setOrders(myOrders);
        setPlans(plansResp);
        setProviders(provResp.providers as BillingProvider[]);
      })
      .catch((e: any) => {
        if (!cancelled) setError(e?.message || "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      clearPoll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthed]);

  // 단일 provider 가 KRW 전용이면 통화 선택기를 해당 통화로 고정(后端 require_currency 400 방지).
  useEffect(() => {
    if (allowedCurrency) setCurrency(allowedCurrency);
  }, [allowedCurrency]);

  async function upgrade() {
    setUpgrading(true);
    setError("");
    setQr(null);
    setNaverParams(null);
    try {
      if (tier === "free") {
        setError("免费档为默认档，无需支付。请选择 lite / standard / sacred / enterprise 升级。");
        return;
      }
      // 단일 active provider 가 KRW 전용이면 강제 KRW(다른 통화 선택 시 backend 400).
      const cur = allowedCurrency || currency;
      const co = await api.checkout(tier, undefined, cur);
      const prov = co.provider;

      if (prov === "manual") {
        // 线下/对账模式: 属主 본인 confirm 이 승격 근거(step-1).
        await api.confirmOrder(co.order_id);
        await refreshAll();
        return;
      }

      if (prov === "wechat") {
        // Native QR: checkout_url = weixin://..., 프론트가 QR 로 렌더. 서버 webhook(验签) 승격 후 폴링으로 반영.
        const url =
          (co.provider_params?.qr_code_url as string | undefined) || co.checkout_url;
        setQr({ url, orderId: co.order_id });
        await pollUntilPaid(co.order_id);
        return;
      }

      if (prov === "naver") {
        // SDK handoff: 이 페이지(landing)에서 provider_params 로 oPay.open 호출.
        // 결제 후 네이버가 returnUrl(landing) 로 paymentId 를 붙여 리다이렉트 → 挂载 핸들러가 approve 호출.
        const params = (co.provider_params as Record<string, unknown>) || {};
        setNaverParams(params);
        return;
      }

      // kakao / stripe / alipay: 收银台 redirect.
      //  - kakao: 승인형 → 리다이렉트 후 approval_url(pg_token) 로 회귀 → approve 호출.
      //  - stripe/alipay: webhook 형 → 서버 비동기 승격 → 폴링으로 반영.
      window.location.href = co.checkout_url;
    } catch (e: any) {
      setError(e?.message || "升级失败");
    } finally {
      setUpgrading(false);
    }
  }

  async function openNaver() {
    if (!naverParams) return;
    setUpgrading(true);
    setError("");
    try {
      // 공식 스크립트 주소는 backend 가 내려준 값을 우선(없으면 상수) — 오타 방지.
      const NaverPay: any = await loadNaverSdk(naverParams.sdk_script as string | undefined);
      const oPay = NaverPay.create({
        mode: naverParams.mode,
        // 공식: 일반결제 SDK 는 payType 을 "normal" 로 설정한다.
        payType: (naverParams.payType as string) || "normal",
        clientId: naverParams.clientId,
        chainId: naverParams.chainId,
      });
      oPay.open({
        merchantUserKey: naverParams.merchantUserKey,
        merchantPayKey: naverParams.merchantPayKey,
        productName: naverParams.productName,
        totalPayAmount: naverParams.totalPayAmount,
        taxScopeAmount: naverParams.taxScopeAmount,
        taxExScopeAmount: naverParams.taxExScopeAmount,
        returnUrl: naverParams.returnUrl,
        // 공식 필수 파라미터(누락 시 결제창이 열리지 않는다).
        productCount: naverParams.productCount ?? 1,
        productItems: naverParams.productItems ?? [],
      });
    } catch (e: any) {
      setError(e?.message || "네이버페이 SDK 오류");
    } finally {
      setUpgrading(false);
    }
  }

  function planPrice(tierKey: string, cur: string): string | null {
    const p = plans.find((x) => x.tier_key === tierKey);
    if (!p) return null;
    const val = cur === "USD" ? p.price_usd : cur === "KRW" ? p.price_krw : p.price_cny;
    const sym = cur === "USD" ? "$" : cur === "KRW" ? "₩" : "¥";
    // 価格이 0(데이터 미입력/무료)이면 "—" 표시(¥0.00 오표기 방지), 실제 0원 결제는 backend 에서 차단.
    if (val === 0) return null;
    return `${sym}${val.toFixed(2)}`;
  }

  async function cancelSub() {
    setUpgrading(true);
    setError("");
    try {
      await api.cancelSubscription();
      await refreshAll();
    } catch (e: any) {
      setError(e?.message || "取消订阅失败");
    } finally {
      setUpgrading(false);
    }
  }

  async function reactivateSub() {
    setUpgrading(true);
    setError("");
    try {
      await api.reactivateSubscription();
      await refreshAll();
    } catch (e: any) {
      setError(e?.message || "恢复订阅失败");
    } finally {
      setUpgrading(false);
    }
  }

  if (!isAuthed) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-16 text-center">
        <p className="text-neutral-400">请先在右上角登录或注册。</p>
      </main>
    );
  }

  const fmt = (n: number) => `¥${n.toFixed(4)}`;
  // 결제 진행 중(wechat QR / naver SDK)이면 업그레이드 버튼 대신 해당 플로우 UI 를 노출.
  const inPaymentFlow = !!qr || !!naverParams;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="mb-1 text-2xl font-bold">账户 · 用量与账单</h1>
      <p className="mb-6 text-sm text-neutral-400">
        {email} · 当前套餐：<span className="text-indigo-400">{data?.tier_key ?? "free"}</span>
      </p>

      {loading && <p className="text-neutral-400">加载中…</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {data && (
        <>
          <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Card label="歌曲总数" value={String(data.total_songs)} />
            <Card label="总成本" value={fmt(data.total_cost_cny)} />
            <Card label="总营收(名义)" value={fmt(data.total_revenue_cny)} />
            <Card
              label="总毛利"
              value={fmt(data.total_margin_cny)}
              danger={data.total_margin_cny < 0}
            />
          </div>

          <div className="mb-8 rounded-xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="text-neutral-300">订阅与支付（真实支付基座 · GAP-004）</span>
              {sub && (
                <span
                  className={`rounded-full px-2 py-0.5 text-xs ${
                    sub.active
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-neutral-700 text-neutral-300"
                  }`}
                >
                  {sub.active ? `已订阅 · ${sub.tier_key}` : `未订阅 · ${sub.tier_key ?? "free"}`}
                </span>
              )}
            </div>
            {sub?.current_period_end && (
              <p className="mb-3 text-xs text-neutral-500">
                当前订阅周期至：{sub.current_period_end}
              </p>
            )}
            {sub?.cancel_at_period_end && (
              <p className="mb-3 text-xs text-amber-400">
                已申请取消，当前周期内仍可使用，到期后不再续费。
              </p>
            )}

            {/* wechat Native QR 플로우 */}
            {qr && (
              <div className="mb-4 flex flex-col items-center gap-3 rounded-lg border border-neutral-700 bg-neutral-950 p-4">
                <p className="text-sm text-neutral-300">请用微信扫描二维码完成支付</p>
                <div className="rounded-lg bg-white p-3">
                  <QRCodeSVG value={qr.url} size={200} />
                </div>
                <p className="text-xs text-neutral-500">
                  支付成功后本页会自动更新（无需手动刷新）。
                </p>
                <button
                  onClick={() => {
                    clearPoll();
                    setQr(null);
                  }}
                  className="text-xs text-neutral-400 underline"
                >
                  取消二维码
                </button>
              </div>
            )}

            {/* naver SDK handoff 플로우 */}
            {naverParams && (
              <div className="mb-4 flex flex-col items-center gap-3 rounded-lg border border-neutral-700 bg-neutral-950 p-4">
                <p className="text-sm text-neutral-300">点击下方按钮通过 네이버페이 完成支付</p>
                <button
                  onClick={openNaver}
                  disabled={upgrading || approving}
                  className="rounded-full bg-emerald-500 px-5 py-2 text-sm font-medium text-white transition hover:bg-emerald-400 disabled:opacity-50"
                >
                  {upgrading ? "결제창 열리는 중…" : "네이버페이로 결제"}
                </button>
                <p className="text-xs text-neutral-500">
                  결제 완료 시 자동으로 구독이 활성화됩니다。
                </p>
              </div>
            )}

            {!inPaymentFlow && (
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={tier}
                  onChange={(e) => setTier(e.target.value)}
                  className="rounded border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm outline-none focus:border-indigo-500"
                >
                  <option value="free">free（免费）</option>
                  {/* 低档位：绑定 mureka-7.6，成本更低，故价格低于 standard */}
                  <option value="lite">lite（8/日 · 轻量模型）</option>
                  <option value="standard">standard（20/日）</option>
                  <option value="sacred">sacred（50/日）</option>
                  <option value="enterprise">enterprise（999/日）</option>
                </select>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  disabled={!!allowedCurrency}
                  title={allowedCurrency ? `当前支付方式仅支持 ${allowedCurrency}` : undefined}
                  className="rounded border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm outline-none focus:border-indigo-500 disabled:opacity-50"
                >
                  <option value="CNY">CNY ¥</option>
                  <option value="USD">USD $</option>
                  <option value="KRW">KRW ₩</option>
                </select>
                {tier !== "free" && plans.length > 0 && (
                  <span className="text-xs text-neutral-400">
                    {planPrice(tier, currency) ?? "—"} / 月
                  </span>
                )}
                <button
                  onClick={upgrade}
                  disabled={upgrading || approving}
                  className="rounded-full bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
                >
                  {upgrading ? "处理中…" : "升级 / 切换套餐"}
                </button>
                {sub?.active &&
                  (sub.cancel_at_period_end ? (
                    <button
                      onClick={reactivateSub}
                      disabled={upgrading}
                      className="rounded-full border border-emerald-500 px-4 py-2 text-sm font-medium text-emerald-400 transition hover:bg-emerald-500/10 disabled:opacity-50"
                    >
                      恢复订阅
                    </button>
                  ) : (
                    <button
                      onClick={cancelSub}
                      disabled={upgrading}
                      className="rounded-full border border-neutral-600 px-4 py-2 text-sm font-medium text-neutral-300 transition hover:bg-neutral-800 disabled:opacity-50"
                    >
                      取消订阅
                    </button>
                  ))}
              </div>
            )}
          </div>

          {orders.length > 0 && (
            <div className="mb-8 rounded-xl border border-neutral-800 bg-neutral-900 p-4">
              <p className="mb-2 text-sm text-neutral-300">支付记录</p>
              <div className="space-y-2">
                {orders.map((o) => (
                  <div
                    key={o.order_id}
                    className="flex items-center justify-between text-xs"
                  >
                    <span className="text-neutral-400">
                      #{o.order_id} · {o.tier_key} · {o.provider}
                    </span>
                    <span className="text-neutral-300">
                      {o.currency === "CNY" ? "¥" : o.currency === "USD" ? "$" : "₩"}
                      {o.amount.toFixed(2)} · {o.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <h2 className="mb-3 text-lg font-semibold">最近歌曲</h2>
          {data.recent.length === 0 ? (
            <p className="text-sm text-neutral-500">还没有生成歌曲。</p>
          ) : (
            <div className="space-y-2">
              {data.recent.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-neutral-100">{s.title}</p>
                    <p className="text-xs text-neutral-500">
                      {s.status} · {s.created_at ?? ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-3 text-right text-xs">
                    <span className="text-neutral-400">成本 {fmt(s.cost_cny)}</span>
                    <span className="text-neutral-300">营收 {fmt(s.price_cny)}</span>
                    <span className={s.margin_cny < 0 ? "text-red-400" : "text-emerald-400"}>
                      毛利 {fmt(s.margin_cny)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}

function Card({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-3">
      <p className="text-xs text-neutral-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${danger ? "text-red-400" : "text-neutral-100"}`}>
        {value}
      </p>
    </div>
  );
}
