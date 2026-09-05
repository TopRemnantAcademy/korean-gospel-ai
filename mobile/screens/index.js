/* ═══════════════════════════════════════════════════════════════
   Screens — 6 tab screens (Bible, Hymns, Sermon, Meditation, Chat, Login)
   ═══════════════════════════════════════════════════════════════ */

const PAGE = 6;  // 讲道无限滚动单次展示数量

/* ── 圣经界面（书卷 → 章 → 节 选择）──────────────────────────── */
/* ── 全局 UI i18n（ko / en / zh-CN / zh-TW）──────────────────────
   单一真相源：所有 UI 文案都从这里取。uiT(key, vars) 永不返回 undefined。
   vars: {name:'...'} 形式插值，匹配 {name}。 */
const UI_I18N = {
  'ko': {
    // ── 底部导航 (components/index.js TABS) ──
    'tab.bible': '성경', 'tab.hymns': '찬송', 'tab.word': '말씀',
    'tab.today': '오늘', 'tab.settings': '설정',
    // ── 聊天 (renderToday) ──
    'chat.title': 'AI에게 물어보기',
    'chat.placeholder': '궁금한 점을 편하게 물어보세요…',
    'chat.send': '보내기',
    'chat.greeting': '안녕하세요! 믿음과 성경에 대해 궁금한 점이 있으면 언제든 물어보세요.',
    'chat.suggestedTitle': '이런 질문은 어떠세요',
    'chat.suggested': ['성경은 어디서부터 읽어야 할까요?', '은혜란 무엇인가요?', '주기도문의 의미는?', '친구에게 어떻게 믿음을 나눌까요?'],
    'chat.privacyNote': '어떤 질문도 실명으로 기록되지 않으며, 질문 풀을 보강하는 용도로만 쓰입니다.',
    // ── 通用 ──
    'common.loading': '불러오는 중...', 'common.cancel': '취소', 'common.save': '저장',
    'common.more': '더 보기', 'common.share': '공유', 'common.delete': '삭제',
    // ── 圣经 (renderBible / renderWord) ──
    'bible.empty': '성경 본문이 아직 업로드되지 않았습니다. 관리자 페이지에서 업로드해 주세요.',
    'bible.loadFail': '성경을 불러올 수 없습니다.',
    'bible.searchPlaceholder': '성경 전체 검색…',
    'bible.noResult': '관련 성경을 찾지 못했습니다.',
    'bible.chapter': '장', 'bible.verse': '절',
    'bible.noteTitle': '📝 메모', 'bible.notePlaceholder': '메모를 입력하세요...',
    'bible.noteCancel': '취소', 'bible.noteSave': '저장',
    'bible.card': '📤 말씀 카드',
    'bible.copy': '복사', 'bible.cardCopied': '말씀 카드가 복사되었습니다.',
    // ── 찬송 (renderHymns) ──
    'hymn.searchPlaceholder': '제목 · 가사 · 장르 · 찬송 번호 검색…',
    'hymn.sort.number': '번호순', 'hymn.sort.title': '제목순', 'hymn.sort.recent': '최근 재생',
    'hymn.recent': '최근 재생',
    'hymn.playAll': '▶ 전체 재생', 'hymn.all': '전체 찬송', 'hymn.empty': '조건에 맞는 찬송이 없습니다.',
    'hymn.today': '오늘의 찬송', 'hymn.offline': '⬇ 오프라인', 'hymn.menu': '메뉴',
    // ── 讲道 (renderSermons) ──
    'sermon.empty': '아직 등록된 설교 오디오가 없습니다. 관리자 페이지에서 업로드해 주세요.',
    'sermon.searchPlaceholder': '제목 · 설교자 · 본문 검색',
    'sermon.featured': '이번 주 추천', 'sermon.all': '전체', 'sermon.more': '더 보기 ›',
    'sermon.listen': '♪ 설교 듣기', 'sermon.copyLink': '🔗 링크 복사',
    'sermon.favOn': '⭐ 즐겨찾기 됨', 'sermon.favOff': '☆ 즐겨찾기',
    'sermon.summary': '설교 요약', 'sermon.related': '🔗 관련 설교',
    'sermon.seriesOther': '📚 {series}의 다른 설교',
    'sermon.summaryEmpty': '요약을 준비 중입니다.',
    // ── 今日/话语 (renderToday / renderWord) ──
    'meditation.dailyLabel': '📅 오늘의 말씀', 'meditation.emptyBody': '오늘도 주님의 말씀으로 묵상하며 하루를 시작해 보세요.',
    'meditation.tab': '묵상',
    'word.home': '🏠 홈', 'word.ask': '💬 말씀 묵상', 'word.fav': '⭐ 즐겨찾기',
    'word.favEmpty': '즐겨찾기한 말씀 카드가 없습니다. 카드의 ⭐를 눌러 추가해 보세요.',
    // ── 我的/마이 (renderMy) ──
    'my.displayFont': '디스플레이 및 글꼴',     'my.bibleSettings': '성경 기본값', 'my.bibleVersion': '기본 성경 버전',
    'my.bibleVersionHint': '성경 탭을 열 때 사용할 기본 버전', 'my.bibleAuto': '시스템 언어 따라감', 'my.dataInfo': '데이터 및 정보',
    'my.clearCache': '캐시/데이터 지우기', 'my.clearCacheHint': '임시 저장된 데이터를 삭제합니다', 'my.clearBtn': '지우기',
    'my.clearDone': '캐시를 지웠습니다.', 'my.clearFail': '캐시를 지우지 못했습니다.', 'my.appVersion': '앱 버전',
    'my.changePassword': '비밀번호 변경', 'my.changePasswordHint': '로그인 비밀번호를 변경합니다', 'my.changeBtn': '변경',
    'my.changeConfirm': '비밀번호 변경', 'my.pwCurrent': '현재 비밀번호', 'my.pwNew': '새 비밀번호 (6자 이상)',
    'my.pwChanged': '비밀번호가 변경되었습니다.',
    'my.deviceManagement': '기기/세션 관리', 'my.deviceManagementHint': '로그인된 기기 확인 및 원격 로그아웃',
    'my.deviceManageBtn': '관리', 'my.noDevices': '로그인된 기기가 없습니다.', 'my.currentDevice': '현재 기기',
    'my.lastSeen': '최근 활동', 'my.logoutBtn': '로그아웃', 'my.justNow': '방금', 'my.minAgo': '분 전',
    'bible.verSimpl': '简体中文和合本', 'bible.verTrad': '繁體中文和合本', 'bible.verKjv': 'King James Version',
    'my.annotation': '말씀 메모/하이라이트',
    'my.annEmpty': '성경 본문 절을 탭하여 하이라이트·메모를 추가하세요.',
    'my.history': '대화 기록', 'my.historyLogin': '로그인 후 서버에 저장된 대화 기록을 확인할 수 있습니다.',
    'my.historyEmpty': '아직 대화 기록이 없습니다.', 'my.historyDelConfirm': '이 대화를 삭제할까요?',
    'my.membership': '멤버십', 'my.membershipLogin': '로그인 후 멤버십을 이용할 수 있습니다.',
    'my.loginRegister': '로그인 / 등록', 'my.memberCurrent': '현재 멤버십: ',
    'my.plansLoadFail': '멤버십 플랜을 불러오지 못했습니다.', 'my.plansEmpty': '이용 가능한 플랜이 없습니다.',
    'my.year': '년', 'my.month': '월', 'my.pay': '결제하기',
    'my.account': '계정', 'my.logout': '로그아웃',
    'my.loginNeeded': '먼저 로그인해 주세요.',
    'my.gpNotice': 'Google Play 결제는 곧 오픈됩니다. 지금은 공식 웹사이트에서 결제해 주세요.',
    'my.payPrep': '결제창을 준비하는 중...',
    'my.payModuleFail': '결제 모듈을 불러오지 못했습니다. 새로고침 후 다시 시도하세요.',
    'my.payFail': '결제가 취소되거나 실패했습니다: ',
    'my.payDone': '결제 완료! 멤버십이 활성화되었습니다.',
    'my.payConfirmFail': '결제는 완료됐으나 서버 확인에 실패했습니다. 잠시 후 다시 시도해 주세요.',
    'my.payError': '결제 오류: ',
    // ── 设置/설정 (app.js) ──
    'settings.title': '설정', 'settings.titleSub': '앱 환경을 나에게 맞게 조정하세요', 'settings.theme': '테마', 'settings.font': '글자 크기',
    'settings.themeHint': '화면 밝기 모드를 선택하세요', 'settings.themeLight': '밝음', 'settings.themeDark': '어두움', 'settings.themeSystem': '시스템 따름',
    'settings.notify': '알림', 'settings.notifyDesc': '푸시 알림 받기', 'settings.language': '언어',
    'settings.langSystem': '시스템 따름', 'settings.account': '계정',
    'theme.system': '시스템', 'theme.light': '라이트', 'theme.dark': '다크',
    'font.small': '작게', 'font.medium': '보통', 'font.large': '크게', 'font.xlarge': '아주 크게',
    'lang.ko': '한국어', 'lang.en': 'English', 'lang.zhcn': '简体中文', 'lang.zhtw': '繁體中文',
    'account.login': '로그인', 'account.email': '이메일', 'account.password': '비밀번호',
    'account.loginBtn': '로그인', 'account.logout': '로그아웃', 'account.logoutOk': '로그아웃되었습니다.',
    'account.notSupported': '이 기기에서는 이 기능을 사용할 수 없습니다.',
    'legal.terms': '이용 약관', 'legal.privacy': '개인정보 처리방침',
    'auth.wrong': '이메일 또는 비밀번호가 올바르지 않습니다.', 'auth.ok': '로그인 성공',
    'account.signup': '회원가입', 'account.signupBtn': '회원가입', 'account.passwordPlaceholder': '비밀번호(6자 이상)',
    'account.google': 'Google 로그인', 'account.googleProcessing': 'Google 로그인 중...',
    'auth.needEmailPw': '이메일과 비밀번호를 입력해 주세요.', 'auth.verifySent': '회원가입 성공! 이메일 인증 링크를 보냈습니다. 메일을 확인해 주세요.',
    'auth.fail': '작업에 실패했습니다.', 'auth.googleFail': 'Google 로그인 실패', 'auth.googleError': 'Google 로그인 중 오류가 발생했습니다.',
    'auth.forgotPassword': '비밀번호를 잊으셨나요?',
    'auth.wrongPw': '이메일 또는 비밀번호가 올바르지 않습니다.',
    'auth.emailTaken': '이미 가입된 이메일입니다.',
    'auth.invalidEmail': '이메일 형식이 올바르지 않습니다.',
    'auth.pwTooShort': '비밀번호는 6자 이상이어야 합니다.',
    'auth.termsAgree': '이용약관에 동의합니다',
    'auth.privacyAgree': '개인정보 처리방침에 동의합니다',
    'auth.consentRequired': '이용약관과 개인정보 처리방침에 동의해야 합니다.',
    'auth.forgotTitle': '비밀번호 찾기',
    'auth.forgotHint': '가입한 이메일을 입력하면 비밀번호 재설정 링크를 보내드립니다.',
    'auth.forgotSent': '비밀번호 재설정 링크를 이메일로 보냈습니다. 메일을 확인해 주세요.',
    'auth.resetTitle': '새 비밀번호 설정',
    'auth.resetHint': '이메일로 받은 링크의 코드를 입력하고 새 비밀번호를 설정해 주세요.',
    'auth.resetOk': '비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요.',
    'auth.backToLogin': '로그인으로 돌아가기',
    'common.processing': '처리 중...', 'common.or': '또는', 'settings.langHint': '앱 메뉴와 버튼의 표시 언어',
    // ── 版本 gate (app.js) ──
    'update.title': '업데이트가 필요합니다',
    'update.body': '현재 버전은 더 이상 지원되지 않습니다. 계속하려면 최신 버전으로 업데이트해 주세요.',
    'update.get': '최신 버전 받기',
    'update.available': '새 버전', 'update.availableTail': '이(가) 있습니다. 설정에서 업데이트할 수 있어요.',
    // ── Toast (공통) ──
    'toast.linkCopied': '링크가 복사되었습니다.', 'toast.noteSaved': '메모가 저장되었습니다.',
    'toast.deleted': '삭제되었습니다.', 'toast.delFail': '삭제에 실패했습니다.',
    'toast.cardSaved': '말씀 카드가 저장되었습니다.', 'toast.cardFail': '카드 생성 실패: ',
    // ── 播放器 (player.js) ──
    'player.nowPlaying': '재생 중', 'player.queue': '재생 목록', 'player.queueEmpty': '재생 목록이 비어 있습니다.',
    'player.noContent': '내용이 없습니다.', 'player.sermonScripture': '설교 본문',
    'player.shuffle': '무작위 재생', 'player.repeat': '반복', 'player.abLoop': '구간 반복', 'player.eq': '이퀄라이저',
    'player.sleep': '수면 타이머',
    'eq.flat': '기본', 'eq.pop': '팝', 'eq.rock': '록', 'eq.classical': '클래식', 'eq.vocal': '보컬', 'eq.bass': '중저음',
    'sleep.15': '15분', 'sleep.30': '30분', 'sleep.45': '45분', 'sleep.60': '60분', 'sleep.90': '90분', 'sleep.off': '끄기',
    'sleep.sub': '{m}분 후 정지',
    'toast.abSetA': 'A점이 설정되었습니다. 다시 누르면 B점을 설정합니다.',
    'toast.abOn': '구간 반복이 켜졌습니다.', 'toast.abOff': '구간 반복이 꺼졌습니다.',
    'toast.sleepEnd': '수면 타이머가 종료되었습니다.',
    // ── 누락 보완 키 ──
    'hymn.sortLocale': 'ko', 'hymn.defaultCategory': '찬송', 'hymn.fav': '내 찬송',
    'hymn.playNext': '다음에 재생', 'hymn.viewLyrics': '가사 보기', 'toast.addedQueue': '재생 목록에 추가됨',
    'sermon.sortLocale': 'ko', 'sermon.uncategorized': '미분류', 'bible.oldTestament': '구약', 'bible.newTestament': '신약',
    'my.fontSample': '여호와는 나의 목자시니 내게 부족함이 없으리로다.',
    'insight.loading': '통찰 불러오는 중…', 'insight.fail': '통찰을 불러올 수 없습니다.', 'insight.error': '통찰 조회 오류',
    'visitor.label': '방문자', 'visitor.loginRegister': '로그인 / 등록', 'auth.continueLogin': '로그인하여 계속',
    'account.title': '내 계정', 'auth.loginTitle': '로그인', 'ad.label': '광고',
    'chat.sendToChat': '💬 채팅으로 보내기', 'chat.sendToChatTitle': '채팅으로 보내기',
    'home.loading': '홈을 불러오는 중…', 'rank.title': '인기 질문',
    'auth.emailPlaceholder': '이메일', 'auth.passwordPlaceholder2': '비밀번호(6자 이상)',
    'rank.empty': '아직 인기 질문이 없습니다. 말씀 나눔을 시작해 보세요!', 'rank.answerCount': '{n}개의 답변', 'rank.categoryFallback': '인기', 'home.fail': '홈 로딩에 실패했습니다. 다시 시도해 주세요.',
  },
  'en': {
    'tab.bible': 'Bible', 'tab.hymns': 'Hymns', 'tab.word': 'Word',
    'tab.today': 'Today', 'tab.settings': 'Settings',
    'chat.title': 'Ask AI',
    'chat.placeholder': 'Ask anything, freely…',
    'chat.send': 'Send',
    'chat.greeting': 'Hello! Feel free to ask me anything about faith and the Bible.',
    'chat.suggestedTitle': 'Try asking like this',
    'chat.suggested': ['Where should I start reading the Bible?', 'What is grace?', 'What does the Lord’s Prayer mean?', 'How do I share my faith with a friend?'],
    'chat.privacyNote': 'Your questions are never recorded by real name; they only help improve the question pool.',
    'common.loading': 'Loading…', 'common.cancel': 'Cancel', 'common.save': 'Save',
    'common.more': 'More', 'common.share': 'Share', 'common.delete': 'Delete',
    'bible.empty': 'Bible text has not been uploaded yet. Please upload it from the admin panel.',
    'bible.loadFail': 'Unable to load scripture.',
    'bible.searchPlaceholder': 'Search the whole Bible…',
    'bible.noResult': 'No matching scripture found.',
    'bible.chapter': 'Ch', 'bible.verse': 'V',
    'bible.noteTitle': '📝 Note', 'bible.notePlaceholder': 'Type your note...',
    'bible.noteCancel': 'Cancel', 'bible.noteSave': 'Save',
    'bible.card': '📤 Verse Card', 'bible.copy': 'Copy', 'bible.cardCopied': 'Verse card copied.',
    'hymn.searchPlaceholder': 'Search title · lyrics · genre · hymn number…',
    'hymn.sort.number': 'By number', 'hymn.sort.title': 'By title', 'hymn.sort.recent': 'Recently played',
    'hymn.recent': 'Recently played',
    'hymn.playAll': '▶ Play All', 'hymn.all': 'All Hymns', 'hymn.empty': 'No hymns match your filters.',
    'hymn.today': 'Hymn of the Day', 'hymn.offline': '⬇ Offline', 'hymn.menu': 'Menu',
    'sermon.empty': 'No sermon audio registered yet. Please upload from the admin panel.',
    'sermon.searchPlaceholder': 'Search title · speaker · passage',
    'sermon.featured': 'Featured This Week', 'sermon.all': 'All', 'sermon.more': 'More ›',
    'sermon.listen': '♪ Listen', 'sermon.copyLink': '🔗 Copy link',
    'sermon.favOn': '⭐ Favorited', 'sermon.favOff': '☆ Favorite',
    'sermon.summary': 'Sermon Summary', 'sermon.related': '🔗 Related Sermons',
    'sermon.seriesOther': '📚 More from {series}',
    'sermon.summaryEmpty': 'Summary is being prepared.',
    'meditation.dailyLabel': '📅 Daily Verse', 'meditation.emptyBody': 'Start your day by meditating on the Lord’s word today.',
    'meditation.tab': 'Devotion',
    'word.home': '🏠 Home', 'word.ask': '💬 Meditate', 'word.fav': '⭐ Favorites',
    'word.favEmpty': 'No favorited verse cards yet. Tap ⭐ on a card to add one.',
    'my.displayFont': 'Display & Font',     'my.bibleSettings': 'Bible Defaults', 'my.bibleVersion': 'Default Bible version',
    'my.bibleVersionHint': 'Version used when opening the Bible tab', 'my.bibleAuto': 'Follow system language', 'my.dataInfo': 'Data & Info',
    'my.clearCache': 'Clear cache/data', 'my.clearCacheHint': 'Remove temporary stored data', 'my.clearBtn': 'Clear',
    'my.clearDone': 'Cache cleared.', 'my.clearFail': 'Could not clear cache.', 'my.appVersion': 'App version',
    'my.changePassword': 'Change Password', 'my.changePasswordHint': 'Update your login password', 'my.changeBtn': 'Change',
    'my.changeConfirm': 'Change Password', 'my.pwCurrent': 'Current password', 'my.pwNew': 'New password (6+ chars)',
    'my.pwChanged': 'Password has been changed.',
    'my.deviceManagement': 'Devices & Sessions', 'my.deviceManagementHint': 'View logged-in devices and log out remotely',
    'my.deviceManageBtn': 'Manage', 'my.noDevices': 'No logged-in devices.', 'my.currentDevice': 'Current device',
    'my.lastSeen': 'Last seen', 'my.logoutBtn': 'Log out', 'my.justNow': 'just now', 'my.minAgo': 'min ago',
    'bible.verSimpl': '简体中文和合本', 'bible.verTrad': '繁體中文和合本', 'bible.verKjv': 'King James Version',
    'my.annotation': 'Verse Notes / Highlights',
    'my.annEmpty': 'Tap a Bible verse to add highlights and notes.',
    'my.history': 'Chat History', 'my.historyLogin': 'Log in to view your server-saved chat history.',
    'my.historyEmpty': 'No chat history yet.', 'my.historyDelConfirm': 'Delete this conversation?',
    'my.membership': 'Membership', 'my.membershipLogin': 'Log in to use Membership.',
    'my.loginRegister': 'Log in / Sign up', 'my.memberCurrent': 'Current membership: ',
    'my.plansLoadFail': 'Unable to load membership plans.', 'my.plansEmpty': 'No plans available.',
    'my.year': 'yr', 'my.month': 'mo', 'my.pay': 'Pay',
    'my.account': 'Account', 'my.logout': 'Log out',
    'my.loginNeeded': 'Please log in first.',
    'my.gpNotice': 'Google Play billing is coming soon. Please pay on the official website for now.',
    'my.payPrep': 'Preparing payment window…',
    'my.payModuleFail': 'Could not load the payment module. Refresh and try again.',
    'my.payFail': 'Payment was cancelled or failed: ',
    'my.payDone': 'Payment complete! Membership activated.',
    'my.payConfirmFail': 'Payment succeeded but server confirmation failed. Please try again shortly.',
    'my.payError': 'Payment error: ',
    'settings.title': 'Settings', 'settings.titleSub': 'Make the app feel like yours', 'settings.theme': 'Theme', 'settings.font': 'Font Size',
    'settings.themeHint': 'Choose your display mode', 'settings.themeLight': 'Light', 'settings.themeDark': 'Dark', 'settings.themeSystem': 'System',
    'settings.notify': 'Notifications', 'settings.notifyDesc': 'Receive push notifications', 'settings.language': 'Language',
    'settings.langSystem': 'Follow System', 'settings.account': 'Account',
    'theme.system': 'System', 'theme.light': 'Light', 'theme.dark': 'Dark',
    'font.small': 'Small', 'font.medium': 'Medium', 'font.large': 'Large', 'font.xlarge': 'Extra Large',
    'lang.ko': '한국어', 'lang.en': 'English', 'lang.zhcn': '简体中文', 'lang.zhtw': '繁體中文',
    'account.login': 'Log In', 'account.email': 'Email', 'account.password': 'Password',
    'account.loginBtn': 'Log In', 'account.logout': 'Log Out', 'account.logoutOk': 'Logged out.',
    'account.notSupported': 'This feature is not available on this device.',
    'legal.terms': 'Terms of Service', 'legal.privacy': 'Privacy Policy',
    'auth.wrong': 'Incorrect email or password.', 'auth.ok': 'Login successful',
    'account.signup': 'Sign up', 'account.signupBtn': 'Sign up', 'account.passwordPlaceholder': 'Password (6+ chars)',
    'account.google': 'Google login', 'account.googleProcessing': 'Signing in with Google...',
    'auth.needEmailPw': 'Please enter email and password.', 'auth.verifySent': 'Signed up! A verification link was sent to your email.',
    'auth.fail': 'Action failed.', 'auth.googleFail': 'Google login failed', 'auth.googleError': 'Error during Google login.',
    'auth.forgotPassword': 'Forgot your password?',
    'auth.wrongPw': 'Invalid email or password.',
    'auth.emailTaken': 'This email is already registered.',
    'auth.invalidEmail': 'Please enter a valid email address.',
    'auth.pwTooShort': 'Password must be at least 6 characters.',
    'auth.termsAgree': 'I agree to the Terms of Service',
    'auth.privacyAgree': 'I agree to the Privacy Policy',
    'auth.consentRequired': 'You must agree to the Terms and Privacy Policy.',
    'auth.forgotTitle': 'Forgot Password',
    'auth.forgotHint': 'Enter your registered email and we will send you a password reset link.',
    'auth.forgotSent': 'A password reset link was sent to your email. Please check your inbox.',
    'auth.resetTitle': 'Set a New Password',
    'auth.resetHint': 'Enter the code from the link you received, then set a new password.',
    'auth.resetOk': 'Your password has been changed. Please log in with your new password.',
    'auth.backToLogin': 'Back to login',
    'common.processing': 'Processing…', 'common.or': 'or', 'settings.langHint': 'Display language for menus and buttons',
    'update.title': 'Update Required',
    'update.body': 'This version is no longer supported. Please update to the latest version to continue.',
    'update.get': 'Get Latest Version',
    'update.available': 'New version', 'update.availableTail': ' is available. You can update in Settings.',
    'toast.linkCopied': 'Link copied.', 'toast.noteSaved': 'Note saved.',
    'toast.deleted': 'Deleted.', 'toast.delFail': 'Failed to delete.',
    'toast.cardSaved': 'Verse card saved.', 'toast.cardFail': 'Card creation failed: ',
    'player.nowPlaying': 'Now Playing', 'player.queue': 'Play Queue', 'player.queueEmpty': 'Play queue is empty.',
    'player.noContent': 'No content.', 'player.sermonScripture': 'Sermon Scripture',
    'player.shuffle': 'Shuffle', 'player.repeat': 'Repeat', 'player.abLoop': 'A-B Loop', 'player.eq': 'Equalizer',
    'player.sleep': 'Sleep Timer',
    'eq.flat': 'Flat', 'eq.pop': 'Pop', 'eq.rock': 'Rock', 'eq.classical': 'Classical', 'eq.vocal': 'Vocal', 'eq.bass': 'Bass',
    'sleep.15': '15 min', 'sleep.30': '30 min', 'sleep.45': '45 min', 'sleep.60': '60 min', 'sleep.90': '90 min', 'sleep.off': 'Off',
    'sleep.sub': 'Stop after {m} min',
    'toast.abSetA': 'Point A set. Tap again to set point B.',
    'toast.abOn': 'A-B loop enabled.', 'toast.abOff': 'A-B loop disabled.',
    'toast.sleepEnd': 'Sleep timer ended.',
    // ── 누락 보완 키 ──
    'hymn.sortLocale': 'en', 'hymn.defaultCategory': 'Hymn', 'hymn.fav': 'My Hymns',
    'hymn.playNext': 'Play next', 'hymn.viewLyrics': 'View lyrics', 'toast.addedQueue': 'Added to play queue',
    'sermon.sortLocale': 'en', 'sermon.uncategorized': 'Uncategorized', 'bible.oldTestament': 'Old Testament', 'bible.newTestament': 'New Testament',
    'my.fontSample': 'The LORD is my shepherd; I shall not want.',
    'insight.loading': 'Loading insights…', 'insight.fail': 'Unable to load insights.', 'insight.error': 'Insight query error',
    'visitor.label': 'Visitor', 'visitor.loginRegister': 'Log in / Sign up', 'auth.continueLogin': 'Log in to continue',
    'account.title': 'My Account', 'auth.loginTitle': 'Log In', 'ad.label': 'Ad',
    'chat.sendToChat': '💬 Send to chat', 'chat.sendToChatTitle': 'Send to chat',
    'home.loading': 'Loading home…', 'rank.title': 'Popular Questions',
    'auth.emailPlaceholder': 'Email', 'auth.passwordPlaceholder2': 'Password (6+ chars)',
    'rank.empty': 'No popular questions yet. Start a conversation!', 'rank.answerCount': '{n} answers', 'rank.categoryFallback': 'Popular', 'home.fail': 'Home failed to load. Please retry.',
  },
  'zh-CN': {
    'tab.bible': '圣经', 'tab.hymns': '诗歌', 'tab.word': '话语',
    'tab.today': '今天', 'tab.settings': '设置',
    'chat.title': '向 AI 提问',
    'chat.placeholder': '想问什么，尽管问我…',
    'chat.send': '发送',
    'chat.greeting': '您好！关于信仰与圣经，有任何问题都可以问我。',
    'chat.suggestedTitle': '试试这样问',
    'chat.suggested': ['圣经该从哪里开始读？', '什么是恩典？', '主祷文是什么意思？', '怎样向朋友分享信仰？'],
    'chat.privacyNote': '你的任何问题都不会实名记录，只会用来强化问题库。',
    'common.loading': '加载中…', 'common.cancel': '取消', 'common.save': '保存',
    'common.more': '查看更多', 'common.share': '分享', 'common.delete': '删除',
    'bible.empty': '圣经经文尚未上传，请前往管理后台上传。',
    'bible.loadFail': '无法加载经文。',
    'bible.searchPlaceholder': '圣经全文搜索…',
    'bible.noResult': '未找到相关经文。',
    'bible.chapter': '章', 'bible.verse': '节',
    'bible.noteTitle': '📝 笔记', 'bible.notePlaceholder': '请输入笔记...',
    'bible.noteCancel': '取消', 'bible.noteSave': '保存',
    'bible.card': '📤 经文卡片', 'bible.copy': '复制', 'bible.cardCopied': '经文卡片已复制。',
    'hymn.searchPlaceholder': '标题 · 歌词 · 流派 · 诗歌编号搜索…',
    'hymn.sort.number': '编号顺序', 'hymn.sort.title': '标题顺序', 'hymn.sort.recent': '最近播放',
    'hymn.recent': '最近播放',
    'hymn.playAll': '▶ 播放全部', 'hymn.all': '全部诗歌', 'hymn.empty': '没有符合条件的诗歌。',
    'hymn.today': '今日诗歌', 'hymn.offline': '⬇ 离线', 'hymn.menu': '菜单',
    'sermon.empty': '尚未登记讲道音频。请前往管理后台上传。',
    'sermon.searchPlaceholder': '标题 · 讲员 · 经文搜索',
    'sermon.featured': '本周精选', 'sermon.all': '全部', 'sermon.more': '查看更多 ›',
    'sermon.listen': '♪ 听讲道', 'sermon.copyLink': '🔗 复制链接',
    'sermon.favOn': '⭐ 已收藏', 'sermon.favOff': '☆ 收藏',
    'sermon.summary': '讲道摘要', 'sermon.related': '🔗 相关讲道',
    'sermon.seriesOther': '📚 {series}的其他讲道',
    'sermon.summaryEmpty': '摘要准备中。',
    'meditation.dailyLabel': '📅 今日经文', 'meditation.emptyBody': '今天也让我们从默想主的话语开始吧。',
    'meditation.tab': '灵修',
    'word.home': '🏠 首页', 'word.ask': '💬 话语默想', 'word.fav': '⭐ 收藏',
    'word.favEmpty': '还没有收藏的经文卡片。点击卡片上的 ⭐ 添加吧。',
    'my.displayFont': '显示与字体',     'my.bibleSettings': '圣经默认', 'my.bibleVersion': '默认圣经版本',
    'my.bibleVersionHint': '打开圣经标签时使用的默认版本', 'my.bibleAuto': '跟随系统语言', 'my.dataInfo': '数据与信息',
    'my.clearCache': '清除缓存/数据', 'my.clearCacheHint': '删除临时保存的数据', 'my.clearBtn': '清除',
    'my.clearDone': '已清除缓存。', 'my.clearFail': '无法清除缓存。', 'my.appVersion': '应用版本',
    'my.changePassword': '修改密码', 'my.changePasswordHint': '更改登录密码', 'my.changeBtn': '修改',
    'my.changeConfirm': '确认修改', 'my.pwCurrent': '当前密码', 'my.pwNew': '新密码（至少6位）',
    'my.pwChanged': '密码已修改。',
    'my.deviceManagement': '设备与登录管理', 'my.deviceManagementHint': '查看已登录设备并可远程退出',
    'my.deviceManageBtn': '管理', 'my.noDevices': '没有已登录的设备。', 'my.currentDevice': '当前设备',
    'my.lastSeen': '最近活动', 'my.logoutBtn': '退出', 'my.justNow': '刚刚', 'my.minAgo': '分钟前',
    'bible.verSimpl': '简体中文和合本', 'bible.verTrad': '繁體中文和合本', 'bible.verKjv': 'King James Version',
    'my.annotation': '话语笔记/高亮',
    'my.annEmpty': '点击圣经经文可添加高亮与笔记。',
    'my.history': '对话记录', 'my.historyLogin': '登录后可查看服务器保存的对话记录。',
    'my.historyEmpty': '还没有对话记录。', 'my.historyDelConfirm': '要删除这段对话吗？',
    'my.membership': '会员', 'my.membershipLogin': '登录后可开通会员。',
    'my.loginRegister': '登录 / 注册', 'my.memberCurrent': '当前会员: ',
    'my.plansLoadFail': '无法加载会员方案。', 'my.plansEmpty': '暂无可用方案。',
    'my.year': '年', 'my.month': '月', 'my.pay': '去支付',
    'my.account': '账户', 'my.logout': '退出登录',
    'my.loginNeeded': '请先登录。',
    'my.gpNotice': 'Google Play 支付即将上线，目前请前往官网支付。',
    'my.payPrep': '正在准备支付窗口…',
    'my.payModuleFail': '无法加载支付模块，请刷新后重试。',
    'my.payFail': '支付已取消或失败：',
    'my.payDone': '支付完成！会员已激活。',
    'my.payConfirmFail': '支付已完成，但服务器确认失败。请稍后重试。',
    'my.payError': '支付错误：',
    'settings.title': '设置', 'settings.theme': '主题', 'settings.font': '字体大小',
    'settings.notify': '通知', 'settings.notifyDesc': '允许推送通知', 'settings.language': '语言',
    'settings.langSystem': '跟随系统', 'settings.account': '账户',
    'theme.system': '跟随系统', 'theme.light': '浅色', 'theme.dark': '深色',
    'font.small': '小', 'font.medium': '中', 'font.large': '大', 'font.xlarge': '特大',
    'lang.ko': '한국어', 'lang.en': 'English', 'lang.zhcn': '简体中文', 'lang.zhtw': '繁體中文',
    'account.login': '登录', 'account.email': '邮箱', 'account.password': '密码',
    'account.loginBtn': '登录', 'account.logout': '退出登录', 'account.logoutOk': '已退出登录。',
    'account.notSupported': '当前设备不支持该功能。',
    'legal.terms': '使用条款', 'legal.privacy': '隐私政策',
    'auth.wrong': '账号或密码错误', 'auth.ok': '登录成功',
    'account.signup': '注册', 'account.signupBtn': '注册', 'account.passwordPlaceholder': '密码（至少6位）',
    'account.google': 'Google 登录', 'account.googleProcessing': '正在 Google 登录...',
    'auth.needEmailPw': '请输入邮箱和密码。', 'auth.verifySent': '注册成功！已发送邮箱验证链接，请查收邮件。',
    'auth.fail': '操作失败。', 'auth.googleFail': 'Google 登录失败', 'auth.googleError': 'Google 登录时出错。',
    'auth.forgotPassword': '忘记密码？',
    'auth.wrongPw': '邮箱或密码不正确。',
    'auth.emailTaken': '该邮箱已注册。',
    'auth.invalidEmail': '请输入有效的邮箱地址。',
    'auth.pwTooShort': '密码至少需要 6 个字符。',
    'auth.termsAgree': '我已阅读并同意服务条款',
    'auth.privacyAgree': '我已阅读并同意隐私政策',
    'auth.consentRequired': '请先同意服务条款和隐私政策。',
    'auth.forgotTitle': '找回密码',
    'auth.forgotHint': '输入注册邮箱，我们会发送密码重置链接到您的邮箱。',
    'auth.forgotSent': '密码重置链接已发送到您的邮箱，请查收。',
    'auth.resetTitle': '设置新密码',
    'auth.resetHint': '输入邮件中链接的代码，然后设置新密码。',
    'auth.resetOk': '密码已修改。请使用新密码登录。',
    'auth.backToLogin': '返回登录',
    'common.processing': '处理中...', 'common.or': '或', 'settings.langHint': '菜单与按钮的显示语言',
    'update.title': '需要更新',
    'update.body': '当前版本不再受支持，请更新到最新版本以继续使用。',
    'update.get': '获取最新版本',
    'update.available': '新版本', 'update.availableTail': ' 已发布，可在设置中更新。',
    'toast.linkCopied': '链接已复制', 'toast.noteSaved': '笔记已保存。',
    'toast.deleted': '已删除。', 'toast.delFail': '删除失败',
    'toast.cardSaved': '经文卡片已保存。', 'toast.cardFail': '卡片生成失败：',
    'player.nowPlaying': '播放中', 'player.queue': '播放列表', 'player.queueEmpty': '播放列表为空。',
    'player.noContent': '暂无内容。', 'player.sermonScripture': '讲道经文',
    'player.shuffle': '随机播放', 'player.repeat': '循环', 'player.abLoop': '段落循环', 'player.eq': '均衡器',
    'player.sleep': '睡眠定时器',
    'eq.flat': '默认', 'eq.pop': '流行', 'eq.rock': '摇滚', 'eq.classical': '古典', 'eq.vocal': '人声', 'eq.bass': '重低音',
    'sleep.15': '15分钟', 'sleep.30': '30分钟', 'sleep.45': '45分钟', 'sleep.60': '60分钟', 'sleep.90': '90分钟', 'sleep.off': '关闭',
    'sleep.sub': '{m}分钟后停止',
    'toast.abSetA': '已设置 A 点，再次点击设置 B 点',
    'toast.abOn': '已开启段落循环', 'toast.abOff': '已关闭段落循环',
    'toast.sleepEnd': '睡眠定时器已结束',
    // ── 遗漏补充键 ──
    'hymn.sortLocale': 'zh', 'hymn.defaultCategory': '诗歌', 'hymn.fav': '我的诗歌',
    'hymn.playNext': '稍后播放', 'hymn.viewLyrics': '查看歌词', 'toast.addedQueue': '已添加到播放列表',
    'sermon.sortLocale': 'zh', 'sermon.uncategorized': '未分类', 'bible.oldTestament': '旧约', 'bible.newTestament': '新约',
    'my.fontSample': '耶和华是我的牧者，我必不至缺乏。',
    'insight.loading': '洞察加载中…', 'insight.fail': '无法加载洞察。', 'insight.error': '洞察查询错误',
    'visitor.label': '访客', 'visitor.loginRegister': '登录 / 注册', 'auth.continueLogin': '登录以继续',
    'account.title': '我的账户', 'auth.loginTitle': '登录', 'ad.label': '广告',
    'chat.sendToChat': '💬 发送到聊天', 'chat.sendToChatTitle': '发送到聊天',
    'home.loading': '正在加载首页…', 'rank.title': '热门问答',
    'auth.emailPlaceholder': '邮箱', 'auth.passwordPlaceholder2': '密码（至少6位）',
    'rank.empty': '还没有热门问题，去聊一聊吧！', 'rank.answerCount': '{n} 个回答', 'rank.categoryFallback': '热门', 'home.fail': '首页加载失败，请重试。',
  },
  'zh-TW': {
    'tab.bible': '聖經', 'tab.hymns': '詩歌', 'tab.word': '話語',
    'tab.today': '今天', 'tab.settings': '設定',
    'chat.title': '向 AI 提問',
    'chat.placeholder': '想問什麼，儘管問我…',
    'chat.send': '傳送',
    'chat.greeting': '您好！關於信仰與聖經，有任何問題都可以問我。',
    'chat.suggestedTitle': '試試這樣問',
    'chat.suggested': ['聖經該從哪裡開始讀？', '什麼是恩典？', '主禱文的意思是什麼？', '怎樣向朋友分享信仰？'],
    'chat.privacyNote': '您的任何問題都不會實名記錄，只會用來強化問題庫。',
    'common.loading': '載入中…', 'common.cancel': '取消', 'common.save': '儲存',
    'common.more': '查看更多', 'common.share': '分享', 'common.delete': '刪除',
    'bible.empty': '聖經經文尚未上傳，請前往管理後台上傳。',
    'bible.loadFail': '無法載入經文。',
    'bible.searchPlaceholder': '聖經全文搜尋…',
    'bible.noResult': '未找到相關經文。',
    'bible.chapter': '章', 'bible.verse': '節',
    'bible.noteTitle': '📝 筆記', 'bible.notePlaceholder': '請輸入筆記...',
    'bible.noteCancel': '取消', 'bible.noteSave': '儲存',
    'bible.card': '📤 經文卡片', 'bible.copy': '複製', 'bible.cardCopied': '經文卡片已複製。',
    'hymn.searchPlaceholder': '標題 · 歌詞 · 流派 · 詩歌編號搜尋…',
    'hymn.sort.number': '編號順序', 'hymn.sort.title': '標題順序', 'hymn.sort.recent': '最近播放',
    'hymn.recent': '最近播放',
    'hymn.playAll': '▶ 播放全部', 'hymn.all': '全部詩歌', 'hymn.empty': '沒有符合條件的詩歌。',
    'hymn.today': '今日詩歌', 'hymn.offline': '⬇ 離線', 'hymn.menu': '選單',
    'sermon.empty': '尚未登記講道音檔。請前往管理後台上傳。',
    'sermon.searchPlaceholder': '標題 · 講員 · 經文搜尋',
    'sermon.featured': '本週精選', 'sermon.all': '全部', 'sermon.more': '查看更多 ›',
    'sermon.listen': '♪ 聽講道', 'sermon.copyLink': '🔗 複製連結',
    'sermon.favOn': '⭐ 已收藏', 'sermon.favOff': '☆ 收藏',
    'sermon.summary': '講道摘要', 'sermon.related': '🔗 相關講道',
    'sermon.seriesOther': '📚 {series}的其他講道',
    'sermon.summaryEmpty': '摘要準備中。',
    'meditation.dailyLabel': '📅 今日經文', 'meditation.emptyBody': '今天也讓我們從默想主的話語開始吧。',
    'meditation.tab': '靈修',
    'word.home': '🏠 首頁', 'word.ask': '💬 話語默想', 'word.fav': '⭐ 收藏',
    'word.favEmpty': '還沒有收藏的經文卡片。點擊卡片上的 ⭐ 新增吧。',
    'my.displayFont': '顯示與字體',     'my.bibleSettings': '聖經預設', 'my.bibleVersion': '預設聖經版本',
    'my.bibleVersionHint': '開啟聖經標籤時使用的預設版本', 'my.bibleAuto': '跟隨系統語言', 'my.dataInfo': '資料與資訊',
    'my.clearCache': '清除快取/資料', 'my.clearCacheHint': '刪除暫存資料', 'my.clearBtn': '清除',
    'my.clearDone': '已清除快取。', 'my.clearFail': '無法清除快取。', 'my.appVersion': '應用程式版本',
    'my.changePassword': '修改密碼', 'my.changePasswordHint': '更改登入密碼', 'my.changeBtn': '修改',
    'my.changeConfirm': '確認修改', 'my.pwCurrent': '目前密碼', 'my.pwNew': '新密碼（至少6位）',
    'my.pwChanged': '密碼已修改。',
    'my.deviceManagement': '裝置與登入管理', 'my.deviceManagementHint': '查看已登入裝置並可遠端登出',
    'my.deviceManageBtn': '管理', 'my.noDevices': '沒有已登入的裝置。', 'my.currentDevice': '目前裝置',
    'my.lastSeen': '最近活動', 'my.logoutBtn': '登出', 'my.justNow': '剛剛', 'my.minAgo': '分鐘前',
    'bible.verSimpl': '简体中文和合本', 'bible.verTrad': '繁體中文和合本', 'bible.verKjv': 'King James Version',
    'my.annotation': '話語筆記/高亮',
    'my.annEmpty': '點擊聖經經文可新增高亮與筆記。',
    'my.history': '對話記錄', 'my.historyLogin': '登入後可查看伺服器儲存的對話記錄。',
    'my.historyEmpty': '還沒有對話記錄。', 'my.historyDelConfirm': '要刪除這段對話嗎？',
    'my.membership': '會員', 'my.membershipLogin': '登入後可開通會員。',
    'my.loginRegister': '登入 / 註冊', 'my.memberCurrent': '當前會員: ',
    'my.plansLoadFail': '無法載入會員方案。', 'my.plansEmpty': '暫無可用方案。',
    'my.year': '年', 'my.month': '月', 'my.pay': '去支付',
    'my.account': '帳戶', 'my.logout': '登出',
    'my.loginNeeded': '請先登入。',
    'my.gpNotice': 'Google Play 支付即將上線，目前請前往官網支付。',
    'my.payPrep': '正在準備支付視窗…',
    'my.payModuleFail': '無法載入支付模組，請重新整理後重試。',
    'my.payFail': '支付已取消或失敗：',
    'my.payDone': '支付完成！會員已啟用。',
    'my.payConfirmFail': '支付已完成，但伺服器確認失敗。請稍後重試。',
    'my.payError': '支付錯誤：',
    'settings.title': '設定', 'settings.titleSub': '將應用調成你喜歡的樣子', 'settings.theme': '主題', 'settings.font': '字體大小',
    'settings.themeHint': '選擇顯示模式', 'settings.themeLight': '淺色', 'settings.themeDark': '深色', 'settings.themeSystem': '跟隨系統',
    'settings.notify': '通知', 'settings.notifyDesc': '允許推播通知', 'settings.language': '語言',
    'settings.langSystem': '跟隨系統', 'settings.account': '帳戶',
    'theme.system': '跟隨系統', 'theme.light': '淺色', 'theme.dark': '深色',
    'font.small': '小', 'font.medium': '中', 'font.large': '大', 'font.xlarge': '特大',
    'lang.ko': '한국어', 'lang.en': 'English', 'lang.zhcn': '简体中文', 'lang.zhtw': '繁體中文',
    'account.login': '登入', 'account.email': '電子郵件', 'account.password': '密碼',
    'account.loginBtn': '登入', 'account.logout': '登出', 'account.logoutOk': '已登出。',
    'account.notSupported': '目前裝置不支援該功能。',
    'legal.terms': '使用條款', 'legal.privacy': '隱私政策',
    'auth.wrong': '帳號或密碼錯誤', 'auth.ok': '登入成功',
    'account.signup': '註冊', 'account.signupBtn': '註冊', 'account.passwordPlaceholder': '密碼（至少6位）',
    'account.google': 'Google 登入', 'account.googleProcessing': '正在 Google 登入...',
    'auth.needEmailPw': '請輸入電子郵件和密碼。', 'auth.verifySent': '註冊成功！已傳送電子郵件驗證連結，請查收。',
    'auth.fail': '操作失敗。', 'auth.googleFail': 'Google 登入失敗', 'auth.googleError': 'Google 登入時出錯。',
    'auth.forgotPassword': '忘記密碼？',
    'auth.wrongPw': '電子郵件或密碼不正確。',
    'auth.emailTaken': '該電子郵件已註冊。',
    'auth.invalidEmail': '請輸入有效的電子郵件地址。',
    'auth.pwTooShort': '密碼至少需要 6 個字元。',
    'auth.termsAgree': '我已閱讀並同意服務條款',
    'auth.privacyAgree': '我已閱讀並同意隱私政策',
    'auth.consentRequired': '請先同意服務條款和隱私政策。',
    'auth.forgotTitle': '找回密碼',
    'auth.forgotHint': '輸入註冊電子郵件，我們會傳送密碼重置連結到您的信箱。',
    'auth.forgotSent': '密碼重置連結已傳送至您的信箱，請查收。',
    'auth.resetTitle': '設定新密碼',
    'auth.resetHint': '輸入郵件中連結的代碼，然後設定新密碼。',
    'auth.resetOk': '密碼已修改。請使用新密碼登入。',
    'auth.backToLogin': '返回登入',
    'common.processing': '處理中...', 'common.or': '或', 'settings.langHint': '選單與按鈕的顯示語言',
    'update.title': '需要更新',
    'update.body': '目前版本不再受支援，請更新到最新版本以繼續使用。',
    'update.get': '取得最新版本',
    'update.available': '新版本', 'update.availableTail': ' 已發布，可在設定中更新。',
    'toast.linkCopied': '連結已複製', 'toast.noteSaved': '筆記已儲存。',
    'toast.deleted': '已刪除。', 'toast.delFail': '刪除失敗',
    'toast.cardSaved': '經文卡片已儲存。', 'toast.cardFail': '卡片生成失敗：',
    'player.nowPlaying': '播放中', 'player.queue': '播放清單', 'player.queueEmpty': '播放清單為空。',
    'player.noContent': '暫無內容。', 'player.sermonScripture': '講道經文',
    'player.shuffle': '隨機播放', 'player.repeat': '循環', 'player.abLoop': '段落循環', 'player.eq': '等化器',
    'player.sleep': '睡眠定時器',
    'eq.flat': '預設', 'eq.pop': '流行', 'eq.rock': '搖滾', 'eq.classical': '古典', 'eq.vocal': '人聲', 'eq.bass': '重低音',
    'sleep.15': '15分鐘', 'sleep.30': '30分鐘', 'sleep.45': '45分鐘', 'sleep.60': '60分鐘', 'sleep.90': '90分鐘', 'sleep.off': '關閉',
    'sleep.sub': '{m}分鐘後停止',
    'toast.abSetA': '已設定 A 點，再次點擊設定 B 點',
    'toast.abOn': '已開啟段落循環', 'toast.abOff': '已關閉段落循環',
    'toast.sleepEnd': '睡眠定時器已結束',
    // ── 遺漏補充鍵 ──
    'hymn.sortLocale': 'zh', 'hymn.defaultCategory': '詩歌', 'hymn.fav': '我的詩歌',
    'hymn.playNext': '稍後播放', 'hymn.viewLyrics': '查看歌詞', 'toast.addedQueue': '已新增到播放清單',
    'sermon.sortLocale': 'zh', 'sermon.uncategorized': '未分類', 'bible.oldTestament': '舊約', 'bible.newTestament': '新約',
    'my.fontSample': '耶和華是我的牧者，我必不致缺乏。',
    'insight.loading': '洞察載入中…', 'insight.fail': '無法載入洞察。', 'insight.error': '洞察查詢錯誤',
    'visitor.label': '訪客', 'visitor.loginRegister': '登入 / 註冊', 'auth.continueLogin': '登入以繼續',
    'account.title': '我的帳戶', 'auth.loginTitle': '登入', 'ad.label': '廣告',
    'chat.sendToChat': '💬 傳送到聊天', 'chat.sendToChatTitle': '傳送到聊天',
    'home.loading': '正在載入首頁…', 'rank.title': '熱門問答',
    'auth.emailPlaceholder': '電子郵件', 'auth.passwordPlaceholder2': '密碼（至少6位）',
    'rank.empty': '還沒有熱門問題，去聊一聊吧！', 'rank.answerCount': '{n} 個回答', 'rank.categoryFallback': '熱門', 'home.fail': '首頁載入失敗，請重試。',
  },
};

