"""Route A：Mureka 商业 API 封装（昆仑万维 Skywork AI）。

官方协议（2026-09-03 全量核对 platform.mureka.ai/docs：全部 28 个 API 操作 + 5 个指南）：
- 服务器：https://api.mureka.ai  （quickstart 确认；config.mureka_api_base=.../v1 对齐）
- 鉴权：Authorization: Bearer <MUREKA_API_KEY>  （quickstart 确认；错误包体 {"error":{"message":...},"trace_id":...}）
- 本封装实际调用：
  · POST {base}/song/generate  （歌词生曲，USED）
      请求体：lyrics(必填,≤5000), model(auto/mureka-7.6/mureka-o2/mureka-8/mureka-9/mureka-9.5),
              n(默认2最大3,按首计费), prompt(≤1024,自由文本风格), gender(female/male),
              reference_id, vocal_id, melody_id, stream
      响应(200)：{ id, created_at, finished_at, model, status, failed_reason, choices[] }
  · GET {base}/song/query/{task_id}  （轮询，USED）
  · GET {base}/account/billing  （get_billing()，查余额/并发上限，见下）
- ⚠️ choices[] 子字段(audio_url/cover_url/lyrics/title/duration/id)的真实 schema：
  经核对 generate/query/easy-generate/extend/remix/region-edit/vocal-clone/stem/instrumental
  共 9 个文档，全部仅标 "object[]" 而**不展开** → 官方文档处处未公开子字段名，
  只能靠**账号充值后实机成功调用**校准。本文件以多候选键容错解析（见 get()）。
- 风格控制：本封装用 generate 的 prompt 自由文本注入 "gospel"。
  ⚠️ 注意 easy-generate(Prompt to song) 才有结构化 styles:["gospel"] 枚举，但它**无 lyrics 字段**；
  本产品是用户歌词生曲 → 用 generate+prompt 注入是正确的（非遗漏）。
- 未实现但已核对的相邻能力（future/out-of-scope，均非歌词生曲主路径）：
  easy-generate(prompt→song)、song/extend、song/remix、song/vocal-clone(vocal_id 源)、
  instrumental/generate+query(prompt-only)、lyrics/generate、song/stem(分轨)、
  song/region-edit(改词)、soundtrack/track/video/tts(其他产品线)、files/upload 分块版(uploads-*)。
- 无官方 webhook/CallbackURL → 走轮询（同 Suno）；回调优势仅火山 GenBGM 享有。

实现要点：
- 对齐 MusicProvider 契约：create() 提交并返回 SongResult(external_id=task_id, status="processing")；
  get() 轮询并映射状态/音频/封面/歌词/时长/模型版本。
- 并发：asyncio.Semaphore(mureka_max_concurrent) 约束提交并发，避免入门档(1并发)被 429。
- 容错解析：choices 字段名在不同版本可能微调，做多候选键容错。
- n>1（多首）暂取 choices[0] 映射单条 SongResult；多首落盘见 P1.5（需多 Song 行）。
"""
import asyncio

import httpx

from app.config import settings
from app.orchestrator.base import GenerateRequest, MusicProvider, SongResult


_STATUS_PROCESSING = {"preparing", "queued", "running", "streaming"}
_STATUS_FAILED = {"failed", "timeouted", "cancelled"}


