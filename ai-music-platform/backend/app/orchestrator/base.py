"""音乐供应商抽象层。

定义统一接口 MusicProvider 与数据结构。
- Route A（当前）：S unoProvider 封装商业 API
- Route B（后续）：实现同一接口，换成 Replicate/Fal 跑开源模型（YuE/CosyVoice）
切换供应商只需改 settings.music_provider，业务代码无需改动。
"""
from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict


class ModerationBlockedError(Exception):
    """供应商在提交阶段（create）明确判定内容违规/被审核拦截时抛出。

    client.generate 捕获后切换到引擎链中的下一引擎（Failover, P2）；
    若所有引擎均拦截，则最终以 failed + moderation_blocked=True 收尾。
    """


class GenerateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prompt: str | None = None
    style: str | None = None          # 风格标签（对应 Suno tags）
    lyric: str | None = None
    title: str | None = None
    vocal_gender: str | None = None
    make_instrumental: bool = False
    # —— 对标 Suno 真实产品能力（2026-08-27 对照 open.suno.cn 协议）——
    task: str = "generate"            # generate | custom | extend | cover | remix
    model_version: str | None = None  # Suno mv，如 "chirp-v4"（chirp-fenix=V5.5），空则供应商默认
    gpt_description_prompt: str | None = None
    continue_song_id: str | None = None   # extend/cover/remix：基于的外部歌曲 custom_id
    clip_seconds: int | None = None       # extend：续写起点（秒，部分服务商支持）
    persona_id: str | None = None         # Suno Persona（open.suno.cn / sunoapi.org 支持 personaId）


class SongResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    external_id: str = ""
    custom_id: str | None = None  # 供应商歌曲 id（续写/翻唱基准，open.suno.cn 为 UUID）
    status: str = "pending"   # pending | processing | completed | failed
    audio_url: str | None = None
    cover_url: str | None = None
    lyric: str | None = None
    title: str | None = None
    model_version: str | None = None
    duration: int | None = None
    # P2 Failover / 明确审核提示：
    moderation_blocked: bool = False  # True=判定为内容拦截（非基础设施失败）
    moderation_note: str | None = None  # 拦截/失败原因，供前端明确提示


class MusicProvider(ABC):
    @abstractmethod
    async def create(self, req: GenerateRequest) -> SongResult:
        """提交一次生成，返回任务/歌曲 external_id（状态 processing）。"""

    @abstractmethod
    async def get(self, external_id: str) -> SongResult:
        """查询生成结果；completed 时带 audio_url 等。"""