/* 取当前 UI 语言：AppState.uiLang 优先，否则跟随系统 */
function _uiLang() {
  const saved = (typeof AppState !== 'undefined' && AppState.get) ? AppState.get('uiLang') : null;
  if (saved && UI_I18N[saved]) return saved;
  return _detectSystemLang();
}
function _detectSystemLang() {
  let raw = null;
  try { raw = (window.__deviceLangCode) || navigator.language || (navigator.languages && navigator.languages[0]) || 'en'; } catch (_) { raw = 'en'; }
  const l = String(raw).toLowerCase();
  if (l.startsWith('ko')) return 'ko';
  if (l.startsWith('zh')) return (l.includes('tw') || l.includes('hant') || l.includes('hk') || l.includes('mo')) ? 'zh-TW' : 'zh-CN';
  if (l.startsWith('en')) return 'en';
  return 'en';
}
/* 全局翻译函数：uiT(key, vars) 永不返回 undefined（缺失 → fallback en → key） */
function uiT(key, vars) {
  const lang = _uiLang();
  const tbl = UI_I18N[lang] || UI_I18N['en'];
  let s = (tbl && tbl[key] != null) ? tbl[key] : (UI_I18N['en'][key] != null ? UI_I18N['en'][key] : key);
  if (vars && typeof s === 'string') {
    for (const k in vars) s = s.replace(new RegExp('\\{' + k + '\\}', 'g'), vars[k]);
  }
  return s;
}
/* 语言变更时刷新所有已渲染界面（不破坏输入焦点） */
function applyUiLangAll() {
  document.documentElement.lang = _uiLang();
  if (typeof renderScreen === 'function') renderScreen(AppState.get('activeTab'));
  if (typeof renderMini === 'function') renderMini();
  if (typeof renderSheet === 'function') renderSheet();
}

