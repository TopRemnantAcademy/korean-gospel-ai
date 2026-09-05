"""请求/响应数据契约（Pydantic）。前端与后端以此为准。"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


# ---------- 鉴权 ----------
class RegisterReq(BaseModel):
    email: EmailStr
    password: str


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResp(BaseModel):
    """当前登录用户（GET /api/auth/me）。"""

    id: int
    email: EmailStr


# ---------- 歌曲生成 ----------
class GenerateReq(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    task: str = "generate"          # generate | custom | extend | cover | remix
    style: Optional[str] = None     # 风格标签，如 "国风 伤感 钢琴"
    prompt: Optional[str] = None    # 主题/情绪，如 "失恋的雨夜"
    lyric: Optional[str] = None     # 自定义歌词（留空则由 LLM 生成，Route B）
    title: Optional[str] = None
    vocal_gender: Optional[str] = None  # male | female | null
    make_instrumental: bool = False
    model_version: Optional[str] = None      # Suno mv，如 chirp-v4.5
    gpt_description_prompt: Optional[str] = None
    continue_song_id: Optional[str] = None   # extend/cover/remix 外部歌曲 id
    clip_seconds: Optional[int] = None       # extend 起点（秒）
    source_song_id: Optional[int] = None     # 站内父歌曲 id（血缘）
    persona_id: Optional[str] = None         # 已对接 open.suno.cn personaId（见 orchestrator/suno.py）
    is_public: Optional[bool] = False         # 是否公开到发现页
    content_category: Optional[str] = None   # 内容分类：general | christian_worship | instrumental（引擎路由依据）


class CropReq(BaseModel):
    start_time: int
    end_time: int


class SpeedReq(BaseModel):
    speed: float


class AlignedLyricsReq(BaseModel):
    lyrics: str


class SoundReq(BaseModel):
    title: str
    tags: Optional[str] = None
    model_version: Optional[str] = None
    tempo: Optional[int] = None
    key: Optional[str] = None
    loop: bool = False


class UploadReq(BaseModel):
    audio_url: str


class UploadResp(BaseModel):
    custom_id: str


class SpawnReq(BaseModel):
    """extend / cover / remix 的可选覆盖参数。"""

    model_config = ConfigDict(protected_namespaces=())

    prompt: Optional[str] = None
    style: Optional[str] = None
    title: Optional[str] = None
    lyric: Optional[str] = None
    make_instrumental: Optional[bool] = None
    model_version: Optional[str] = None
    clip_seconds: Optional[int] = None


class GenerateResp(BaseModel):
    song_id: int
    status: str


class SongOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    title: str
    custom_id: Optional[str] = None
    style: Optional[str] = None
    prompt: Optional[str] = None
    lyric: Optional[str] = None
    audio_url: Optional[str] = None
    cover_url: Optional[str] = None
    status: str
    make_instrumental: bool = False
    task_type: str = "generate"
    duration: int = 0
    parent_song_id: Optional[int] = None
    moderation_status: str = "pending"
    moderation_note: Optional[str] = None
    is_public: bool = False
    play_count: int = 0
    is_owner: bool = False
    content_category: Optional[str] = None
    cost_cny: Optional[float] = None
    # ---- 프리미엄 시청 게이트（미구독 = 앞 N초 프리뷰） ----
    preview_audio_url: Optional[str] = None   # 试听片段链接（前 N 秒）
    preview_seconds: Optional[int] = None     # 试听片段时长（秒）
    can_play_full: bool = False               # 是否可播放完整版（= 已订阅）
    can_download: bool = False                # 是否可下载完整音频（= 已订阅）
    created_at: str


# ---------- 管理后台（歌曲审核） ----------
class AdminSongOut(SongOut):
    user_email: Optional[str] = None
    # 以下字段仅后台可见（计费归因 / 模型版本 / 单位经济）；公共 SongOut 已剥离，避免向终端用户暴露引擎名与成本
    engine_name: Optional[str] = None
    model_version: Optional[str] = None
    price_cny: Optional[float] = None     # 对用户计费（名义收入）
    margin_cny: Optional[float] = None    # 毛利 = price - cost（负=亏损）
    tier_key: Optional[str] = None        # 适用套餐


class AdminStatsOut(BaseModel):
    total: int
    by_status: dict = {}
    by_moderation: dict = {}
    # 单位经济汇总（全量歌曲累计）
    total_cost_cny: float = 0
    total_revenue_cny: float = 0
    total_margin_cny: float = 0


class RejectReq(BaseModel):
    note: Optional[str] = None


# ---------- 管理后台（引擎/路由/计费：后台控制） ----------
class EngineConfigOut(BaseModel):
    provider: str
    display_name: Optional[str] = None
    enabled: bool = True
    is_default: bool = False
    api_base: Optional[str] = None
    api_key_set: bool = False          # 脱敏：仅表示是否配置，不返回明文
    cost_per_song_cny: float = 0
    priority: int = 0
    notes: Optional[str] = None


class EngineConfigCreate(BaseModel):
    provider: str                                 # suno/mock/musicgen/ace_step_private/tencent_mps/volcano
    display_name: Optional[str] = None
    enabled: bool = True
    is_default: bool = False
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    cost_per_song_cny: Optional[float] = None
    priority: Optional[int] = None
    notes: Optional[str] = None


class EngineConfigUpdate(BaseModel):
    display_name: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None     # 空字符串/不传表示不改
    cost_per_song_cny: Optional[float] = None
    priority: Optional[int] = None
    notes: Optional[str] = None


class RoutingRuleOut(BaseModel):
    id: int
    category: str
    provider: str
    priority: int
    enabled: bool


class RoutingRuleCreate(BaseModel):
    category: str
    provider: str
    priority: int = 0
    enabled: bool = True


class RoutingRuleUpdate(BaseModel):
    category: Optional[str] = None
    provider: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class PricingTierOut(BaseModel):
    id: int
    tier_key: str
    tier_name: Optional[str] = None
    engine_provider: Optional[str] = None
    price_cny: float = 0
    credits_per_song: int = 1
    model_version: Optional[str] = None   # 绑定生成模型（如 mureka-7.6）；空=引擎默认
    description: Optional[str] = None
    enabled: bool


class PricingTierCreate(BaseModel):
    tier_key: str
    tier_name: Optional[str] = None
    engine_provider: Optional[str] = None
    price_cny: Optional[float] = None
    credits_per_song: Optional[int] = None
    model_version: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True


class PricingTierUpdate(BaseModel):
    tier_name: Optional[str] = None
    engine_provider: Optional[str] = None
    price_cny: Optional[float] = None
    credits_per_song: Optional[int] = None
    model_version: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class AuditLogOut(BaseModel):
    id: int
    method: str
    path: str
    status_code: int
    actor_token_prefix: str = ""
    actor_role: str = "none"
    client_ip: str = ""
    created_at: Optional[str] = None


class ConfigDashboardOut(BaseModel):
    engines: list[EngineConfigOut]
    routing_rules: list[RoutingRuleOut]
    pricing_tiers: list[PricingTierOut]
    # 成本（供应商计费估算）
    cost_by_engine: dict = {}
    cost_by_category: dict = {}
    # 收入 / 毛利（按套餐标准价快照）
    revenue_by_tier: dict = {}
    margin_by_tier: dict = {}
    revenue_by_category: dict = {}
    margin_by_category: dict = {}
    # 全量汇总
    total_cost_cny: float = 0
    total_revenue_cny: float = 0
    total_margin_cny: float = 0
    margin_rate: float = 0  # 毛利率 0~1（毛利/收入）
    pending_moderation: int = 0


# ---------- FLOW APP 同步 ----------
class SyncStatusOut(BaseModel):
    sync_id: Optional[int] = None
    status: str  # not_synced | pending | synced | failed
    audio_cdn_url: Optional[str] = None


class FlowSongOut(BaseModel):
    song_id: int
    title: str
    audio_cdn_url: Optional[str] = None
    cover_url: Optional[str] = None
    lyric: Optional[str] = None
    style: Optional[str] = None
    synced_at: str


# ---------- FLOW APP 同步：令牌交换 / 绑定 ----------
class FlowLinkReq(BaseModel):
    """用户授权绑定：APP 同时持有音乐 JWT 与 FLOW subscriber_id 时调用（幂等 upsert）。"""

    subscriber_id: str


class FlowExchangeReq(BaseModel):
    """FLOW 后端 server-to-server：用 subscriber_id 换取 scope 限定(sync:flow) JWT。"""

    subscriber_id: str


class FlowExchangeResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    scope: str = "sync:flow"
