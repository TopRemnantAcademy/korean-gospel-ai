import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface Remittance {
  id: string;
  remittedAt: string;
  remittanceKey: string;
  bankName: string;
  amountUsd: number;
  exchangeRate: number;
  amountKrw: number;
  feeUsd: number;
  feeKrw: number;
  justification: string | null;
}

interface ReconciliationLog {
  id: string;
  targetMonth: string;
  status: string;
  matchedPaymentsCount: number;
  totalPgAmountKrw: number;
  totalTaxDocAmountKrw: number;
  totalRemittanceKrw: number;
  varianceAmountKrw: number;
  feeVarianceKrw: number;
  fxLossKrw: number;
  fxGainKrw: number;
  verifiedAt: string;
  remittance: Remittance | null;
}

const Reconciliation: React.FC = () => {
  const [logs, setLogs] = useState<ReconciliationLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  
  // CSV Import State
  const [csvText, setCsvText] = useState<string>('');
  const [importStatus, setImportStatus] = useState<string | null>(null);
  
  // Run Reconciliation State
  const [targetMonth, setTargetMonth] = useState<string>('');
  const [runStatus, setRunStatus] = useState<string | null>(null);

  const token = localStorage.getItem('admin_token');
  const api = axios.create({
    headers: { Authorization: `Bearer ${token}` },
  });

  const fetchLogs = async () => {
    try {
      setLoading(true);
      const res = await api.get('/api/admin/reconciliation/logs');
      setLogs(res.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.error || '대조 정산 로그 목록을 불러오는 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!csvText.trim()) {
      alert('CSV 내용을 입력하거나 템플릿을 붙여넣어 주세요.');
      return;
    }

    try {
      setImportStatus('업로드 중...');
      const res = await api.post('/api/admin/reconciliation/import', { csvData: csvText });
      setImportStatus(`성공: ${res.data.message}`);
      setCsvText('');
      fetchLogs();
    } catch (err: any) {
      setImportStatus(`실패: ${err.response?.data?.error || '업로드 오류가 발생했습니다.'}`);
    }
  };

  const handleRunReconciliation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetMonth) {
      alert('대상 연월을 입력해 주세요.');
      return;
    }

    try {
      setRunStatus('대조 정산 엔진 실행 중...');
      const res = await api.post('/api/admin/reconciliation/run', { month: targetMonth });
      setRunStatus(`완료: 정산 대조가 성공적으로 끝났습니다. 상태: ${res.data.reconLog.status}`);
      fetchLogs();
    } catch (err: any) {
      setRunStatus(`실패: ${err.response?.data?.error || '실행 중 오류가 발생했습니다.'}`);
    }
  };

  const downloadReport = (month: string) => {
    window.open(`/api/admin/reconciliation/report?month=${month}`, '_blank');
  };

  const loadTemplate = () => {
    const template = `date,remittanceKey,bankName,amountUsd,exchangeRate,feeUsd,feeKrw,justification
2026-05-15,REMIT-001,Hana Bank,11000.00,1385.50,50.00,69275,Outbound remittance transfer for credit settlement
2026-06-02,REMIT-002,Shinhan Bank,8500.00,1392.20,40.00,55688,Settling remote platform charges`;
    setCsvText(template);
  };

  return (
    <div className="space-y-8 text-slate-100">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-violet-400 to-indigo-300 bg-clip-text text-transparent">
          3자 대조 정산 관리
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          PG 원화 수금액, 국내 증빙 발행액, 본사 외화 송금액을 교차 대조하여 환율 편차 및 수수료 내역을 자동 태깅합니다.
        </p>
      </div>

      {/* Action Panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* CSV Import Panel */}
        <div className="p-6 rounded-2xl border border-violet-500/20 bg-slate-900/60 backdrop-blur-xl space-y-4 shadow-xl">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-bold text-violet-300">본사 해외송금 이력 가져오기</h2>
            <button
              onClick={loadTemplate}
              className="text-xs text-indigo-400 hover:text-indigo-300 underline"
            >
              템플릿 채우기
            </button>
          </div>
          <form onSubmit={handleImport} className="space-y-3">
            <textarea
              className="w-full h-32 p-3 bg-slate-950 border border-slate-800 rounded-xl focus:border-violet-500 focus:outline-none text-xs font-mono text-emerald-400"
              placeholder="date,remittanceKey,bankName,amountUsd,exchangeRate,feeUsd,feeKrw,justification..."
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
            />
            <div className="flex justify-between items-center">
              <button
                type="submit"
                className="px-4 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 rounded-xl text-sm font-semibold shadow-lg shadow-violet-500/20 transition-all"
              >
                CSV 송금 내역 업로드
              </button>
              {importStatus && <span className="text-xs font-medium text-slate-400">{importStatus}</span>}
            </div>
          </form>
        </div>

        {/* Run Reconciliation Engine */}
        <div className="p-6 rounded-2xl border border-violet-500/20 bg-slate-900/60 backdrop-blur-xl space-y-4 shadow-xl flex flex-col justify-between">
          <div>
            <h2 className="text-xl font-bold text-violet-300">정산 대조 엔진 실행</h2>
            <p className="text-xs text-slate-400 mt-1">
              선택한 연월에 대해 은행 송금 내역과 PG사 결제액, 세금계산서 증빙 금액을 교차 분석하여 환차손익을 태깅합니다.
            </p>
          </div>
          <form onSubmit={handleRunReconciliation} className="space-y-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">대상 정산월</label>
              <input
                type="month"
                className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl focus:border-violet-500 focus:outline-none text-sm text-slate-200"
                value={targetMonth}
                onChange={(e) => setTargetMonth(e.target.value)}
              />
            </div>
            <div className="flex justify-between items-center">
              <button
                type="submit"
                className="px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 rounded-xl text-sm font-semibold shadow-lg transition-all"
              >
                대조 프로세스 실행 (3-Way Match)
              </button>
              {runStatus && <span className="text-xs font-medium text-slate-400">{runStatus}</span>}
            </div>
          </form>
        </div>
      </div>

      {/* Reconciliation History List */}
      <div className="p-6 rounded-2xl border border-violet-500/20 bg-slate-900/60 backdrop-blur-xl shadow-xl space-y-4">
        <h2 className="text-xl font-bold text-violet-300">정산 및 3자 대조 내역</h2>

        {loading ? (
          <div className="text-center py-8 text-slate-400 text-sm">로딩 중...</div>
        ) : error ? (
          <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm">{error}</div>
        ) : logs.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">기록된 정산 대조 내역이 없습니다. 송금 데이터 업로드 및 대조 엔진을 실행해 주세요.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-xs text-slate-400 uppercase">
                  <th className="py-3 px-4">정산월</th>
                  <th className="py-3 px-4">대조 상태</th>
                  <th className="py-3 px-4">PG 총액</th>
                  <th className="py-3 px-4">세금계산서 증빙</th>
                  <th className="py-3 px-4">USD 송금(원화환산)</th>
                  <th className="py-3 px-4">수수료</th>
                  <th className="py-3 px-4">환차익 / 환차손</th>
                  <th className="py-3 px-4">관리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {logs.map((log) => {
                  const isOk = log.status === 'AUTO_MATCHED';
                  return (
                    <tr key={log.id} className="hover:bg-slate-800/20 transition-all">
                      <td className="py-3 px-4 font-semibold text-slate-200">{log.targetMonth}</td>
                      <td className="py-3 px-4">
                        <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                          isOk ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-300 border border-rose-500/20'
                        }`}>
                          {log.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-medium">{log.totalPgAmountKrw.toLocaleString()}원</td>
                      <td className="py-3 px-4 text-slate-300">{log.totalTaxDocAmountKrw.toLocaleString()}원</td>
                      <td className="py-3 px-4 text-slate-300">
                        ${log.remittance?.amountUsd.toLocaleString()} ({log.totalRemittanceKrw.toLocaleString()}원)
                      </td>
                      <td className="py-3 px-4 text-slate-400">{log.feeVarianceKrw.toLocaleString()}원</td>
                      <td className="py-3 px-4 font-semibold">
                        {log.fxGainKrw > 0 && <span className="text-emerald-400">+{log.fxGainKrw.toLocaleString()}원 (환차익)</span>}
                        {log.fxLossKrw > 0 && <span className="text-rose-400">-{log.fxLossKrw.toLocaleString()}원 (환차손)</span>}
                        {log.fxGainKrw === 0 && log.fxLossKrw === 0 && <span className="text-slate-400">0원</span>}
                      </td>
                      <td className="py-3 px-4">
                        <button
                          onClick={() => downloadReport(log.targetMonth)}
                          className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-medium rounded-lg text-indigo-300 hover:text-indigo-200 transition-all border border-slate-700"
                        >
                          대조 보고서 (CSV)
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default Reconciliation;