// LOCAL-FULL-TEXT-SEARCH 用：转义 HTML 后高亮匹配词（防 XSS）。
function _highlight(text, term) {
  const esc = String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const t = String(term).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  try {
    return esc.replace(new RegExp('(' + t + ')', 'gi'), '<mark>$1</mark>');
  } catch (_) { return esc; }
}

function _loading() {
  return h('div', { className: 'loading-placeholder' },
    h('div', { className: 'spinner' }),
    h('p', { textContent: uiT('common.loading') }));
}

/* ── 성경 버전 결정 (2026-08-18) ──
 * 사용자가 명시 선택(bibleVersion != null) → 그 버전 사용.
 * 미지정(null) → 시스템/UI 언어에 따라 자동 매핑:
 *   en → kjv(KJV 영어), zh-TW → trad(번체), ko/zh-CN/기타 → simpl(간체)
 */
function _systemBibleVersion() {
  const lang = (_uiLang() || 'ko').toLowerCase();
  if (lang.startsWith('en')) return 'kjv';
  if (lang.indexOf('tw') >= 0 || lang.indexOf('hant') >= 0) return 'trad';
  return 'simpl';
}
function _resolveBibleVersion() {
  const stored = AppState.get('bibleVersion');
  return stored || _systemBibleVersion();
}

