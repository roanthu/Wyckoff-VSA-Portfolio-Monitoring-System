import os
import hmac
import hashlib
import base64
import datetime
import uuid
import http.client
import urllib.parse
from email.utils import formatdate

def load_env_file():
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

def test_raw_http():
    load_env_file()
    api_key = os.environ.get("DNSE_API_KEY", "").strip()
    secret_key = os.environ.get("DNSE_SECRET_KEY", "").strip()
    
    now = datetime.datetime.now(datetime.timezone.utc)
    date_header_dnse = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
    nonce = uuid.uuid4().hex
    
    path = "/price/ohlc"
    params = {"symbol": "FPT", "type": "STOCK", "resolution": "D", "from": "1777740282", "to": "1782924282"}
    query_str = urllib.parse.urlencode(params)
    full_path = f"{path}?{query_str}"
    
    # 1. Sign without query string, Request WITH query string
    signing_string1 = f"(request-target): get {path}\ndate: {date_header_dnse}\nnonce: {nonce}"
    sig1 = hmac.new(secret_key.encode("utf-8"), signing_string1.encode("utf-8"), hashlib.sha256).digest()
    encoded_sig1 = base64.b64encode(sig1).decode("utf-8").replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
    x_signature1 = f'Signature keyId="{api_key}",algorithm="hmac-sha256",headers="(request-target) date",signature="{encoded_sig1}",nonce="{nonce}"'
    
    print(f"=== TEST RECENT DATA ===")
    conn = http.client.HTTPSConnection("openapi.dnse.com.vn")
    headers1 = {"x-api-key": api_key, "Date": date_header_dnse, "X-Signature": x_signature1}
    conn.request("GET", full_path, headers=headers1)
    resp1 = conn.getresponse()
    print(f"Status: {resp1.status} {resp1.reason}")
    print(f"Body: {resp1.read().decode('utf-8')[:200]}\n")
    
    # 2. Sign WITH query string, Request WITH query string
    signing_string2 = f"(request-target): get {full_path}\ndate: {date_header_dnse}\nnonce: {nonce}"
    sig2 = hmac.new(secret_key.encode("utf-8"), signing_string2.encode("utf-8"), hashlib.sha256).digest()
    encoded_sig2 = base64.b64encode(sig2).decode("utf-8").replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
    x_signature2 = f'Signature keyId="{api_key}",algorithm="hmac-sha256",headers="(request-target) date",signature="{encoded_sig2}",nonce="{nonce}"'
    
    print(f"=== TEST 2: Sign {full_path}, Request {full_path} ===")
    conn2 = http.client.HTTPSConnection("openapi.dnse.com.vn")
    headers2 = {"x-api-key": api_key, "Date": date_header_dnse, "X-Signature": x_signature2}
    conn2.request("GET", full_path, headers=headers2)
    resp2 = conn2.getresponse()
    print(f"Status: {resp2.status} {resp2.reason}")
    print(f"Body: {resp2.read().decode('utf-8')[:200]}\n")

if __name__ == "__main__":
    test_raw_http()
