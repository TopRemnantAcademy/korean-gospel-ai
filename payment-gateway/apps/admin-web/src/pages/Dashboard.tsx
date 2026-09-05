import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function Dashboard() {
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');

  const fetchMetrics = async () => {
    try {
      const response = await axios.get('/api/admin/dashboard');
      setMetrics(response.data);
    } catch (err: any) {
      setError('대시보드 메트릭을 불러올 수 없습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000); // refresh every 5s
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <span className="w-8 h-8 border-4 border-violet-600/30 border-t-violet-500 rounded-full animate-spin"></span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">운영 대시보드</h1>
        <p className="text-sm text-slate-500 mt-1">오늘의 결제 수치 및 비동기 처리 오류 상태를 한눈에 모니터링합니다.</p>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-950/30 border border-red-900/50 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Today's Sales */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 relative overflow-hidden">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">오늘의 총 거래액</div>
          <div className="text-3xl font-extrabold text-violet-400 mt-2 font-mono">
            {metrics.salesToday?.toLocaleString()} KRW
          </div>
          <div className="absolute right-6 bottom-4 text-4xl opacity-10">💰</div>
        </div>

        {/* Total Payments */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 relative overflow-hidden">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">누적 결제 시도 건수</div>
          <div className="text-3xl font-extrabold text-slate-200 mt-2 font-mono">
            {metrics.totalPaymentsCount?.toLocaleString()} 건
          </div>
          <div className="absolute right-6 bottom-4 text-4xl opacity-10">💳</div>
        </div>

        {/* Failed Credit Sync */}
        <div className={`border rounded-2xl p-6 relative overflow-hidden transition-all ${
          metrics.failedCreditCount > 0 
            ? 'bg-red-950/20 border-red-900/60 shadow-lg shadow-red-900/5' 
            : 'bg-slate-900 border-slate-800'
        }`}>
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">원격 플랫폼 크레딧 지급 실패 건수</div>
          <div className={`text-3xl font-extrabold mt-2 font-mono ${metrics.failedCreditCount > 0 ? 'text-red-400' : 'text-slate-200'}`}>
            {metrics.failedCreditCount?.toLocaleString()} 건
          </div>
          {metrics.failedCreditCount > 0 && (
            <span className="absolute top-4 right-4 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
            </span>
          )}
          <div className="absolute right-6 bottom-4 text-4xl opacity-10">⚡</div>
        </div>

        {/* Failed Tax Document */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 relative overflow-hidden">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">세금계산서 발행 대기/진행 건수</div>
          <div className="text-3xl font-extrabold text-slate-200 mt-2 font-mono">
            {metrics.pendingTaxCount?.toLocaleString()} 건
          </div>
          <div className="absolute right-6 bottom-4 text-4xl opacity-10">📝</div>
        </div>

        {/* Failed Cash Receipt */}
        <div className={`border rounded-2xl p-6 relative overflow-hidden transition-all ${
          metrics.failedCashCount > 0 
            ? 'bg-red-950/20 border-red-900/60 shadow-lg shadow-red-900/5' 
            : 'bg-slate-900 border-slate-800'
        }`}>
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">현금영수증 발행 실패 건수</div>
          <div className={`text-3xl font-extrabold mt-2 font-mono ${metrics.failedCashCount > 0 ? 'text-red-400' : 'text-slate-200'}`}>
            {metrics.failedCashCount?.toLocaleString()} 건
          </div>
          {metrics.failedCashCount > 0 && (
            <span className="absolute top-4 right-4 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
            </span>
          )}
          <div className="absolute right-6 bottom-4 text-4xl opacity-10">🧾</div>
        </div>
      </div>

      {/* System Status Explainer */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-6 space-y-4">
        <h3 className="font-bold text-sm text-slate-300">비동기 Worker 상태 점검</h3>
        <p className="text-xs text-slate-500 leading-relaxed">
          - <strong>원격 플랫폼 크레딧 지급 실패</strong>: 원격 플랫폼 서버에 연결할 수 없거나 계정이 만료된 경우 발생합니다. 결제 탭에서 개별 재전송 버튼을 통해 수동 해결이 가능합니다.<br />
          - <strong>세금계산서 대기/진행</strong>: 국세청 연동 API 배치 작업 대기 상태를 나타냅니다.<br />
          - <strong>현금영수증 실패</strong>: 입력한 전화번호 또는 주민등록번호에 오류가 있는 경우 발생합니다. 고객 지원팀을 통한 마스킹 해제 조회가 권장됩니다.
        </p>
      </div>
    </div>
  );
}