async function renderBible() {
  const container = $('#screen-container');
  empty(container);
  container.append(_loading());

  // 성경 버전 — 사용자 선택 우선, 없으면 시스템 언어 자동 적용
  const version = _resolveBibleVersion();
  const versions = await BibleService.getVersions();
  const books = await BibleService.getBooks(version);
  if (!books.length) {
    empty(container);
    container.append(h('p', { className: 'empty-text', textContent: uiT('bible.empty') }));
    return;
  }

  // 校正当前书卷/章/节状态
  let currentBook = AppState.get('currentBook');
  if (!books.some(b => b.id === currentBook)) currentBook = books[0].id;
  let currentChapter = AppState.get('currentChapter') || 1;

  const bookObj = books.find(b => b.id === currentBook);
  const totalChapters = bookObj ? bookObj.chapters : 1;
  if (currentChapter > totalChapters) currentChapter = totalChapters;
  if (currentChapter < 1) currentChapter = 1;

  /* 书卷选择（旧约/新约 optgroup 分组） */
  const oldBooks = books.filter(b => b.testament === 'old');
  const newBooks = books.filter(b => b.testament === 'new');
  const makeBookOption = b => h('option', { value: b.id, textContent: b.name });
  const bookSelect = h('select', {
    onChange: async e => {
      AppState.set('currentBook', e.target.value);
      AppState.set('currentChapter', 1);
      renderBible();
    }
  });
  // 성경 버전 전환 select (간체/번체)
  const versionSelect = h('select', {
    className: 'bible-version-select',
    onChange: async e => {
      AppState.set('bibleVersion', e.target.value);
      AppState.set('currentChapter', 1);
      renderBible();
    }
  });
  for (const v of versions) {
    const opt = h('option', { value: v.id, textContent: v.label });
    if (v.id === version) opt.selected = true;
    versionSelect.append(opt);
  }
  if (oldBooks.length) {
    bookSelect.append(h('optgroup', { label: uiT('bible.oldTestament') }, ...oldBooks.map(makeBookOption)));
  }
  if (newBooks.length) {
    bookSelect.append(h('optgroup', { label: uiT('bible.newTestament') }, ...newBooks.map(makeBookOption)));
  }
  bookSelect.value = currentBook;

  /* 章选择（下拉 + 上/下） */
  const chapterOptions = [];
  for (let c = 1; c <= totalChapters; c++) chapterOptions.push(h('option', { value: c, textContent: `第${c}章` }));
  const chapterSelect = h('select', {
    className: 'chapter-dropdown',
    onChange: async e => {
      AppState.set('currentChapter', parseInt(e.target.value));
      renderBible();
    }
  }, ...chapterOptions);
  chapterSelect.value = String(currentChapter);

  const chapterRow = h('div', { className: 'chapter-selector' },
    h('button', { className: 'btn-icon', textContent: '◀', onClick: () => {
      if (currentChapter > 1) { AppState.set('currentChapter', currentChapter - 1); renderBible(); }
    }}),
    chapterSelect,
    h('button', { className: 'btn-icon', textContent: '▶', onClick: () => {
      if (currentChapter < totalChapters) { AppState.set('currentChapter', currentChapter + 1); renderBible(); }
    }}),
  );

  /* 经文正文 (기본 20px) */
  const fontSize = AppState.get('fontSize');
  const passageEl = h('div', { className: 'passage-container', style: { fontSize: fontSize + 'px', lineHeight: (fontSize * 1.8 + 'px') } });

  /* 글자 크기 조절: 성경 화면에서는 화면 버튼/슬라이더 없이
     실제 폰의 하드웨어 볼륨(±)키로만 조절한다 (네이티브 브리지 → 'volume-key' 이벤트).
     PWA/브라우저 등 네이티브 브리지가 없는 환경에서는 「마이」 페이지의 슬라이더를 이용. */

  const passage = await BibleService.getPassage(currentBook, currentChapter, null, null, version);
  if (passage && passage.verses && passage.verses.length) {
    AppState.addRecentReading(`${currentBook}-${currentChapter}`);
    passageEl.append(renderPassage(passage, null, null, {
      book: currentBook, chapter: currentChapter,
      onVerseTap: (vv, vtext, ann) => _openVerseSheet(currentBook, bookObj.name || currentBook, currentChapter, vv, vtext, ann),
    }));
  } else {
    passageEl.append(h('p', { className: 'empty-text', textContent: uiT('bible.loadFail') }));
  }

  empty(container);
  container.append(
    h('div', { className: 'bible-controls' }, bookSelect, versionSelect, chapterRow),
  );

  /* LOCAL-FULL-TEXT-SEARCH: 本地圣经全文搜索框（无需服务器，替代 /mobile/bible/search 的 RAG 管线）。
     有查询词时隐藏本卷正文、显示结果列表；点击结果跳转该书卷/章。 */
  const searchResults = h('div', { className: 'bible-search-results' });
  const searchInput = h('input', {
    className: 'bible-search-input',
    type: 'search',
    placeholder: uiT('bible.searchPlaceholder'),
    style: { width: '100%', boxSizing: 'border-box', padding: '8px 10px', margin: '8px 0', borderRadius: '8px', border: '1px solid #d0d7de', fontSize: '14px' },
  });
  let _bibleSearchTimer = null;
  searchInput.addEventListener('input', (e) => {
    const q = e.target.value;
    clearTimeout(_bibleSearchTimer);
    _bibleSearchTimer = setTimeout(async () => {
      const term = q.trim();
      if (!term) { searchResults.innerHTML = ''; passageEl.style.display = ''; return; }
      passageEl.style.display = 'none';
      const results = await BibleService.searchLocal(term, 60);
      if (typeof EventService !== 'undefined') EventService.search(term, results.length);
      searchResults.innerHTML = '';
      if (!results.length) {
        searchResults.append(h('p', { className: 'empty-text', textContent: uiT('bible.noResult') }));
        return;
      }
      results.forEach(r => {
        searchResults.append(h('div', {
          className: 'bible-search-item',
          style: { padding: '8px 6px', borderBottom: '1px solid #eee', cursor: 'pointer' },
          onClick: () => {
            AppState.set('currentBook', r.bookId);
            AppState.set('currentChapter', r.chapter);
            renderBible();
          },
        },
          h('div', { className: 'bible-search-ref', textContent: r.reference, style: { fontWeight: '600', color: '#0a7d4f', marginBottom: '2px' } }),
          h('div', { className: 'bible-search-text', innerHTML: _highlight(r.text, term), style: { fontSize: '14px', lineHeight: '1.6' } }),
        ));
      });
    }, 250);
  });
  const searchRow = h('div', { className: 'bible-search-row' }, searchInput);

  container.append(searchRow, passageEl, searchResults);
}

/* ── 诗歌 / 敬拜界面（专业音乐 App 风格）─────────────────────────── */
async function renderHymns() {
  const container = $('#screen-container');
  empty(container);
  container.append(_loading());

  const hymns = await WorshipService.getAll();
  window.__hymnCache = hymns;
  const favIds = new Set(AppState.get('hymnFavorites'));
  const recentIds = (AppState.get('hymnRecent') || []).map(String);
  const categories = [uiT('hymn.all'), ...Array.from(new Set(hymns.map(x => x.category))).filter(Boolean)];
  let filter = AppState.get('hymnFilter') || uiT('hymn.all');
  let query = '';
  let sort = AppState.get('hymnSort') || 'number';

  /* 搜索栏：默认收缩，点击/聚焦时展开（배치는 "全部诗歌" 행 우측으로 이동） */
  const search = SearchBar({ placeholder: uiT('hymn.searchPlaceholder'), compact: true,
    onInput: (v) => { query = v.trim().toLowerCase(); draw(); } });

  /* 分类（流派）标签 + 排序 */
  const chipRow = h('div', { className: 'cat-chips' });
  categories.forEach(c => {
    const chip = h('button', {
      className: 'cat-chip' + (c === filter ? ' active' : ''), textContent: c,
      onClick: () => {
        filter = c; AppState.set('hymnFilter', c);
        [...chipRow.children].forEach(ch => ch.classList.toggle('active', ch.textContent === c));
        draw();
      }
    });
    chipRow.append(chip);
  });
  const sortSel = h('select', { className: 'sort-select hymn-sort',
    onChange: (e) => { sort = e.target.value; AppState.set('hymnSort', sort); draw(); } },
    h('option', { value: 'number', textContent: uiT('hymn.sort.number') }),
    h('option', { value: 'title', textContent: uiT('hymn.sort.title') }),
    h('option', { value: 'recent', textContent: uiT('hymn.sort.recent') }),
  );
  sortSel.value = sort;

  /* 今日诗歌（英雄卡） */
  const featured = hymns.find(x => favIds.has(x.id)) || hymns[0];
  const hero = featured ? buildHero(featured, hymns) : null;

  /* 我的诗歌 / 最近播放 —— 改为竖向列表（不再横向滑动） */
  const favTracks = hymns.filter(x => favIds.has(x.id));
  const favRow = favTracks.length ? buildVSection(uiT('hymn.fav') + ' ★', favTracks) : null;
  const recentTracks = recentIds.map(id => hymns.find(x => String(x.id) === id)).filter(Boolean);
  const recRow = recentTracks.length ? buildVSection(uiT('hymn.recent'), recentTracks) : null;

  /* 「全部诗歌」区块头部：标题 + 播放全部 + 排序 */
  const playAllBtn = h('button', { className: 'btn-text play-all-btn', textContent: uiT('hymn.playAll'),
    onClick: () => { if (hymns.length) Player.play(hymns[0], hymns, 0); openSheet(); } });
  const listHead = h('div', { className: 'lib-head list-head' },
    h('span', { textContent: uiT('hymn.all') }),
    h('div', { className: 'list-head-actions' }, playAllBtn, sortSel, search));
  const listEl = h('div', { className: 'track-list' });

  empty(container);
  container.append(chipRow);
  if (hero) container.append(hero);
  if (favRow) container.append(favRow);
  if (recRow) container.append(recRow);
  container.append(listHead, listEl);

  function sortList(arr) {
    const a = arr.slice();
    if (sort === 'title') a.sort((x, y) => String(x.title).localeCompare(String(y.title), uiT('hymn.sortLocale')));
    else if (sort === 'recent') {
      const order = recentIds;
      a.sort((x, y) => order.indexOf(String(x.id)) - order.indexOf(String(y.id)));
    } else a.sort((x, y) => (Number(x.number) || 0) - (Number(y.number) || 0));
    return a;
  }
  function matches(t) {
    if (filter !== uiT('hymn.all') && t.category !== filter) return false;
    if (query) {
      const num = String(t.number || '');
      const hay = (t.title + ' ' + (t.subtitle || '') + ' ' + (t.category || '') + ' ' + num + ' ' + (t.lyrics || []).join(' ')).toLowerCase();
      if (!hay.includes(query) && !num.includes(query)) return false;
    }
    return true;
  }
  function draw() {
    empty(listEl);
    const filtered = sortList(hymns.filter(matches));
    if (!filtered.length) {
      listEl.append(h('p', { className: 'empty-text', textContent: uiT('hymn.empty') }));
      return;
    }
    filtered.forEach(t => listEl.append(buildTrack(t, filtered)));
    syncPlaylistUI();
  }
  draw();
}

/* 英雄卡 */
function buildHero(t, queue) {
  const idx = queue.findIndex(x => x.id === t.id);
  const card = h('div', { className: 'hymn-hero', onClick: () => playOrToggle(t, queue, idx) },
    h('div', { className: 'hero-art', textContent: t.number || '♪' },
      h('span', { className: 'hero-play', id: 'hero-play-btn', textContent: '▶' })),
    h('div', { className: 'hero-meta' },
      h('span', { className: 'hero-tag', textContent: uiT('hymn.today') }),
      h('div', { className: 'hero-title', textContent: t.title }),
      h('div', { className: 'hero-sub', textContent: t.subtitle || '' }),
    ),
  );
  return card;
}

/* 竖向资料库区块（我的诗歌 / 最近播放）—— 复用全部诗歌的 track 卡片 */
function buildVSection(label, tracks) {
  if (!tracks || !tracks.length) return null;
  const list = h('div', { className: 'track-list' }, ...tracks.map(t => buildTrack(t, tracks)));
  return h('div', { className: 'lib-block' },
    h('div', { className: 'lib-head' },
      h('span', { textContent: label }),
      h('span', { className: 'lib-count', textContent: tracks.length })),
    list,
  );
}

/* 全部歌曲卡片（菜单 + 下载徽标） */
function buildTrack(t, queue) {
  const isFav = AppState.get('hymnFavorites').includes(t.id);
  const idx = queue.findIndex(x => x.id === t.id);
  const isDl = Player.isDownloaded(String(t.id));
  const card = h('article', { className: 'track', 'data-hymn-id': t.id,
      onClick: () => playOrToggle(t, queue, idx) },
    h('div', { className: 'track-art', textContent: t.number || '♪' },
      h('span', { className: 'track-num', textContent: '#' + (t.number != null ? t.number : '?') }),
      h('button', { className: 'track-play', textContent: '▶',
        onClick: (e) => { e.stopPropagation(); playOrToggle(t, queue, idx); } })),
    h('div', { className: 'track-meta' },
      h('div', { className: 'track-title', textContent: t.title }),
      h('div', { className: 'track-sub', textContent: t.subtitle || '' }),
      h('div', { className: 'track-chips' },
        h('span', { className: 'chip', textContent: t.category || uiT('hymn.defaultCategory') }),
        isDl ? h('span', { className: 'chip dl-chip', textContent: uiT('hymn.offline') }) : null,
      ),
    ),
    h('div', { className: 'track-actions' },
      h('button', { className: 'btn-icon' + (isFav ? ' active' : ''), textContent: isFav ? '⭐' : '☆',
        onClick: (e) => { e.stopPropagation(); AppState.toggleHymnFav(t.id); renderHymns(); } }),
      h('button', { className: 'btn-icon', textContent: '⋮', title: uiT('hymn.menu'),
        onClick: (e) => { e.stopPropagation(); openTrackMenu(t, queue, idx); } }),
    ),
  );
  return card;
}

/* 歌曲右键菜单 */
function openTrackMenu(t, queue, idx) {
  const items = [
    { icon: '⏭', label: uiT('hymn.playNext'), onClick: () => { Player.queueAddNext(t); showToast(uiT('toast.addedQueue')); } },
    { icon: '🎵', label: uiT('hymn.viewLyrics'), onClick: () => { playOrToggle(t, queue, idx); openSheet(); } },
  ];
  showActionSheet(t.title, items);
}


/* 播放/暂停切换辅助 */
function playOrToggle(t, queue, idx) {
  if (Player.isCurrent(t.id)) Player.toggle();
  else Player.play(t, queue, idx);
}

/* 根据当前播放曲目同步列表 UI（实时） */
function syncPlaylistUI() {
  const s = Player.getState();
  $$('.track').forEach(el => {
    const cur = s.current && String(s.current.id) === String(el.dataset.hymnId);
    el.classList.toggle('playing', !!cur);
    const btn = el.querySelector('.track-play');
    if (btn) btn.textContent = (cur && s.isPlaying) ? '⏸' : '▶';
  });
  const heroBtn = $('#hero-play-btn');
  if (heroBtn && s.current) heroBtn.textContent = (s.isPlaying && Player.isCurrent(s.current.id)) ? '⏸' : '▶';
}

/* ── 讲道界面（专业级媒体流）───────────────────────────── */
let _sermonDetail = null;     // 复用的详情浮层
let _sermonUnSub = null;      // Player 取消订阅句柄
let _sermonIO = null;         // 讲道页 IntersectionObserver（防止内存泄漏）

/* ═══════════════════════════════════════════════════════════════
   讲道分类模板框架 — SERMON_CATEGORY_DEFS 为单一扩展点
   扩展方式：向本数组追加一项即可（id 精确匹配；aliases 做包含匹配）。
   accent 取 styles.css 中已定义的 cv-* 颜色名（emerald/brass/ink/cream/rust）。
   ═══════════════════════════════════════════════════════════════ */
const SERMON_CATEGORY_DEFS = [
  { id: '主日讲道', aliases: ['主日'],              label: '主日讲道', icon: '📖', accent: 'brass',   desc: '主日礼拜讲道' },
  { id: '周末三休', aliases: ['周末', '三休'],       label: '周末三休', icon: '☘', accent: 'emerald', desc: '周末三休聚会' },
  { id: 'RT传道学', aliases: ['RT', '传道', '전도'], label: 'RT传道学', icon: '📣', accent: 'rust',    desc: 'RT 传道学训练' },
  { id: '青年',      aliases: ['청년', 'young'],     label: '青年',     icon: '🔥', accent: 'ink',     desc: '青年部讲道' },
  { id: '特别聚会', aliases: ['特别', 'special'],    label: '特别聚会', icon: '✨', accent: 'cream',   desc: '节期与特别聚会' },
];

// 将数据的 category 文本解析为模板定义（未知类别兜底）
function resolveCategoryDef(cat) {
  if (!cat || cat === '未分类') return { id: cat || '未分类', label: cat || '未分类', icon: '✚', accent: 'emerald', desc: '' };
  const hit = SERMON_CATEGORY_DEFS.find(d =>
    d.id === cat || (d.aliases || []).some(a => cat.includes(a) || a.includes(cat)));
  return hit || { id: cat, label: cat, icon: '✚', accent: 'emerald', desc: '' };
}

// 按模板顺序 + 数据出现顺序，产出用于导航的分类列表（已剔除 '全部'）
function buildCategoryList(categories) {
  const known = [];
  const seen = new Set();
  SERMON_CATEGORY_DEFS.forEach(d => {
    if (categories.includes(d.id) || categories.some(c => (d.aliases || []).some(a => c.includes(a)))) {
      known.push(d.id); seen.add(d.id);
    }
  });
  categories.forEach(c => { if (!seen.has(c) && c !== '全部') { known.push(c); seen.add(c); } });
  return known;
}

function _fmtDate(iso) {
  if (!iso) return '';
  const p = iso.split('-');
  return p.length === 3 ? `${p[0]}.${p[1]}.${p[2]}` : iso;
}
// NOTE: showToast 在 player.js 中全局定义（本文件之后加载），
// 因此已移除重复的本地定义以避免覆盖歧义。

function _sermonCoverClass(cover) {
  return 'cv-' + (cover || 'emerald');
}

/* ── 讲道 + 灵修 合并为 “말씀(Word)” 标签 ─────────────────────────────────── */
async function renderWord() {
  const container = $('#screen-container');
  empty(container);
  container.className = 'screen word-screen';
  // 离开 본 탭 시 설교 재생 상태 리스너 정리
  if (_sermonUnSub) { _sermonUnSub.forEach(fn => fn()); _sermonUnSub = null; }
  if (_sermonIO) { _sermonIO.disconnect(); _sermonIO = null; }

  const sub = h('div', { className: 'sub-tabs' });
  const mkSub = (key, label) => h('button', {
    className: 'sub-tab' + (key === 'sermon' ? ' active' : ''),
    'data-sub': key, textContent: label,
    onClick: (e) => {
      sub.querySelectorAll('.sub-tab').forEach(b => b.classList.toggle('active', b === e.currentTarget));
      mount(key);
    },
  });
  sub.append(mkSub('sermon', uiT('sermon.listen')), mkSub('meditation', uiT('meditation.tab')));

  const body = h('div', { className: 'sub-body' });
  container.append(sub, body);

  let cur = null;
  async function mount(key) {
    if (cur === key) return;
    cur = key;
    empty(body);
    if (key === 'sermon') await mountSermon(body);
    else await mountMeditation(body);
  }
  await mount('sermon');
}

