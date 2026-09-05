"""
iPad Safari 정밀 스와이프 & 터치 최적화 모듈
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
iPad Safari에서 모든 UI 기능을 스와이프로 제어할 수 있도록 정밀 설계된
CSS + JavaScript 주입 모듈입니다.

지원 제스처:
  • ← 좌측 스와이프: 패널 닫기, 리스트 액션 노출, 탭 이동
  • → 우측 스와이프: 사이드바 열기, 이전 탭 이동
  • ↑ 당겨서 새로고침 (Pull-to-Refresh)
  • 2손가락 스와이프: 탭 간 빠른 이동
  • 롱프레스: 컨텍스트 메뉴
  • 핀치 투 줌: 성경 본문 / 콘텐츠 확대
"""

from __future__ import annotations
import streamlit as st


# ══════════════════════════════════════════════════════════════════════════════
# iPad 전용 CSS
# ══════════════════════════════════════════════════════════════════════════════

IPAD_CSS = r"""
/* ═══════════════════════════════════════════════════════════════════════════
   iPad Safari Viewport & Safe Area Foundation
   ═══════════════════════════════════════════════════════════════════════════ */

/* iOS dynamic viewport — Safari 주소창 높이 변화에 대응 */
:root {
    --safe-area-top: env(safe-area-inset-top, 0px);
    --safe-area-bottom: env(safe-area-inset-bottom, 0px);
    --safe-area-left: env(safe-area-inset-left, 0px);
    --safe-area-right: env(safe-area-inset-right, 0px);
    --touch-target-min: 44px;
}

/* 실제 뷰포트 높이 (100dvh 지원) */
html, body, .stApp {
    min-height: 100dvh;
    min-height: -webkit-fill-available;
}

/* Safe Area 패딩 자동 적용 */
.stApp {
    padding-top: var(--safe-area-top) !important;
    padding-bottom: var(--safe-area-bottom) !important;
    padding-left: var(--safe-area-left) !important;
    padding-right: var(--safe-area-right) !important;
}

/* iPad 전역 터치 최적화 */
@media (pointer: coarse) {
    html {
        -webkit-tap-highlight-color: transparent;
        touch-action: manipulation;
        -webkit-user-select: none;
        user-select: none;
    }

    /* 텍스트 입력 영역은 선택 허용 */
    input, textarea, [contenteditable="true"],
    .stMarkdown p, .stMarkdown li, .stMarkdown h1, .stMarkdown h2,
    .stMarkdown h3, .stMarkdown h4,
    [data-testid="stChatMessageContent"] {
        -webkit-user-select: text !important;
        user-select: text !important;
    }

    /* 모든 상호작용 요소에 최소 터치 영역 확보 (44pt Apple HIG) */
    button, .stButton button, [data-testid="stChatInput"] button,
    [data-testid="stSidebar"] .stButton button,
    .prompt-chip, .stTabs [data-baseweb="tab"],
    [data-testid="stPopover"] > button,
    .stCheckbox label, .stRadio label, .stToggle label,
    [data-testid="stSidebarCollapsedControl"] button,
    select, [data-baseweb="select"] {
        min-height: var(--touch-target-min) !important;
        min-width: var(--touch-target-min) !important;
    }

    /* 터치 피드백 — 살짝 누르면 스케일 다운 */
    button:active, .stButton button:active,
    .prompt-chip:active, [data-testid="stSidebar"] .stButton button:active {
        transform: scale(0.96) !important;
        transition: transform 0.08s ease-out !important;
    }
}

/* ── iPad Safari Momentum Scroll ──────────────────────────────────────────── */
/* 모든 스크롤 영역에 iOS 부드러운 모멘텀 스크롤 적용 */
[data-testid="stSidebarContent"],
.st-emotion-cache,
.block-container,
[data-testid="stAppViewContainer"],
.stMainBlockContainer,
[data-testid="stChatMessage"] + div,
.gemini-panel-body,
[data-testid="stPopover"] > div:first-child,
[data-testid="stSidebar"] [data-testid="stPopover"] > div:first-child,
section[data-testid="stSidebar"],
.stTabs [role="tabpanel"],
[data-testid="stExpander"] .stExpander details,
[data-testid="stChatInputTextArea"],
.stDataFrame {
    -webkit-overflow-scrolling: touch !important;
    overscroll-behavior: contain !important;
    overflow-y: auto !important;
}

/* ── iPad Safari Swipe-Back Conflict Prevention ──────────────────────────── */
/* 좌측 가장자리 스와이프 백 제스처와 충돌 방지 */
@media (pointer: coarse) {
    /* 사이드바를 제외한 메인 영역에서 좌측 스와이프 충돌 방지 */
    [data-testid="stAppViewContainer"] {
        overscroll-behavior-x: contain !important;
        touch-action: pan-y pinch-zoom !important;
    }

    /* 사이드바는 좌측 스와이프로 닫기 허용 */
    [data-testid="stSidebar"] {
        overscroll-behavior-x: auto !important;
    }

    /* 수평 스크롤이 필요한 요소는 X축 터치 허용 */
    [data-testid="stTable"],
    .stDataFrame,
    .stTabs [data-baseweb="tab-list"],
    code, pre {
        touch-action: pan-x pan-y pinch-zoom !important;
    }
}

/* ── iPad Safe Area: Sidebar ─────────────────────────────────────────────── */
@supports (padding-top: env(safe-area-inset-top)) {
    [data-testid="stSidebar"] {
        padding-top: env(safe-area-inset-top) !important;
    }
    [data-testid="stSidebarContent"] {
        padding-bottom: env(safe-area-inset-bottom) !important;
    }
    [data-testid="stBottomBlockContainer"] {
        padding-bottom: calc(0.75rem + env(safe-area-inset-bottom)) !important;
    }
}

/* ── iPad Safe Area: 채팅 하단 입력창 ────────────────────────────────────── */
@media (pointer: coarse) {
    [data-testid="stBottomBlockContainer"] {
        padding-bottom: calc(1rem + var(--safe-area-bottom)) !important;
    }

    /* 고정 입력창 보정 */
    .main:has(.greeting) [data-testid="stBottomBlockContainer"] {
        padding-bottom: calc(1rem + var(--safe-area-bottom)) !important;
    }
}

/* ── iPad Safe Area: 패널 ───────────────────────────────────────────────── */
@media (pointer: coarse) {
    .gemini-panel-header {
        padding-top: calc(1.1rem + var(--safe-area-top)) !important;
    }
    .gemini-panel-body {
        padding-bottom: calc(1.25rem + var(--safe-area-bottom)) !important;
    }
}

/* ── iPad: 가로/세로 전환 대응 ───────────────────────────────────────────── */
/* iPad 가로 모드 */
@media (pointer: coarse) and (min-width: 768px) and (orientation: landscape) {
    .block-container {
        max-width: 680px !important;
    }

    [data-testid="stChatMessageContent"] {
        max-width: 620px !important;
    }

    /* 가로모드: 사이드바 너비 증가 */
    [data-testid="stSidebar"] {
        min-width: 280px !important;
        max-width: 320px !important;
    }
}

/* iPad 세로 모드 */
@media (pointer: coarse) and (orientation: portrait) {
    .block-container {
        max-width: 100% !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    .greeting {
        padding: 2.5rem 0.8rem 1.2rem !important;
    }

    .greeting h2 {
        font-size: 1.6rem !important;
    }
}

/* ── iPad Pro 11" / 12.9" ────────────────────────────────────────────────── */
@media (pointer: coarse) and (min-width: 1024px) {
    .greeting {
        padding-top: 4rem !important;
    }
    .greeting::before {
        width: 64px !important;
        height: 64px !important;
        border-radius: 20px !important;
    }
    .greeting h2 {
        font-size: 2.2rem !important;
    }
}

/* ── iPad Mini / Air Portrait ────────────────────────────────────────────── */
@media (pointer: coarse) and (max-width: 834px) and (max-height: 1200px) and (orientation: portrait) {
    .greeting {
        padding: 2rem 0.8rem 1rem !important;
    }
    .greeting::before {
        width: 48px !important;
        height: 48px !important;
        border-radius: 16px !important;
    }
    .greeting h2 {
        font-size: 1.5rem !important;
    }
}

/* ── iPad: Swipe Action Indicator ────────────────────────────────────────── */
/* 리스트 항목에 왼쪽으로 스와이프 가능함을 나타내는 힌트 */
@media (pointer: coarse) {
    .swipe-hint-left::after {
        content: '';
        position: absolute;
        right: 0;
        top: 0;
        bottom: 0;
        width: 4px;
        background: linear-gradient(to left, rgba(66,133,244,0.3), transparent);
        border-radius: 0 12px 12px 0;
        pointer-events: none;
    }
}

/* ── iPad: Focus Ring 제거 (키보드 입력 시) ──────────────────────────────── */
@media (pointer: coarse) {
    *:focus:not(:focus-visible) {
        outline: none !important;
        box-shadow: none !important;
    }

    /* 키보드 사용자에게만 포커스 표시 */
    *:focus-visible {
        outline: 2px solid rgba(66,133,244,0.5) !important;
        outline-offset: 2px !important;
    }
}

/* ── iPad: Pull-to-Refresh Indicator ─────────────────────────────────────── */
.pull-indicator {
    position: fixed;
    top: 0;
    left: 50%;
    transform: translateX(-50%) translateY(-100%);
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: rgba(66,133,244,0.9);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 1.2rem;
    z-index: 9999;
    opacity: 0;
    transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1),
                opacity 0.2s ease;
    pointer-events: none;
    box-shadow: 0 2px 12px rgba(66,133,244,0.4);
}
.pull-indicator.active {
    transform: translateX(-50%) translateY(20px);
    opacity: 1;
}
.pull-indicator.spinning {
    animation: pullSpinner 0.6s linear infinite;
}
@keyframes pullSpinner {
    from { transform: translateX(-50%) translateY(20px) rotate(0deg); }
    to   { transform: translateX(-50%) translateY(20px) rotate(360deg); }
}

/* ── iPad: 스와이프 스냅 포인트 (패널 닫기) ─────────────────────────────── */
@media (pointer: coarse) {
    /* 패널이 30% 이상 오른쪽으로 드래그되면 자동 닫힘 */
    [data-st-key="gemini_panel_container"] {
        transition: transform 0.35s cubic-bezier(0.22, 0.61, 0.36, 1) !important;
        will-change: transform;
    }
    [data-st-key="gemini_panel_container"].swiping {
        transition: none !important;
    }
}

/* ── iPad: Swipe-to-Action 배경 (리스트 아이템) ──────────────────────────── */
.swipe-action-bg {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0 12px 12px 0;
    font-size: 0.78rem;
    font-weight: 500;
    color: #ffffff;
    transition: width 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    overflow: hidden;
    pointer-events: none;
}
.swipe-action-bg.delete { background: #ea4335; }
.swipe-action-bg.archive { background: #f9ab00; }
.swipe-action-bg.publish { background: #34a853; }

/* ── iPad Management Admin 전용 ────────────────────────────────────────── */
/* 관리자 페이지 전용 iPad 최적화 */
@media (pointer: coarse) {
    /* 데이터프레임 — 가로 스크롤 허용 */
    [data-testid="stDataFrame"] {
        touch-action: pan-x pan-y !important;
        -webkit-overflow-scrolling: touch !important;
    }

    /* 탭 — 스와이프로 전환 가능하게 (JS 보조) */
    .stTabs {
        touch-action: pan-y !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        -webkit-overflow-scrolling: touch !important;
        overflow-x: auto !important;
        scroll-snap-type: x proximity;
        -ms-overflow-style: none;
        scrollbar-width: none;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
        display: none;
    }
    .stTabs [data-baseweb="tab"] {
        scroll-snap-align: start;
        flex-shrink: 0;
    }

    /* 폼 요소 — 터치 친화적 간격 */
    [data-testid="stForm"] {
        gap: 1rem !important;
    }

    /* Metric 카드 */
    [data-testid="stMetric"] {
        min-width: 120px;
    }

    /* 사이드바 너비 */
    [data-testid="stSidebar"] {
        min-width: 260px !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding: 1rem !important;
    }
}

/* ── iPad: 사이드바 햅틱 피드백 ─────────────────────────────────────────── */
@media (pointer: coarse) {
    [data-testid="stSidebar"] .stButton button:active {
        background: rgba(66,133,244,0.12) !important;
        transition: background 0.05s ease-out !important;
    }
}

/* ── iPad: Prevent Zoom on Double Tap ───────────────────────────────────── */
@media (pointer: coarse) {
    button, .stButton button, input, select, textarea,
    [data-testid="stChatInput"] {
        touch-action: manipulation !important;
    }
}

/* ── iPad: Panel backdrop swipe detection ────────────────────────────────── */
.panel-backdrop {
    touch-action: none !important;
    cursor: pointer;
}
"""


