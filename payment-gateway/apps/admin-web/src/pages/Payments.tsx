import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { AdminRole, PaymentStatus } from '@gospel-pay/shared';

interface PaymentsProps {
  adminUser: {
    id: string;
    email: string;
    role: AdminRole;
  };
}

export default function Payments({ adminUser }: PaymentsProps) {
  const [payments, setPayments] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [selectedPayment, setSelectedPayment] = useState<any>(null);

  // Refund Dialog
  const [showRefundModal, setShowRefundModal] = useState<boolean>(false);
  const [refundAmount, setRefundAmount] = useState<number>(0);
  const [refundReason, setRefundReason] = useState<string>('');
  const [refundBankCode, setRefundBankCode] = useState<string>('004');
  const [refundAccountNumber, setRefundAccountNumber] = useState<string>('');
  const [refundAccountHolder, setRefundAccountHolder] = useState<string>('');

  // Decrypt PII Dialog
  const [showDecryptModal, setShowDecryptModal] = useState<boolean>(false);
  const [decryptReason, setDecryptReason] = useState<string>('');
  const [decryptedData, setDecryptedData] = useState<any>(null);
  
  // Traces State
  const [traceLogs, setTraceLogs] = useState<any[]>([]);

  // Webhook Override Dialog
  const [showOverrideModal, setShowOverrideModal] = useState<boolean>(false);
  const [overrideReason, setOverrideReason] = useState<string>('');

  const fetchPayments = async () => {
    setLoading(true);
    try {
      const url = filterStatus ? `/api/admin/payments?status=${filterStatus}` : '/api/admin/payments';
      const response = await axios.get(url);
      setPayments(response.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPayments();
  }, [filterStatus]);

  const handleSelectPayment = async (uuid: string) => {
    try {
      const response = await axios.get(`/api/admin/payments/${uuid}`);
      setSelectedPayment(response.data);
      setDecryptedData(null);
      setDecryptReason('');
      setRefundAmount(response.data.amountTotal - (response.data.refunds || [])
        .filter((r: any) => r.refundStatus === 'DONE')
        .reduce((sum: number, r: any) => sum + r.refundAmount, 0)
      );

      // Fetch trace logs
      try {
        const traceRes = await axios.get(`/api/admin/payments/${uuid}/traces`);
        setTraceLogs(traceRes.data);
      } catch (err) {
        console.error('Failed to fetch traces', err);
        setTraceLogs([]);
      }
    } catch (err) {
      alert('상세 정보를 불러올 수 없습니다.');
    }
  };

  const handleRetryAction = async (actionPath: string) => {
    try {
      await axios.post(`/api/admin/payments/${selectedPayment.paymentUuid}/${actionPath}`);
      alert('재처리 작업이 큐에 성공적으로 등록되었습니다.');
      handleSelectPayment(selectedPayment.paymentUuid);
      fetchPayments();
    } catch (err: any) {
      alert(err.response?.data?.error || '작업 등록에 실패했습니다.');
    }
  };

  const handleRefundSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload: any = {
        refundAmount,
        refundReason,
      };

      if (selectedPayment.paymentMethod.includes('가상계좌')) {
        payload.refundBankCode = refundBankCode;
        payload.refundAccountNumber = refundAccountNumber;
        payload.refundAccountHolder = refundAccountHolder;
      }

      await axios.post(`/api/admin/payments/${selectedPayment.paymentUuid}/refund`, payload);
      alert('환불 요청이 정상적으로 처리 큐에 적재되었습니다.');
      setShowRefundModal(false);
      handleSelectPayment(selectedPayment.paymentUuid);
      fetchPayments();
    } catch (err: any) {
      alert(err.response?.data?.error || '환불 처리에 실패했습니다.');
    }
  };

  const handleDecryptSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const response = await axios.post(`/api/admin/payments/${selectedPayment.paymentUuid}/decrypt`, {
        reason: decryptReason,
      });
      setDecryptedData(response.data.decrypted);
      setShowDecryptModal(false);
      alert('민감 정보 복호화 조회가 완료되었습니다. 이 행위는 보안 감사 로그에 기록되었습니다.');
    } catch (err: any) {
      alert(err.response?.data?.error || '민감 정보 복호화 처리에 실패했습니다.');
    }
  };

  const handleOverrideSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await axios.post(`/api/admin/payments/${selectedPayment.paymentUuid}/override-webhook`, {
        reason: overrideReason,
      });
      alert('웹훅 상태 수동 승인이 완료되었습니다. 감사 로그에 기록되었습니다.');
      setShowOverrideModal(false);
      handleSelectPayment(selectedPayment.paymentUuid);
      fetchPayments();
    } catch (err: any) {
      alert(err.response?.data?.error || '수동 승인 처리에 실패했습니다.');
    }
  };

  const isReadOnly = adminUser.role === AdminRole.READONLY;
  const isFinanceOrSuper = adminUser.role === AdminRole.SUPER_ADMIN || adminUser.role === AdminRole.FINANCE_ADMIN;
  const isOpsOrDevOrSuper = adminUser.role === AdminRole.SUPER_ADMIN || adminUser.role === AdminRole.OPS_ADMIN || adminUser.role === AdminRole.DEVELOPER;

  const getPgPaymentStage = () => {
    if (!selectedPayment) return null;
    const isSuccess = selectedPayment.paymentStatus === 'PAID' || selectedPayment.paymentStatus === 'REFUNDED' || selectedPayment.paymentStatus === 'PARTIALLY_REFUNDED';
    const isFailed = selectedPayment.paymentStatus === 'FAILED';
    const isProcessing = selectedPayment.paymentStatus === 'PENDING_DEPOSIT';
    return {
      stage: 'PG_PAYMENT',
      label: 'PG 결제 승인',
      status: isSuccess ? 'SUCCESS' : isFailed ? 'FAILED' : isProcessing ? 'PROCESSING' : 'WAITING',
      details: isSuccess ? `${selectedPayment.amountTotal?.toLocaleString()}원 결제 승인 완료` : isFailed ? '결제 승인 실패' : '가상계좌 입금 대기 중'
    };
  };

  const getCreditDispatchStage = () => {
    if (!selectedPayment) return null;
    const status = selectedPayment.creditStatus;
    const isSuccess = status === 'CONFIRMED' || status === 'SENT' || status === 'REVERSED';
    const isFailed = status === 'FAILED';
    const isProcessing = status === 'PROCESSING';
    return {
      stage: 'CREDIT_DISPATCH',
      label: '원격 크레딧 전송',
      status: isSuccess ? 'SUCCESS' : isFailed ? 'FAILED' : isProcessing ? 'PROCESSING' : 'WAITING',
      details: isSuccess 
        ? `크레딧 ${selectedPayment.creditAmount}개 전송 완료` 
        : isFailed 
          ? `전송 실패: ${selectedPayment.creditDispatches?.[0]?.lastErrorMessage || '오류 발생'}` 
          : isProcessing ? '크레딧 전송 요청 중...' : '결제 완료 후 전송 대기'
    };
  };

  const getTaxDocumentStage = () => {
    if (!selectedPayment) return null;
    if (selectedPayment.receiptType === 'NONE') {
      return null;
    }
    
    if (selectedPayment.receiptType === 'TAX_INVOICE' || selectedPayment.receiptType === 'INVOICE') {
      const status = selectedPayment.invoiceRequestStatus;
      const isSuccess = status === 'SENT' || status === 'CANCELLED';
      const isFailed = status === 'FAILED';
      const isProcessing = status === 'PROCESSING';
      return {
        stage: 'TAX_DOCUMENT',
        label: 'B2B 세금계산서 발행',
        status: isSuccess ? 'SUCCESS' : isFailed ? 'FAILED' : isProcessing ? 'PROCESSING' : 'WAITING',
        details: isSuccess 
          ? `세금계산서 발행 완료` 
          : isFailed ? '세금계산서 발행 실패' : '세금계산서 발행 대기 중'
      };
    } else if (selectedPayment.receiptType === 'CASH_RECEIPT') {
      const receipt = selectedPayment.cashReceipts?.[0];
      const status = receipt?.receiptStatus;
      const isSuccess = status === 'SENT' || status === 'CANCELLED';
      const isFailed = status === 'FAILED';
      const isProcessing = status === 'PROCESSING';
      return {
        stage: 'TAX_DOCUMENT',
        label: '현금영수증 발행',
        status: isSuccess ? 'SUCCESS' : isFailed ? 'FAILED' : isProcessing ? 'PROCESSING' : 'WAITING',
        details: isSuccess 
          ? `현금영수증 발행 완료` 
          : isFailed ? `발행 실패: ${receipt?.lastErrorMessage || '오류'}` : '현금영수증 발행 대기 중'
      };
    } else {
      return {
        stage: 'TAX_DOCUMENT',
        label: '신용카드 영수증 증빙',
        status: 'SUCCESS',
        details: '카드 전표가 세무 증빙을 갈음합니다.'
      };
    }
  };

  const getChinaWebhookStage = () => {
    if (!selectedPayment) return null;
    const status = selectedPayment.creditStatus;
    const isSuccess = status === 'CONFIRMED';
    const isFailed = status === 'FAILED' && selectedPayment.creditDispatches?.[0]?.dispatchStatus !== 'FAILED';
    const isPending = status === 'SENT';
    
    return {
      stage: 'CHINA_WEBHOOK',
      label: '원격 플랫폼 웹훅 확인',
      status: isSuccess ? 'SUCCESS' : isFailed ? 'FAILED' : isPending ? 'PROCESSING' : 'WAITING',
      details: isSuccess 
        ? '원격 플랫폼 웹훅 수신 및 동기화 확정 완료' 
        : isFailed 
          ? '원격 플랫폼 웹훅 처리 실패' 
          : isPending ? '원격 플랫폼으로부터 웹훅 콜백 수신 대기 중...' : '크레딧 전송 완료 후 웹훅 대기'
    };
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">결제 & 거래 정보 관리</h1>
        <p className="text-sm text-slate-500 mt-1">대한민국 PG 결제 내역 및 비동기 작업 결과와 세무 문서를 조회/제어합니다.</p>
      </div>

      {/* Filter and List Container */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        
        {/* Payments List Column */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex justify-between items-center bg-slate-900 border border-slate-800 rounded-xl p-4">
            <span className="text-xs font-semibold text-slate-400">결제 상태 필터</span>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded-lg p-1.5 text-xs text-slate-200 focus:outline-none"
            >
              <option value="">모든 거래</option>
              <option value="PAID">결제완료</option>
              <option value="PENDING_DEPOSIT">입금대기</option>
              <option value="FAILED">결제실패</option>
              <option value="REFUNDED">환불완료</option>
              <option value="PARTIALLY_REFUNDED">부분환불</option>
            </select>
          </div>

          {loading ? (
            <div className="flex justify-center py-8">
              <span className="w-8 h-8 border-4 border-violet-600/30 border-t-violet-500 rounded-full animate-spin"></span>
            </div>
          ) : payments.length === 0 ? (
            <div className="text-center py-12 bg-slate-900/20 border border-slate-900 rounded-2xl text-slate-500 text-sm">
              일치하는 결제 건이 존재하지 않습니다.
            </div>
          ) : (
            <div className="space-y-2">
              {payments.map((p) => (
                <button
                  key={p.id}
                  onClick={() => handleSelectPayment(p.paymentUuid)}
                  className={`w-full text-left p-4 rounded-xl border transition-all flex justify-between items-center ${
                    selectedPayment?.paymentUuid === p.paymentUuid
                      ? 'bg-violet-600/10 border-violet-500 text-violet-300'
                      : 'border-slate-800 bg-slate-900/60 hover:bg-slate-900/80 text-slate-400'
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500 font-mono">{p.paymentUuid.slice(0, 8)}...</span>
                      <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                        UID: {p.userUid.slice(0, 8)}...
                      </span>
                    </div>
                    <div className="text-sm font-semibold text-slate-200">{p.amountTotal?.toLocaleString()} 원 ({p.paymentMethod})</div>
                    <div className="text-[10px] text-slate-500">{new Date(p.createdAt).toLocaleString()}</div>
                  </div>

                  <div className="flex flex-col items-end gap-1.5">
                    {/* Status Badges */}
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                      p.paymentStatus === 'PAID' ? 'bg-emerald-950 text-emerald-400' :
                      p.paymentStatus === 'PENDING_DEPOSIT' ? 'bg-amber-950 text-amber-400' : 'bg-slate-800 text-slate-400'
                    }`}>
                      {p.paymentStatus}
                    </span>
                    <div className="flex gap-1">
                      {p.creditStatus === 'CONFIRMED' && <span className="text-[8px] px-1 rounded bg-indigo-950 text-indigo-400">CR</span>}
                      {p.invoiceRequestStatus === 'SENT' && <span className="text-[8px] px-1 rounded bg-blue-950 text-blue-400">TAX</span>}
                      {p.receiptType === 'CASH_RECEIPT' && <span className="text-[8px] px-1 rounded bg-teal-950 text-teal-400">CASH</span>}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Selected Payment Detail Drawer / View */}
        <div className="space-y-6">
          {selectedPayment ? (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-6 max-h-[85vh] overflow-y-auto">
              <div className="border-b border-slate-800 pb-4 flex justify-between items-start">
                <div>
                  <h3 className="font-bold text-base text-slate-200">결제 상세 정보</h3>
                  <span className="text-[10px] text-slate-500 font-mono block mt-1">{selectedPayment.paymentUuid}</span>
                </div>
                <button 
                  onClick={() => setSelectedPayment(null)}
                  className="text-slate-500 hover:text-slate-300"
                >
                  ✕
                </button>
              </div>

              {/* User PII (Masked) */}
              <div className="space-y-2 text-xs">
                <h4 className="font-semibold text-slate-400 uppercase tracking-wider text-[10px]">고객 인적정보 (마스킹)</h4>
                <div className="grid grid-cols-2 gap-2 p-3 bg-slate-950/40 rounded-xl">
                  <div>
                    <span className="text-slate-500">소셜 계정</span>
                    <div className="text-slate-300 capitalize">{selectedPayment.user.provider} ({selectedPayment.user.uid.slice(0, 8)}...)</div>
                  </div>
                  <div>
                    <span className="text-slate-500">전화번호</span>
                    <div className="text-slate-300">
                      {decryptedData?.userPhone || selectedPayment.user.phoneMasked || '없음'}
                    </div>
                  </div>
                  <div className="col-span-2">
                    <span className="text-slate-500">이메일</span>
                    <div className="text-slate-300">
                      {decryptedData?.userEmail || selectedPayment.user.emailMasked || '없음'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Tax Invoice Info (if requested) */}
              {selectedPayment.receiptType !== 'NONE' && selectedPayment.companyRegNumberMasked && (
                <div className="space-y-2 text-xs">
                  <h4 className="font-semibold text-slate-400 uppercase tracking-wider text-[10px]">사업자 세무증빙 정보</h4>
                  <div className="grid grid-cols-2 gap-2 p-3 bg-slate-950/40 rounded-xl">
                    <div>
                      <span className="text-slate-500">회사명 / 대표자</span>
                      <div className="text-slate-300">{selectedPayment.companyName} / {selectedPayment.ceoName}</div>
                    </div>
                    <div>
                      <span className="text-slate-500">사업자번호</span>
                      <div className="text-slate-300 font-mono">
                        {decryptedData?.companyRegNumber || selectedPayment.companyRegNumberMasked}
                      </div>
                    </div>
                    <div className="col-span-2">
                      <span className="text-slate-500">계산서 이메일</span>
                      <div className="text-slate-300">
                        {decryptedData?.taxEmail || selectedPayment.taxEmailMasked}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Unified Tracing Timeline */}
              <div className="space-y-3 text-xs">
                <h4 className="font-semibold text-slate-400 uppercase tracking-wider text-[10px]">통합 거래 추적 타임라인</h4>
                <div className="p-4 bg-slate-950/40 rounded-xl space-y-4 border border-slate-900">
                  {[
                    getPgPaymentStage(),
                    getCreditDispatchStage(),
                    getTaxDocumentStage(),
                    getChinaWebhookStage(),
                  ]
                    .filter(Boolean)
                    .map((stageInfo: any, idx) => {
                      const isSuccess = stageInfo.status === 'SUCCESS';
                      const isFailed = stageInfo.status === 'FAILED';
                      const isProcessing = stageInfo.status === 'PROCESSING';
                      
                      return (
                        <div key={idx} className="flex justify-between items-start gap-4">
                          <div className="flex gap-3 items-start">
                            {/* Icon Indicator */}
                            <span className={`w-3.5 h-3.5 mt-0.5 rounded-full border-2 flex items-center justify-center text-[8px] font-bold ${
                              isSuccess ? 'border-emerald-500 bg-emerald-950 text-emerald-400' :
                              isFailed ? 'border-rose-500 bg-rose-950 text-rose-400' :
                              isProcessing ? 'border-violet-500 bg-violet-950 text-violet-400 animate-pulse' :
                              'border-slate-800 bg-slate-950 text-slate-600'
                            }`}>
                              {isSuccess && '✓'}
                              {isFailed && '✕'}
                              {isProcessing && '●'}
                            </span>
                            
                            <div className="space-y-0.5">
                              <div className="font-semibold text-slate-200">{stageInfo.label}</div>
                              <div className="text-[10px] text-slate-400 font-mono">{stageInfo.details}</div>
                            </div>
                          </div>

                          {/* Actions Inside Timeline */}
                          <div className="flex gap-1.5">
                            {stageInfo.stage === 'CREDIT_DISPATCH' && isFailed && !isReadOnly && isOpsOrDevOrSuper && (
                              <button
                                onClick={() => handleRetryAction('retry-credit')}
                                className="bg-violet-600 hover:bg-violet-500 text-white px-2 py-1 rounded text-[10px] font-semibold transition"
                              >
                                전송 재시도
                              </button>
                            )}

                            {stageInfo.stage === 'TAX_DOCUMENT' && isFailed && !isReadOnly && isFinanceOrSuper && (
                              <button
                                onClick={() => {
                                  if (selectedPayment.receiptType === 'CASH_RECEIPT') {
                                    handleRetryAction('retry-cash-receipt');
                                  } else {
                                    handleRetryAction('retry-tax-document');
                                  }
                                }}
                                className="bg-violet-600 hover:bg-violet-500 text-white px-2 py-1 rounded text-[10px] font-semibold transition"
                              >
                                발행 재시도
                              </button>
                            )}

                            {stageInfo.stage === 'CHINA_WEBHOOK' && (isFailed || stageInfo.status === 'PROCESSING') && !isReadOnly && isOpsOrDevOrSuper && (
                              <button
                                onClick={() => {
                                  setOverrideReason('');
                                  setShowOverrideModal(true);
                                }}
                                className="bg-amber-600 hover:bg-amber-500 text-white px-2 py-1 rounded text-[10px] font-semibold transition"
                              >
                                수동 승인
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>

              {/* Audit Trace Logs Timeline */}
              <div className="space-y-2 text-xs">
                <h4 className="font-semibold text-slate-400 uppercase tracking-wider text-[10px]">감사 로그 & 트레이싱 타임라인</h4>
                <div className="p-3.5 bg-slate-950/40 rounded-xl space-y-3 font-mono text-[11px] border border-slate-900">
                  {traceLogs.length === 0 ? (
                    <div className="text-slate-500 text-center py-2">등록된 감사 로그가 없습니다.</div>
                  ) : (
                    <div className="relative border-l border-slate-800 pl-4 space-y-4 ml-2 my-2">
                      {traceLogs.map((log: any) => {
                        const isSuccess = log.status === 'SUCCESS';
                        const isFailed = log.status === 'FAILED';
                        return (
                          <div key={log.id} className="relative">
                            <span className={`absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full border-2 bg-slate-950 ${
                              isSuccess ? 'border-emerald-500 bg-emerald-500' : isFailed ? 'border-rose-500 bg-rose-500' : 'border-violet-500 bg-violet-500'
                            }`} />
                            <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
                              <span className="font-bold">{log.stage} ({log.status})</span>
                              <span>{new Date(log.createdAt).toLocaleTimeString()}</span>
                            </div>
                            <p className="text-slate-300 leading-normal">{log.message}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Actions & Refunds */}
              {decryptedData && (
                <div className="p-3 bg-violet-950/20 border border-violet-900/30 rounded-xl text-[11px] text-violet-300 leading-relaxed">
                  🛡️ 보안 감사 로그 기록 하에 본 결제의 상세 개인식별정보(PII)가 정상 복호화 조회되었습니다.
                </div>
              )}

              {/* Decrypt PII Action */}
              {!isReadOnly && isFinanceOrSuper && !decryptedData && (
                <div className="space-y-2 pt-2 border-t border-slate-800">
                  <button
                    onClick={() => {
                      setDecryptReason('');
                      setShowDecryptModal(true);
                    }}
                    className="w-full py-2.5 bg-violet-950/20 hover:bg-violet-950/40 border border-violet-900/30 text-violet-400 font-semibold rounded-xl text-xs transition flex items-center justify-center gap-1.5"
                  >
                    <span>🛡️ 민감 정보 안전 복호화 (Audit Log)</span>
                  </button>
                </div>
              )}

              {!isReadOnly && isFinanceOrSuper && (
                <div className="space-y-2 pt-2 border-t border-slate-800">
                  <button
                    onClick={() => {
                      setRefundReason('');
                      setShowRefundModal(true);
                    }}
                    className="w-full py-2.5 bg-red-950/20 hover:bg-red-950/40 border border-red-900/30 text-red-400 font-semibold rounded-xl text-xs transition"
                  >
                    결제 환불 / 취소 처리 (Refund Drawer)
                  </button>
                </div>
              )}

              {/* Raw PG JSON Payload */}
              <div className="space-y-2 text-xs">
                <h4 className="font-semibold text-slate-400 uppercase tracking-wider text-[10px]">PG API 결과 원본 페이로드 (Masked JSON)</h4>
                <pre className="p-3 bg-slate-950/80 border border-slate-900 rounded-xl overflow-x-auto text-[10px] font-mono text-slate-400 max-h-48 scrollbar">
                  {JSON.stringify(selectedPayment.rawPgPayload, null, 2)}
                </pre>
              </div>

            </div>
          ) : (
            <div className="bg-slate-900/20 border border-slate-800 border-dashed rounded-2xl p-12 text-center text-slate-500 text-sm">
              상세 내역을 조회하려면 결제 내역을 선택해 주세요.
            </div>
          )}
        </div>
      </div>

      {/* REFUND MODAL */}
      {showRefundModal && selectedPayment && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <form onSubmit={handleRefundSubmit} className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-6">
            <div className="flex justify-between items-center pb-4 border-b border-slate-800">
              <span className="font-bold text-slate-300">결제 환불/취소 요청</span>
              <button 
                type="button"
                onClick={() => setShowRefundModal(false)}
                className="text-slate-500 hover:text-slate-300"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-sm">
              <div>
                <label className="block text-xs text-slate-400 mb-1">환불 가능 최대 금액</label>
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg font-bold text-slate-200">
                  {selectedPayment.amountTotal?.toLocaleString()} 원
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">환불 요청 금액</label>
                <input
                  type="number"
                  value={refundAmount}
                  onChange={(e) => setRefundAmount(Number(e.target.value))}
                  max={selectedPayment.amountTotal}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 font-mono focus:outline-none focus:border-violet-500"
                  required
                />
                <span className="text-[10px] text-slate-500 block mt-1">
                  * 부분환불이 가능한 결제 수단에 한하여 분할 취소가 가능합니다.
                </span>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">환불 사유</label>
                <input
                  type="text"
                  value={refundReason}
                  onChange={(e) => setRefundReason(e.target.value)}
                  placeholder="예: 고객 요청에 의한 전액 환불"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 focus:outline-none focus:border-violet-500"
                  required
                />
              </div>

              {/* Virtual Account Refund detail */}
              {selectedPayment.paymentMethod.includes('가상계좌') && (
                <div className="space-y-3 p-3 bg-slate-950/60 border border-slate-900 rounded-xl">
                  <h4 className="text-xs font-bold text-slate-400">가상계좌 환불 계좌 정보 입력</h4>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[10px] text-slate-500 mb-1">은행 코드</label>
                      <select
                        value={refundBankCode}
                        onChange={(e) => setRefundBankCode(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5 text-xs focus:outline-none"
                      >
                        <option value="004">KB국민은행</option>
                        <option value="088">신한은행</option>
                        <option value="020">우리은행</option>
                        <option value="011">NH농협은행</option>
                        <option value="081">하나은행</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-500 mb-1">예금주명</label>
                      <input
                        type="text"
                        value={refundAccountHolder}
                        onChange={(e) => setRefundAccountHolder(e.target.value)}
                        placeholder="예금주"
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5 text-xs focus:outline-none"
                        required
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-[10px] text-slate-500 mb-1">계좌 번호</label>
                      <input
                        type="text"
                        value={refundAccountNumber}
                        onChange={(e) => setRefundAccountNumber(e.target.value)}
                        placeholder="숫자만 입력해 주세요"
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5 text-xs focus:outline-none font-mono"
                        required
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setShowRefundModal(false)}
                className="py-3 border border-slate-800 rounded-xl text-slate-400 text-sm hover:bg-slate-800 transition"
              >
                닫기
              </button>
              <button
                type="submit"
                className="py-3 bg-red-600 hover:bg-red-500 text-white font-semibold rounded-xl text-sm transition"
              >
                환불 승인 요청
              </button>
            </div>
          </form>
        </div>
      )}

      {/* DECRYPT PII MODAL */}
      {showDecryptModal && selectedPayment && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <form onSubmit={handleDecryptSubmit} className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-6">
            <div className="flex justify-between items-center pb-4 border-b border-slate-800">
              <span className="font-bold text-slate-300">민감 개인정보 복호화 요청</span>
              <button 
                type="button"
                onClick={() => setShowDecryptModal(false)}
                className="text-slate-500 hover:text-slate-300"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-sm">
              <div className="p-3 bg-red-950/20 border border-red-900/30 rounded-xl text-xs text-red-400 leading-relaxed font-normal">
                ⚠️ 경고: 본 기능은 개인정보 보호정책 및 세무 감사 목적으로만 제한적으로 허용됩니다. 조회 시 관리자 이메일, 조회 시간, IP, 조회 사유가 영구적으로 <strong>감사 로그(Audit Log)</strong>에 기록됩니다.
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">복호화 조회 사유</label>
                <textarea
                  value={decryptReason}
                  onChange={(e) => setDecryptReason(e.target.value)}
                  placeholder="예: 국세청 세무조사 증빙 제출을 위한 사업자번호 실 확인 필요"
                  rows={3}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-violet-500 resize-none"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setShowDecryptModal(false)}
                className="py-3 border border-slate-800 rounded-xl text-slate-400 text-sm hover:bg-slate-800 transition"
              >
                취소
              </button>
              <button
                type="submit"
                className="py-3 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl text-sm transition"
              >
                복호화 및 조회
              </button>
            </div>
          </form>
        </div>
      )}

      {/* WEBHOOK OVERRIDE MODAL */}
      {showOverrideModal && selectedPayment && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <form onSubmit={handleOverrideSubmit} className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-6">
            <div className="flex justify-between items-center pb-4 border-b border-slate-800">
              <span className="font-bold text-slate-300">웹훅 수동 승인/오버라이드</span>
              <button 
                type="button"
                onClick={() => setShowOverrideModal(false)}
                className="text-slate-500 hover:text-slate-300"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-sm">
              <div className="p-3 bg-amber-950/20 border border-amber-900/30 rounded-xl text-xs text-amber-400 leading-relaxed font-normal">
                ⚠️ 경고: 본 기능은 외부 플랫폼과의 연동 과정에서 웹훅이 누락되었거나 지연되었을 때, 관리자 권한으로 수동 승인 처리하기 위한 기능입니다. 수동 승인 처리 사유는 <strong>감사 로그</strong>에 영구 보존됩니다.
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">수동 승인 사유</label>
                <textarea
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="예: 원격 서버 크레딧 지급 완료가 유선상으로 확인되었으나 웹훅 콜백 누락으로 인한 수동 동기화 완료 처리"
                  rows={3}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-violet-500 resize-none"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setShowOverrideModal(false)}
                className="py-3 border border-slate-800 rounded-xl text-slate-400 text-sm hover:bg-slate-800 transition"
              >
                취소
              </button>
              <button
                type="submit"
                className="py-3 bg-amber-600 hover:bg-amber-500 text-white font-semibold rounded-xl text-sm transition"
              >
                수동 승인 완료
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