/* 讲道内容挂载（말씀 탭 하위） */
async function mountSermon(target) {
  target.append(_loading());
  if (_sermonUnSub) { _sermonUnSub.forEach(fn => fn()); _sermonUnSub = null; }
  if (_sermonIO) { _sermonIO.disconnect(); _sermonIO = null; }

  const _allCat = uiT('sermon.all');
  const filter = AppState.get('sermonFilter') || { q: '', category: _allCat, series: _allCat, sort: 'recent' };
  if (!filter.category) filter.category = _allCat;

  /* ── 数据 ── */
  const [all, hlList, rawCats] = await Promise.all([
    SermonService.getAll(),
    SermonService.getHighlights(8),
    SermonService.getCategories(),
  ]);

  if (!all.length) {
    empty(target);
    target.append(h('p', { className: 'empty-text', textContent: uiT('sermon.empty') }));
    return;
  }

  const catList = buildCategoryList(rawCats);

  // 分类导航
  const nav = h('div', { className: 'cat-nav', id: 'sermon-catnav' });
  function mkChip(key, label, icon) {
    const chip = h('button', {
      className: 'cat-chip' + (key === filter.category ? ' active' : ''),
      'data-key': key,
      onClick: () => selectCategory(key),
    });
    if (icon) chip.append(h('span', { className: 'cat-ico', textContent: icon }));
    chip.append(h('span', { textContent: label }));
    return chip;
  }
  nav.append(mkChip(_allCat, _allCat, ''));
  catList.forEach(c => {
    const def = resolveCategoryDef(c);
    nav.append(mkChip(c, def.label, def.icon));
  });

  // 搜索
  const search = h('div', { className: 'search-wrap cat-search' },
    h('span', { className: 'search-ico', textContent: '🔍' }),
    h('input', {
      className: 'search-input', type: 'search', placeholder: uiT('sermon.searchPlaceholder'),
      value: filter.q,
      onInput: (e) => { filter.q = e.target.value; AppState.set('sermonFilter', filter); renderContent(); },
    }),
  );

  const content = h('div', { className: 'sermon-content', id: 'sermon-content' });

  empty(target);
  target.append(nav, search, content);

  /* ── 选中分类切换 ── */
  function selectCategory(key) {
    filter.category = key; AppState.set('sermonFilter', filter);
    nav.querySelectorAll('.cat-chip').forEach(b => b.classList.toggle('active', b.getAttribute('data-key') === key));
    if (content.scrollIntoView) content.scrollIntoView({ behavior: 'smooth', block: 'start' });
    renderContent();
  }

  /* ── 区块 / 卡片 ── */
  function sectionHead(catKey, count) {
    const def = resolveCategoryDef(catKey);
    return h('div', { className: 'cat-section-head' },
      h('div', { className: 'cat-section-ico cv-' + def.accent, textContent: def.icon }),
      h('div', { className: 'cat-section-titles' },
        h('h3', { className: 'section-title', textContent: count != null ? `${def.label} · ${count}篇` : def.label }),
        def.desc ? h('p', { className: 'cat-section-desc', textContent: def.desc }) : null,
      ),
    );
  }
  function buildSection(catKey, items) {
    return h('section', { className: 'cat-section' },
      sectionHead(catKey, items.length),
      h('div', { className: 'sermon-grid' },
        ...items.map((s, i) => _sermonCard(s, all, all.findIndex(x => x.id === s.id)))),
    );
  }

  let _moreVisible = PAGE;

  function renderContent() {
    empty(content);
    const q = (filter.q || '').trim().toLowerCase();
    const matchQ = (s) => !q || (s.title || '').toLowerCase().includes(q) ||
      (s.preacher || '').toLowerCase().includes(q) || (s.scripture || '').toLowerCase().includes(q) ||
      (s.summary || '').toLowerCase().includes(q);

    if (filter.category === '全部') {
      if (hlList.length) {
        const hl = h('section', { className: 'cat-section' },
          h('h3', { className: 'section-title', textContent: uiT('sermon.featured') }),
          h('div', { className: 'hl-row', id: 'sermon-hl' }));
        const row = hl.querySelector('#sermon-hl');
        hlList.forEach(s => row.append(h('div', {
          className: 'hl-card', onClick: () => _openDetail(s, all, all.findIndex(x => x.id === s.id)),
        },
          h('div', { className: 'hl-cover ' + _sermonCoverClass(s.cover) }, h('span', { className: 'hl-glyph', textContent: '✚' })),
          h('div', { className: 'hl-info' },
            h('div', { className: 'hl-title', textContent: s.title }),
            h('div', { className: 'hl-sub', textContent: s.preacher || '' }),
          ),
        )));
        content.append(hl);
      }
      catList.forEach(c => {
        const items = all.filter(s => { const d = resolveCategoryDef(s.category); return d.id === c && matchQ(s); });
        if (!items.length) return;
        const sec = buildSection(c, items.slice(0, 6));
        if (items.length > 6) sec.append(h('button', { className: 'cat-section-more', textContent: uiT('sermon.more'),
          onClick: () => selectCategory(c) }));
        content.append(sec);
      });
    } else {
      let items = all.filter(s => { const d = resolveCategoryDef(s.category); return d.id === filter.category && matchQ(s); });
      if (filter.sort === 'views') items.sort((a, b) => (b.views || 0) - (a.views || 0));
      else if (filter.sort === 'title') items.sort((a, b) => (a.title || '').localeCompare(b.title || '', uiT('sermon.sortLocale')));
      else items.sort((a, b) => (b.date || '').localeCompare(a.date || '', uiT('sermon.sortLocale')));
      content.append(sectionHead(filter.category, items.length));
      const grid = h('div', { className: 'sermon-grid' });
      items.slice(0, _moreVisible).forEach((s, i) => grid.append(_sermonCard(s, all, all.findIndex(x => x.id === s.id))));
      content.append(grid);
      if (_moreVisible < items.length) content.append(h('button', { className: 'more-btn', textContent: uiT('sermon.more'),
        onClick: () => { _moreVisible += PAGE; renderContent(); } }));
    }
    _syncCardsAll();
  }

  function _syncCardsAll() {
    const root = $('#sermon-content'); if (!root) return;
    root.querySelectorAll('.sermon-card').forEach(card => {
      const id = card.getAttribute('data-id');
      const btn = card.querySelector('.play-btn'); if (!btn) return;
      const playing = Player.isCurrent(id) && Player.getState().isPlaying;
      btn.textContent = playing ? '⏸' : '▶';
      card.classList.toggle('is-playing', Player.isCurrent(id));
    });
  }

  renderContent();

  _sermonUnSub = [
    Player.on('track', _syncCardsAll),
    Player.on('play', _syncCardsAll),
    Player.on('pause', _syncCardsAll),
  ];
}

/* 讲道卡片构建器 */
function _sermonCard(s, queue, idx) {
  const isFav = AppState.get('sermonFavorites').includes(s.id);
  const cover = h('div', { className: 'sermon-cover ' + _sermonCoverClass(s.cover) },
    h('span', { className: 'cover-glyph', textContent: '✚' }),
    h('span', { className: 'dur-badge', textContent: window.fmtTime ? fmtTime(s.duration) : (Math.floor((s.duration||0)/60) + '分钟') }),
    s.featured ? h('span', { className: 'feat-ribbon', textContent: 'FEATURED' }) : null,
  );
  const body = h('div', { className: 'card-body' },
    h('span', { className: 'card-cat', textContent: s.category }),
    h('div', { className: 'card-title', textContent: s.title }),
    h('div', { className: 'card-meta', textContent: `${s.preacher || ''} · ${_fmtDate(s.date)}` }),
    s.scripture ? h('span', { className: 'card-scripture', textContent: s.scripture }) : null,
  );
  const actions = h('div', { className: 'card-actions' },
    h('button', {
      className: 'play-btn', textContent: '▶',
      onClick: (e) => { e.stopPropagation(); Player.play(_toTrack(s), queue, idx); openSheet(); },
    }),
    h('button', {
      className: 'fav-btn' + (isFav ? ' active' : ''), textContent: isFav ? '⭐' : '☆',
      onClick: (e) => {
        e.stopPropagation();
        AppState.toggleSermonFav(s.id);
        e.currentTarget.textContent = AppState.get('sermonFavorites').includes(s.id) ? '⭐' : '☆';
        e.currentTarget.classList.toggle('active');
      },
    }),
    h('button', {
      className: 'share-btn', textContent: '↗',
      onClick: (e) => { e.stopPropagation(); _shareSermon(s); },
    }),
  );
  return h('article', {
    className: 'sermon-card', 'data-id': s.id,
    onClick: () => _openDetail(s, queue, idx),
  }, cover, body, actions);
}

/* SermonService 对象 → Player 曲目规范化 */
function _toTrack(s) {
  return {
    id: s.id, title: s.title, subtitle: s.preacher, category: s.category,
    number: '✚', duration: s.duration, stream_url: s.stream_url,
    summary: s.summary, transcript: s.transcript, lyrics: null,
    kind: 'sermon', cover: s.cover,
  };
}

/* 分享 */
function _shareSermon(s) {
  const url = location.origin + location.pathname + '#sermon/' + s.id;
  const text = `[${s.title}] ${s.preacher} · ${s.scripture}`;
  if (typeof EventService !== 'undefined') {
    EventService.share({ type: 'sermon', media_id: s.id, title: s.title });
  }
  if (navigator.share) {
    navigator.share({ title: s.title, text, url }).catch(() => {});
  } else if (navigator.clipboard) {
    navigator.clipboard.writeText(url).then(() => showToast(uiT('toast.linkCopied'))).catch(() => showToast(url));
  } else {
    showToast(url);
  }
}

/* ── 말씀 하이라이트/북마크/메모 액션시트 ─────────────────────────────── */
const _VERSE_COLORS = [
  { key: 'yellow', hex: '#F6E05E' },
  { key: 'green',  hex: '#68D391' },
  { key: 'blue',   hex: '#63B3ED' },
  { key: 'pink',   hex: '#F687B3' },
];
let _verseSheet = null;
function _closeVerseSheet() { if (_verseSheet) hide(_verseSheet); }

function _openVerseSheet(bookId, bookName, chapter, verse, verseText, ann) {
  if (!_verseSheet) {
    _verseSheet = h('div', { id: 'verse-sheet', className: 'verse-sheet hidden' },
      h('div', { className: 'verse-sheet-backdrop', onClick: _closeVerseSheet }),
      h('div', { className: 'verse-sheet-panel' }),
    );
    document.body.append(_verseSheet);
  }
  const panel = _verseSheet.querySelector('.verse-sheet-panel');
  empty(panel);
  const ref = `${bookName} ${chapter}:${verse}`;
  panel.append(h('p', { className: 'verse-sheet-ref', textContent: ref }));
  panel.append(h('p', { className: 'verse-sheet-text', textContent: (verseText || '').slice(0, 80) }));

  const swatchRow = h('div', { className: 'verse-sheet-swatches' });
  _VERSE_COLORS.forEach(c => {
    const active = ann && ann.color === c.key;
    swatchRow.append(h('button', {
      className: 'verse-swatch' + (active ? ' active' : ''),
      style: { background: c.hex },
      title: c.key,
      onClick: () => _applyVerseColor(bookId, chapter, verse, ann, c.key),
    }));
  });
  panel.append(swatchRow);

  const actions = h('div', { className: 'verse-sheet-actions' },
    h('button', { className: 'verse-sheet-btn', textContent: uiT('bible.noteTitle'), onClick: () => _editVerseNote(bookId, chapter, verse, ann) }),
    h('button', { className: 'verse-sheet-btn', textContent: uiT('bible.card'), onClick: () => { _closeVerseSheet(); _shareVerseCard(ref, verseText || ''); } }),
    ann ? h('button', { className: 'verse-sheet-btn danger', textContent: uiT('common.delete'), onClick: () => _removeVerseAnnotation(ann, bookId, chapter, verse) }) : null,
  );
  panel.append(actions);
  show(_verseSheet);
}

function _applyVerseColor(bookId, chapter, verse, ann, colorKey) {
  const current = ann && ann.color;
  const next = (current === colorKey) ? null : colorKey;
  const note = ann && ann.note;
  const existed = !!ann;
  AppState.upsertAnnotation(bookId, chapter, verse, next, note);
  if (typeof EventService !== 'undefined') {
    EventService.annotate(existed ? 'verse_annotation_update' : 'verse_annotation_create',
      { book: bookId, chapter: chapter, verse: verse, kind: 'highlight', color: next });
  }
  _syncAnnotationUpsert(bookId, chapter, verse, next, note);
  _closeVerseSheet();
  renderBible();
}

/* 커스텀 메모 다이얼로그 (window.prompt 대체 — WebView 호환) */
let _noteDialog = null;
function _closeNoteDialog() { if (_noteDialog) hide(_noteDialog); }
function _openNoteDialog(bookId, chapter, verse, ann) {
  if (!_noteDialog) {
    _noteDialog = h('div', { id: 'note-dialog', className: 'verse-sheet hidden' },
      h('div', { className: 'verse-sheet-backdrop', onClick: _closeNoteDialog }),
      h('div', { className: 'verse-sheet-panel' }),
    );
    document.body.append(_noteDialog);
  }
  const panel = _noteDialog.querySelector('.verse-sheet-panel');
  empty(panel);
  panel.append(h('p', { className: 'verse-sheet-ref', textContent: uiT('bible.noteTitle') }));
  const ta = h('textarea', { className: 'note-textarea', placeholder: uiT('bible.notePlaceholder') });
  ta.value = (ann && ann.note) || '';
  const btnRow = h('div', { className: 'verse-sheet-actions' },
    h('button', { className: 'verse-sheet-btn', textContent: uiT('bible.noteCancel'), onClick: _closeNoteDialog }),
    h('button', {
      className: 'verse-sheet-btn', textContent: uiT('bible.noteSave'),
      onClick: () => {
        const color = ann && ann.color;
        const trimmed = (ta.value || '').trim();
        AppState.upsertAnnotation(bookId, chapter, verse, color, trimmed);
        if (typeof EventService !== 'undefined') {
          EventService.annotate(ann ? 'verse_annotation_update' : 'verse_annotation_create',
            { book: bookId, chapter: chapter, verse: verse, kind: 'note', color: color });
        }
        _syncAnnotationUpsert(bookId, chapter, verse, color, trimmed);
        _closeNoteDialog();
        showToast(uiT('toast.noteSaved'));
        renderBible();
      },
    }),
  );
  panel.append(ta, btnRow);
  show(_noteDialog);
  ta.focus();
}

function _editVerseNote(bookId, chapter, verse, ann) {
  _closeVerseSheet();
  _openNoteDialog(bookId, chapter, verse, ann);
}

function _removeVerseAnnotation(ann, bookId, chapter, verse) {
  AppState.removeAnnotation(ann.id);
  if (typeof EventService !== 'undefined') {
    EventService.annotate('verse_annotation_delete', { book: bookId, chapter: chapter, verse: verse });
  }
  _syncAnnotationDelete(bookId, chapter, verse);
  _closeVerseSheet();
  showToast(uiT('toast.deleted'));
  renderBible();
}

/* 서버 동기화(로그인 사용자, fire-and-forget) */
function _syncAnnotationUpsert(book, chapter, verse, color, note) {
  if (!AppState.get('isLoggedIn')) return;
  AnnotationService.save({ book, chapter, verse, color, note }).catch(() => {});
}
function _syncAnnotationDelete(book, chapter, verse) {
  if (!AppState.get('isLoggedIn')) return;
  AnnotationService.removeByRef(book, chapter, verse).catch(() => {});
}

/* ── 말씀 공유 이미지 카드 (canvas) ─────────────────────────────────── */
function _wrapCanvasText(ctx, text, maxWidth) {
  const chars = [...text];
  const lines = [];
  let line = '';
  for (const ch of chars) {
    const test = line + ch;
    if (ctx.measureText(test).width > maxWidth && line) { lines.push(line); line = ch; }
    else line = test;
  }
  if (line) lines.push(line);
  return lines;
}

function _buildVerseCard(ref, text) {
  const W = 720, H = 900;
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, W, H);
  grad.addColorStop(0, '#143529');
  grad.addColorStop(1, '#0b2018');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, H);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = 'rgba(246,239,226,0.3)';
  ctx.font = '64px sans-serif';
  ctx.fillText('✚', W / 2, 160);
  ctx.fillStyle = '#f6efe2';
  ctx.font = '42px "Noto Sans KR","Apple SD Gothic Neo",sans-serif';
  const lines = _wrapCanvasText(ctx, text, W - 120);
  let y = 320;
  lines.forEach(line => { ctx.fillText(line, W / 2, y); y += 64; });
  ctx.fillStyle = '#d8bd72';
  ctx.font = '30px "Noto Sans KR",sans-serif';
  ctx.fillText('— ' + ref, W / 2, y + 50);
  return canvas;
}

function _downloadDataUrl(url, filename) {
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.append(a); a.click(); a.remove();
}

function _shareVerseCard(ref, text) {
  try {
    const canvas = _buildVerseCard(ref, text);
    const url = canvas.toDataURL('image/png');
    if (typeof EventService !== 'undefined') {
      EventService.share({ type: 'verse_card', ref: ref });
    }
    _downloadDataUrl(url, 'verse-card.png');
    if (navigator.share && navigator.canShare) {
      canvas.toBlob(blob => {
        if (!blob) return;
        const file = new File([blob], 'verse-card.png', { type: 'image/png' });
        if (navigator.canShare({ files: [file] })) {
          navigator.share({ files: [file], title: ref, text }).catch(() => {});
        } else {
          showToast(uiT('toast.cardSaved'));
        }
      });
    } else {
      showToast(uiT('toast.cardSaved'));
    }
  } catch (e) {
    showToast(uiT('toast.cardFail') + e.message);
  }
}

