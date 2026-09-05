"""全局配置：从 .env 读取（参考 .env.example）。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 基础
    database_url: str = "sqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-please"
    access_token_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:3000"

    # 对象存储（S3 兼容，可留空）
    storage_endpoint: str = ""
    storage_region: str = "ap-hongkong"
    storage_bucket: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_public_base: str = ""

    # 音乐供应商：切换生成后端（Route B 供应商抽象）。
    #   suno : 商业 API（open.suno.cn 协议基线），需配置 SUNO_API_KEY
    #   mock : 本地开发 / CI，不调用任何外部 API，返回固定假数据
    # 业务代码只依赖 MusicProvider 接口（create/get），切换供应商无需改动业务层。
    # 注：真实引擎选择已改为 DB 后台配置驱动（app.orchestrator.selection），
    # 此处的 music_provider 仅作为「无后台配置时的最后回退默认值」。
    music_provider: str = "mureka"
    # Suno 商业 API 基址。协议基线以 open.suno.cn 为准（详见 app/orchestrator/suno.py）。
    # 接入 sunoapi.org / api.suno.ai 等其他服务时，需按各自文档调整端点与字段。
    suno_api_base: str = "https://open.suno.cn/api/v1"
    suno_api_key: str = ""    # Bearer key（open.suno.cn / sunoapi.org）
    suno_email: str = ""      # 无 key 时，gcui-art/suno-api 风格邮箱密码登录换 token
    suno_password: str = ""
    song_poll_interval: int = 8
    song_poll_timeout: int = 240

    # Mureka 商业 API（昆仑万维 Skywork AI）：主引擎（中文+英文主线）。
    # 官方文档：https://platform.mureka.ai/docs/api/ ；基址 https://api.mureka.ai/v1
    # 鉴权：Authorization: Bearer <MUREKA_API_KEY>；无官方 webhook → 轮询（同 Suno）。
    mureka_api_base: str = "https://api.mureka.ai/v1"
    mureka_api_key: str = ""
    mureka_model: str = "mureka-9"            # V9（与 Suno V5.5 Elo 持平、韩语反超）
    mureka_n: int = 1                         # 每次生成首数（1=单首省成本；2~3 需多 Song 落盘，见 P1.5）
    mureka_max_concurrent: int = 1            # 提交并发信号量上限，与采购档位对齐（入门1/基础5/标准15…）

    # 限流（MVP 内存实现；多实例生产改 Redis）
    enable_rate_limit: bool = True
    sync_rate_limit_per_minute: int = 10
    generate_rate_limit_per_minute: int = 5  # 单用户每分钟生成突发上限（429）
    login_rate_limit_per_minute: int = 10    # 单 IP 每分钟登录尝试上限（429）
    per_user_daily_quota: int = 3            # 免费用户每日生成配额（超限 402 引导订阅）

    # 审核（默认启用文本机审；P3 音频机审默认关闭）
    # 启用：enable_moderation=True 开文本机审（blocklist.txt 实际词库，见 moderation._blocklist_path）；
    #       enable_audio_moderation=True 开 P3 音频机审（需接 ASR+审核 API）。
    # [D33] 공존 출시 기준: 중국 대상 서비스이므로 텍스트 심의를 기본 ON 으로 한다.
    #       OFF 로 두면 생성곡이 미심의(pending) 로 남아 explore/sync 에서 제외된다.
    enable_moderation: bool = True
    # 音频机审（P3）：生成完成后对最终音频做内容审核（需接 ASR+审核 API）。
    # 默认关闭：MVP 不阻塞生成、不依赖外部；启用后未通过标记 rejected。
    enable_audio_moderation: bool = False

    # 音频后处理（F1 响度 / F2 母带 / F3 降噪 / F4 分离；默认关闭，需 storage 下载/重托管）
    enable_audio_postprocess: bool = False
    audio_postprocess_steps: str = "loudness,mastering,denoise"  # 可选追加 separation（需 GPU）
    audio_postprocess_ffmpeg_bin: str = "ffmpeg"
    # ---- 未订阅试听门控（freemium：完整生成，未订阅只给前 N 秒试听） ----
    # 说明：生成始终是完整歌曲（Mureka 无 duration 参数，见 orchestrator/mureka.py 注释）；
    #      门控只发生在「分发」环节——未订阅者拿到的是裁剪后的试听片段链接。
    enable_preview_clip: bool = True      # 生成完成时产出试听片段（ffmpeg 裁剪上传）
    preview_seconds: int = 60             # 未订阅者可试听时长（秒）
    # 试听片段存放位置：
    #   · 配好 storage_*  → 上传到对象存储桶（生产推荐，走 CDN）
    #   · 未配 storage_*  → 落本地缓存目录，由 GET /api/songs/{id}/preview 按需生成并下发
    #     （⚠ 必须有这条回退：否则未订阅者因片段生成失败而「完全听不到」，门控变功能停止）
    preview_cache_dir: str = ".cache/preview"
    # 按需生成试听片段时需先下载完整音频——上游慢/卡住会一直占着请求线程，
    # 而 httpx 的 timeout 是「两次读取之间的空闲」上限，对"匀速慢速"上游无效，故另设整体护栏。
    preview_fetch_timeout: float = 25.0   # 整体下载上限（秒），超时按片段不可用处理
    preview_fetch_max_mb: int = 80        # 单曲音频体积上限（MB），防止异常大文件拖垮本机

    # 管理后台
    admin_token: str = ""  # 管理台访问密钥（X-Admin-Token）；为空则禁用 admin 路由
    admin_viewer_token: str = ""  # 只读管理员令牌；仅允许 GET，变更类接口返回 403
    encryption_key: str = ""      # Fernet 密钥（base64 32字节或任意口令自动派生）；生产必须设置

    # FLOW ↔ 音乐 co-location 令牌交换（server-to-server 内部密钥）。
    # 为空则 /api/auth/flow-exchange 返回 503（功能未启用）。绝不向客户端暴露。
    flow_internal_token: str = ""
    # flow-exchange 发放的 scope 限定(sync:flow) JWT 寿命（分钟）。默认 60。
    flow_exchange_token_expire_minutes: int = 60

    # ---- 计费 / 支付 (GAP-004 真实支付基座) ----
    # billing_mode:
    #   offline — 允许 mock /api/auth/subscribe 与 manual 确认(开发·运维对账). 默认, 不破坏现有前端.
    #   live    — 仅真实 provider 流程; mock /subscribe 返回 410(防止绕过支付直接升档).
    billing_mode: str = "offline"
    # billing_provider: manual | stripe | kakao | naver | wechat | alipay
    #   step-1: manual = 全功能(无外部依赖, 可测可运营); stripe = webhook 验签已实现, checkout SDK 为 step-2 seam.
    billing_provider: str = "manual"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    billing_return_url: str = ""  # 支付完成回跳前端地址(Stripe success_url 等)
    # ---- 多币种(USD/KRW) — step-2 provider 子轨 ----
    # billing_currencies: 允许的计费币种(逗号分隔). 默认仅 CNY.
    billing_currencies: str = "CNY,USD,KRW"
    # 固定汇率(以 CNY 为基准): 1 CNY = x 外币.
    # ⚠ MVP 固定值, 非实时行情(拒绝幻觉: 不臆造实时汇率 API; 真实部署应定期刷新这些值或接入汇率服务).
    fx_rate_cny_to_usd: float = 0.14    # ¥1 ≈ $0.14 (≈ $1 ≈ ¥7.14)
    fx_rate_cny_to_krw: float = 190.0   # ¥1 ≈ ₩190 (≈ ₩1 ≈ ¥0.00526)
    # Stripe Checkout 订阅周期(默认月付)
    stripe_recurring_interval: str = "month"

    # ================= 亚洲本地 PG(step-4) =================
    # 说明: 以下字段全部默认空 → 对应 provider 未配置时抛出明确 RuntimeError(503),
    #       绝不静默降级为"看起来成功"。所有端点/签名算法均取自各家官方文档。

    # ---- KakaoPay (KRW) ----
    # ⚠ 实证(2026-09-04, 카카오페이 개발자센터 공식): 구 카카오디벨로퍼스 경로
    #   (kapi.kakao.com/v1/payment/*) 는 **공식 종료**되었다. 현행 공식값은 아래 하나뿐이다.
    #     Host : https://open-api.kakaopay.com   (개발/샌드박스 호스트 없음)
    #     Path : /online/v1/payment/ready , /online/v1/payment/approve
    #     인증 : Authorization: SECRET_KEY ${SECRET_KEY}
    #     바디 : JSON 객체 (Content-Type: application/json)
    #   아래 kakao_pay_api_base / kakao_pay_auth_scheme 의 KakaoAK 는 레거시 호환용으로만 남긴다.
    kakao_pay_cid: str = ""                       # 가맹점 코드(테스트: TC0ONETIME)
    kakao_pay_credential: str = ""                # Secret key (레거시 호환: ADMIN_KEY)
    kakao_pay_auth_scheme: str = "SECRET_KEY"     # SECRET_KEY(공식/기본) | KakaoAK(레거시)
    kakao_pay_api_base: str = "https://open-api.kakaopay.com"

    # ---- NaverPay (KRW) ----
    # 결제창은 프론트 JS SDK(Naver.Pay.create → oPay.open) handoff 방식.
    # 서버 승인(apply) API 는 **공식 문서로 확정**(docs.pay.naver.com, 2026-09-04 실증):
    #     POST https://{dev-pay|pay}.paygate.naver.com/naverpay-partner/naverpay/payments/v2.2/apply/payment
    #     body(form-urlencoded): paymentId
    #     header: X-Naver-Client-Id / X-Naver-Client-Secret / X-NaverPay-Chain-Id / X-NaverPay-Idempotency-Key
    #   → 따라서 naver_pay_apply_url 을 비워도 NAVER_PAY_MODE 로 공식 호스트를 유도한다.
    #     (계약상 별도 도메인을 쓰는 경우에만 naver_pay_apply_url 로 전체 URL 덮어쓰기)
    naver_pay_client_id: str = ""
    naver_pay_chain_id: str = ""
    naver_pay_secret_key: str = ""
    naver_pay_mode: str = "development"      # development | production (JS SDK + API 호스트)
    # 서버 승인 API 의 **전체 URL** 오버라이드(파트너 계약 문서 기준). 비우면 위 공식 호스트 사용.
    naver_pay_apply_url: str = ""
    naver_pay_api_base: str = ""             # 조회/취소 등 확장용(현재 미사용, 계약 문서 값)

    # ---- WeChat Pay v3 (CNY) ----
    # Native 下单: POST {api_base}/v3/pay/transactions/native   (官方 native_prepay.md)
    #   主域名 https://api.mch.weixin.qq.com / 备域名 https://api2.mch.weixin.qq.com
    #   必填头: Authorization + Accept: application/json + Content-Type: application/json
    #   description 上限 127 字符; out_trade_no 6~32 位, 仅 数字/字母/_-|*
    # 认证头: Authorization: WECHATPAY2-SHA256-RSA2048 mchid=..,nonce_str=..,timestamp=..,serial_no=..,signature=..
    #   待签名串 = f"{METHOD}\n{PATH}\n{ts}\n{nonce}\n{body}\n"(五行, 含末尾换行)
    #   官方明确: 五项签名信息无顺序要求(signature-generation.html 第 4 节)
    # 回调(native_notify.md):
    #   验签头 = Wechatpay-Timestamp/Nonce/Signature/**, Wechatpay-Serial 用于选择验签密钥**
    #     官方原文: "微信支付公钥的序列号固定采用 PUB_KEY_ID_数字串 格式; 若请求头中的序列号
    #                不符合该格式, 则应使用平台证书进行验签。"
    #   官方 SDK(wechatpay-java NotificationParser) 对 serialNumber 缺失直接抛异常
    #   业务数据在 resource 里, 用 APIv3 密钥(32 字节)做 AES-256-GCM 解密
    #   应答: 验签通过 → 200/204(无需报文); 不通过 → 4xx/5xx + {"code":"FAIL"}
    #   官方会发送 WECHATPAY/SIGNTEST/ 前缀的假签名探测, 必须正常验签并拒答(4013053249 第 5 节)
    wechat_pay_mch_id: str = ""
    wechat_pay_app_id: str = ""
    wechat_pay_api_v3_key: str = ""          # APIv3 密钥(32 字节), 回调 AES-256-GCM 解密用
    wechat_pay_cert_serial_no: str = ""      # 商户 API 证书序列号
    wechat_pay_private_key: str = ""         # 商户私钥 PEM 内容(\n 可写成字面 \\n)
    wechat_pay_private_key_path: str = ""    # 或私钥文件路径(二者取其一, inline 优先)
    wechat_pay_platform_public_key: str = ""       # 微信支付平台公钥 PEM(回调验签)
    wechat_pay_platform_public_key_path: str = ""
    # 微信支付公钥 ID(形如 PUB_KEY_ID_3000000001). 空 = 平台证书模式.
    # 官方(sign_verify.md 2.2)把「微信支付公钥」标为【推荐】, 平台证书为可选项.
    # 两种模式的 PEM 都是公钥, 区别只在"回调头 Wechatpay-Serial 应与哪个标识匹配":
    #   非空 → 公钥模式: 回调 serial 必须与此值完全一致, 否则拒绝(防密钥错配)
    #   空   → 平台证书模式: 若回调 serial 形如 PUB_KEY_ID_*, 说明微信在用公钥签名而我们
    #          配的是平台证书 → 明确报错引导配置, 不用错密钥静默验签失败
    wechat_pay_pub_key_id: str = ""
    wechat_pay_notify_url: str = ""          # 回调地址(须公网 HTTPS)
    wechat_pay_api_base: str = "https://api.mch.weixin.qq.com"

    # ---- Alipay (CNY) ----
    # 电脑网站支付: alipay.trade.page.pay(FAST_INSTANT_TRADE_PAY), 网关 https://openapi.alipay.com/gateway.do
    # 签名(RSA2 = SHA256withRSA): 待签名串 = 剔除 sign(保留 sign_type) → 字母序 → "k=v&k=v"(值不编码)
    # 验签(rsaCheckV1, 官方指定用于支付接口): 待验签串 = **同时剔除 sign 与 sign_type** → 其余参数
    #   URLDecode 后字母序拼接。官方依据:
    #     - 官方文档 opendocs.alipay.com/open/02pa44「异步通知结果验签」:
    #       "在通知返回参数列表中, 除去 sign、sign_type 两个参数外, 凡是通知返回回来的参数皆是待验签的参数"
    #     - 官方 SDK Java AlipaySignature.getSignCheckContentV1: params.remove("sign"); remove("sign_type")
    #     - 官方 SDK PHP AopClient.rsaCheckV1: unset($params['sign']); unset($params['sign_type'])
    #   (rsaCheckV2 保留 sign_type, 仅用于生活号/服务窗异步, 不适用于本接口)
    # 应答: 必须返回纯文本 success, 其它一律视为失败并多次重投.
    alipay_app_id: str = ""
    alipay_private_key: str = ""             # 应用私钥 PEM(签名)
    alipay_private_key_path: str = ""
    alipay_public_key: str = ""              # 支付宝公钥 PEM(验异步通知签名)
    alipay_public_key_path: str = ""
    alipay_gateway: str = "https://openapi.alipay.com/gateway.do"
    alipay_notify_url: str = ""
    alipay_sign_type: str = "RSA2"           # 仅支持 RSA2(RSA/SHA1 已被支付宝弃用)

    # ---- PayPal (Subscriptions API · 多币种) ----
    # 官方实证(2026-09-05, developer.paypal.com/*.md 原文):
    #   Host  : sandbox = https://api-m.sandbox.paypal.com   live = https://api-m.paypal.com
    #   取 token: POST /v1/oauth2/token  Basic(client_id:client_secret)
    #             Content-Type: application/x-www-form-urlencoded  body: grant_type=client_credentials
    #   建订阅 : POST /v1/billing/subscriptions  必需字段仅 plan_id(26 位, ^P-[A-Z0-9]*$)
    #             custom_id = 商户自定义 ID(1~127 位可打印 ASCII) ← 用于回调回贴本地订单
    #             application_context.user_action=SUBSCRIBE_NOW 时买家批准后自动激活
    #             响应 links[].rel == "approve" 的 href 即买家批准页(https://www.paypal.com/webapps/billing/subscriptions?ba_token=...)
    #   回调验签: **不是本地 HMAC**, 而是把回调回传给 PayPal 服务器核验:
    #             POST /v1/notifications/verify-webhook-signature
    #             body = {auth_algo, cert_url, transmission_id, transmission_sig,
    #                     transmission_time, webhook_id, webhook_event}
    #             五个字段分别取自回调头 PAYPAL-AUTH-ALGO / PAYPAL-CERT-URL /
    #             PAYPAL-TRANSMISSION-ID / PAYPAL-TRANSMISSION-SIG / PAYPAL-TRANSMISSION-TIME
    #             成功响应 = {"verification_status": "SUCCESS"}
    #   回调应答: 2xx 视为收到; 非 2xx 重试最多 25 次 / 3 天.
    #
    # ⚠ 官方币种表(developer.paypal.com/reference/currency-codes)共 25 种, **不含 KRW**
    #   → 韩国主体不可能用 PayPal 收韩元。
    # ⚠ CNY / BRL / MYR 官方脚注: "supported as a payment currency or settlement currency
    #   only for in-country PayPal accounts" —— 非中国主体收 CNY 会被换算为账户主币种并加价差。
    #   → 默认受理集合已剔除这三种; 若确为 PayPal 中国主体账户, 在 PAYPAL_CURRENCIES 里显式加回 CNY.
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_mode: str = "sandbox"             # sandbox | live
    paypal_webhook_id: str = ""              # Developer Portal 里该 webhook 的 ID(验签必传)
    # tier_key → plan_id 的 JSON 映射(plan 需在 PayPal 侧预先建好).
    # 支持两种 key: "standard" (不区分币种) 与 "standard:USD" (按币种指定). 查表顺序: 带币种优先.
    # 例: {"standard": "P-5ML4271244454362WXNWU5NQ", "pro:USD": "P-XXXX", "pro:EUR": "P-YYYY"}
    paypal_plan_ids: str = ""
    paypal_return_url: str = ""              # 留空则回退 billing_return_url
    # 可受理币种(逗号分隔). 默认 = 官方 25 种中剔除 CNY/BRL/MYR(限本国账户)后的全部.
    paypal_currencies: str = (
        "AUD,CAD,CZK,DKK,EUR,GBP,HKD,HUF,ILS,JPY,MXN,NZD,NOK,PHP,PLN,SGD,SEK,CHF,THB,TWD,USD"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @staticmethod
    def _load_pem(inline: str, path: str) -> str:
        """PEM 取值: inline 优先(支持 .env 里把换行写成字面 \\n), 否则读文件; 都无则空串。

        返回空串代表"未配置" —— 调用方须据此抛出明确错误, 不得静默继续.
        """
        if inline and inline.strip():
            return inline.replace("\\n", "\n")
        if path and path.strip():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError:
                return ""
        return ""

    @property
    def wechat_pay_private_key_pem(self) -> str:
        return self._load_pem(self.wechat_pay_private_key, self.wechat_pay_private_key_path)

    @property
    def wechat_pay_platform_public_key_pem(self) -> str:
        return self._load_pem(
            self.wechat_pay_platform_public_key, self.wechat_pay_platform_public_key_path
        )

    @property
    def alipay_private_key_pem(self) -> str:
        return self._load_pem(self.alipay_private_key, self.alipay_private_key_path)

    @property
    def alipay_public_key_pem(self) -> str:
        return self._load_pem(self.alipay_public_key, self.alipay_public_key_path)


settings = Settings()
