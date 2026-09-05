import React, { useEffect, useState, useRef, useCallback } from 'react';
import axios from 'axios';

interface ResultProps {
  paymentUuid: string;
  onRestart: () => void;
}

export default function Result({ paymentUuid, onRestart }: ResultProps) {
  const [statusData, setStatusData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');

  // SSO States
  const [ssoLoading, setSsoLoading] = useState<boolean>(false);
  const [ssoToken, setSsoToken] = useState<string>('');
  const [introspectResponse, setIntrospectResponse] = useState<any>(null);
  const [showSsoSandbox, setShowSsoSandbox] = useState<boolean>(false);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const terminalStates = ['PAID', 'FAILED', 'REFUNDED', 'CANCELLED'];

  const fetchStatus = useCallback(async () => {
    try {
      const response = await axios.get(`/api/payments/${paymentUuid}/status`);
      setStatusData(response.data);
      // Stop polling if payment reached a terminal state
      if (terminalStates.includes(response.data.paymentStatus)) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.error || '결제 상태를 불러올 수 없습니다.');
    } finally {
      setLoading(false);
    }
  }, [paymentUuid]);

  useEffect(() => {
    fetchStatus();
    // Poll status every 4 seconds with backoff
    pollingRef.current = setInterval(fetchStatus, 4000);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [fetchStatus]);

  const handleGenerateSSO = async () => {
    setSsoLoading(true);
    setIntrospectResponse(null);
    try {
      // Use the current origin as redirect URL (matches allowlist in production)
      const redirectUrl = window.location.origin;
      const response = await axios.post('/api/auth/sso-token', {
        uid: statusData.creditDispatches?.[0]?.uid || statusData.paymentUuid,
        redirectUrl,
      });
      setSsoToken(response.data.token);
      
      // If opened as a popup, perform secure handback and close window
      if (window.opener) {
        try {
          // Use postMessage for secure cross-origin communication
          window.opener.postMessage({ type: 'SSO_TOKEN', token: response.data.token }, '*');
        } catch (e) {
          // Cross-origin postMessage may fail silently
        }
        window.close();
      } else {
        setShowSsoSandbox(true);
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'SSO 토큰 발급에 실패했습니다.');
    } finally {
      setSsoLoading(false);
    }
  };

  const handleSimulateChinaVerification = async () => {
    try {
      const response = await axios.post('/api/auth/sso/introspect', {
        token: ssoToken,
      });
      setIntrospectResponse(response.data);
    } catch (err: any) {
      setIntrospectResponse({ active: false, error: err.response?.data?.error || '검증 실패' });
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 space-y-4">
        <span className="w-8 h-8 border-4 border-violet-600/30 border-t-violet-500 rounded-full animate-spin"></span>
        <span className="text-slate-400 text-sm">결제 처리 상태를 조회하고 있습니다...</span>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    const maps: Record<string, { label: string; style: string }> = {
      PAID: { label: '결제완료 (PAID)', style: 'bg-emerald-950/40 text-emerald-400 border border-emerald-900/50' },
      PENDING_DEPOSIT: { label: '입금대기 (PENDING)', style: 'bg-amber-950/40 text-amber-400 border border-amber-900/50' },
      FAILED: { label: '결제실패 (FAILED)', style: 'bg-red-950/40 text-red-400 border border-red-900/50' },
      REFUNDED: { label: '전액환불 (REFUNDED)', style: 'bg-slate-800/60 text-slate-400 border border-slate-700/80' },
      PARTIALLY_REFUNDED: { label: '부분환불 (PARTIAL)', style: 'bg-slate-800/60 text-slate-400 border border-slate-700/80' },
      CONFIRMED: { label: '지급완료 (CONFIRMED)', style: 'bg-emerald-950/30 text-emerald-400 border border-emerald-900/30' },
      SENT: { label: '전송완료 (SENT)', style: 'bg-blue-950/30 text-blue-400 border border-blue-900/30' },
      PROCESSING: { label: '처리중 (PROCESSING)', style: 'bg-violet-950/30 text-violet-400 border border-violet-900/30 animate-pulse' },
      READY: { label: '대기 (READY)', style: 'bg-slate-900 text-slate-500 border border-slate-800' },
      CANCELLED: { label: '발행취소 (CANCELLED)', style: 'bg-red-950/20 text-red-400/80 border border-red-900/20' },
    };

    const config = maps[status] || { label: status, style: 'bg-slate-800 text-slate-400' };
    return <span className={`px-2.5 py-1 rounded-md text-xs font-semibold ${config.style}`}>{config.label}</span>;
  };

  return (
    <div className="w-full max-w-2xl space-y-6">
      
      {/* Status Card */}
      <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800 rounded-2xl p-8 shadow-xl space-y-6">
        <div className="text-center pb-6 border-b border-slate-800">
          <div className="w-12 h-12 rounded-full bg-emerald-950/60 border border-emerald-800/60 text-emerald-400 flex items-center justify-center text-2xl mx-auto mb-4">
            ✓
          </div>
          <h1 className="text-2xl font-bold text-slate-100">결제 정보 및 진행 현황</h1>
          <p className="text-xs text-slate-500 mt-2 font-mono">주문 고유번호: {statusData?.paymentUuid}</p>
        </div>

        {error && (
          <div className="p-3 bg-red-950/20 border border-red-900/50 rounded-xl text-red-400 text-xs">
            {error}
          </div>
        )}

        {statusData && (
          <>
            {/* Breakdown Row */}
            <div className="grid grid-cols-2 gap-4 pb-6 border-b border-slate-800">
              <div>
                <span className="text-xs text-slate-500 block mb-1">결제 상태</span>
                {getStatusBadge(statusData.paymentStatus)}
              </div>
              <div className="text-right">
                <span className="text-xs text-slate-500 block mb-1">총 결제액</span>
                <span className="text-lg font-bold text-slate-200">{statusData.amountTotal?.toLocaleString()} 원</span>
              </div>
            </div>

            {/* State Machine Subtasks */}
            <div className="space-y-4">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">백그라운드 비동기 처리 상태</h3>
              
              <div className="space-y-3">
                {/* Credit Dispatch */}
                <div className="flex justify-between items-center p-3 rounded-xl bg-slate-950/40 border border-slate-900">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-indigo-500"></span>
                    <span className="text-sm">작업 플랫폼 크레딧 지급 (Credit sync)</span>
                  </div>
                  {getStatusBadge(statusData.creditStatus)}
                </div>

                {/* Tax Document */}
                {statusData.receiptType !== 'NONE' && (statusData.receiptType === 'TAX_INVOICE' || statusData.receiptType === 'INVOICE') && (
                  <div className="flex justify-between items-center p-3 rounded-xl bg-slate-950/40 border border-slate-900">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-blue-500"></span>
                      <span className="text-sm">B2B 세금계산서/계산서 발행</span>
                    </div>
                    {getStatusBadge(statusData.invoiceRequestStatus || 'READY')}
                  </div>
                )}

                {/* Cash Receipt */}
                {statusData.receiptType === 'CASH_RECEIPT' && (
                  <div className="flex justify-between items-center p-3 rounded-xl bg-slate-950/40 border border-slate-900">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-teal-500"></span>
                      <span className="text-sm">현금영수증 발행 (Cash Receipt)</span>
                    </div>
                    {getStatusBadge(statusData.cashReceipts?.[0]?.receiptStatus || 'READY')}
                  </div>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-4 pt-4">
              <button
                onClick={fetchStatus}
                className="flex-grow py-3 border border-slate-800 hover:border-slate-700 bg-slate-950/30 rounded-xl text-sm font-semibold transition"
              >
                상태 새로고침
              </button>
              
              <button
                onClick={handleGenerateSSO}
                disabled={ssoLoading}
                className="flex-grow py-3 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold rounded-xl text-sm shadow-lg shadow-violet-500/20 transition flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {ssoLoading ? (
                  <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                ) : (
                  '🔒 작업 플랫폼으로 안전하게 복귀 (SSO)'
                )}
              </button>
            </div>
            <div className="text-center text-[10px] text-slate-500 font-medium">
              * 클릭 시 암호화된 일회용(OTP) 토큰과 함께 작업 플랫폼으로 안전하게 복귀합니다.
            </div>
          </>
        )}
      </div>

      {/* SSO TOKENS MOCK SANDBOX INTEGRATION EXPLAINER */}
      {showSsoSandbox && (
        <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-6 space-y-6">
          <div className="border-b border-slate-800 pb-4">
            <h3 className="font-bold text-sm text-violet-400">SSO Token Handoff Sandbox Simulator</h3>
            <p className="text-xs text-slate-500 mt-1">
              보안 결제 서버가 발행한 1분 수명의 JWT 토큰입니다. 작업 플랫폼 서버는 아래 토큰을 검증해 사용자를 자동으로 로그인시킵니다.
            </p>
          </div>

          <div className="space-y-3">
            <div>
              <span className="text-xs text-slate-500 block mb-1">발급된 Signed JWT SSO Token (마스킹됨)</span>
              <div className="w-full bg-slate-950/80 border border-slate-900 rounded-xl p-3 text-[10px] font-mono text-slate-400 break-all">
                {ssoToken.slice(0, 20)}...{ssoToken.slice(-10)} ({ssoToken.length} chars)
              </div>
            </div>

            <button
              onClick={handleSimulateChinaVerification}
              className="w-full py-2.5 bg-slate-850 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-semibold transition"
            >
              작업 플랫폼 관점에서 토큰 유효성 검증(Introspect) 시뮬레이션
            </button>

            {introspectResponse && (
              <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-900 font-mono text-xs space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-500">인증 유효 상태 (Active)</span>
                  <span className={introspectResponse.active ? 'text-emerald-400' : 'text-red-400'}>
                    {introspectResponse.active ? 'TRUE (통과)' : 'FALSE (반려)'}
                  </span>
                </div>
                {introspectResponse.active && (
                  <div className="flex justify-between">
                    <span className="text-slate-500">작업 플랫폼이 식별한 사용자 UID</span>
                    <span className="text-violet-400">{introspectResponse.uid}</span>
                  </div>
                )}
                {introspectResponse.error && (
                  <div className="text-red-400">
                    에러 상세: {introspectResponse.error}
                  </div>
                )}
                <div className="text-[10px] text-slate-600 leading-relaxed border-t border-slate-900 pt-2">
                  * JTI replay 차단으로 인해 동일 토큰은 2회째 검증(새로고침) 시 무조건 반려 처리됩니다.
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-center pt-2">
            <button
              onClick={onRestart}
              className="text-xs text-slate-500 hover:text-slate-300 underline"
            >
              처음 화면으로 돌아가기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