# ══════════════════════════════════════════════════════════════════════════════
# iPad 전용 JavaScript
# ══════════════════════════════════════════════════════════════════════════════

IPAD_JS = r"""
<script>
(function () {
    'use strict';

    // ── 디바이스 감지 ──────────────────────────────────────────────────────
    const isIPad = /iPad|Macintosh/.test(navigator.userAgent) &&
                   navigator.maxTouchPoints > 1 &&
                   'ontouchstart' in window;
    const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);

    if (!isIPad) return;

    console.log('[iPad Swipe] iPad Safari 감지됨 — 정밀 스와이프 최적화 활성화');

    // ── 전역 제스처 파라미터 ──────────────────────────────────────────────
    const SWIPE = {
        threshold: 50,      // 최소 스와이프 거리 (px)
        velocity: 0.3,      // 최소 속도 (px/ms)
        resistance: 0.4,    // 드래그 저항 계수 (패널 경계 넘을 때)
        snapBack: 350,      // 스냅백 애니메이션 (ms)
    };

    // ── 1. Gemini 패널 스와이프 닫기 (iOS 스타일) ───────────────────────────
    function initPanelSwipeDismiss() {
        const panel = document.querySelector('[data-st-key="gemini_panel_container"]');
        const backdrop = document.querySelector('.panel-backdrop');

        if (!panel) return;

        let startX = 0, startY = 0, currentX = 0;
        let isDragging = false;
        let startTime = 0;

        function onStart(e) {
            const touch = e.touches[0];
            startX = touch.clientX;
            startY = touch.clientY;
            currentX = 0;
            isDragging = false;
            startTime = Date.now();
            panel.classList.remove('closing');
        }

        function onMove(e) {
            if (!isDragging) {
                const dx = Math.abs(e.touches[0].clientX - startX);
                const dy = Math.abs(e.touches[0].clientY - startY);
                // 수평 스와이프가 수직보다 클 때만 드래그 시작
                if (dx > 10 && dx > dy) {
                    isDragging = true;
                    panel.classList.add('swiping');
                    e.preventDefault();
                }
                return;
            }

            const dx = e.touches[0].clientX - startX;
            // 오른쪽으로만 드래그 (왼쪽은 무시)
            if (dx <= 0) {
                currentX = 0;
                panel.style.transform = 'translateX(0)';
                return;
            }

            // 저항 적용 (50px 이상은 저항 증가)
            const raw = dx;
            const resisted = raw > 80
                ? 80 + (raw - 80) * SWIPE.resistance
                : raw;
            currentX = resisted;
            panel.style.transform = `translateX(${resisted}px)`;

            // 백드롭 투명도 조정
            if (backdrop) {
                const progress = Math.min(resisted / 200, 1);
                backdrop.style.opacity = String(1 - progress * 0.7);
            }
        }

        function onEnd(e) {
            if (!isDragging) return;

            panel.classList.remove('swiping');
            const elapsed = Date.now() - startTime;
            const velocity = currentX / (elapsed || 1);

            // 닫기 조건: 스와이프 거리 > threshold 또는 높은 속도
            if (currentX > SWIPE.threshold || velocity > SWIPE.velocity) {
                // 닫기 애니메이션
                panel.style.transform = 'translateX(100vw)';
                panel.style.opacity = '0';
                if (backdrop) backdrop.style.opacity = '0';

                // 닫기 버튼 클릭 시뮬레이션
                setTimeout(() => {
                    const closeBtn = document.querySelector('#gemini_close button') ||
                                     document.querySelector('[data-testid="stButton"] button[kind]');
                    // Streamlit 버튼 찾기 대신 DOM 이벤트 발생
                    const allBtns = panel.querySelectorAll('button');
                    for (const btn of allBtns) {
                        if (btn.textContent.includes('✕') || btn.ariaLabel?.includes('닫기')) {
                            btn.click();
                            break;
                        }
                    }
                }, 350);
            } else {
                // 스냅백
                panel.style.transform = 'translateX(0)';
                if (backdrop) backdrop.style.opacity = '';
            }

            isDragging = false;
            currentX = 0;
        }

        panel.addEventListener('touchstart', onStart, { passive: false });
        panel.addEventListener('touchmove', onMove, { passive: false });
        panel.addEventListener('touchend', onEnd);
        panel.addEventListener('touchcancel', onEnd);

        // 백드롭 터치로 패널 닫기
        if (backdrop) {
            backdrop.addEventListener('click', function () {
                const allBtns = panel.querySelectorAll('button');
                for (const btn of allBtns) {
                    if (btn.textContent.includes('✕') || btn.ariaLabel?.includes('닫기')) {
                        btn.click();
                        break;
                    }
                }
            });
        }

        console.log('[iPad Swipe] 패널 스와이프 닫기 활성화');
    }

    // ── 2. 탭 스와이프 네비게이션 ──────────────────────────────────────────
    function initTabSwipeNavigation() {
        const tabPanels = document.querySelectorAll('.stTabs [role="tabpanel"]');

        tabPanels.forEach(function (panel) {
            let touchStartX = 0, touchStartY = 0;
            let swiped = false;

            panel.addEventListener('touchstart', function (e) {
                touchStartX = e.touches[0].clientX;
                touchStartY = e.touches[0].clientY;
                swiped = false;
            }, { passive: true });

            panel.addEventListener('touchmove', function (e) {
                if (swiped) return;
                const dx = Math.abs(e.touches[0].clientX - touchStartX);
                const dy = Math.abs(e.touches[0].clientY - touchStartY);

                // 수평 스와이프 감지
                if (dx > 40 && dx > dy * 1.5) {
                    swiped = true;
                    const direction = e.touches[0].clientX - touchStartX > 0 ? 'right' : 'left';

                    // 탭 리스트 찾기
                    const tabContainer = panel.closest('.stTabs');
                    if (!tabContainer) return;

                    const tabs = tabContainer.querySelectorAll('[data-baseweb="tab"]');
                    const activeTab = tabContainer.querySelector('[data-baseweb="tab"][aria-selected="true"]');

                    if (!activeTab || tabs.length < 2) return;

                    // 현재 활성 탭 인덱스
                    let currentIdx = Array.from(tabs).indexOf(activeTab);
                    let nextIdx = direction === 'left'
                        ? Math.min(currentIdx + 1, tabs.length - 1)
                        : Math.max(currentIdx - 1, 0);

                    if (nextIdx !== currentIdx) {
                        tabs[nextIdx].click();

                        // 스와이프 방향 표시
                        tabContainer.style.setProperty('--swipe-dir', direction);
                        tabContainer.classList.add('tab-swiped');
                        setTimeout(() => tabContainer.classList.remove('tab-swiped'), 400);
                    }
                }
            }, { passive: true });
        });

        if (tabPanels.length > 0) {
            console.log('[iPad Swipe] 탭 스와이프 네비게이션 활성화 (' + tabPanels.length + ' 패널)');
        }
    }

    // ── 3. Pull-to-Refresh ─────────────────────────────────────────────────
    function initPullToRefresh() {
        const indicator = document.createElement('div');
        indicator.className = 'pull-indicator';
        indicator.innerHTML = '⟳';
        document.body.appendChild(indicator);

        const scrollContainer = document.querySelector('.block-container') ||
                                document.querySelector('[data-testid="stAppViewContainer"]');

        if (!scrollContainer) return;

        let pullStartY = 0, pulling = false;
        let refreshTriggered = false;

        function onTouchStart(e) {
            // 상단에 있을 때만 Pull-to-Refresh 활성화
            if (scrollContainer.scrollTop > 5) return;
            pullStartY = e.touches[0].clientY;
            pulling = true;
            refreshTriggered = false;
            indicator.classList.remove('spinning', 'active');
        }

        function onTouchMove(e) {
            if (!pulling || refreshTriggered) return;
            const dy = e.touches[0].clientY - pullStartY;

            if (dy > 10 && scrollContainer.scrollTop <= 0) {
                const pull = Math.min(dy * 0.5, 80);
                indicator.classList.add('active');
                indicator.style.transform = `translateX(-50%) translateY(${Math.min(pull, 50)}px)`;
                indicator.style.opacity = String(Math.min(pull / 50, 1));

                if (dy > 80) {
                    refreshTriggered = true;
                    indicator.classList.add('spinning');

                    // 페이지 리로드 (Streamlit rerun)
                    setTimeout(() => {
                        window.location.reload();
                    }, 400);
                }
            }
        }

        function onTouchEnd() {
            if (!pulling) return;
            pulling = false;
            if (!refreshTriggered) {
                indicator.classList.remove('active', 'spinning');
                indicator.style.opacity = '0';
                indicator.style.transform = 'translateX(-50%) translateY(-100%)';
            }
        }

        document.addEventListener('touchstart', onTouchStart, { passive: false });
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onTouchEnd);
        document.addEventListener('touchcancel', onTouchEnd);

        console.log('[iPad Swipe] Pull-to-Refresh 활성화');
    }

    // ── 4. 사이드바 엣지 스와이프 ──────────────────────────────────────────
    function initSidebarEdgeSwipe() {
        const sidebar = document.querySelector('[data-testid="stSidebar"]');
        const toggleBtn = document.querySelector('[data-testid="stSidebarCollapsedControl"] button');

        if (!sidebar || !toggleBtn) return;

        let edgeStartX = 0;
        let edgeStarted = false;

        document.addEventListener('touchstart', function (e) {
            const touchX = e.touches[0].clientX;

            // 화면 왼쪽 30px 가장자리에서만 감지
            if (touchX < 30) {
                edgeStartX = touchX;
                edgeStarted = true;
            }
        }, { passive: true });

        document.addEventListener('touchmove', function (e) {
            if (!edgeStarted) return;
            const dx = e.touches[0].clientX - edgeStartX;

            if (dx > 50) {
                edgeStarted = false;
                // 사이드바가 닫혀있으면 열기
                if (sidebar.getAttribute('aria-expanded') !== 'true') {
                    toggleBtn.click();
                    // 약간의 햅틱 느낌을 위한 진동 (지원 시)
                    if (navigator.vibrate) {
                        navigator.vibrate(10);
                    }
                }
            }
        }, { passive: true });

        document.addEventListener('touchend', function () {
            edgeStarted = false;
        });

        // 사이드바 내에서 좌측 스와이프로 닫기
        sidebar.addEventListener('touchstart', function (e) {
            edgeStartX = e.touches[0].clientX;
        }, { passive: true });

        sidebar.addEventListener('touchmove', function (e) {
            const dx = edgeStartX - e.touches[0].clientX;
            if (dx > 80) {
                edgeStarted = false;
                // 내용 영역 바깥이면 닫기
                const sidebarContent = sidebar.querySelector('[data-testid="stSidebarContent"]');
                const isOnSidebarContent = sidebarContent && sidebarContent.contains(e.target);
                if (!isOnSidebarContent && sidebar.getAttribute('aria-expanded') === 'true') {
                    toggleBtn.click();
                }
            }
        }, { passive: true });

        console.log('[iPad Swipe] 사이드바 엣지 스와이프 활성화');
    }

    // ── 5. 리스트 항목 스와이프 액션 ───────────────────────────────────────
    function initSwipeActions() {
        // 대화 기록, 라이브러리 항목 등 리스트 컨테이너에 적용
        function addSwipeToContainer(selector, actions) {
            const container = document.querySelector(selector);
            if (!container) return;

            const items = container.querySelectorAll('.stButton, [data-testid="column"]');
            items.forEach(function (item) {
                let startX = 0, movedX = 0;
                let swiping = false;

                item.addEventListener('touchstart', function (e) {
                    startX = e.touches[0].clientX;
                    swiping = false;
                }, { passive: true });

                item.addEventListener('touchmove', function (e) {
                    const dx = e.touches[0].clientX - startX;
                    const dy = Math.abs(e.touches[0].clientY - startX);

                    if (Math.abs(dx) > 15 && Math.abs(dx) > dy && !swiping) {
                        swiping = true;
                    }

                    if (swiping && dx < -30 && dx > -120) {
                        movedX = dx;
                        item.style.transform = `translateX(${dx}px)`;
                        item.style.transition = 'none';
                    }
                }, { passive: true });

                item.addEventListener('touchend', function () {
                    if (swiping && movedX < -60) {
                        // 스와이프 액션 완료
                        item.style.transform = 'translateX(-100px)';
                        item.style.transition = 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)';

                        // 2초 후 리셋
                        setTimeout(function () {
                            item.style.transform = 'translateX(0)';
                        }, 2000);
                    } else if (swiping) {
                        // 충분히 드래그하지 않음 — 스냅백
                        item.style.transform = 'translateX(0)';
                        item.style.transition = 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)';
                    }
                    swiping = false;
                    movedX = 0;
                });
            });
        }

        // 사이드바 대화 기록에 스와이프 액션 적용
        setTimeout(function () {
            addSwipeToContainer('[data-testid="stSidebarContent"]', [
                { label: '삭제', color: '#ea4335', icon: '🗑' },
            ]);
        }, 1500);

        console.log('[iPad Swipe] 리스트 스와이프 액션 활성화');
    }

    // ── 6. 채팅 메시지 롱프레스 컨텍스트 ────────────────────────────────────
    function initLongPressContext() {
        let longPressTimer = null;

        document.addEventListener('touchstart', function (e) {
            const msg = e.target.closest('[data-testid="stChatMessageContent"]');
            if (!msg) return;

            longPressTimer = setTimeout(function () {
                // 피드백 버튼 하이라이트
                const buttons = msg.closest('[data-testid="stChatMessage"]')
                    ?.querySelectorAll('.stButton button');
                if (buttons) {
                    buttons.forEach(function (btn) {
                        btn.style.transform = 'scale(1.15)';
                        btn.style.transition = 'transform 0.15s ease';
                        btn.style.boxShadow = '0 0 12px rgba(66,133,244,0.4)';
                        setTimeout(function () {
                            btn.style.transform = '';
                            btn.style.boxShadow = '';
                        }, 600);
                    });
                }
                // 선택 텍스트 복사 가능하게
                msg.style.userSelect = 'text';
                msg.style.webkitUserSelect = 'text';

                // 진동 피드백
                if (navigator.vibrate) {
                    navigator.vibrate(20);
                }
            }, 500);
        }, { passive: true });

        document.addEventListener('touchend', function () {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
        });

        document.addEventListener('touchmove', function () {
            if (longPressTimer) {
                clearTimeout(longPressTimer);
                longPressTimer = null;
            }
        });

        console.log('[iPad Swipe] 롱프레스 컨텍스트 메뉴 활성화');
    }

    // ── 7. 입력창 제스처: 아래로 스와이프로 키보드 닫기 ──────────────────────
    function initKeyboardDismissGesture() {
        const chatInput = document.querySelector('[data-testid="stChatInput"]');

        document.addEventListener('touchstart', function (e) {
            // 입력창 바깥을 아래로 스와이프 → 키보드 닫기
            if (chatInput && !chatInput.contains(e.target)) {
                window._kbDismissStartY = e.touches[0].clientY;
            }
        }, { passive: true });

        document.addEventListener('touchmove', function (e) {
            if (window._kbDismissStartY) {
                const dy = e.touches[0].clientY - window._kbDismissStartY;
                if (dy > 80) {
                    if (document.activeElement) {
                        document.activeElement.blur();
                    }
                    window._kbDismissStartY = null;
                }
            }
        }, { passive: true });

        document.addEventListener('touchend', function () {
            window._kbDismissStartY = null;
        });

        console.log('[iPad Swipe] 키보드 닫기 제스처 활성화');
    }

    // ── 8. 데이터프레임/테이블 스와이프 ─────────────────────────────────────
    function initTableSwipe() {
        const tables = document.querySelectorAll('[data-testid="stDataFrame"], .stTable');

        tables.forEach(function (table) {
            let tableStartX = 0, tableScrolling = false;

            table.addEventListener('touchstart', function (e) {
                tableStartX = e.touches[0].clientX;
                tableScrolling = false;
            }, { passive: true });

            table.addEventListener('touchmove', function (e) {
                const dx = Math.abs(e.touches[0].clientX - tableStartX);
                if (dx > 10 && !tableScrolling) {
                    tableScrolling = true;
                    table.style.setProperty('--table-swiping', '1');
                }
            }, { passive: true });

            table.addEventListener('touchend', function () {
                if (tableScrolling) {
                    setTimeout(function () {
                        table.style.setProperty('--table-swiping', '0');
                    }, 300);
                }
            });
        });
    }

    // ── 9. 애니메이션 최적화 (ProMotion 120Hz) ──────────────────────────────
    function initProMotionOptimization() {
        // requestAnimationFrame 기반 부드러운 애니메이션
        const animatedElements = document.querySelectorAll(
            '.gemini-panel, .prompt-chip, .stButton button, [data-testid="stChatMessage"]'
        );

        animatedElements.forEach(function (el) {
            el.style.willChange = 'transform';
            el.style.backfaceVisibility = 'hidden';
            el.style.webkitBackfaceVisibility = 'hidden';
        });

        console.log('[iPad Swipe] ProMotion 120Hz 최적화 활성화');
    }

    // ── 초기화 ─────────────────────────────────────────────────────────────
    function init() {
        // DOM이 완전히 로드된 후 실행
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () {
                setTimeout(initAll, 800);
            });
        } else {
            setTimeout(initAll, 800);
        }
    }

    function initAll() {
        initPanelSwipeDismiss();
        initTabSwipeNavigation();
        initPullToRefresh();
        initSidebarEdgeSwipe();
        initSwipeActions();
        initLongPressContext();
        initKeyboardDismissGesture();
        initTableSwipe();
        initProMotionOptimization();

        console.log('[iPad Swipe] 모든 제스처 시스템 초기화 완료 ✓');
    }

    // ── Streamlit 페이지 전환 시 재초기화 ─────────────────────────────────
    // SPA 네비게이션 감지
    const origPushState = history.pushState;
    history.pushState = function () {
        origPushState.apply(this, arguments);
        setTimeout(initAll, 600);
    };
    const origReplaceState = history.replaceState;
    history.replaceState = function () {
        origReplaceState.apply(this, arguments);
        setTimeout(initAll, 600);
    };

    // DOM 변화 감지 (새 콘텐츠 로드 시)
    const domObserver = new MutationObserver(function (mutations) {
        // 패널이 추가/제거될 때 재초기화
        let shouldReinit = false;
        for (const m of mutations) {
            if (m.type === 'childList' && m.addedNodes.length > 0) {
                for (const node of m.addedNodes) {
                    if (node.nodeType === 1 &&
                        (node.querySelector?.('[data-st-key="gemini_panel_container"]') ||
                         node.querySelector?.('.stTabs'))) {
                        shouldReinit = true;
                        break;
                    }
                }
            }
            if (shouldReinit) break;
        }
        if (shouldReinit) {
            setTimeout(initAll, 300);
        }
    });
    domObserver.observe(document.body, { childList: true, subtree: true });

    // ── 시작 ───────────────────────────────────────────────────────────────
    init();

})();
</script>
"""


