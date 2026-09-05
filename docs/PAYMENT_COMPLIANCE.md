# 결제 컴플라이언스 & 채널 격리 아키텍처

> 최종 갱신: 2026-07-31. 사용자 결정사항 + 기술 구현 매핑.

## 1. 비즈니스 컨텍스트 (확정 사실)
- **운영자 위치**: 대한민국 거주
- **주 사용자**: 중국 본토 (대륙)
- **서버 위치**: 홍콩 (대륙에서 직접 접근 가능, 무비안기록, 저지연)
- **자금 귀속**: 대한민국 대금 인출 필요
- **상품 속성**: 디지털 가상 상품 (음악/찬양 스트리밍, 멤버십)

## 2. 결제 전략 (사용자 승인)
**1순위: 대한민국 법인 + PortOne跨境 모듈 (단일 채널로 충분)**
- PortOne 이 한국 카드 + 중국 위챗페이(알리페이 Alipay+) 해외 채널을 이미
  집계 → 별도 위챗/알리페이 가맹 불필요, 1개 SDK 로 커버.
- 사용자 명시: "PortOne 하나면 당분간 충분". 추가 법인/채널은 사업 검증 후.

**예비: 홍콩 법인 + 환급 가능 기관 (连连/PingPong/WorldFirst)** — 아직 미적용.
**비권장: 중국 본토 법인 + 서비스무역 결제** — 외환통제 리스크.

## 3. Google Play 상점 정책 (절대 준수)
> GP 개발자 정책: 앱 내 디지털 상품 결제는 **Google Play Billing 전용**,
> 위챗/알리페이 등 제3자 결제 코드/진입점 금지 (발견 시 삭제+계정 정지).

→ **물리적 채널 격리** (코드 레벨 분리, 런타임 토글 아님):
| 채널 | 배포 | PortOne SDK | 결제 진입 |
|------|------|-------------|-----------|
| `direct` (기본) | 홍콩 자체 도메인 직분 / 사설 배포 | ✅ 주입 | PortOne (위챗/알리페이/한국카드) |
| `googleplay` | GP 상점 (해외用户) | ❌ 완전 제거 | GP Billing placeholder (향후 연동) |

중국 직분 패키지도 PortOne 을 사용 (위챗/알리페이는 PortOne 채널 내장 —
**독립 제3자 SDK 가 아님** → GP 정책 위반 아님. GP 패키지에서는 PortOne 자체를 제거).

## 4. 빌드 채널 주입 (scripts/build-config.js)
```
node scripts/build-config.js android --market=cn   --channel=direct     # 중국 직분
node scripts/build-config.js android --market=global --channel=direct   # 해외 직분
node scripts/build-config.js android --channel=googleplay              # GP 상점용
```
- `--channel=googleplay` → `__GOSPEL_PORTONE_SDK__` 를 빈 문자열로 치환(PortOne 코드 0),
  `window.GOSPEL_PAYMENT_CHANNEL='googleplay'`.
- `mobile/screens/index.js` 의 `openPayment()` 는 `googleplay` 채널에서 PortOne 을
  호출하지 않고 GP Billing 안내로 폴백 (GP 정책 안전망).

## 5. 백엔드 (이미 구현·검증)
- `backend/app/api/payment.py`: PortOne V2 pre-register 흐름. plans:
  standard_monthly(3,900) / premium_monthly(9,900) / premium_yearly(99,000) / lifetime(299,000).
- `PORTONE_CHANNEL_KEY` / `PORTONE_WEBHOOK_SECRET` 콘솔 발급 필요 (미설정 시 503/무인증으로 안전 폴백).
- 결제 완료 → subscriber 승급 (`subscriber.is_lifetime_member` 등).

## 6. 해야 할 것 (수동·법인)
- [ ] 한국(또는 홍콩) 법인 등록 + PortOne跨境 모듈 개통 (매니저 문의)
- [ ] 음원 저작권 증명 / 가상상품 클래스 심사 자료
- [ ] 한국 법인: 부가세+법인세 신고. 홍콩 법인: 회계감사 (조건부 오프쇼어 면제 가능)
- [ ] GP 상점 진출 시: 별도 패키지명 + GP Billing 실제 연동 (channel=googleplay 빌드 사용)
- [ ] 회색 채널(개인 수금코드/제4자 대리징수/사적 환전) 절대 금지