/* 详情浮层 */
function _openDetail(s, queue, idx) {
  if (!_sermonDetail) {
    _sermonDetail = h('div', { id: 'sermon-detail', className: 'sermon-detail hidden' },
      h('div', { className: 'detail-backdrop', onClick: () => _closeDetail() }),
      h('div', { className: 'detail-panel' }),
    );
    document.body.append(_sermonDetail);
  }
  const panel = _sermonDetail.querySelector('.detail-panel');
  empty(panel);

  /* 相关讲道：优先同系列，其次同分类 */
  const allS = queue && queue.length ? queue : (window.__sermonCache || []);
  const related = (queue || []).filter(x => x.id !== s.id && (s.series ? x.series === s.series : x.category === s.category)).slice(0, 8);
  const seriesItems = (queue || []).filter(x => (x.series || uiT('sermon.uncategorized')) === (s.series || uiT('sermon.uncategorized')) && x.id !== s.id);

  const head = h('div', { className: 'detail-head' },
    h('button', { className: 'detail-close', textContent: '✕', onClick: () => _closeDetail() }),
  );
  const hero = h('div', { className: 'detail-hero ' + _sermonCoverClass(s.cover) },
    h('span', { className: 'cover-glyph', textContent: '✚' }),
  );
  const info = h('div', { className: 'detail-info' },
    h('span', { className: 'card-cat', textContent: s.category }),
    h('h2', { className: 'detail-title', textContent: s.title }),
    h('p', { className: 'detail-meta', textContent: `${s.preacher || ''} · ${_fmtDate(s.date)}` }),
    s.scripture ? h('p', { className: 'detail-scripture', textContent: '📖 ' + s.scripture }) : null,
    h('button', {
      className: 'detail-play',
      onClick: () => { Player.play(_toTrack(s), queue, idx); openSheet(); },
    }, h('span', { textContent: '▶' }), h('span', { textContent: uiT('sermon.listen') })),
    h('div', { className: 'share-row' },
      h('button', { className: 'share-pill', textContent: uiT('sermon.copyLink'), onClick: () => _shareSermon(s) }),
      h('button', {
        className: 'share-pill', textContent: AppState.get('sermonFavorites').includes(s.id) ? uiT('sermon.favOn') : uiT('sermon.favOff'),
        onClick: (e) => { AppState.toggleSermonFav(s.id); e.currentTarget.textContent = AppState.get('sermonFavorites').includes(s.id) ? uiT('sermon.favOn') : uiT('sermon.favOff'); e.currentTarget.classList.toggle('active'); },
      }),
    ),
  );
  const summary = h('div', { className: 'detail-summary' },
    h('h4', { textContent: uiT('sermon.summary') }),
    h('p', { textContent: s.summary || uiT('sermon.summaryEmpty') }),
  );

  panel.append(head, hero, info, summary);

  if (seriesItems.length) {
    panel.append(h('div', { className: 'detail-related' },
      h('h4', { textContent: uiT('sermon.seriesOther', { series: s.series || uiT('sermon.uncategorized') }) }),
      h('div', { className: 'related-row' },
        ...seriesItems.map(x => h('div', {
          className: 'related-card',
          onClick: () => { _openDetail(x, queue, queue.findIndex(q => q.id === x.id)); },
        },
          h('div', { className: 'related-cover ' + _sermonCoverClass(x.cover) }, h('span', { textContent: '✚' })),
          h('div', { className: 'related-title', textContent: x.title }),
          h('div', { className: 'related-sub', textContent: _fmtDate(x.date) }),
        )),
      ),
    ));
  } else if (related.length) {
    panel.append(h('div', { className: 'detail-related' },
      h('h4', { textContent: uiT('sermon.related') }),
      h('div', { className: 'related-row' },
        ...related.map(x => h('div', {
          className: 'related-card',
          onClick: () => { _openDetail(x, queue, queue.findIndex(q => q.id === x.id)); },
        },
          h('div', { className: 'related-cover ' + _sermonCoverClass(x.cover) }, h('span', { textContent: '✚' })),
          h('div', { className: 'related-title', textContent: x.title }),
          h('div', { className: 'related-sub', textContent: _fmtDate(x.date) }),
        )),
      ),
    ));
  }

  _sermonDetail.classList.remove('hidden');
  _sermonDetail.style.willChange = 'transform';
  requestAnimationFrame(() => _sermonDetail.classList.add('open'));
}
function _closeDetail() {
  if (!_sermonDetail) return;
  _sermonDetail.classList.remove('open');
  const onEnd = (e) => {
    if (e.target !== _sermonDetail || e.propertyName !== 'transform') return;
    _sermonDetail.style.willChange = 'auto';
    _sermonDetail.removeEventListener('transitionend', onEnd);
  };
  _sermonDetail.addEventListener('transitionend', onEnd);
  setTimeout(() => _sermonDetail.classList.add('hidden'), 280);
}

/* ── 灵修内容挂载（말씀 탭 하위）──────────────────────────── */
async function mountMeditation(target) {
  target.append(_loading());

  const daily = await MeditationService.getDaily();
  const safeDaily = daily || {};
  const dailyCard = h('div', { className: 'daily-card' },
    h('p', { className: 'daily-label', textContent: uiT('meditation.dailyLabel') }),
    h('h3', { className: 'daily-title', textContent: safeDaily.subtitle || '' }),
    h('p', { className: 'daily-verse', textContent: `"${safeDaily.verseText || ''}"` }),
    h('p', { className: 'daily-ref', textContent: `— ${safeDaily.verse || ''}` }),
    h('p', { className: 'daily-body', textContent: safeDaily.body || uiT('meditation.emptyBody') }),
  );

  const cards = (await MeditationService.getCards()) || [];
  const cardList = h('div', { className: 'meditation-list' },
    ...cards.map(c => Card({
      title: c.title, subtitle: `— ${c.verse}`,
      body: c.text, thumbnail: c.thumbnail,
    }))
  );

  empty(target);
  target.append(dailyCard, cardList);
}

/* ── 마이(My) 페이지 ──────────────────────────────────────
   계정 + 설정(테마/글자크기/언어) 을 한곳에 모음. */
async function renderMy() {
  const container = $('#screen-container');
  empty(container);
  container.className = 'screen my-screen';

  /* 계정 (비로그인 시 로그인/등록 버튼 1개만 표시) */
  const account = h('div', { className: 'my-account' });
  _renderMyAccount(account);

  /* 설정 그룹 */
  const settings = h('div', { className: 'my-settings' });

  const displayGroup = h('div', { className: 'my-settings-group' });
  displayGroup.append(h('p', { className: 'my-settings-group__label', textContent: uiT('my.displayFont') }));
  displayGroup.append(_buildThemeSection());
  displayGroup.append(_buildFontSection());
  settings.append(displayGroup);

  /* 성경 기본값 (간체/번체) */
  const bibleGroup = h('div', { className: 'my-settings-group' });
  bibleGroup.append(h('p', { className: 'my-settings-group__label', textContent: uiT('my.bibleSettings') }));
  bibleGroup.append(_buildBibleDefaultSection());
  settings.append(bibleGroup);

  /* 데이터 / 정보 */
  const infoGroup = h('div', { className: 'my-settings-group' });
  infoGroup.append(h('p', { className: 'my-settings-group__label', textContent: uiT('my.dataInfo') }));
  infoGroup.append(_buildDataInfoSection());
  settings.append(infoGroup);

  /* 말씀 메모/하이라이트 */
  const annGroup = h('div', { className: 'my-settings-group' });
  _renderAnnotationSection(annGroup);
  settings.append(annGroup);

  /* 대화 기록 (로그인 시 서버 조회) */
  const histGroup = h('div', { className: 'my-settings-group' });
  settings.append(histGroup);
  _renderHistorySection(histGroup);

  /* 구독 / 멤버십 */
  const subscription = h('div', { className: 'my-subscription' });
  _renderSubscription(subscription);

  container.append(account, subscription, settings);

  _refreshSettingsTheme();  // 토글 상태 동기화
}

/* 말씀 메모/하이라이트 목록 (로컬 영속 + 로그인 시 서버 병합) */
async function _renderAnnotationSection(el) {
  el.append(h('p', { className: 'my-settings-group__label', textContent: uiT('my.annotation') }));
  // 크로스디바이스 복원: 로그인 시 서버 → 로컬 병합(서버 우선)
  if (AppState.get('isLoggedIn')) {
    try {
      const { annotations } = await AnnotationService.list();
      annotations.forEach(a => AppState.upsertAnnotation(a.book, a.chapter, a.verse, a.color, a.note));
    } catch (_) { /* 오프라인/미로그인 시 로컬만 */ }
  }
  const anns = AppState.get('annotations');
  if (!anns.length) {
    el.append(h('p', { className: 'text-muted', textContent: uiT('my.annEmpty') }));
    return;
  }
  anns.slice(0, 50).forEach(a => {
    const row = h('div', { className: 'ann-item' },
      h('p', { className: 'ann-ref', textContent: `${a.book} ${a.chapter}:${a.verse}` }),
      a.note ? h('p', { className: 'ann-note', textContent: a.note }) : null,
    );
    row.addEventListener('click', () => {
      AppState.set('currentBook', a.book);
      AppState.set('currentChapter', a.chapter);
      AppState.set('activeTab', 'bible');
    });
    const del = h('button', { className: 'history-item-del', textContent: '🗑' });
    del.addEventListener('click', (e) => {
      e.stopPropagation();
      AppState.removeAnnotation(a.id);
      _syncAnnotationDelete(a.book, a.chapter, a.verse);
      _renderAnnotationSection(el);
    });
    row.append(del);
    el.append(row);
  });
}

/* 대화 기록 (서버 /mobile/history) */
async function _renderHistorySection(el) {
  el.append(h('p', { className: 'my-settings-group__label', textContent: uiT('my.history') }));
  if (!AppState.get('isLoggedIn')) {
    el.append(h('p', { className: 'text-muted', textContent: uiT('my.historyLogin') }));
    return;
  }
  el.append(h('p', { className: 'text-muted', textContent: uiT('common.loading') }));
  const { history } = await HistoryService.list('', 50);
  empty(el);
  el.append(h('p', { className: 'my-settings-group__label', textContent: uiT('my.history') }));
  if (!history.length) {
    el.append(h('p', { className: 'text-muted', textContent: uiT('my.historyEmpty') }));
    return;
  }
  history.forEach(it => {
    const row = h('div', { className: 'history-item' },
      h('div', { className: 'history-item-main' },
        h('p', { className: 'history-item-q', textContent: (it.question || '').slice(0, 60) }),
        h('p', { className: 'history-item-meta', textContent: _fmtDate(it.created_at) }),
      ),
    );
    row.addEventListener('click', () => _resumeConversation(it));
    const del = h('button', { className: 'history-item-del', textContent: '🗑' });
    del.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!window.confirm(uiT('my.historyDelConfirm'))) return;
      const ok = await HistoryService.remove(it.interaction_id);
      if (ok) { showToast(uiT('toast.deleted')); _renderHistorySection(el); }
      else showToast(uiT('toast.delFail'));
    });
    row.append(del);
    el.append(row);
  });
}

/* 과거 대화 복원 → 채팅 탭으로 이동 */
function _resumeConversation(it) {
  AppState.set('chatMessages', [
    { role: 'user', content: it.question },
    { role: 'assistant', content: it.answer },
  ]);
  AppState.set('activeTab', 'today');
}

/* 구독/멤버십 카드 렌더 */
async function _renderSubscription(el) {
  empty(el);
  const head = h('div', { className: 'my-settings-group' });
  head.append(h('p', { className: 'my-settings-group__label', textContent: uiT('my.membership') }));
  el.append(head);

  if (!AppState.get('isLoggedIn')) {
    const notice = h('div', { className: 'visitor-membership' });
    notice.append(h('div', { className: 'visitor-membership__icon', textContent: '🔒' }));
    notice.append(h('p', {
      className: 'visitor-membership__zh',
      textContent: uiT('my.membershipLogin'),
    }));
    el.append(notice);
    return;
  }

  /* 현재 구독 상태 */
  const user = AppState.get('user') || {};
  const tier = user.subscription_tier || 'free';
  if (tier && tier !== 'free') {
    const exp = user.subscription_expires_at;
    const expStr = exp ? (' · 到期 ' + new Date(exp).toLocaleDateString()) : ' · 永久';
    el.append(h('p', { className: 'sub-status', textContent: uiT('my.memberCurrent') + tier + expStr }));
  }

  /* 플랜 목록 */
  let plans = [];
  try {
    const data = await PaymentService.getPlans();
    plans = data.plans || [];
  } catch (e) {
    el.append(h('p', { className: 'text-muted', textContent: uiT('my.plansLoadFail') }));
    return;
  }

  if (!plans.length) {
    el.append(h('p', { className: 'text-muted', textContent: uiT('my.plansEmpty') }));
    return;
  }

  const grid = h('div', { className: 'plan-grid' });
  plans.forEach((p) => {
    const unit = p.duration_days >= 365 ? uiT('my.year') : uiT('my.month');
    const card = h('div', { className: 'plan-card' },
      h('div', { className: 'plan-name', textContent: p.name }),
      h('div', { className: 'plan-price', textContent: Number(p.amount).toLocaleString() + '원 / ' + unit }),
      h('button', {
        className: 'plan-btn',
        textContent: uiT('my.pay'),
        onclick: () => openPayment(p.plan_id),
      }),
    );
    grid.append(card);
  });
  el.append(grid);
}

/* PortOne 결제 흐름: prepare → SDK 결제 → complete(승급)
   채널 격리: googleplay 빌드에서는 제3자 결제(PortOne) 호출 금지(GP 정책).
   → GP Billing placeholder 로 폴백(현재는 안내만, 실제 GP Billing 연동은 향후). */
async function openPayment(planId) {
  if (!AppState.get('isLoggedIn')) { showToast(uiT('my.loginNeeded')); return; }
  if (window.GOSPEL_PAYMENT_CHANNEL === 'googleplay') {
    showToast(uiT('my.gpNotice'));
    return;
  }
  try {
    showToast(uiT('my.payPrep'));
    const data = await PaymentService.prepare(planId);
    if (!window.PortOne) {
      showToast(uiT('my.payModuleFail'));
      return;
    }
    const result = await window.PortOne.requestPayment({
      paymentId: data.payment_id,
      channelKey: data.channel_key,
      orderName: data.order_name,
      totalAmount: data.total_amount,
      currency: data.currency,
      payMethod: data.pay_method,
      customer: data.customer,
    });
    if (result && result.code) {
      showToast(uiT('my.payFail') + (result.message || result.code));
      return;
    }
    const done = await PaymentService.complete(data.payment_id);
    if (done && done.status === 'paid') {
      const u = AppState.get('user') || {};
      u.subscription_tier = done.tier;
      if (done.expires_at) u.subscription_expires_at = done.expires_at;
      AppState.set('user', u);
      showToast(uiT('my.payDone'));
    } else {
      showToast(uiT('my.payConfirmFail'));
    }
  } catch (e) {
    showToast(uiT('my.payError') + (e.message || e));
  }
  await renderMy();
}

/* 계정 카드 (비로그인: 로그인/등록 버튼 1개 / 로그인: 프로필+로그아웃) */
function _renderMyAccount(el) {
  empty(el);
  if (!AppState.get('isLoggedIn')) {
    el.append(
      h('button', {
        className: 'btn-primary btn-block',
        textContent: uiT('my.loginRegister'),
        onClick: () => { AppState.set('activeTab', 'login'); },
      }),
    );
    return;
  }
  const user = AppState.get('user') || {};
  el.append(
    h('div', { className: 'profile-card' },
      h('div', { className: 'avatar-lg', textContent: (user.name || '?')[0].toUpperCase() }),
      h('p', { className: 'text-lg', textContent: user.name }),
      h('p', { className: 'text-muted', textContent: user.email || '' }),
    ),
    h('button', {
      className: 'btn-primary', textContent: uiT('my.logout'),
      onClick: () => { AppState.logout(); _renderMyAccount(el); },
    }),
  );
}

/* 글자 크기 슬라이더 (하드웨어 볼륨키 폴백 + PWA 조절) */
function _buildFontSection() {
  const sec = h('div', { className: 'settings-card' });
  const cur = AppState.get('fontSize');
  const slider = h('input', {
    type: 'range', min: '14', max: '28', step: '2', value: String(cur),
    className: 'bible-vol-slider', 'aria-label': uiT('my.displayFont'),
  });
  const sample = h('p', {
    className: 'font-sample',
    textContent: uiT('my.fontSample'),
    style: { fontSize: cur + 'px' },
  });
  slider.addEventListener('input', (e) => {
    const px = parseInt(e.target.value, 10);
    AppState.setFontSize(px);
    sample.style.fontSize = px + 'px';
  });
  sec.append(slider, sample);
  return sec;
}

/* 성경 버전 기본값 설정 (간체/번체) */
function _buildBibleDefaultSection() {
  const sec = h('div', { className: 'settings-card settings-card--pad' });
  const text = h('div', { className: 'settings-row__text settings-row__text--icon' },
    h('span', { className: 'settings-row__icon', textContent: '📖' }),
    h('div', {},
      h('p', { className: 'settings-row__title', textContent: uiT('my.bibleVersion') }),
      h('p', { className: 'settings-row__sub', textContent: uiT('my.bibleVersionHint') }),
    ),
  );
  const stored = AppState.get('bibleVersion');
  const current = stored || _systemBibleVersion();  // 미지정 → 시스템 언어 기반 버전 표시
  const opts = h('div', { className: 'bible-ver-options' });
  const choices = [
    { code: 'auto', label: uiT('my.bibleAuto') },
    { code: 'simpl', label: uiT('bible.verSimpl') },
    { code: 'trad', label: uiT('bible.verTrad') },
    { code: 'kjv', label: uiT('bible.verKjv') },
  ];
  choices.forEach(c => {
    const b = h('button', {
      className: 'bible-ver-opt' + (c.code === 'auto' ? (!stored ? ' active' : '') : (current === c.code ? ' active' : '')),
      textContent: c.label,
      onClick: () => {
        // auto(시스템 따름) 선택 → null 저장 (localStorage 제거)
        AppState.set('bibleVersion', c.code === 'auto' ? null : c.code);
        opts.querySelectorAll('.bible-ver-opt').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
      },
    });
    opts.append(b);
  });
  sec.append(text, opts);
  return sec;
}

