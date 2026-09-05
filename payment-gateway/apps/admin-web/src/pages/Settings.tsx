import React, { useEffect, useState } from 'react';
import axios from 'axios';

export default function Settings() {
  const [configs, setConfigs] = useState<any[]>([]);
  const [retentionPolicies, setRetentionPolicies] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchSettings = async () => {
    try {
      // Fetch configs from public get list
      const configsRes = await axios.get('/api/payment-methods');
      setConfigs(configsRes.data);

      // Fetch policies from admin settings
      const settingsRes = await axios.get('/api/admin/settings');
      setRetentionPolicies(settingsRes.data.retentionPolicies);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleToggleMethod = async (id: string, currentEnabled: boolean) => {
    try {
      await axios.patch(`/api/admin/payment-method-configs/${id}`, {
        enabled: !currentEnabled,
      });
      alert('결제수단 설정이 변경되었습니다.');
      fetchSettings();
    } catch (err) {
      alert('설정 저장 실패');
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <span className="w-8 h-8 border-4 border-violet-600/30 border-t-violet-500 rounded-full animate-spin"></span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">결제수단 및 시스템 설정</h1>
        <p className="text-sm text-slate-500 mt-1">결제 페이지에 활성화할 국내 결제수단을 제어하고 개인정보 보존 기한 정책을 열람합니다.</p>
      </div>

      {/* Payment Toggles */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
        <h3 className="font-bold text-sm text-slate-300">결제 수단 활성화 / 비활성화 (On-Off)</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {configs.map((c) => (
            <div 
              key={c.id} 
              className="flex justify-between items-center p-4 rounded-xl bg-slate-950/40 border border-slate-900"
            >
              <div>
                <span className="font-semibold text-sm text-slate-200">{c.displayName}</span>
                <div className="text-[10px] text-slate-500 font-mono mt-0.5">{c.paymentMethod}</div>
                
                {/* Capabilities list */}
                <div className="flex gap-1.5 mt-2">
                  {c.supportsRefund && <span className="text-[8px] bg-emerald-950 text-emerald-400 px-1 py-0.5 rounded">환불가능</span>}
                  {c.supportsPartialRefund && <span className="text-[8px] bg-blue-950 text-blue-400 px-1 py-0.5 rounded">부분취소</span>}
                  {c.supportsCashReceipt && <span className="text-[8px] bg-teal-950 text-teal-400 px-1 py-0.5 rounded">현금영수증</span>}
                </div>
              </div>

              <button
                onClick={() => handleToggleMethod(c.id, c.enabled)}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition ${
                  c.enabled
                    ? 'bg-violet-600/20 text-violet-400 border border-violet-500/30 hover:bg-violet-600/30'
                    : 'bg-slate-900 text-slate-500 border border-slate-800 hover:bg-slate-800'
                }`}
              >
                {c.enabled ? '활성화 (ON)' : '비활성 (OFF)'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Retention Policies */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-4">
        <h3 className="font-bold text-sm text-slate-300">개인정보 보존 및 파기 정책 (PII Retention Policies)</h3>
        
        <div className="space-y-3">
          {retentionPolicies.map((p) => (
            <div 
              key={p.id}
              className="p-4 rounded-xl bg-slate-950/40 border border-slate-900 flex justify-between items-center text-sm"
            >
              <div>
                <div className="font-semibold text-slate-200 font-mono text-xs">{p.dataCategory}</div>
                <div className="text-xs text-slate-500 mt-1">
                  데이터 보존 기한: <strong>{p.retentionDays} 일</strong>
                </div>
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <span className="text-xs px-2.5 py-0.5 rounded bg-slate-800 font-semibold text-violet-400">
                  파기 방식: {p.disposalMethod}
                </span>
                <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  정상 모니터링 중
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
