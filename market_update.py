"""
Market Update Script
Fetches stock/market data, summarizes with Claude, and emails you the result.

Setup:
  pip install requests anthropic

Required environment variables:
  ANTHROPIC_API_KEY     - from console.anthropic.com
  ALPHA_VANTAGE_KEY     - from alphavantage.co (free tier)
  EMAIL_FROM            - your Gmail address
  EMAIL_TO              - where to send updates (can be same address)
  EMAIL_APP_PASSWORD    - Gmail App Password (not your regular password)

Usage:
  python market_update.py
"""

import os
import json
import time
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────

REQUIRED_VARS = [
    "ANTHROPIC_API_KEY",
    "ALPHA_VANTAGE_KEY",
    "EMAIL_FROM",
    "EMAIL_TO",
    "EMAIL_APP_PASSWORD",
]

missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing:
    print("❌ Missing required environment variables:")
    for v in missing:
        print(f"   - {v}")
    print("\nMake sure all 5 secrets are added in GitHub → Settings → Secrets and variables → Actions")
    raise SystemExit(1)

ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
ALPHA_VANTAGE_KEY  = os.environ["ALPHA_VANTAGE_KEY"]
EMAIL_FROM         = os.environ["EMAIL_FROM"]
EMAIL_TO           = os.environ["EMAIL_TO"]
EMAIL_APP_PASSWORD = os.environ["EMAIL_APP_PASSWORD"]

print(f"✅ All secrets loaded. Sending to: {EMAIL_TO}")

# Stocks/ETFs to track — customize this list
TICKERS = ["SPY", "QQQ", "VIX", "TLT", "GLD", "NVDA"]

# ── Data Fetching ─────────────────────────────────────────────────────────────

def fetch_quote(ticker: str) -> dict:
    """Fetch latest price quote from Alpha Vantage."""
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker,
        "apikey": ALPHA_VANTAGE_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json().get("Global Quote", {})
        if not data:
            return {"ticker": ticker, "error": "No data"}
        return {
            "ticker": ticker,
            "price": data.get("05. price", "N/A"),
            "change": data.get("09. change", "N/A"),
            "change_pct": data.get("10. change percent", "N/A"),
            "volume": data.get("06. volume", "N/A"),
            "high": data.get("03. high", "N/A"),
            "low": data.get("04. low", "N/A"),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def fetch_market_news() -> list[str]:
    """Fetch top market news headlines from Alpha Vantage News Sentiment."""
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "NEWS_SENTIMENT",
        "topics": "financial_markets,economy_macro",
        "limit": 8,
        "apikey": ALPHA_VANTAGE_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        feed = r.json().get("feed", [])
        headlines = []
        for item in feed:
            title = item.get("title", "")
            source = item.get("source", "")
            sentiment = item.get("overall_sentiment_label", "")
            if title:
                headlines.append(f"[{source}] {title} ({sentiment})")
        return headlines
    except Exception as e:
        return [f"Could not fetch news: {e}"]


def fetch_economic_indicators() -> dict:
    """Fetch key economic indicators: Fed funds rate, CPI, unemployment."""
    indicators = {}
    av_functions = {
        "Federal Funds Rate": "FEDERAL_FUNDS_RATE",
        "CPI": "CPI",
        "Unemployment Rate": "UNEMPLOYMENT",
    }
    for label, fn in av_functions.items():
        url = "https://www.alphavantage.co/query"
        params = {"function": fn, "apikey": ALPHA_VANTAGE_KEY}
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json().get("data", [])
            if data:
                latest = data[0]
                indicators[label] = f"{latest.get('value', 'N/A')} (as of {latest.get('date', 'N/A')})"
            else:
                indicators[label] = "N/A"
        except Exception as e:
            indicators[label] = f"Error: {e}"
        time.sleep(12)  # rate limit between indicator calls
    return indicators


# ── Claude Summary ────────────────────────────────────────────────────────────

def generate_summary(quotes: list[dict], news: list[str], econ: dict) -> str:
    """Send raw data to Claude and get a clean market briefing."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    data_payload = {
        "quotes": quotes,
        "news_headlines": news,
        "economic_indicators": econ,
        "timestamp": datetime.now().strftime("%A, %B %d %Y at %I:%M %p ET"),
    }

    prompt = f"""You are a sharp, concise financial analyst. 
    
Here is today's market data:
{json.dumps(data_payload, indent=2)}

Write a clean daily market briefing covering:
1. **Market Snapshot** — summarize the key movers and overall tone (risk-on/risk-off)
2. **Portfolio Watchlist** — note any significant moves, patterns, or alerts in the tickers
3. **Top Stories** — 3-4 sentence synthesis of the most important news themes
4. **Economic Pulse** — brief take on the macro indicators
5. **One Thing to Watch** — one key thing to keep an eye on today

Keep it tight: no fluff, use bullet points where helpful. Use plain language.
Format it nicely for an HTML email (use <h2>, <ul>, <li>, <b>, <p> tags)."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ── Email Sender ──────────────────────────────────────────────────────────────

def send_email(subject: str, html_body: str):
    """Send the briefing as an HTML email via Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print(f"✅ Email sent to {EMAIL_TO}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.now(ZoneInfo("America/New_York"))
    print(f"🏦 Fetching market data at {now.strftime('%H:%M')}...")

    quotes = []
    for ticker in TICKERS:
        quotes.append(fetch_quote(ticker))
        print(f"  fetched {ticker}")
        time.sleep(12)  # Alpha Vantage free tier: 5 calls/min = 12s gap

    print("  fetching news...")
    news = fetch_market_news()
    time.sleep(12)

    print("  fetching economic indicators...")
    econ = fetch_economic_indicators()

    print("🤖 Generating Claude summary...")
    summary  = generate_summary(quotes, news, econ)

    hour_label = now.strftime("%I:%M %p")
    subject  = f"📈 Market Update — {now.strftime('%b %d')} ({hour_label})"

    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 680px; margin: auto; color: #222;">
      <div style="background:#1a1a2e; color:white; padding:16px 24px; border-radius:8px 8px 0 0;">
        <h1 style="margin:0; font-size:20px;">📈 Daily Market Briefing</h1>
        <p style="margin:4px 0 0; opacity:0.7;">{now.strftime("%A, %B %d, %Y · %I:%M %p ET")}</p>
      </div>
      <div style="padding:24px; border:1px solid #eee; border-top:none; border-radius:0 0 8px 8px;">
        {summary}
      </div>
      <p style="font-size:11px; color:#aaa; text-align:center; margin-top:12px;">
        Powered by Claude · Not financial advice
      </p>
    </body></html>
    """

    send_email(subject, html_body)
    print("✅ Done.")


if __name__ == "__main__":
    main()