/* 데이터 관리 / 정보 */
function _buildDataInfoSection() {
  const sec = h('div', { className: 'settings-card settings-card--pad' });

  // 캐시 지우기
  const cacheRow = h('div', { className: 'settings-row' });
  cacheRow.append(h('div', { className: 'settings-row__text settings-row__text--icon' },
    h('span', { className: 'settings-row__icon', textContent: '🗑️' }),
    h('div', {},
      h('p', { className: 'settings-row__title', textContent: uiT('my.clearCache') }),
      h('p', { className: 'settings-row__sub', textContent: uiT('my.clearCacheHint') }),
    ),
  ));
  cacheRow.append(h('button', {
    className: 'btn-ghost btn-sm', textContent: uiT('my.clearBtn'),
    onClick: () => {
      try {
        const keys = Object.keys(localStorage).filter(k => !k.startsWith('gospel_user') && k !== 'gospel_uilang');
        keys.forEach(k => localStorage.removeItem(k));
        showToast(uiT('my.clearDone'));
      } catch (e) { showToast(uiT('my.clearFail')); }
    },
  }));
  sec.append(cacheRow);

  // 비밀번호 변경 (로그인 상태에서만)
  if (AppState.get('isLoggedIn')) {
    const pwRow = h('div', { className: 'settings-row' });
    pwRow.append(h('div', { className: 'settings-row__text settings-row__text--icon' },
      h('span', { className: 'settings-row__icon', textContent: '🔑' }),
      h('div', {},
        h('p', { className: 'settings-row__title', textContent: uiT('my.changePassword') }),
        h('p', { className: 'settings-row__sub', textContent: uiT('my.changePasswordHint') }),
      ),
    ));
    pwRow.append(h('button', {
      className: 'btn-ghost btn-sm', textContent: uiT('my.changeBtn'),
      onClick: () => togglePasswordForm(sec),
    }));
    sec.append(pwRow);

    // 세션 관리
    const sessRow = h('div', { className: 'settings-row' });
    sessRow.append(h('div', { className: 'settings-row__text settings-row__text--icon' },
      h('span', { className: 'settings-row__icon', textContent: '📱' }),
      h('div', {},
        h('p', { className: 'settings-row__title', textContent: uiT('my.deviceManagement') }),
        h('p', { className: 'settings-row__sub', textContent: uiT('my.deviceManagementHint') }),
      ),
    ));
    sessRow.append(h('button', {
      className: 'btn-ghost btn-sm', textContent: uiT('my.deviceManageBtn'),
      onClick: () => openSessionsModal(),
    }));
    sec.append(sessRow);
  }

  // 앱 버전
  const versionRow = h('div', { className: 'settings-row' });
  versionRow.append(h('div', { className: 'settings-row__text settings-row__text--icon' },
    h('span', { className: 'settings-row__icon', textContent: 'ℹ️' }),
    h('div', {},
      h('p', { className: 'settings-row__title', textContent: uiT('my.appVersion') }),
      h('p', { className: 'settings-row__sub', textContent: '1.0.0' }),
    ),
  ));
  sec.append(versionRow);

  return sec;
}

/* ── 비밀번호 변경 인라인 폼 (로그인 상태) ─────────────────────── */
function togglePasswordForm(sec) {
  let form = sec.querySelector('.pw-change-form');
  if (form) { form.remove(); return; }
  const err = h('p', { className: 'error-text hidden', id: 'pwChangeError' });
  form = h('div', { className: 'pw-change-form' },
    h('input', { type: 'password', className: 'input', id: 'pwCurrent', placeholder: uiT('my.pwCurrent') }),
    h('input', { type: 'password', className: 'input', id: 'pwNew', placeholder: uiT('my.pwNew') }),
    err,
    h('button', {
      className: 'btn-primary btn-sm', textContent: uiT('my.changeConfirm'),
      onClick: async (e) => {
        const cur = $('#pwCurrent')?.value || '';
        const pw = $('#pwNew')?.value || '';
        if (!cur || !pw) { err.textContent = uiT('auth.needEmailPw'); show(err); return; }
        if (pw.length < 6) { err.textContent = uiT('auth.pwTooShort'); show(err); return; }
        hide(err);
        const btn = e.currentTarget;
        btn.disabled = true; btn.textContent = uiT('common.processing');
        const res = await AuthService.changePassword(cur, pw);
        if (res.ok) {
          err.textContent = uiT('my.pwChanged'); err.className = 'success-text'; show(err);
          $('#pwCurrent').value = ''; $('#pwNew').value = '';
        } else {
          err.textContent = res.error || uiT('auth.fail'); err.className = 'error-text'; show(err);
        }
        btn.disabled = false; btn.textContent = uiT('my.changeConfirm');
      },
    }),
  );
  sec.append(form);
}

/* ── 기기/세션 관리 모달 ───────────────────────────────────────── */
async function openSessionsModal() {
  const res = await AuthService.listSessions();
  if (!res.ok) { showToast(res.error || uiT('auth.fail')); return; }
  const sessions = res.sessions || [];
  const curId = res.current_device_id;

  const overlay = h('div', { className: 'modal-overlay' });
  const panel = h('div', { className: 'settings-modal' });
  panel.append(h('div', { className: 'settings-panel-header' },
    h('div', { className: 'settings-panel-header__inner' },
      h('span', { className: 'settings-panel-header__icon', textContent: '📱' }),
      h('div', { className: 'settings-panel-header__text' },
        h('h3', { textContent: uiT('my.deviceManagement') }),
        h('p', { className: 'settings-panel-header__sub', textContent: uiT('my.deviceManagementHint') }),
      ),
    ),
    h('button', { className: 'btn-icon settings-close', textContent: '✕', onClick: () => overlay.remove() }),
  ));
  const body = h('div', { className: 'settings-body' });
  if (!sessions.length) {
    body.append(h('p', { className: 'settings-empty', textContent: uiT('my.noDevices') }));
  } else {
    sessions.forEach(sess => {
      const isCurrent = sess.device_id === curId;
      const row = h('div', { className: 'session-row' },
        h('span', { className: 'session-row__icon', textContent: isCurrent ? '📌' : '📱' }),
        h('div', { className: 'session-row__info' },
          h('p', { className: 'session-row__name', textContent: sess.device_name || 'Web' }),
          h('p', { className: 'session-row__meta', textContent: (isCurrent ? uiT('my.currentDevice') + ' · ' : '') + uiT('my.lastSeen') + ': ' + fmtTime(sess.last_seen) }),
        ),
        isCurrent ? null : h('button', {
          className: 'btn-ghost btn-sm session-row__logout', textContent: uiT('my.logoutBtn'),
          onClick: async (e) => {
            const btn = e.currentTarget;
            btn.disabled = true;
            const res2 = await AuthService.revokeSession(sess.device_id);
            if (res2.ok) { overlay.remove(); openSessionsModal(); }
            else { showToast(res2.error || uiT('auth.fail')); btn.disabled = false; }
          },
        }),
      );
      body.append(row);
    });
  }
  panel.append(body);
  overlay.append(panel);
  document.body.append(overlay);
}

function fmtTime(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffMin = Math.floor((now - d) / 60000);
  if (diffMin < 1) return uiT('my.justNow');
  if (diffMin < 60) return diffMin + uiT('my.minAgo');
  return d.toLocaleDateString(_uiLang() === 'ko' ? 'ko-KR' : (_uiLang().startsWith('zh') ? 'zh-CN' : 'en-US'));
}

/* ── 聊天界面 ───────────────────────────────────────────────── */
/* ── Chat UI builder (reused by renderChat & renderToday) ── */
function buildChatSection() {
  const chatEl = h('div', { className: 'chat-container' });

  /* 欢迎卡片：没有历史消息时显示，代替大面积空白 */
  const suggestedWrap = h('div', { className: 'chat-suggested-wrap' });
  uiT('chat.suggested').forEach(q => {
    suggestedWrap.append(h('button', {
      className: 'chat-suggested-chip',
      textContent: q,
      onClick: () => {
        const input = $('#chatInput');
        if (input) { input.value = q; sendMessage(); }
      },
    }));
  });

  const welcomeCard = h('div', { className: 'chat-welcome' },
    h('div', { className: 'chat-welcome-icon' }, svgIcon('chat', 28)),
    h('p', { className: 'chat-welcome-title', textContent: uiT('chat.title') }),
    h('p', { className: 'chat-welcome-text', textContent: uiT('chat.greeting') }),
    h('p', { className: 'chat-suggested-title', textContent: uiT('chat.suggestedTitle') }),
    suggestedWrap,
    h('p', { className: 'chat-privacy-note', textContent: uiT('chat.privacyNote') }),
  );

  const inputRow = h('div', { className: 'chat-input-row' },
    h('textarea', {
      className: 'chat-input', placeholder: uiT('chat.placeholder'), rows: 1, id: 'chatInput',
      onInput: (e) => {
        // U-4: 自动调整高度（最大 104px）
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(e.target.scrollHeight, 104) + 'px';
      },
      onKeyDown: (e) => {
        // S-3: 回车发送，Shift+回车换行（输入法组合过程中忽略）
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          sendMessage();
        }
      },
    }),
    h('button', {
      className: 'btn-send', 'aria-label': uiT('chat.send'), onClick: sendMessage,
    }, svgIcon('send', 20)),
  );

  function setWelcomeVisible(show) {
    if (welcomeCard) welcomeCard.classList.toggle('hidden', !show);
  }

  // 还原历史对话 — 切换标签页后也保留记录
  const prevMessages = AppState.get('chatMessages') || [];
  if (prevMessages.length > 0) {
    prevMessages.forEach(m => addMessage(m.role, m.content));
    // S-7: 返回标签页后将滚动位置恢复到最新消息
    requestAnimationFrame(() => { chatEl.scrollTop = chatEl.scrollHeight; });
  } else {
    chatEl.append(welcomeCard);
  }

  async function sendMessage() {
    const input = $('#chatInput');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.style.height = 'auto';

    const sendBtn = $('.btn-send');
    if (sendBtn) { sendBtn.disabled = true; sendBtn.classList.add('is-sending'); }

    setWelcomeVisible(false);

    // history 只需传入“当前消息之外”的先前轮次。
    // 后端会把 req.history 扩展到 messages，再单独附加当前 query，
    // 若把当前消息放入 history，会导致问题被重复送入 LLM（重复 bug，见 P6-12）。
    const history = AppState.get('chatMessages') || [];
    addMessage('user', text);
    AppState.set('chatMessages', [...history, { role: 'user', content: text }]);

    // ⚡ OPT-SPEED: 预先创建空回复气泡，流式 token 到达时实时填充。
    // （nvidia 实测 TTFT 0.48s → 约 0.5 秒后开始逐字输入，体感等待大幅缩短）
    const emptyMsg = addMessage('assistant', '');
    const bubbleP = emptyMsg.querySelector('.chat-bubble p');

    const response = await ChatService.send(
      text, history, AppState.get('targetLang') || 'auto',
      (c) => { if (bubbleP) { bubbleP.textContent = c; chatEl.scrollTop = chatEl.scrollHeight; } }
    );

    if (response.quotaExceeded) {
      // 移除空气泡后，在聊天中显示友好提示
      if (emptyMsg && emptyMsg.parentNode) emptyMsg.parentNode.removeChild(emptyMsg);
      const quotaMsg = addMessage(response.role, response.content);
      // 不自动弹出登录窗口，而是在提示气泡内附加“登录”按钮，
      // 引导用户主动点击打开（登录后即可使用）。
      if (response.loginRequired) {
        const bubble = quotaMsg.querySelector('.chat-bubble');
        if (bubble) {
          bubble.append(h('button', {
            className: 'btn-login-prompt',
            textContent: uiT('auth.continueLogin'),
            onClick: () => AppState.set('activeTab', 'mypage'),
          }));
        }
      }
      AppState.set('chatMessages', [
        ...history,
        { role: 'user', content: text },
        { role: response.role, content: response.content },
      ]);
    } else if (!response.content) {
      // 修复 BUG-08: 回复失败时，从 chatMessages 回滚刚添加的用户消息。
      if (emptyMsg && emptyMsg.parentNode) emptyMsg.parentNode.removeChild(emptyMsg);
      AppState.set('chatMessages', history);
      addMessage('assistant', '抱歉，未能生成回复。请稍后再试。');
    } else {
      // 成功：空气泡已承载流式内容 → 最终保留
      AppState.set('chatMessages', [
        ...history,
        { role: 'user', content: text },
        { role: response.role, content: response.content },
      ]);
    }

    if (sendBtn) { sendBtn.disabled = false; sendBtn.classList.remove('is-sending'); }
  }

  function addThinking() {
    const bubble = h('div', { className: 'chat-bubble thinking' },
      h('div', { className: 'thinking-dots' }, h('span'), h('span'), h('span')),
    );
    const msg = h('div', { className: 'chat-message assistant' }, bubble);
    chatEl.append(msg);
    chatEl.scrollTop = chatEl.scrollHeight;
    return msg;
  }

  function removeThinking(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  async function typeOut(el, text) {
    const graphemes = (typeof Intl !== 'undefined' && Intl.Segmenter)
      ? Array.from(new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(text)).map(s => s.segment)
      : Array.from(text);
    el.textContent = '';
    const total = graphemes.length;
    if (total === 0) return;
    const step = total > 120 ? 2 : 1;
    const delay = total > 120 ? 16 : 22;
    for (let i = 0; i < total; i += step) {
      el.textContent += graphemes.slice(i, i + step).join('');
      chatEl.scrollTop = chatEl.scrollHeight;
      // eslint-disable-next-line no-await-in-loop
      await new Promise(r => setTimeout(r, delay));
    }
  }

  function addMessage(role, content) {
    setWelcomeVisible(false);
    const msg = h('div', { className: 'chat-message ' + role },
      h('div', { className: 'chat-bubble' }, h('p', { textContent: content })),
    );
    chatEl.append(msg);
    chatEl.scrollTop = chatEl.scrollHeight;
    return msg;
  }

  // 热门问答 클릭 → QA 탭 진입 시 질문 자동 전송
  const pending = AppState.get('pendingQuestion');
  if (pending) {
    AppState.set('pendingQuestion', null);
    const input = $('#chatInput');
    if (input) {
      input.value = pending;
      setTimeout(sendMessage, 30);
    }
  }

  return { chatEl, inputRow };
}

async function renderChat() {
  const container = $('#screen-container');
  empty(container);
  container.className = 'screen chat-screen';

  const header = h('div', { className: 'screen-header' },
    h('div', { className: 'screen-actions' }),
  );

  const { chatEl, inputRow } = buildChatSection();
  container.append(header, chatEl, inputRow);
}

/* ── 登录界面 ───────────────────────────────────────────────── */
async function renderLogin() {
  const container = $('#screen-container');
  empty(container);

  if (AppState.get('isLoggedIn')) {
    const user = AppState.get('user') || {};
    container.append(
      h('div', { className: 'screen-header' },
        h('h2', { textContent: uiT('account.title') }),
        h('div', { className: 'screen-actions' }),
      ),
      h('div', { className: 'profile-card' },
        h('div', { className: 'avatar-lg', textContent: (user.name || '?')[0].toUpperCase() }),
        h('p', { className: 'text-lg', textContent: user.name }),
        h('p', { className: 'text-muted', textContent: user.email }),
      ),
      h('button', {
        className: 'btn-primary', textContent: uiT('my.logout'),
        onClick: () => { AppState.logout(); renderLogin(); }
      }),
    );
    return;
  }

  // authMode: 'login' | 'signup'
  if (!window._authMode) window._authMode = 'login';
  const mode = window._authMode;

  const form = h('div', { className: 'login-form' });

  // 标签切换（登录 / 注册）
  const tabs = h('div', { className: 'auth-tabs' },
    h('button', {
      className: 'auth-tab' + (mode === 'login' ? ' active' : ''),
      textContent: uiT('account.loginBtn'),
      onClick: () => { window._authMode = 'login'; renderLogin(); }
    }),
    h('button', {
      className: 'auth-tab' + (mode === 'signup' ? ' active' : ''),
      textContent: uiT('account.signupBtn'),
      onClick: () => { window._authMode = 'signup'; renderLogin(); }
    }),
  );
  form.append(tabs);

  form.append(
    h('input', { type: 'email', placeholder: uiT('auth.emailPlaceholder'), className: 'input', id: 'loginEmail' }),
    h('input', { type: 'password', placeholder: uiT('auth.passwordPlaceholder2'), className: 'input', id: 'loginPassword' }),
  );

  // 비밀번호 찾기 링크 (로그인 모드에서만 표시)
  if (mode === 'login') {
    form.append(h('button', {
      className: 'auth-forgot-btn',
      textContent: uiT('auth.forgotPassword'),
      onClick: () => renderForgotPassword(),
    }));
  }

  // 이용약관/개인정보 동의 (가입 모드에서만)
  if (mode === 'signup') {
    form.append(
      h('label', { className: 'auth-consent' },
        h('input', { type: 'checkbox', id: 'termsAccepted' }),
        h('span', { textContent: uiT('auth.termsAgree') }),
      ),
      h('label', { className: 'auth-consent' },
        h('input', { type: 'checkbox', id: 'privacyAccepted' }),
        h('span', { textContent: uiT('auth.privacyAgree') }),
      ),
    );
  }

  const errorEl = h('p', { className: 'error-text hidden', id: 'loginError' });
  form.append(errorEl);

  form.append(h('button', {
    className: 'btn-primary',
    textContent: mode === 'login' ? '登录' : '注册',
    onClick: async (event) => {
      const emailEl = $('#loginEmail');
      const pwEl = $('#loginPassword');
      if (!emailEl || !pwEl) return;
      const email = emailEl.value.trim();
      const pw = pwEl.value;
      if (!email || !pw) {
        errorEl.textContent = '请输入邮箱和密码。';
        show(errorEl);
        return;
      }
      // 클라이언트 측 사전 검증 (메일 포맷 + 파스워드 최소 길이)
      // 회원가입/로그인 모두 ID는 이메일이어야 하므로, 형식이 틀리면 해당 메시지 표시
      const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
      if (!emailOk) {
        errorEl.textContent = uiT('auth.invalidEmail');
        show(errorEl);
        return;
      }
      if (mode !== 'login' && pw.length < 6) {
        errorEl.textContent = uiT('auth.pwTooShort');
        show(errorEl);
        return;
      }
      hide(errorEl);
      const btn = event.currentTarget;
      if (btn) {
        btn.textContent = '处理中...';
        btn.disabled = true;
      }

      if (mode === 'signup') {
        const termsEl = $('#termsAccepted');
        const privacyEl = $('#privacyAccepted');
        if (!termsEl || !termsEl.checked || !privacyEl || !privacyEl.checked) {
          errorEl.textContent = uiT('auth.consentRequired');
          show(errorEl);
          return;
        }
      }
      const result = mode === 'login'
        ? await AuthService.login(email, pw)
        : await AuthService.signup(email, pw, undefined, $('#termsAccepted')?.checked, $('#privacyAccepted')?.checked);

      if (result.ok) {
        if (result.email_verification_required) {
          errorEl.textContent = '注册成功！我们已发送邮箱验证链接，请查收邮件。';
          show(errorEl);
          if (btn) { btn.textContent = mode === 'login' ? '登录' : '注册'; btn.disabled = false; }
          return;
        }
        AppState.login(result.user, result.token, result.sub_id);
        // 로그인 성공 후 마이페이지로 이동 (로그인 화면은 별도 탭이라 탭바에 없음)
        AppState.set('activeTab', 'mypage');
      } else {
        // 상태코드 기준으로 i18n 번역 메시지 표시 (백엔드 detail은 한국어 고정이라 그대로 쓰지 않음)
        if (result.code === 401) {
          errorEl.textContent = uiT('auth.wrongPw');
        } else if (result.code === 409) {
          errorEl.textContent = uiT('auth.emailTaken');
        } else {
          errorEl.textContent = result.error || '操作失败。';
        }
        show(errorEl);
        btn.textContent = mode === 'login' ? '登录' : '注册';
        btn.disabled = false;
      }
    }
  }));

  // 分隔线 + Google 登录
  form.append(
    h('div', { className: 'divider' }, h('span', { textContent: uiT('common.or') })),
  );

  // Google 登录按钮
  const googleBtn = h('button', {
    className: 'btn-google',
    onClick: async () => {
      googleBtn.textContent = '正在使用 Google 登录...';
      googleBtn.disabled = true;
      const result = await AuthService.loginWithGoogle();
      if (result.ok) {
        AppState.login(result.user, result.token, result.sub_id);
        // 로그인 성공 후 마이페이지로 이동
        AppState.set('activeTab', 'mypage');
      } else {
        errorEl.textContent = result.error || 'Google 登录失败';
        show(errorEl);
        googleBtn.innerHTML = '<span class="g-logo">G</span> 使用 Google 登录';
        googleBtn.disabled = false;
      }
    }
  });
  googleBtn.innerHTML = '<span class="g-logo">G</span> 使用 Google 登录';
  form.append(googleBtn);

  const loginHeader = h('div', { className: 'screen-header' },
    h('h2', { textContent: uiT('auth.loginTitle') }),
    h('div', { className: 'screen-actions' },
      // 로그인/회원가입 화면은 별도 탭이라 하단 탭바에 없음 → 뒤로가기(✕) 버튼 제공
      h('button', {
        className: 'btn-close-icon',
        textContent: '✕',
        onClick: () => AppState.set('activeTab', 'mypage'),
      }),
    ),
  );
  container.append(loginHeader, form);
}

