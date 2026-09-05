import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function ExternalLogs() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<{ logId: string; type: 'req' | 'res' | 'curl' } | null>(null);

  const handleCopy = async (text: string, logId: string, type: 'req' | 'res' | 'curl') => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus({ logId, type });
      setTimeout(() => setCopyStatus(null), 2000);
    } catch (err) {
      console.error('Copy failed', err);
    }
  };

  const getCurlCommand = (log: any) => {
    const headers = log.requestHeaders || {};
    const headersStr = Object.entries(headers)
      .map(([k, v]) => `-H "${k}: ${v}"`)
      .join(' ');
    const bodyStr = log.requestBody ? `-d '${JSON.stringify(log.requestBody).replace(/'/g, "'\\''")}'` : '';
    return `curl -X POST "${log.targetUrl}" ${headersStr} ${bodyStr}`.trim();
  };

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await axios.get('/api/admin/external-call-logs');
        setLogs(response.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchLogs();
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <span className="w-8 h-8 border-4 border-violet-600/30 border-t-violet-500 rounded-full animate-spin"></span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">외부 API 호출 통합 로그 (External Call Logs)</h1>
        <p className="text-sm text-slate-500 mt-1">PG 결제 승인/환불, 국세청 세금계산서, 원격 크레딧 API 호출 원본 입출력 값을 추적합니다.</p>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/40 text-slate-400 font-semibold uppercase tracking-wider">
                <th className="p-4">시간</th>
                <th className="p-4">대상 도메인</th>
                <th className="p-4">URL</th>
                <th className="p-4">HTTP 상태</th>
                <th className="p-4">상태</th>
                <th className="p-4">호출 원본</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-500">
                    통합 로그가 존재하지 않습니다.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <React.Fragment key={log.id}>
                    <tr className="hover:bg-slate-900/40">
                      <td className="p-4 whitespace-nowrap text-slate-500 font-mono">
                        {new Date(log.createdAt).toLocaleString()}
                      </td>
                      <td className="p-4 font-bold text-slate-200">
                        {log.domain}
                      </td>
                      <td className="p-4 font-mono text-[10px] text-slate-400 truncate max-w-xs">
                        {log.targetUrl}
                      </td>
                      <td className="p-4 font-mono font-semibold text-slate-300">
                        {log.responseStatus || 'N/A'}
                      </td>
                      <td className="p-4">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          log.success 
                            ? 'bg-emerald-950/40 text-emerald-400 border border-emerald-900/50'
                            : 'bg-red-950/40 text-red-400 border border-red-900/50'
                        }`}>
                          {log.success ? 'SUCCESS' : 'FAILED'}
                        </span>
                      </td>
                      <td className="p-4">
                        <button
                          onClick={() => setExpandedLogId(expandedLogId === log.id ? null : log.id)}
                          className="text-violet-400 hover:text-violet-300 underline font-medium"
                        >
                          {expandedLogId === log.id ? '접기' : '상세보기'}
                        </button>
                      </td>
                    </tr>
                    {expandedLogId === log.id && (
                      <tr className="bg-slate-950/40 border-b border-slate-800">
                        <td colSpan={6} className="p-4 space-y-4">
                          {log.errorMessage && (
                            <div className="p-3 bg-red-950/20 border border-red-900/50 text-red-400 rounded-xl">
                              에러 내용: {log.errorMessage}
                            </div>
                          )}

                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <div className="flex justify-between items-center mb-1">
                                <span className="text-[10px] text-slate-500 block">Request Payload</span>
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => handleCopy(JSON.stringify(log.requestBody, null, 2), log.id, 'req')}
                                    className="text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 px-2 py-0.5 rounded transition-colors"
                                  >
                                    {copyStatus?.logId === log.id && copyStatus?.type === 'req' ? '복사 완료! ✓' : 'JSON 복사'}
                                  </button>
                                  <button
                                    onClick={() => handleCopy(getCurlCommand(log), log.id, 'curl')}
                                    className="text-[10px] bg-violet-900/60 hover:bg-violet-800 text-violet-200 px-2 py-0.5 rounded transition-colors"
                                  >
                                    {copyStatus?.logId === log.id && copyStatus?.type === 'curl' ? 'cURL 복사 완료! ✓' : 'cURL 복사'}
                                  </button>
                                </div>
                              </div>
                              <pre className="p-3 bg-slate-950 border border-slate-900 rounded-xl text-[10px] font-mono text-slate-400 overflow-x-auto max-h-48 scrollbar">
                                {JSON.stringify(log.requestBody, null, 2)}
                              </pre>
                            </div>
                            <div>
                              <div className="flex justify-between items-center mb-1">
                                <span className="text-[10px] text-slate-500 block">Response Payload</span>
                                <button
                                  onClick={() => handleCopy(JSON.stringify(log.responseBody, null, 2), log.id, 'res')}
                                  className="text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 px-2 py-0.5 rounded transition-colors"
                                >
                                  {copyStatus?.logId === log.id && copyStatus?.type === 'res' ? '복사 완료! ✓' : 'JSON 복사'}
                                </button>
                              </div>
                              <pre className="p-3 bg-slate-950 border border-slate-900 rounded-xl text-[10px] font-mono text-slate-400 overflow-x-auto max-h-48 scrollbar">
                                {JSON.stringify(log.responseBody, null, 2)}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
