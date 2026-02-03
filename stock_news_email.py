# -*- coding: utf-8 -*-
"""
매일 아침 코스피·나스닥 관련 한국어 경제(주식) 뉴스를 수집해 이메일로 발송합니다.
- 실행: python stock_news_email.py
- 예약: GitHub Actions 등
"""

import os
import sys
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote, urlparse
import re
import json

# Windows UTF-8
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

# ===== 설정 (환경 변수 우선) =====
# 수신자: 쉼표로 구분 (예: gourmetlee0324@gmail.com)
_to = os.environ.get("STOCK_NEWS_TO_EMAIL", "gourmetlee0324@gmail.com,grandsaga@naver.com")
TO_EMAILS = [e.strip() for e in _to.split(",") if e.strip()]

# Gmail SMTP (발신자: youngmin060324@gmail.com)
SMTP_HOST = os.environ.get("STOCK_NEWS_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("STOCK_NEWS_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("STOCK_NEWS_SMTP_USER", "")
SMTP_PASS = os.environ.get("STOCK_NEWS_SMTP_PASS", "")   # Gmail 앱 비밀번호 (stock_news_email_bot.ps1에서 설정)

# 한국어 경제·증시 뉴스 RSS
RSS_FEEDS = [
    ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml"),
    ("연합뉴스 마켓+ (증시)", "https://www.yna.co.kr/rss/market.xml"),
    ("연합뉴스 산업", "https://www.yna.co.kr/rss/industry.xml"),
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_ITEMS_PER_FEED = 3

# 오늘의 증시에 표시할 지수 (Yahoo 심볼)
MARKET_INDICES = [
    ("KOSPI", "^KS11"),
    ("KOSDAQ", "^KQ11"),
    ("NASDAQ", "^IXIC"),
]


def fetch_market_summary() -> list:
    """Yahoo Finance chart API(v8)로 주요 지수 시세 조회. 인증 불필요. [{name, price, change, change_pct}, ...]"""
    import urllib.request
    result = []
    for name, symbol in MARKET_INDICES:
        try:
            # v8 chart API는 인증 없이 동작 (quoteSummary는 401 발생)
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=5d" % quote(symbol, safe="")
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            chart = data.get("chart", {}).get("result")
            if not chart:
                continue
            meta = chart[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
            if price is None and chart[0].get("indicators", {}).get("quote"):
                quotes = chart[0]["indicators"]["quote"][0]
                closes = quotes.get("close")
                if closes:
                    price = next((c for c in reversed(closes) if c is not None), None)
                    if prev is None and len(closes) > 1:
                        prev = next((c for c in reversed(closes[:-1]) if c is not None), None)
            if price is None:
                continue
            prev = prev or price
            ch = (price - prev) if prev else 0
            ch_pct = (ch / prev * 100) if prev and prev != 0 else 0
            result.append({
                "name": name,
                "price": round(price, 2),
                "change": round(ch, 2),
                "change_pct": round(ch_pct, 2),
            })
        except Exception as e:
            print("증시 조회 실패 %s: %s" % (symbol, e), file=sys.stderr)
    return result


def fetch_rss(url: str) -> list:
    """RSS URL에서 뉴스 항목 리스트 반환. 실패 시 빈 리스트."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print("RSS 요청 실패 %s: %s" % (url[:60], e), file=sys.stderr)
        return []

    items = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(data)
        # RSS 2.0: channel -> item
        channel = root.find("channel")
        if channel is None:
            channel = root
        for item in channel.findall("item")[:MAX_ITEMS_PER_FEED]:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            source_el = item.find("source")
            title = (title_el.text or "").strip() if title_el is not None else ""
            link = (link_el.text or "").strip() if link_el is not None else ""
            desc = (desc_el.text or "").strip() if desc_el is not None else ""
            pub = (pub_el.text or "").strip() if pub_el is not None else ""
            # 출처: RSS <source> 텍스트 또는 링크 도메인
            source = ""
            if source_el is not None and (source_el.text or "").strip():
                source = (source_el.text or "").strip()
            if not source and link:
                try:
                    netloc = urlparse(link).netloc or ""
                    source = netloc.replace("www.", "") if netloc else "Yahoo Finance"
                except Exception:
                    source = "연합뉴스"
            if not source:
                source = "연합뉴스"
            if title or link:
                items.append({"title": title, "link": link, "description": desc, "pubDate": pub, "source": source})
    except Exception as e:
        print("RSS 파싱 실패: %s" % e, file=sys.stderr)
    return items


def build_html_mail(to_email: str) -> tuple:
    """수집한 뉴스로 HTML 본문과 제목 생성. (subject, html_body) 반환."""
    lines = []
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append("<h2>주식 뉴스 브리핑 (%s)</h2>" % today)
    lines.append("<p>코스피·나스닥 관련 한국어 경제·증시 뉴스입니다.</p>")

    # 오늘의 증시 (최상단)
    market = fetch_market_summary()
    if market:
        lines.append("<h3>오늘의 증시</h3>")
        lines.append("<table style='border-collapse:collapse; margin-bottom:1.2em; font-size:0.95em;'>")
        lines.append("  <tr style='background:#f5f5f5;'>")
        lines.append("    <th style='padding:6px 12px; text-align:left; border:1px solid #ddd;'>지수</th>")
        lines.append("    <th style='padding:6px 12px; text-align:right; border:1px solid #ddd;'>종가</th>")
        lines.append("    <th style='padding:6px 12px; text-align:right; border:1px solid #ddd;'>등락</th>")
        lines.append("  </tr>")
        for m in market:
            ch = m["change"]
            ch_pct = m["change_pct"]
            ch_str = "%+.2f (%+.2f%%)" % (ch, ch_pct) if ch is not None and ch_pct is not None else "-"
            ch_color = "#c00" if ch and ch < 0 else "#08a" if ch and ch > 0 else "#666"
            price_str = "%.2f" % m["price"] if isinstance(m["price"], float) else str(m["price"])
            lines.append("  <tr>")
            lines.append("    <td style='padding:6px 12px; border:1px solid #ddd;'>%s</td>" % m["name"])
            lines.append("    <td style='padding:6px 12px; text-align:right; border:1px solid #ddd;'>%s</td>" % price_str)
            lines.append("    <td style='padding:6px 12px; text-align:right; border:1px solid #ddd; color:%s;'>%s</td>" % (ch_color, ch_str))
            lines.append("  </tr>")
        lines.append("</table>")
        lines.append("<p><small style='color:#666;'>기준: Yahoo Finance (전일 종가 또는 최근 시세)</small></p>")
    else:
        lines.append("<p><em>오늘의 증시 데이터를 불러오지 못했습니다.</em></p>")

    for feed_name, url in RSS_FEEDS:
        items = fetch_rss(url)
        lines.append("<h3>%s</h3>" % feed_name)
        if not items:
            lines.append("<p><em>뉴스를 불러오지 못했습니다.</em></p>")
            continue
        lines.append("<ul style='list-style:none; padding-left:0;'>")
        for n in items:
            title = n["title"].replace("<", "&lt;").replace(">", "&gt;")
            link = n["link"]
            pub = n["pubDate"]
            desc = (n.get("description") or "").strip()
            source = (n.get("source") or "Yahoo Finance").replace("<", "&lt;").replace(">", "&gt;")
            # HTML 태그 제거 후 요약 (길면 200자 제한)
            if desc:
                desc = re.sub(r"<[^>]+>", " ", desc)
                desc = " ".join(desc.split())
                if len(desc) > 200:
                    desc = desc[:197] + "..."
                desc = desc.replace("<", "&lt;").replace(">", "&gt;")
            lines.append("<li style='margin-bottom:1em; padding-bottom:1em; border-bottom:1px solid #eee;'>")
            lines.append('  <strong><a href="%s">%s</a></strong>' % (link, title or "(제목 없음)"))
            if desc:
                lines.append("  <p style='margin:0.35em 0 0.25em 0; font-size:0.9em; color:#444; line-height:1.4;'>%s</p>" % desc)
            if pub:
                lines.append("  <small style='color:#666;'>%s</small>" % pub.replace("<", "&lt;").replace(">", "&gt;"))
            lines.append('  <small style="color:#888;"> · 출처: %s</small>' % source)
            lines.append("</li>")
        lines.append("</ul>")

    lines.append("<hr><p><small>자동 발송 · 뉴스 수집: 연합뉴스 RSS · 각 기사 출처는 항목별로 표기</small></p>")
    html_body = "\n".join(lines)
    subject = "[주식 뉴스] 코스피·증시 한국어 브리핑 %s" % datetime.now().strftime("%Y-%m-%d")
    return subject, html_body


def html_to_plain(html_body: str) -> str:
    """HTML을 제거해 평문으로 변환. 메일 클라이언트가 전체 본문을 접지 않도록 평문 파트 제공."""
    text = re.sub(r"<br\s*/?>", "\n", html_body, flags=re.I)
    text = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r" +", " ", text).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """SMTP로 이메일 발송. 성공 시 True. plain+html multipart로 접힘/잘림 완화."""
    if not SMTP_USER or not SMTP_PASS:
        print("STOCK_NEWS_SMTP_USER, STOCK_NEWS_SMTP_PASS 환경 변수를 설정하세요.", file=sys.stderr)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Importance"] = "high"
    msg["X-Priority"] = "1"
    plain_body = html_to_plain(html_body)
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=ctx)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        print("이메일 발송 완료: %s" % to_email)
        return True
    except Exception as e:
        print("이메일 발송 실패: %s" % e, file=sys.stderr)
        return False


def main():
    subject, html_body = build_html_mail(TO_EMAILS[0] if TO_EMAILS else "")
    ok_all = True
    for to in TO_EMAILS:
        if not send_email(to, subject, html_body):
            ok_all = False
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
