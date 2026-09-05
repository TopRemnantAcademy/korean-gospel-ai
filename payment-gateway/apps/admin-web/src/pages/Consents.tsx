import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function Consents() {
  const [consents, setConsents] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchConsents = async () => {
      try {
        const response = await axios.get('/api/admin/consents');
        setConsents(response.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchConsents();
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
        <h1 className="text-2xl font-bold">개인정보 수집 및 국외이전 동의 기록</h1>
        <p className="text-sm text-slate-500 mt-1">대한민국 개인정보보호법에 의거하여 저장된 사용자의 결제/국외이전 동의 시간, IP, 고지 항목을 감사 추적합니다.</p>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/40 text-slate-400 font-semibold uppercase tracking-wider">
                <th className="p-4">동의 일시</th>
                <th className="p-4">사용자 UID</th>
                <th className="p-4">동의 약관 유형</th>
                <th className="p-4">수집/제공 항목</th>
                <th className="p-4">이전 국가 / 수령인</th>
                <th className="p-4">접속 IP / 단말 정보</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {consents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-500">
                    동의 기록이 존재하지 않습니다.
                  </td>
                </tr>
              ) : (
                consents.map((c) => (
                  <tr key={c.id} className="hover:bg-slate-900/40">
                    <td className="p-4 whitespace-nowrap text-slate-500 font-mono">
                      {new Date(c.createdAt).toLocaleString()}
                    </td>
                    <td className="p-4 font-mono text-[10px] text-slate-400">
                      {c.user?.uid.slice(0, 8)}...
                    </td>
                    <td className="p-4">
                      <span className="px-2.5 py-0.5 rounded bg-slate-950 text-violet-400 border border-slate-800 font-semibold">
                        {c.consentType} (v{c.version})
                      </span>
                    </td>
                    <td className="p-4 text-slate-400 max-w-xs truncate">
                      {JSON.stringify(c.disclosedItems)}
                    </td>
                    <td className="p-4 text-slate-400">
                      {c.country} ({c.recipientName})
                    </td>
                    <td className="p-4 text-slate-500 font-mono text-[9px]">
                      {c.ipAddress} <br />
                      <span className="truncate block max-w-[150px]">{c.userAgent}</span>
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
