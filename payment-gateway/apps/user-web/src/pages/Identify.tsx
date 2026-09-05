import React, { useState } from 'react';
import axios from 'axios';
import { UserSession } from '../App';

interface IdentifyProps {
  onIdentified: (user: UserSession) => void;
}

export default function Identify({ onIdentified }: IdentifyProps) {
  const [provider, setProvider] = useState<string>('google');
  const [subject, setSubject] = useState<string>('');
  const [phone, setPhone] = useState<string>('');
  const [email, setEmail] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    if (!subject.trim()) {
      setError('소셜 Subject ID를 입력해 주세요.');
      return;
    }

    setLoading(true);
    try {
      const payload: any = {
        provider,
        providerSubject: subject,
      };
      
      if (email.trim()) payload.email = email;
      if (phone.trim()) payload.phone = phone;

      // Request identify API
      const response = await axios.post('/api/social/identify', payload);
      
      onIdentified({
        userId: response.data.userId,
        uid: response.data.uid,
        emailMasked: response.data.emailMasked,
        phoneMasked: response.data.phoneMasked,
      });
    } catch (err: any) {
      const msg = err.response?.data?.error || '사용자 식별 과정 중 오류가 발생했습니다.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-2xl p-8 shadow-xl shadow-slate-950/40">
      {/* Secure Gateway Transition Banner */}
      <div className="mb-6 p-4 rounded-xl bg-violet-950/20 border border-violet-500/20 text-xs text-slate-300 space-y-2">
        <div className="flex items-center gap-2 text-violet-400 font-semibold">
          <span className="text-sm">🛡️</span>
          <span>안전 결제 게이트웨이 보안 연결 완료</span>
        </div>
        <p className="leading-relaxed text-[11px] text-slate-400">
          안전한 보안 결제 환경으로 연결되었습니다. 결제 정보 및 세무 증빙은 최고 수준의 보안 하에 안전하게 처리되며, 결제 완료 시 작업 플랫폼으로 고유 식별 신호만 동기화됩니다.
        </p>
      </div>

      <div className="text-center mb-6">
        <h1 className="text-2xl font-bold bg-gradient-to-r from-violet-400 to-indigo-200 bg-clip-text text-transparent">
          GOSPEL PAY 본인 식별 & 가입
        </h1>
        <p className="text-xs text-slate-400 mt-1.5">
          본인 확인 및 결제 진행을 위해 정보를 입력하세요.
        </p>
      </div>

      {error && (
        <div className="mb-6 p-4 rounded-xl bg-red-950/30 border border-red-900/50 text-red-400 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Provider Selection */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            소셜 로그인 제공사
          </label>
          <div className="grid grid-cols-3 gap-3">
            {[
              { id: 'google', name: 'Google' },
              { id: 'kakao', name: '카카오' },
              { id: 'apple', name: 'Apple' },
            ].map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setProvider(p.id)}
                className={`py-2 px-3 rounded-xl border text-sm font-medium transition-all ${
                  provider === p.id
                    ? 'bg-violet-600/15 border-violet-500 text-violet-300 shadow-md shadow-violet-500/5'
                    : 'border-slate-800 bg-slate-950/40 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                }`}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Subject ID Input */}
        <div>
          <label htmlFor="subject" className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            소셜 Subject ID (고유 키)
          </label>
          <input
            id="subject"
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="e.g. google_user_10293847"
            className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-violet-500 transition-all font-mono"
            required
          />
        </div>

        {/* Phone Input (Optional) */}
        <div>
          <label htmlFor="phone" className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            휴대폰 번호 (선택, UID 생성 및 계정 병합용)
          </label>
          <input
            id="phone"
            type="text"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="e.g. 010-1234-5678"
            className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-violet-500 transition-all"
          />
          <p className="text-[10px] text-slate-500 mt-1">
            * 입력시 동일 전화번호의 기존 가입 정보로 계정이 연동됩니다.
          </p>
        </div>

        {/* Email Input (Optional) */}
        <div>
          <label htmlFor="email" className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            이메일 주소 (선택)
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="e.g. user@example.com"
            className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-violet-500 transition-all"
          />
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold py-3.5 px-4 rounded-xl shadow-lg shadow-violet-500/20 transition-all flex items-center justify-center gap-2 hover:-translate-y-0.5"
        >
          {loading ? (
            <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
          ) : (
            '식별 완료 및 계속하기'
          )}
        </button>
      </form>
    </div>
  );
}
