# GOSPEL PAY 게이트웨이 (payment-gateway) - Korean PG Payment & China Integration Platform

GOSPEL PAY 게이트웨이는 korean-gospel-ai 프로젝트의 중국 채널 전용 결제 게이트웨이입니다. 한국 고객 PII(개인식별정보)와 중국 처리 시스템을 분리하기 위해 결정론적 불변 UID를 생성하고, 멱등 큐를 통해 동기화 이벤트를 비동기 라우팅합니다.

이 모노레포는 `korean-gospel-ai/payment-gateway/` 하위에 위치하며, korean-gospel-ai 메인 백엔드(포트 8000, 글로벌/다이렉트 채널용 PortOne)와는 별도의 포트 5000에서 중국(cn) 채널을 전담합니다.

---

## 1. API Endpoint Reference

### Public APIs

#### 1. Social Identify
* **Endpoint**: `POST /api/social/identify`
* **Description**: Authenticates or signs up a Korean customer, deterministic UID calculation, handles phone-based account linking.
* **Authentication**: None (Rate limited).
* **Request Schema**:
  ```json
  {
    "provider": "google | kakao | apple",
    "providerSubject": "string",
    "email": "string (optional)",
    "phone": "string (optional, e.g. 010-1234-5678)"
  }
  ```
* **Response Example (200 OK / 201 Created)**:
  ```json
  {
    "userId": "d290f1ee-6c54-4b01-90e6-d701748f0851",
    "uid": "a3f4e8b9... (64-character SHA-256 hex user ID)",
    "emailMasked": "pia******@gmail.com",
    "phoneMasked": "010-****-5678"
  }
  ```
* **Error Cases**:
  - `400 Bad Request`: Invalid email format or phone pattern (Zod validation error).

#### 2. Get Payment Methods
* **Endpoint**: `GET /api/payment-methods`
* **Description**: Returns all active and configured Korean payment channels.
* **Response Example (200 OK)**:
  ```json
  [
    {
      "id": "e9b23b32...",
      "paymentMethod": "CREDIT_CARD",
      "enabled": true,
      "displayName": "신용카드",
      "supportsRefund": true,
      "supportsPartialRefund": true,
      "supportsCashReceipt": false
    }
  ]
  ```

#### 3. Prepare Payment Order
* **Endpoint**: `POST /api/payments/prepare`
* **Description**: Registers a checkout order pre-authorization.
* **Request Schema**:
  ```json
  {
    "userId": "d290f1ee-6c54...",
    "productCode": "CREDIT_100 | CREDIT_500 | CREDIT_1000",
    "selectedPaymentMethod": "CREDIT_CARD | ACCOUNT_TRANSFER | ...",
    "invoiceRequested": true,
    "cashReceiptRequested": false
  }
  ```
* **Response Example (201 Created)**:
  ```json
  {
    "paymentOrderUuid": "f1092ab7-5501...",
    "pgOrderId": "order_id_prisma_key",
    "amountTotal": 11000,
    "productName": "100 Credits Package"
  }
  ```

#### 4. PG Checkout Confirm (Callback Webhook)
* **Endpoint**: `POST /api/payments/callback`
* **Description**: Confirms the authorization code from PG, performs VAT breakdown, encrypts billing PII, logs outbound communication, and enqueues worker tasks.
* **Request Schema**:
  ```json
  {
    "paymentKey": "mock_key_abc123",
    "orderId": "order_id_prisma_key",
    "amount": 11000,
    "paymentMethod": "CREDIT_CARD",
    "status": "DONE",
    "invoiceRequested": false,
    "cashReceiptRequested": false
  }
  ```
* **Response Example (200 OK)**:
  ```json
  {
    "success": true,
    "paymentUuid": "f1092ab7-5501..."
  }
  ```

#### 5. Get Payment Status
* **Endpoint**: `GET /api/payments/:paymentUuid/status`
* **Description**: Returns real-time status of payment confirmation and background worker subtasks (credit dispatches, tax documents).
* **Response Example (200 OK)**:
  ```json
  {
    "paymentUuid": "f1092ab7-5501...",
    "paymentStatus": "PAID",
    "receiptType": "NONE",
    "creditStatus": "CONFIRMED",
    "creditedAt": "2026-06-11T12:00:00.000Z",
    "invoiceRequestStatus": null
  }
  ```

---

### Admin APIs

#### 1. Admin Authentication Login
* **Endpoint**: `POST /api/admin/auth/login`
* **Request**: `{ "email": "piaoyhyh@gmail.com", "password": "..." }`
* **Response (200 OK)**: `{ "token": "JWT_TOKEN", "user": { "id": "...", "email": "piaoyhyh@gmail.com", "role": "SUPER_ADMIN" } }`

#### 2. Process Refund
* **Endpoint**: `POST /api/admin/payments/:paymentUuid/refund`
* **Role Requirement**: `SUPER_ADMIN` or `FINANCE_ADMIN`.
* **Request Schema (Total/Partial)**:
  ```json
  {
    "refundAmount": 5500,
    "refundReason": "고객 부분 취소 요청",
    "refundBankCode": "004 (optional if VA)",
    "refundAccountNumber": "string (optional)",
    "refundAccountHolder": "string (optional)"
  }
  ```
* **Response (201 Created)**: `{ "success": true, "refundUuid": "..." }`

---

## 2. Regulatory Compliance Disclosures

### A. 개인정보 처리방침 (국외이전 관련 고지 조항 초안)

> **[개인정보의 국외 이전 동의]**
> 
> 회사는 서비스 이용자에게 해외 크레딧 충전 및 싱킹 연동 서비스를 제공하기 위해 아래와 같이 개인정보를 국외로 이전합니다.
> 
> 1. **이전받는 자**: China central credit storage server (partner-credit@worksite.example.com)
> 2. **이전되는 국가**: 중국 (China)
> 3. **이전 일시 및 방법**: 결제 완료 시 보안 프로토콜(HTTPS TLS 1.3)을 통해 즉시 전자적 전송
> 4. **이전되는 개인정보 항목**: **실명, 이메일, 전화번호 등 일체의 식별가능 인적정보 제외**, 오직 암호화된 **고유 UID(SHA-256 해시값)** 및 **크레딧 충전 수량/결제 식별코드**에 한함.
> 5. **이전받는 자의 이용 목적**: 중국 소셜 계정의 크레딧 지급 및 충전 잔액 동기화
> 6. **보유 및 이용 기간**: 대한민국 국세기본법에 따른 거래 증빙 보관의무(5년)가 완료될 때까지 보존 후 파기
> 7. **동의 거부 권리**: 이용자는 본 동의를 거부할 권리가 있으나, 거부 시 크레딧 자동 싱킹 서비스 이용이 제한됩니다.

---

### B. 세금계산서 및 현금영수증 상충방지 규정
대한민국 부가가치세법 제32조에 따라 동일 거래에 대해 **신용카드 매출전표(PG 영수증)**, **전자세금계산서**, **현금영수증**은 중복 발행할 수 없습니다.
- **카드 결제**: PG사 대행 결제완료 시 자동으로 신용카드 영수증(매출전표)이 세무 증빙으로 효력을 가지므로, 세금계산서 및 현금영수증 신청은 서버 비즈니스 로직에 의해 원천 차단됩니다.
- **현금 결제 (계좌이체/가상계좌)**: 세금계산서를 발급한 경우 소득세법 제162조의3에 의거하여 현금영수증 중복 발급이 불가합니다. Checkout logic에서 `invoiceRequested`가 참이면 `cashReceiptRequested` 설정을 자동으로 false 변경하여 더블 신청을 차단합니다.