# ══════════════════════════════════════════════════════════════════════════════
# 관리자 전용 iPad JS (데이터 테이블, 차트 등)
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_IPAD_JS = r"""
<script>
(function () {
    'use strict';

    const isIPad = /iPad|Macintosh/.test(navigator.userAgent) &&
                   navigator.maxTouchPoints > 1 &&
                   'ontouchstart' in window;

    if (!isIPad) return;

    console.log('[iPad Admin] 관리자 스와이프 최적화 활성화');

    // ── Admin 탭 스와이프 (전체 페이지 수준) ──────────────────────────────
    function initAdminTabSwipe() {
        const sidebar = document.querySelector('[data-testid="stSidebar"]');
        if (!sidebar) return;

        // st.navigation 탭은 사이드바에 있으므로, 사이드바에서
        // 상하 스와이프로 빠르게 탭 전환 지원
        const tabItems = sidebar.querySelectorAll('a[href], [data-testid="stSidebarNavItems"] a');
        let tabSwipeY = 0;
        let tabSwipeStarted = false;

        sidebar.addEventListener('touchstart', function(e) {
            tabSwipeY = e.touches[0].clientY;
            tabSwipeStarted = true;
        }, { passive: true });

        sidebar.addEventListener('touchmove', function(e) {
            if (!tabSwipeStarted) return;
            const dy = e.touches[0].clientY - tabSwipeY;

            // 수직 스와이프로 사이드바 탭 간 빠른 이동
            if (Math.abs(dy) > 60) {
                tabSwipeStarted = false;
                const target = dy > 0
                    ? e.target.closest('a')?.nextElementSibling
                    : e.target.closest('a')?.previousElementSibling;

                if (target && target.tagName === 'A') {
                    target.click();
                }
            }
        }, { passive: true });

        sidebar.addEventListener('touchend', function() {
            tabSwipeStarted = false;
        });
    }

    // ── 데이터프레임 고스트 스크롤 ──────────────────────────────────────────
    function initDataFrameGhostScroll() {
        const dfs = document.querySelectorAll('[data-testid="stDataFrame"], [data-testid="stTable"]');

        dfs.forEach(function(df) {
            df.addEventListener('touchstart', function(e) {
                // 2손가락 터치 = 가로 스크롤
                if (e.touches.length === 2) {
                    df.style.scrollBehavior = 'auto';
                }
            }, { passive: true });

            df.addEventListener('touchend', function() {
                df.style.scrollBehavior = 'smooth';
            });
        });
    }

    // ── Metric 카드 롱프레스 → 상세 ────────────────────────────────────────
    function initMetricLongPress() {
        document.addEventListener('touchstart', function(e) {
            const metric = e.target.closest('[data-testid="stMetric"]');
            if (!metric) return;

            let timer = setTimeout(function() {
                // 하이라이트
                metric.style.boxShadow = '0 0 0 4px rgba(66,133,244,0.3)';
                metric.style.borderRadius = '12px';
                metric.style.transition = 'box-shadow 0.3s ease';
                if (navigator.vibrate) navigator.vibrate(15);

                setTimeout(function() {
                    metric.style.boxShadow = '';
                }, 1200);
            }, 400);

            metric._longPressTimer = timer;
        }, { passive: true });

        document.addEventListener('touchend', function(e) {
            const metric = e.target.closest('[data-testid="stMetric"]');
            if (metric && metric._longPressTimer) {
                clearTimeout(metric._longPressTimer);
                delete metric._longPressTimer;
            }
        });
    }

    // ── 초기화 ─────────────────────────────────────────────────────────────
    setTimeout(function() {
        initAdminTabSwipe();
        initDataFrameGhostScroll();
        initMetricLongPress();
        console.log('[iPad Admin] 관리자 제스처 초기화 완료 ✓');
    }, 1000);

    // Streamlit SPA 감지 (관리자 페이지 전환)
    window.addEventListener('popstate', function() {
        setTimeout(function() {
            initAdminTabSwipe();
            initDataFrameGhostScroll();
        }, 600);
    });

})();
</script>
"""