class MurekaProvider(MusicProvider):
    def __init__(self):
        self.base = settings.mureka_api_base.rstrip("/")
        self.api_key = settings.mureka_api_key
        self.model = settings.mureka_model or "mureka-9"
        self.n = max(1, min(int(settings.mureka_n or 1), 3))
        self._sem = asyncio.Semaphore(max(1, int(settings.mureka_max_concurrent or 1)))
        self._timeout = httpx.Timeout(connect=10, read=180, write=10, pool=10)

    def _auth_header(self) -> dict:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    @staticmethod
    def _extract_error(resp: "httpx.Response") -> str:
        """Mureka 错误包体为 {"error":{"message":...},"trace_id":...}（实测 429 验证）。

        统一抽取服务端真实原因，避免 raise_for_status 把 "You exceeded your current
        quota" 之类关键信息吞掉，导致歌曲静默失败却看不到原因。
        """
        try:
            data = resp.json()
        except Exception:
            return (resp.text or "")[:300]
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
            if data.get("message"):
                return str(data["message"])
            if data.get("detail"):
                return str(data["detail"])
        return (resp.text or "")[:300]

    @staticmethod
    def _should_retry(resp: "httpx.Response") -> bool:
        """429 有两种（错误码文档 platform.mureka.ai/docs/en/error-codes.html）：

        - 限流(Rate limit reached) → 可退避重试；
        - 额度耗尽(You exceeded your current quota / billing) → **不可重试**，等也白等。
        5xx(服务器/引擎过载) → 可重试。其余(401/403/400) → 直接失败。
        """
        if resp.status_code in (500, 502, 503, 504):
            return True
        if resp.status_code == 429:
            msg = MurekaProvider._extract_error(resp).lower()
            if any(k in msg for k in ("quota", "billing", "credit", "余额", "额度")):
                return False
            return True
        return False

    async def _post(self, path: str, json: dict) -> dict:
        headers = self._auth_header()
        headers["Content-Type"] = "application/json"
        last = None
        for attempt in range(4):
            async with self._sem:                      # 约束提交并发（避免入门档 429）
                async with httpx.AsyncClient(timeout=self._timeout) as c:
                    last = await c.post(f"{self.base}{path}", headers=headers, json=json)
            if last.status_code < 400:
                return last.json()
            if self._should_retry(last):
                await asyncio.sleep(min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"Mureka POST {path} 失败 {last.status_code}: {self._extract_error(last)}")
        raise RuntimeError(f"Mureka POST {path} 重试耗尽 {last.status_code}: {self._extract_error(last)}")

    async def _get(self, path: str) -> dict:
        headers = self._auth_header()
        last = None
        for attempt in range(4):
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                last = await c.get(f"{self.base}{path}", headers=headers)
            if last.status_code < 400:
                return last.json()
            if self._should_retry(last):
                await asyncio.sleep(min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"Mureka GET {path} 失败 {last.status_code}: {self._extract_error(last)}")
        raise RuntimeError(f"Mureka GET {path} 重试耗尽 {last.status_code}: {self._extract_error(last)}")

    def _build_prompt(self, req: GenerateRequest) -> str:
        """generate 端点用自由文本 prompt 控制风格；强制注入 gospel 提升宗教曲风命中。"""
        parts: list[str] = ["gospel"]
        if req.style:
            parts.append(req.style)
        if req.vocal_gender:
            parts.append(str(req.vocal_gender).lower())  # female/male
        if req.prompt and req.prompt != req.style:
            parts.append(req.prompt)
        return ", ".join(p for p in parts if p)

    async def create(self, req: GenerateRequest) -> SongResult:
        prompt = self._build_prompt(req)
        # 官方约束 prompt ≤1024 字符（post-v1-song-generate.html），超长截断避免 400；
        # gospel 前缀在最前，截断后仍保留（风格命中不丢）。
        if len(prompt) > 1024:
            prompt = prompt[:1021] + "..."
        payload: dict = {
            "lyrics": (req.lyric or req.prompt or "一首歌"),
            # 요청에 모델이 지정되면 **그 모델을 쓴다**(저가 티어 lite → mureka-7.6 원가절감의 핵심).
            # 종전엔 self.model 로 고정해 req.model_version 을 무시했고, 그 결과
            # "티어별 모델 차등" 이 코드상 존재해도 실제로는 발화하지 않았다(no-op).
            "model": (req.model_version or self.model),
            "n": self.n,
            "prompt": prompt,
        }
        if req.vocal_gender:
            vmap = {"male": "male", "female": "female"}
            payload["gender"] = vmap.get(str(req.vocal_gender).lower(), req.vocal_gender)
        # 注意：Mureka 生成请求体无 title 字段（官方文档确认），歌名由 choices[].title 回传，
        # 故不在此上传 title（上传会被忽略，且易误导）。
        body = await self._post("/song/generate", json=payload)
        task_id = body.get("id")
        if not task_id:
            raise RuntimeError(f"Mureka create 未返回 id，响应: {body}")
        used_model = body.get("model") or self.model
        return SongResult(
            external_id=str(task_id),
            status="processing",
            model_version=str(used_model),
        )

    async def get(self, external_id: str) -> SongResult:
        body = await self._get(f"/song/query/{external_id}")
        status_raw = str(body.get("status", "preparing")).lower()
        if status_raw in _STATUS_FAILED:
            # failed_reason 为 Mureka 返回的失败原因（内容拦截/额度/超时等），作为审核提示落库
            return SongResult(
                external_id=external_id,
                status="failed",
                moderation_note=body.get("failed_reason"),
            )
        if status_raw != "succeeded":
            return SongResult(external_id=external_id, status="processing")
        # 成功：取 choices[0]（n>1 的其余首见 P1.5）
        choices = body.get("choices") or []
        choice = choices[0] if choices else {}
        audio_url = (
            choice.get("audio_url") or choice.get("url") or choice.get("mp3_url")
        )
        cover_url = (
            choice.get("cover_url") or choice.get("image_url") or choice.get("cover")
        )
        lyric = choice.get("lyrics") or choice.get("lyric")
        title = choice.get("title")
        duration = choice.get("duration")
        custom_id = choice.get("id") or choice.get("custom_id") or choice.get("clip_id")
        model_version = body.get("model") or choice.get("model") or self.model
        return SongResult(
            external_id=external_id,
            custom_id=str(custom_id) if custom_id else None,
            status="completed",
            audio_url=audio_url,
            cover_url=cover_url,
            lyric=lyric,
            title=title,
            model_version=str(model_version),
            duration=int(duration) if duration is not None else None,
        )

    async def get_billing(self) -> dict:
        """查询账号账单/额度（GET /v1/account/billing）。

        返回字段（官方文档，2026-09-03 核对）：
          account_id, balance(分), total_recharge(分), total_spending(分),
          concurrent_request_limit(账号最大并发请求数)
        用途：生产环境应在生成前或启动健康检查时调用，用 balance<=0 给出清晰
        “余额不足”错误，而非等到生成时收到 429 "You exceeded your current quota"
        （当时我们正是因此困惑——429 双义：限流可重试 vs 额度耗尽不可重试）。
        concurrent_request_limit 即权威并发上限，可取代手填 MUREKA_MAX_CONCURRENT。
        """
        body = await self._get("/account/billing")
        return {
            "account_id": body.get("account_id"),
            "balance": body.get("balance"),
            "total_recharge": body.get("total_recharge"),
            "total_spending": body.get("total_spending"),
            "concurrent_request_limit": body.get("concurrent_request_limit"),
        }
