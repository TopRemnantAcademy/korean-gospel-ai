import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function AuditLogs() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const response = await axios.get('/api/admin/audit-logs');
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
        <h1 className="text-2xl font-bold">관리자 감사 로그 (Audit Logs)</h1>
        <p className="text-sm text-slate-500 mt-1">시스템 관리자들의 환불 승인, 설정 업데이트, 수동 작업 재시도 이력을 감사 추적합니다.</p>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/40 text-slate-400 font-semibold uppercase tracking-wider">
                <th className="p-4">시간</th>
                <th className="p-4">관리자 ID</th>
                <th className="p-4">수행 액션</th>
                <th className="p-4">대상 모델 / 키</th>
                <th className="p-4">접속 IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-slate-500">
                    감사 로그가 비어 있습니다.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-900/40">
                    <td className="p-4 whitespace-nowrap text-slate-500 font-mono">
                      {new Date(log.createdAt).toLocaleString()}
                    </td>
                    <td className="p-4 font-mono text-[10px] text-slate-400">
                      {log.adminUserId}
                    </td>
                    <td className="p-4">
                      <span className="px-2 py-0.5 rounded bg-slate-950/80 font-bold border border-slate-800/80 text-violet-400">
                        {log.action}
                      </span>
                    </td>
                    <td className="p-4 text-slate-400">
                      {log.entityType} ({log.entityId.slice(0, 8)}...)
                    </td>
                    <td className="p-4 font-mono text-[10px] text-slate-500">
                      {log.ipAddress}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