# ══════════════════════════════════════════════════════════════════════════════
# iPad Viewport Meta Tag
# ══════════════════════════════════════════════════════════════════════════════

VIEWPORT_META = """<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, viewport-fit=cover, user-scalable=yes">"""


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def inject_ipad_optimizations(include_admin_js: bool = False) -> None:
    """iPad Safari 스와이프 최적화를 전체 앱에 주입합니다.

    Args:
        include_admin_js: 관리자 페이지 전용 JS도 포함할지 여부
    """
    # Viewport 메타 태그 (iOS PWA/safari 최적화)
    st.markdown(VIEWPORT_META, unsafe_allow_html=True)

    # iPad CSS
    st.markdown(f"<style>{IPAD_CSS}</style>", unsafe_allow_html=True)

    # iPad JS (기본 제스처)
    st.markdown(IPAD_JS, unsafe_allow_html=True)

    # 관리자 전용 JS
    if include_admin_js:
        st.markdown(ADMIN_IPAD_JS, unsafe_allow_html=True)


def inject_ipad_css_only() -> None:
    """CSS만 주입 (JS 불필요한 경우)."""
    st.markdown(VIEWPORT_META, unsafe_allow_html=True)
    st.markdown(f"<style>{IPAD_CSS}</style>", unsafe_allow_html=True)
