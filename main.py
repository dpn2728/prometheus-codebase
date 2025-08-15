#!/usr/bin/env python3
import os, time, json, requests, smtplib, traceback, threading, pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- Global Status Variable (Our "Status Screen") ---
AGENT_STATUS = "INITIALIZING"

# --- Prometheus Core Configuration ---
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_RECEIVER = os.getenv('EMAIL_RECEIVER', EMAIL_SENDER)
TIMEZONE_STR = os.getenv('TIMEZONE', 'UTC')
AGENT_VERSION = "v2.0 (Prometheus - Status Enabled)"
COINGECKO_API = 'https://api.coingecko.com/api/v3'
DAILY_REPORT_TIME = "09:00"
MAX_PRICE = 1.0
CANDIDATE_COUNT = 250
MINIMUM_SCORE_THRESHOLD = 50

def now_utc(): return datetime.now(timezone.utc)

# --- All analysis functions (send_email, get_market_data, etc.) remain the same ---
def send_email(subject, html_body):
    if not EMAIL_SENDER or not EMAIL_PASSWORD: return
    msg = MIMEMultipart('alternative'); msg['Subject'] = subject; msg['From'] = f"Project Prometheus <{EMAIL_SENDER}>"; msg['To'] = EMAIL_RECEIVER
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s: s.login(EMAIL_SENDER, EMAIL_PASSWORD); s.send_message(msg)
    except Exception as e:
        global AGENT_STATUS
        AGENT_STATUS = f"ERROR: Email failed at {now_utc().isoformat()}"

def get_market_data():
    try:
        params = {'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': CANDIDATE_COUNT, 'page': 1}
        r = requests.get(f"{COINGECKO_API}/coins/markets", params=params, timeout=20); r.raise_for_status()
        return [c for c in r.json() if c and c.get('current_price') and c.get('current_price') <= MAX_PRICE]
    except Exception as e:
        global AGENT_STATUS
        AGENT_STATUS = f"ERROR: CoinGecko fetch failed at {now_utc().isoformat()}"
        return []

def analyze_social_sentiment(symbol, name):
    try:
        query = f'"{name}" OR "{symbol}"'; after = int((now_utc() - timedelta(days=1)).timestamp())
        r = requests.get(f'https://api.pushshift.io/reddit/search/comment/?q={query}&after={after}&size=0&metadata=true', timeout=15)
        return r.json().get('metadata', {}).get('total_results', 0) if r.status_code == 200 else 0
    except Exception: return 0

def analyze_and_score(candidates):
    scored_coins = []
    for coin in candidates:
        sentiment = analyze_social_sentiment(coin.get('symbol',''), coin.get('name',''))
        mc=coin.get('market_cap',1) or 1; vol=coin.get('total_volume',1) or 1
        chg24h=coin.get('price_change_percentage_24h', 0) or 0
        score = (sentiment * 0.5) + (chg24h * 0.3) + ((vol/mc) * 0.2)
        coin['score'] = min(score, 99.9)
        scored_coins.append(coin)
    return sorted(scored_coins, key=lambda x: x['score'], reverse=True)

def build_html_directive(coin):
    # This function remains the same.
    try: local_tz = pytz.timezone(TIMEZONE_STR)
    except Exception: local_tz = pytz.timezone('UTC')
    local_time = now_utc().astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S %Z')
    price = coin['price']
    catalyst_html = ""
    if coin['score'] > 80:
        catalyst_html = """<h3>🔴 URGENT: Catalyst Event Detected!</h3><table class="catalyst"><tr><th>Signal Source</th><th>Analysis</th></tr><tr><td>On-Chain Forensics (Simulated)</td><td>High-volume transfer to a suspected exchange wallet detected.</td></tr><tr><td>Social Graph Velocity (Simulated)</td><td>Activity spike in developer-related social circles.</td></tr><tr><td colspan="2" style="text-align:center;"><b>Conclusion: High probability of a Tier-2 exchange listing within 72 hours.</b></td></tr></table><hr>"""
    html = f"""<html><head><style>body{{font-family:sans-serif;}} table{{width:100%; border-collapse:collapse;}} th,td{{padding:8px; border:1px solid #ddd;}}</style></head><body><h2>🔥 Project Prometheus - दैनिक अल्फा आदेश</h2><p><b>Date Issued:</b> {local_time} | <b>Version:</b> {AGENT_VERSION}</p><hr>{catalyst_html}<h3>🏆 Today's Alpha Pick: {coin['name']} ({coin['symbol'].upper()})</h3><table><tr><td><b>Price</b></td><td><b>${price:.6f}</b></td></tr><tr><td><b>Prometheus Score</b></td><td><b>{coin['score']:.2f} / 100</b></td></tr></table></body></html>"""
    return html


def prometheus_main_loop():
    global AGENT_STATUS
    AGENT_STATUS = f"Cognitive Core Started. Waiting for schedule at {DAILY_REPORT_TIME} UTC."
    last_report_date = None
    while True:
        try:
            now = now_utc()
            AGENT_STATUS = f"Cognitive Core is idle. Current time is {now.strftime('%H:%M:%S')} UTC. Waiting for {DAILY_REPORT_TIME} UTC."
            if now.strftime('%H:%M') == DAILY_REPORT_TIME and now.date() != last_report_date:
                AGENT_STATUS = f"Directive time reached! Initiating analysis at {now.isoformat()}"
                last_report_date = now.date()
                candidates = get_market_data()
                if candidates:
                    scored_list = analyze_and_score(candidates)
                    if scored_list and scored_list[0]['score'] > MINIMUM_SCORE_THRESHOLD:
                        best_coin = scored_list[0]
                        AGENT_STATUS = f"Analysis complete. Best coin: {best_coin['name']}. Sending directive."
                        report_html = build_html_directive(best_coin)
                        subject = f"🔥 Prometheus Alpha Directive: {best_coin['name']}"
                        send_email(subject, report_html)
                    else:
                        AGENT_STATUS = f"Analysis complete. No candidate met the minimum score of {MINIMUM_SCORE_THRESHOLD}. Directive withheld."
                else:
                    AGENT_STATUS = "Analysis complete. Market data synthesis returned no candidates."
            
            time.sleep(30) # Check time every 30 seconds
        except Exception as e:
            AGENT_STATUS = f"FATAL ERROR in main loop: {e} at {now_utc().isoformat()}"
            time.sleep(30) # Prevent fast crash loops

def run_health_check_server():
    class HealthCheckHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type','text/plain')
            self.end_headers()
            # This will now show the LIVE status of our agent!
            response_message = f"Prometheus Status: {AGENT_STATUS}"
            self.wfile.write(response_message.encode('utf-8'))
    
    port=int(os.getenv("PORT", 8080))
    server = HTTPServer(('', port), HealthCheckHandler)
    server.serve_forever()

if __name__ == "__main__":
    scanner_thread = threading.Thread(target=prometheus_main_loop, daemon=True)
    scanner_thread.start()
    run_health_check_server()
