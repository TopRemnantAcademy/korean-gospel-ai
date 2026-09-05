import React, { useState } from 'react';
import axios from 'axios';
import { UserSession } from '../App';
import { PaymentMethod, ReceiptType, InvoiceType, CashReceiptType, CashReceiptIdentityType } from '@gospel-pay/shared';

interface CheckoutProps {
  session: UserSession;
  onPaymentCompleted: (uuid: string) => void;
}

export default function Checkout({ session, onPaymentCompleted }: CheckoutProps) {
  // Products (fetched from API in production; hardcoded for demo)
  const products = [
    { code: 'CREDIT_100', name: '100 크레딧 패키지', price: 11000, desc: '10,000원 + 부가세 1,000원' },
    { code: 'CREDIT_500', name: '500 크레딧 패키지', price: 55000, desc: '50,000원 + 부가세 5,000원' },
    { code: 'CREDIT_1000', name: '1,000 크레딧 패키지', price: 110000, desc: '100,000원 + 부가세 10,000원' },
  ];

  // State Variables
  const [selectedProduct, setSelectedProduct] = useState<string>('CREDIT_100');
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>(PaymentMethod.CREDIT_CARD);
  
  // Tax Invoice Form State
  const [invoiceRequested, setInvoiceRequested] = useState<boolean>(false);
  const [invoiceType, setInvoiceType] = useState<InvoiceType>(InvoiceType.TAX_INVOICE);
  const [companyRegNumber, setCompanyRegNumber] = useState<string>('');
  const [companyName, setCompanyName] = useState<string>('');
  const [ceoName, setCeoName] = useState<string>('');
  const [taxEmail, setTaxEmail] = useState<string>('');

  // Cash Receipt Form State
  const [cashReceiptRequested, setCashReceiptRequested] = useState<boolean>(false);
  const [cashReceiptType, setCashReceiptType] = useState<CashReceiptType>(CashReceiptType.INCOME_DEDUCTION);
  const [cashReceiptIdentityType, setCashReceiptIdentityType] = useState<CashReceiptIdentityType>(CashReceiptIdentityType.PHONE);
  const [cashReceiptIdentityValue, setCashReceiptIdentityValue] = useState<string>('');

  // Consents State
  const [agreeTerms, setAgreeTerms] = useState<boolean>(false);
  const [agreeCrossBorder, setAgreeCrossBorder] = useState<boolean>(false);

  // PG Simulation Modal
  const [showPgModal, setShowPgModal] = useState<boolean>(false);
  const [prepData, setPrepData] = useState<any>(null);
  const [pgLoading, setPgLoading] = useState<boolean>(false);

  // Global Page State
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showSuccessToast, setShowSuccessToast] = useState<boolean>(false);

  const isCashMethod = paymentMethod === PaymentMethod.ACCOUNT_TRANSFER || paymentMethod === PaymentMethod.VIRTUAL_ACCOUNT;
  const isCardMethod = !isCashMethod; // Card/simple pay methods cannot request tax invoices or cash receipts

  const handleOpenCheckout = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!agreeTerms || !agreeCrossBorder) {
      setError('모든 필수 약관에 동의해 주세요.');
      return;
    }

    if (invoiceRequested) {
      if (!companyRegNumber.trim() || !companyName.trim() || !ceoName.trim() || !taxEmail.trim()) {
        setError('세금계산서 발행 정보를 모두 입력해 주세요.');
        return;
      }
      if (!/^\d{3}-\d{2}-\d{5}$/.test(companyRegNumber)) {
        setError('사업자등록번호 형식이 올바르지 않습니다 (예: 123-45-67890).');
        return;
      }
    }

    if (cashReceiptRequested && isCashMethod) {
      if (!cashReceiptIdentityValue.trim()) {
        setError('현금영수증 식별 정보를 입력해 주세요.');
        return;
      }
    }

    setLoading(true);
    try {
      // 1. Prepare payment
      const response = await axios.post('/api/payments/prepare', {
        userId: session.userId,
        productCode: selectedProduct,
        selectedPaymentMethod: paymentMethod,
        invoiceRequested,
        cashReceiptRequested: isCashMethod && cashReceiptRequested,
      });

      setPrepData(response.data);
      setShowPgModal(true); // Open mock checkout modal
    } catch (err: any) {
      setError(err.response?.data?.error || '결제 준비 실패. 다시 시도해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  const handleSimulatePgApprove = async () => {
    setPgLoading(true);
    try {
      const payload: any = {
        paymentKey: `mock_${crypto.randomUUID()}`,
        orderId: prepData.pgOrderId,
        amount: prepData.amountTotal,
        paymentMethod: paymentMethod,
        status: paymentMethod === PaymentMethod.VIRTUAL_ACCOUNT ? 'WAITING_FOR_DEPOSIT' : 'DONE',
        invoiceRequested,
        cashReceiptRequested: isCashMethod && cashReceiptRequested,
      };

      if (invoiceRequested) {
        payload.companyRegNumber = companyRegNumber;
        payload.companyName = companyName;
        payload.ceoName = ceoName;
        payload.taxEmail = taxEmail;
        payload.invoiceType = invoiceType;
      }

      if (isCashMethod && cashReceiptRequested) {
        payload.cashReceiptType = cashReceiptType;
        payload.cashReceiptIdentityType = cashReceiptIdentityType;
        payload.cashReceiptIdentityValue = cashReceiptIdentityValue;
      }

      // 2. Trigger pg callback to confirm payment
      const response = await axios.post('/api/payments/callback', payload);
      
      setShowPgModal(false);
      setShowSuccessToast(true);
      
      // Delay transition by 2 seconds to show secure success message
      setTimeout(() => {
        setShowSuccessToast(false);
        onPaymentCompleted(response.data.paymentUuid);
      }, 2000);
    } catch (err: any) {
      alert(err.response?.data?.error || 'PG 결제 승인 처리 중 에러가 발생했습니다.');
    } finally {
      setPgLoading(false);
    }
  };

  return (
    <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-3 gap-8 items-start">
      {/* Checkout Form */}
      <form onSubmit={handleOpenCheckout} className="md:col-span-2 space-y-6">
        
        {/* Step 1: Select Product */}
        <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800 rounded-2xl p-6">
          <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
            <span className="text-xs w-5 h-5 rounded-full bg-violet-600 flex items-center justify-center text-white">1</span>
            크레딧 패키지 선택
          </h2>
          <div className="space-y-3">
            {products.map((p) => (
              <label
                key={p.code}
                className={`flex justify-between items-center p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedProduct === p.code
                    ? 'bg-violet-600/10 border-violet-500 text-violet-300'
                    : 'border-slate-800 bg-slate-950/20 hover:border-slate-700 text-slate-400'
                }`}
              >
                <div className="flex items-center gap-3">
                  <input
                    type="radio"
                    name="product"
                    checked={selectedProduct === p.code}
                    onChange={() => setSelectedProduct(p.code)}
                    className="accent-violet-500"
                  />
                  <div>
                    <div className="font-semibold text-slate-200">{p.name}</div>
                    <div className="text-xs text-slate-400 mt-0.5">{p.desc}</div>
                  </div>
                </div>
                <div className="text-base font-bold text-slate-100">{p.price.toLocaleString()} 원</div>
              </label>
            ))}
          </div>
        </div>

        {/* Step 2: Select Payment Method */}
        <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800 rounded-2xl p-6">
          <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
            <span className="text-xs w-5 h-5 rounded-full bg-violet-600 flex items-center justify-center text-white">2</span>
            결제 수단 선택
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {[
              { id: PaymentMethod.CREDIT_CARD, name: '일반 신용카드' },
              { id: PaymentMethod.KAKAO_PAY, name: '카카오페이' },
              { id: PaymentMethod.NAVER_PAY, name: '네이버페이' },
            ].map((method) => (
              <button
                key={method.id}
                type="button"
                onClick={() => {
                  setPaymentMethod(method.id);
                  setCashReceiptRequested(false);
                  setInvoiceRequested(false);
                }}
                className={`py-3 px-4 rounded-xl border text-sm font-medium transition-all ${
                  paymentMethod === method.id
                    ? 'bg-violet-600/15 border-violet-500 text-violet-300 shadow-md shadow-violet-500/5'
                    : 'border-slate-800 bg-slate-950/20 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                }`}
              >
                {method.name}
              </button>
            ))}
          </div>
        </div>

        {/* Step 3: Tax Invoicing & Cash Receipts */}
        <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800 rounded-2xl p-6 space-y-4">
          <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
            <span className="text-xs w-5 h-5 rounded-full bg-violet-600 flex items-center justify-center text-white">3</span>
            세무 증빙 서류 신청
          </h2>

          {isCardMethod && (
            <div className="p-3 bg-slate-950/40 border border-slate-800/60 rounded-xl text-xs text-slate-400">
              카드/간편결제는 PG사 매출전표가 자동 발행되어 세무 증빙으로 효력이 있으므로, 세금계산서 및 현금영수증 신청이 불가합니다.
            </div>
          )}

          {/* Tax Invoice Toggle - only available for cash methods */}
          {!isCardMethod && (<div className="border border-slate-800/60 rounded-xl p-4 bg-slate-950/20">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={invoiceRequested}
                onChange={(e) => {
                  setInvoiceRequested(e.target.checked);
                  if (e.target.checked) setCashReceiptRequested(false);
                }}
                className="accent-violet-500 rounded"
              />
              <div>
                <span className="font-semibold text-sm">B2B 세금계산서 / 계산서 발행 신청</span>
                <p className="text-xs text-slate-500 mt-0.5">사업자 결제 시 세무 회계용 영수증을 발행합니다.</p>
              </div>
            </label>

            {invoiceRequested && (
              <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4 border-t border-slate-800/60 pt-4 space-y-2 sm:space-y-0">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">증빙 종류</label>
                  <select
                    value={invoiceType}
                    onChange={(e) => setInvoiceType(e.target.value as InvoiceType)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-violet-500"
                  >
                    <option value={InvoiceType.TAX_INVOICE}>전자세금계산서 (과세)</option>
                    <option value={InvoiceType.INVOICE}>전자계산서 (면세/비과세)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">사업자등록번호</label>
                  <input
                    type="text"
                    value={companyRegNumber}
                    onChange={(e) => setCompanyRegNumber(e.target.value)}
                    placeholder="e.g. 123-45-67890"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-violet-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">상호명 / 회사명</label>
                  <input
                    type="text"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="상호명 입력"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-violet-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">대표자명</label>
                  <input
                    type="text"
                    value={ceoName}
                    onChange={(e) => setCeoName(e.target.value)}
                    placeholder="대표자 이름"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-violet-500"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-xs text-slate-400 mb-1">세금계산서 수신용 이메일</label>
                  <input
                    type="email"
                    value={taxEmail}
                    onChange={(e) => setTaxEmail(e.target.value)}
                    placeholder="tax@company.com"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-violet-500"
                  />
                </div>
              </div>
            )}
          </div>
          )}

          {/* Cash Receipt Toggle */}
          {isCashMethod && (
            <div className="border border-slate-800/60 rounded-xl p-4 bg-slate-950/20">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={cashReceiptRequested}
                  onChange={(e) => {
                    setCashReceiptRequested(e.target.checked);
                    if (e.target.checked) setInvoiceRequested(false);
                  }}
                  className="accent-violet-500 rounded"
                />
                <div>
                  <span className="font-semibold text-sm">현금영수증 발행 신청</span>
                  <p className="text-xs text-slate-500 mt-0.5">계좌이체 또는 가상계좌 입금 결제 시 신청 가능합니다.</p>
                </div>
              </label>

              {cashReceiptRequested && (
                <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4 border-t border-slate-800/60 pt-4 space-y-2 sm:space-y-0">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">용도</label>
                    <select
                      value={cashReceiptType}
                      onChange={(e) => setCashReceiptType(e.target.value as CashReceiptType)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-violet-500"
                    >
                      <option value={CashReceiptType.INCOME_DEDUCTION}>개인 소득공제용</option>
                      <option value={CashReceiptType.EXPENSE_PROOF}>사업자 지출증빙용</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">인증수단 유형</label>
                    <select
                      value={cashReceiptIdentityType}
                      onChange={(e) => setCashReceiptIdentityType(e.target.value as CashReceiptIdentityType)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-violet-500"
                    >
                      <option value={CashReceiptIdentityType.PHONE}>전화번호</option>
                      <option value={CashReceiptIdentityType.PERSONAL_ID}>주민등록번호 / 현금영수증카드번호</option>
                      <option value={CashReceiptIdentityType.BUSINESS_REG_NO}>사업자등록번호</option>
                    </select>
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block text-xs text-slate-400 mb-1">식별 정보 입력</label>
                    <input
                      type="text"
                      value={cashReceiptIdentityValue}
                      onChange={(e) => setCashReceiptIdentityValue(e.target.value)}
                      placeholder="숫자만 입력해 주세요"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs focus:outline-none focus:border-violet-500 font-mono"
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </form>

      {/* Checkout Sidebar Summary */}
      <div className="space-y-6">
        {/* Summary Card */}
        <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800 rounded-2xl p-6 space-y-4">
          <h3 className="font-bold text-sm text-slate-300 uppercase tracking-wider">주문 요약</h3>
          
          <div className="border-b border-slate-800 pb-4">
            <span className="text-xs text-slate-500">선택 상품</span>
            <div className="font-bold text-slate-200 mt-0.5">
              {products.find((p) => p.code === selectedProduct)?.name}
            </div>
          </div>

          <div className="border-b border-slate-800 pb-4">
            <span className="text-xs text-slate-500">결제 수단</span>
            <div className="font-medium text-slate-200 mt-0.5">
              {paymentMethod === PaymentMethod.CREDIT_CARD && '일반 신용카드'}
              {paymentMethod === PaymentMethod.KAKAO_PAY && '카카오페이'}
              {paymentMethod === PaymentMethod.NAVER_PAY && '네이버페이'}
            </div>
          </div>

          {/* Consents Box */}
          <div className="space-y-3 pt-2">
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={agreeTerms}
                onChange={(e) => setAgreeTerms(e.target.checked)}
                className="accent-violet-500 mt-0.5 rounded"
              />
              <span className="text-xs text-slate-400">개인정보 수집 및 결제대행 이용 약관에 동의합니다. (필수)</span>
            </label>

            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={agreeCrossBorder}
                onChange={(e) => setAgreeCrossBorder(e.target.checked)}
                className="accent-violet-500 mt-0.5 rounded"
              />
              <span className="text-xs text-slate-400">
                작업 플랫폼 연동을 위한 제3자 제공 동의 (필수) <br />
                <span className="text-[10px] text-slate-500 block mt-0.5 leading-relaxed">
                  * 연동되는 작업 플랫폼에는 개인정보가 배제된 <strong>고유 ID</strong> 및 결제 상태 신호만 전송되며,
                  실명, 전화번호, 세무 정보 등은 보안 서버에만 암호화 보관됩니다.
                </span>
              </span>
            </label>
          </div>

          {error && (
            <div className="p-3 bg-red-950/20 border border-red-900/50 rounded-xl text-red-400 text-xs">
              {error}
            </div>
          )}

          <div className="pt-2">
            <div className="flex justify-between items-baseline mb-4">
              <span className="text-sm text-slate-400">총 결제금액</span>
              <span className="text-2xl font-bold text-violet-400">
                {(products.find((p) => p.code === selectedProduct)?.price || 0).toLocaleString()} 원
              </span>
            </div>

            <button
              type="button"
              onClick={handleOpenCheckout}
              disabled={loading}
              className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold py-3 px-4 rounded-xl shadow-lg shadow-violet-500/20 transition-all flex items-center justify-center gap-2 hover:-translate-y-0.5"
            >
              {loading ? (
                <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
              ) : (
                '안전결제 대행창 열기'
              )}
            </button>
          </div>
        </div>
      </div>

      {/* MOCK PG MODAL DIALOG */}
      {showPgModal && prepData && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-6">
            <div className="flex justify-between items-center pb-4 border-b border-slate-800">
              <span className="font-bold text-slate-300">TossPayments 대행사 결제창 (MOCK)</span>
              <button 
                onClick={() => setShowPgModal(false)}
                className="text-slate-500 hover:text-slate-300"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-sm text-slate-400">
              <div className="flex justify-between">
                <span>상품명</span>
                <span className="font-medium text-slate-200">{prepData.productName}</span>
              </div>
              <div className="flex justify-between">
                <span>결제요청액</span>
                <span className="font-medium text-slate-200">{prepData.amountTotal.toLocaleString()} 원</span>
              </div>
              <div className="flex justify-between font-mono text-xs">
                <span>가맹점 주문코드</span>
                <span className="text-slate-300">{prepData.pgOrderId}</span>
              </div>
              <div className="flex justify-between">
                <span>선택수단</span>
                <span className="font-medium text-slate-200">{paymentMethod}</span>
              </div>
            </div>

            <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-2 text-xs text-slate-500 leading-relaxed">
              <p>✔ 이 창은 실제 PG 연동 모듈을 시뮬레이션하기 위한 안전 샌드박스 화면입니다.</p>
              {paymentMethod === PaymentMethod.VIRTUAL_ACCOUNT ? (
                <p className="text-violet-400 font-semibold">✔ 가상계좌 결제는 즉시 입금대기(WAITING)로 등록되며, Admin 패널에서 수납 확인이 가능합니다.</p>
              ) : (
                <p className="text-violet-400 font-semibold">✔ 승인하기 클릭 시 backend webhook callback에 서명을 보내 최종 PAID 처리됩니다.</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setShowPgModal(false)}
                className="py-3 border border-slate-800 rounded-xl text-slate-400 text-sm hover:bg-slate-800 transition"
              >
                결제 취소
              </button>
              <button
                type="button"
                onClick={handleSimulatePgApprove}
                disabled={pgLoading}
                className="py-3 bg-violet-600 hover:bg-violet-500 text-white font-semibold rounded-xl text-sm transition flex items-center justify-center"
              >
                {pgLoading ? (
                  <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                ) : (
                  paymentMethod === PaymentMethod.VIRTUAL_ACCOUNT ? '가상계좌 생성 승인' : '결제 최종 승인하기'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {showSuccessToast && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm bg-slate-900/90 border border-slate-800/80 backdrop-blur-md rounded-2xl p-6 shadow-2xl text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-emerald-950/60 border border-emerald-800/80 text-emerald-400 flex items-center justify-center text-2xl mx-auto">
              ✓
            </div>
            <div className="space-y-1">
              <h3 className="font-bold text-slate-100 text-lg">결제 요청 완료</h3>
              <p className="text-xs text-slate-400">보안 채널을 통해 결제 승인이 안전하게 처리되었습니다. 결과 확인 페이지로 이동합니다.</p>
            </div>
            <div className="flex justify-center">
              <span className="w-5 h-5 border-2 border-violet-600/30 border-t-violet-500 rounded-full animate-spin"></span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
