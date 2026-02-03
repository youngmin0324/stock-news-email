# 주식 뉴스 이메일 (매일 08:00 KST 자동 발송)

매일 **한국 시간 오전 8시**에 코스피·증시 관련 한국어 뉴스와 오늘의 증시를 이메일로 보냅니다.  
GitHub Actions에서 실행되므로 PC를 켜 두지 않아도 됩니다.

---

## 1. GitHub 저장소 만들기

1. [GitHub](https://github.com) 로그인 후 **New repository** 클릭
2. 저장소 이름 예: `stock-news-email` (원하는 이름 사용 가능)
3. **Create repository** 클릭

---

## 2. 이 폴더를 저장소에 푸시하기

터미널(PowerShell 또는 CMD)에서:

```
cd "c:\Users\Гостевой вход\.cursor\stock-news-email"
git init
git add .
git commit -m "Add stock news email (daily 8am KST)"
git branch -M main
git remote add origin https://github.com/본인아이디/stock-news-email.git
git push -u origin main
```

`본인아이디/stock-news-email` 부분을 방금 만든 저장소 주소로 바꾸세요.

---

## 3. Secrets 설정 (한 번만)

1. GitHub 저장소 페이지에서 **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭 후 아래 5개를 추가:

| Name | Value |
|------|--------|
| STOCK_NEWS_TO_EMAIL | gourmetlee0324@gmail.com,grandsaga@naver.com |
| STOCK_NEWS_SMTP_HOST | smtp.gmail.com |
| STOCK_NEWS_SMTP_PORT | 587 |
| STOCK_NEWS_SMTP_USER | youngmin060324@gmail.com |
| STOCK_NEWS_SMTP_PASS | Gmail 앱 비밀번호 16자리 |

※ Gmail 앱 비밀번호: Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호 생성

---

## 4. 동작 확인

- **자동 실행**: 매일 **한국 시간 08:00**에 워크플로가 실행되어 이메일이 발송됩니다.
- **수동 실행**: 저장소 **Actions** 탭 → **Send Stock News Email** → **Run workflow**

수신자·발신자 변경은 위 Secrets에서 STOCK_NEWS_TO_EMAIL, STOCK_NEWS_SMTP_* 값을 수정하면 됩니다.