/* ── 找回密码（第一步：输入邮箱） ────────────────────────────── */
async function renderForgotPassword() {
  const container = $('#screen-container');
  empty(container);
  container.className = 'screen chat-screen';

  const form = h('div', { className: 'login-form' });
  form.append(
    h('p', { className: 'auth-hint', textContent: uiT('auth.forgotHint') }),
    h('input', { type: 'email', placeholder: uiT('auth.emailPlaceholder'), className: 'input', id: 'forgotEmail' }),
  );
  const errorEl = h('p', { className: 'error-text hidden', id: 'forgotError' });
  form.append(errorEl);

  form.append(h('button', {
    className: 'btn-primary',
    textContent: uiT('auth.forgotTitle'),
    onClick: async (event) => {
      const emailEl = $('#forgotEmail');
      if (!emailEl) return;
      const email = emailEl.value.trim();
      if (!email) {
        errorEl.textContent = uiT('auth.needEmailPw');
        show(errorEl);
        return;
      }
      hide(errorEl);
      const btn = event.currentTarget;
      if (btn) { btn.disabled = true; btn.textContent = uiT('common.processing'); }
      const result = await AuthService.forgotPassword(email, _uiLang());
      if (result.ok) {
        errorEl.textContent = uiT('auth.forgotSent');
        errorEl.className = 'success-text';
        show(errorEl);
      } else {
        errorEl.textContent = result.error || uiT('auth.fail');
        errorEl.className = 'error-text';
        show(errorEl);
      }
      if (btn) { btn.disabled = false; btn.textContent = uiT('auth.forgotTitle'); }
    },
  }));

  form.append(h('button', {
    className: 'auth-back-btn',
    textContent: uiT('auth.backToLogin'),
    onClick: () => { window._authMode = 'login'; renderLogin(); },
  }));

  const header = h('div', { className: 'screen-header' },
    h('h2', { textContent: uiT('auth.forgotTitle') }),
    h('div', { className: 'screen-actions' }),
  );
  container.append(header, form);
}

/* ── 找回密码（第二步：输入令牌 + 新密码） ────────────────────── */
async function renderResetPassword() {
  const container = $('#screen-container');
  empty(container);
  container.className = 'screen chat-screen';

  const form = h('div', { className: 'login-form' });
  form.append(
    h('p', { className: 'auth-hint', textContent: uiT('auth.resetHint') }),
    h('input', { type: 'text', placeholder: 'Token', className: 'input', id: 'resetToken' }),
    h('input', { type: 'password', placeholder: uiT('auth.passwordPlaceholder2'), className: 'input', id: 'resetPassword' }),
  );
  const errorEl = h('p', { className: 'error-text hidden', id: 'resetError' });
  form.append(errorEl);

  form.append(h('button', {
    className: 'btn-primary',
    textContent: uiT('auth.resetTitle'),
    onClick: async (event) => {
      const tokenEl = $('#resetToken');
      const pwEl = $('#resetPassword');
      if (!tokenEl || !pwEl) return;
      const token = tokenEl.value.trim();
      const pw = pwEl.value;
      if (!token || !pw) {
        errorEl.textContent = uiT('auth.needEmailPw');
        show(errorEl);
        return;
      }
      hide(errorEl);
      const btn = event.currentTarget;
      if (btn) { btn.disabled = true; btn.textContent = uiT('common.processing'); }
      const result = await AuthService.resetPassword(token, pw, _uiLang());
      if (result.ok) {
        errorEl.textContent = uiT('auth.resetOk');
        errorEl.className = 'success-text';
        show(errorEl);
      } else {
        errorEl.textContent = result.error || uiT('auth.fail');
        errorEl.className = 'error-text';
        show(errorEl);
      }
      if (btn) { btn.disabled = false; btn.textContent = uiT('auth.resetTitle'); }
    },
  }));

  form.append(h('button', {
    className: 'auth-back-btn',
    textContent: uiT('auth.backToLogin'),
    onClick: () => { window._authMode = 'login'; renderLogin(); },
  }));

  const header = h('div', { className: 'screen-header' },
    h('h2', { textContent: uiT('auth.resetTitle') }),
    h('div', { className: 'screen-actions' }),
  );
  container.append(header, form);
}

/* ═══════════════════════════════════════════════════════════════════════════
   인기 QA — 질문 랭킹 + 광고 배너
   ═══════════════════════════════════════════════════════════════════════════ */
/* ── Top ad banner builder (reused by renderToday) ── */
function buildTopAdBanner(topAd, opts = {}) {
  if (!topAd) return null;
  const clickable = !!topAd.link_url;
  const isTab = clickable && topAd.link_url.startsWith('tab:');
  const banner = h('a', {
    className: 'ad-banner ad-banner-top' + (opts.home ? ' ad-banner-home' : '') + (clickable ? ' is-clickable' : ''),
    href: isTab ? '#' : (topAd.link_url || '#'),
    target: (!clickable || isTab) ? '' : '_blank',
    rel: 'noopener',
    onClick: (e) => {
      if (isTab) { e.preventDefault(); AppState.set('activeTab', topAd.link_url.slice(4)); }
      else if (!clickable) { e.preventDefault(); }
    },
  });
  if (topAd.image_url) {
    banner.append(h('img', {
      className: 'ad-banner-img',
      src: AdService.imageUrl(topAd.id),
      alt: topAd.title,
      loading: 'lazy',
    }));
  }
  const overlay = h('div', { className: 'ad-overlay' });
  overlay.append(
    h('span', { className: 'ad-label', textContent: uiT('ad.label') }),
    h('strong', { className: 'ad-title', textContent: topAd.title }),
    topAd.subtitle ? h('span', { className: 'ad-subtitle', textContent: topAd.subtitle }) : null,
    clickable ? h('span', { className: 'ad-cta' }, '了解更多', svgIcon('arrow', 16)) : null,
  );
  banner.append(overlay);
  return banner;
}

/* ── 성경 폰트: 하드웨어 볼륨키 브리지 ──────────────────────────────────────
   • 실제 폰(APK/Capacitor WebView): 네이티브 MainActivity.onKeyDown 이 볼륨키를
     가로채 window.dispatchEvent(new CustomEvent('volume-key',{detail:{dir}})) 를 호출.
   • 성경 화면에 버튼/슬라이더는 없으며, PWA/브라우저 등 네이티브 브리지가 없는
     환경에서는 「마이」 페이지의 슬라이더로 폰트를 조절한다. */
function enableFontKeyCapture() {
  try { window.Capacitor?.Plugins?.FontKey?.enableCapture?.(); } catch (e) {}
}
function disableFontKeyCapture() {
  try { window.Capacitor?.Plugins?.FontKey?.disableCapture?.(); } catch (e) {}
}

function showFontToast(px) {
  let t = document.getElementById('font-size-toast');
  if (!t) {
    t = h('div', { id: 'font-size-toast', className: 'font-size-toast' });
    document.body.append(t);
  }
  t.textContent = `字体大小 ${px}px`;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 900);
}

window.addEventListener('volume-key', (e) => {
  const dir = e.detail && e.detail.dir;
  if (!dir) return;
  const cur = AppState.get('fontSize');
  const next = Math.min(28, Math.max(14, cur + (dir === 'down' ? -2 : 2)));
  AppState.setFontSize(next);
  document.querySelectorAll('.passage-container').forEach(el => {
    el.style.fontSize = next + 'px';
    el.style.lineHeight = (next * 1.8) + 'px';
  });
  showFontToast(next);
});

/* ── QA ranking list builder (reused by renderToday) ── */
/* 热门问答 클릭 → Today 탭 채팅에 질문 자동 전송 (qa 탭은 오늘(Today)에 통합됨) */
function askQuestion(q) {
  if (!q) return;
  AppState.set('pendingQuestion', q);
  AppState.set('activeTab', 'today');
}

/* Y-2: 인기질문 인사이트(4단계 통찰) 패널 조회 */
async function fetchInsight(snapshotId, targetEl) {
  targetEl.innerHTML = '';
  targetEl.append(h('p', { className: 'empty-text', textContent: uiT('insight.loading') }));
  try {
    const base = API_BASE || '';
    const resp = await fetch(`${base}/insight/${encodeURIComponent(snapshotId)}`); // P0-10: 백엔드 라우트는 /insight/{id} (trending 접두어 없음)
    if (!resp.ok) {
      targetEl.innerHTML = '';
      targetEl.append(h('p', { className: 'empty-text', textContent: uiT('insight.fail') }));
      return;
    }
    const data = await resp.json();
    targetEl.innerHTML = '';
    const sections = [
      ['근본 원인', data.root_cause],
      ['AI 진단', data.ai_diagnosis],
      ['이 답변이 좋은 이유', data.best_answer_why],
      ['되돌아볼 질문', data.reflection_prompt],
    ];
    sections.forEach(([title, body]) => {
      if (body) {
        targetEl.append(h('div', { className: 'qa-insight-block' },
          h('strong', { textContent: title }),
          h('p', { textContent: body }),
        ));
      }
    });
    if (data.pending_question) {
      const sendBtn = h('button', {
        className: 'qa-chat-btn',
        textContent: uiT('chat.sendToChat'),
        onClick: () => askQuestion(data.pending_question),
      });
      targetEl.append(sendBtn);
    }
  } catch (e) {
    targetEl.innerHTML = '';
    targetEl.append(h('p', { className: 'empty-text', textContent: uiT('insight.error') }));
  }
}

function buildQARankingList(ranking, feedAds) {
  const rankList = h('ol', { className: 'qa-rank-list' });

  ranking.forEach((item, idx) => {
    const rankItem = h('li', { className: 'qa-rank-item' });

    const rankBadge = h('span', {
      className: 'qa-rank-badge' + (idx < 3 ? ' rank-' + (idx + 1) : ''),
      textContent: String(idx + 1),
    });

    const q = item.question || item.question_text || '';
    const cnt = item.answer_count || item.answers || item.total || item.count || 0;
    const qText = h('span', { className: 'qa-question', textContent: q || '(暂无问题)' });
    const qMeta = h('span', { className: 'qa-meta' },
      svgIcon('chat', 14),
      h('span', { textContent: cnt > 0 ? uiT('rank.answerCount').replace('{n}', String(cnt)) : (item.category || uiT('rank.categoryFallback')) }),
    );

    const snapshotId = item.snapshot_id || '';
    const chatBtn = h('button', {
      className: 'qa-chat-btn',
      title: uiT('chat.sendToChatTitle'),
      onClick: (e) => { e.stopPropagation(); askQuestion(q); },
    }, svgIcon('chat', 14));

    rankItem.append(rankBadge, qText, qMeta, chatBtn);

    // Y-2: 인사이트 패널 (has_detail 항목만). Y-4: 채팅 버튼은 askQuestion 호출.
    if (snapshotId && item.has_detail) {
      rankItem.classList.add('qa-has-detail');
      const detail = h('div', { className: 'qa-insight' });
      detail.style.display = 'none';
      let loaded = false;
      rankItem.addEventListener('click', (e) => {
        if (e.target === chatBtn) return;
        if (detail.style.display === 'none') {
          detail.style.display = 'block';
          if (!loaded) { loaded = true; fetchInsight(snapshotId, detail); }
        } else {
          detail.style.display = 'none';
        }
      });
      rankList.append(rankItem);
      rankList.append(detail);
    } else {
      rankItem.addEventListener('click', () => askQuestion(q));
      rankList.append(rankItem);
    }

    // ── Feed ad insertion: after 5th, 10th, 15th items ──
    const insertPos = [4, 9, 14];
    if (insertPos.includes(idx)) {
      const feedAd = feedAds[Math.min(Math.floor(idx / 5), feedAds.length - 1)];
      if (feedAd) {
        const adCard = h('li', { className: 'ad-inline' },
          h('a', {
            className: 'ad-inline-card',
            href: feedAd.link_url || '#',
            target: feedAd.link_url ? '_blank' : '',
            rel: 'noopener',
            onClick: feedAd.link_url ? null : (e) => e.preventDefault(),
          },
            feedAd.image_url ? h('img', {
              className: 'ad-inline-img',
              src: AdService.imageUrl(feedAd.id),
              alt: feedAd.title,
              loading: 'lazy',
            }) : null,
            h('span', { className: 'ad-label', textContent: 'AD' }),
            h('span', { className: 'ad-inline-title', textContent: feedAd.title }),
            feedAd.subtitle ? h('span', { className: 'ad-inline-sub', textContent: feedAd.subtitle }) : null,
          ),
        );
        rankList.append(adCard);
      }
    }
  });

  return rankList;
}

/* ═══════════════════════════════════════════════════════════════════════════
   Today — 인기 QA(광고+랭킹) + 채팅 합병 탭
   · 상단 배너: today_top 슬롯 광고 (admin 광고관리와 연동)
   · 인기 QA: qa_top/qa_feed 광고 + 랭킹 (admin QA관리 데이터와 동일 백엔드)
   · 채팅: buildChatSection 재사용 (별도 qa 탭은 Today 에 통합됨)
   ═══════════════════════════════════════════════════════════════════════════ */
async function renderToday() {
  const container = $('#screen-container');
  empty(container);
  container.className = 'screen-container today-screen home';

  // Loading placeholder
  const loading = h('div', { className: 'loading-placeholder' },
    h('div', { className: 'spinner' }),
    h('span', { textContent: uiT('home.loading') }),
  );
  container.append(loading);

  const goTab = (id) => AppState.set('activeTab', id);

  try {
    const [adsData, qaData] = await Promise.all([
      AdService.fetchAds(),
      QAService.fetchRanking(20),
    ]);
    const ads = (adsData && adsData.ads) ? adsData.ads : [];
    const ranking = (qaData && qaData.ranking) ? qaData.ranking : [];
    loading.remove();

    // ── Today top ad (today_top 슬롯) → 제일 위로 고정 ──
    const todayTop = ads.filter(a => a.slot === 'today_top');
    const todayBanner = buildTopAdBanner(todayTop[0], { home: true });
    if (todayBanner) container.append(todayBanner);

    // ── Popular QA (top 5) ──
    const topFive = ranking.slice(0, 5);
    const rankWrap = h('div', { className: 'home-ranklist' });
    if (topFive.length === 0) {
      rankWrap.append(h('p', { className: 'empty-text', textContent: uiT('rank.empty') }));
    } else {
      topFive.forEach((item, idx) => {
        const q = item.question || item.question_text || '';
        const cnt = item.answer_count || item.answers || item.total || item.count || 0;
        rankWrap.append(h('button', { className: 'home-rank-item', onClick: () => askQuestion(q) },
          h('span', { className: 'qa-rank-badge' + (idx < 3 ? ' rank-' + (idx + 1) : ''), textContent: String(idx + 1) }),
          h('span', { className: 'home-rank-body' },
            h('span', { className: 'home-rank-q', textContent: q }),
            h('span', { className: 'qa-meta' }, svgIcon('chat', 14), h('span', { textContent: cnt > 0 ? uiT('rank.answerCount').replace('{n}', String(cnt)) : (item.category || uiT('rank.categoryFallback')) })),
          ),
        ));
      });
    }
    container.append(h('section', { className: 'home-section' },
      h('div', { className: 'home-section-head' },
        h('h2', { className: 'home-section-title' }, svgIcon('flame', 18), h('span', { textContent: uiT('rank.title') })),
      ),
      rankWrap,
    ));

    // ── Chat (별도 qa 탭에서 Today 로 통합: 热门问答 클릭 시 질문 자동 전송) ──
    const chat = buildChatSection();
    container.append(h('section', { className: 'home-section qa-chat' },
      chat.chatEl,
      chat.inputRow,
    ));

  } catch (e) {
    loading.remove();
    container.append(h('p', { className: 'empty-text', textContent: uiT('home.fail') }));
  }
}
