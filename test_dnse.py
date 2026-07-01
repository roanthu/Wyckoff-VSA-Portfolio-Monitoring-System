import os
import hmac
import hashlib
import base64
import datetime
import uuid
import requests
import urllib.parse

def load_env_file():
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

def test_dnse():
    load_env_file()
    api_key = os.environ.get("DNSE_API_KEY", "").strip()
    secret_key = os.environ.get("DNSE_SECRET_KEY", "").strip()
    
    if not api_key or not secret_key:
        print("Missing API key or Secret key in .env")
        return
        
    method = "GET"
    path = "/price/ohlc"
    params = {"symbol": "FPT", "type": "STOCK", "resolution": "1D", "from": "1777740000", "to": "1782924000"}
    query = urllib.parse.urlencode(params)
    full_path = f"{path}?{query}"
    
    aux_date = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    nonce = uuid.uuid4().hex
    
    print("=== TEST 1: CHỮ KÝ CÓ CHỨA QUERY STRING ===")
    signing_string = f"(request-target): get {full_path}\ndate: {aux_date}\nnonce: {nonce}"
    sig = hmac.new(secret_key.encode(), signing_string.encode(), hashlib.sha256).digest()
    encoded = base64.b64encode(sig).decode().replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
    
    headers = {
        "X-API-Key": api_key,
        "Date": aux_date,
        "X-Aux-Date": aux_date,
        "X-Signature": f'Signature keyId="{api_key}",algorithm="hmac-sha256",headers="(request-target) date",signature="{encoded}",nonce="{nonce}"'
    }
    resp = requests.get(f"https://openapi.dnse.com.vn{full_path}", headers=headers)
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}\n")
    
    print("=== TEST 2: CHỮ KÝ KHÔNG CHỨA QUERY STRING ===")
    signing_string2 = f"(request-target): get {path}\ndate: {aux_date}\nnonce: {nonce}"
    sig2 = hmac.new(secret_key.encode(), signing_string2.encode(), hashlib.sha256).digest()
    encoded2 = base64.b64encode(sig2).decode().replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
    
    headers2 = {
        "X-API-Key": api_key,
        "Date": aux_date,
        "X-Aux-Date": aux_date,
        "X-Signature": f'Signature keyId="{api_key}",algorithm="hmac-sha256",headers="(request-target) date",signature="{encoded2}",nonce="{nonce}"'
    }
    resp2 = requests.get(f"https://openapi.dnse.com.vn{path}", params=params, headers=headers2)
    print(f"Status Code: {resp2.status_code}")
    print(f"Response: {resp2.text}\n")
    print("=== TEST 3: CHỮ KÝ SỬ DỤNG x-aux-date THAY VÌ date ===")
    signing_string3 = f"(request-target): get {full_path}\nx-aux-date: {aux_date}\nnonce: {nonce}"
    sig3 = hmac.new(secret_key.encode(), signing_string3.encode(), hashlib.sha256).digest()
    encoded3 = base64.b64encode(sig3).decode().replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
    
    headers3 = {
        "X-API-Key": api_key,
        "Date": aux_date,
        "X-Aux-Date": aux_date,
        "X-Signature": f'Signature keyId="{api_key}",algorithm="hmac-sha256",headers="(request-target) x-aux-date",signature="{encoded3}",nonce="{nonce}"'
    }
    resp3 = requests.get(f"https://openapi.dnse.com.vn{full_path}", headers=headers3)
    print("Đang đồng bộ thời gian với máy chủ DNSE...")
    try:
        tmp_resp = requests.get("https://openapi.dnse.com.vn/")
        server_date_str = tmp_resp.headers.get("Date")
        if server_date_str:
            server_time = datetime.datetime.strptime(server_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=datetime.timezone.utc)
            local_time = datetime.datetime.now(datetime.timezone.utc)
            delta = server_time - local_time
            print(f"Server time: {server_time}, Local time: {local_time}")
            print(f"Độ lệch thời gian: {delta.total_seconds()} giây")
        else:
            delta = datetime.timedelta(seconds=0)
    except Exception as e:
        delta = datetime.timedelta(seconds=0)
        
    aux_date = (datetime.datetime.now(datetime.timezone.utc) + delta).strftime("%a, %d %b %Y %H:%M:%S +0000")
    nonce = uuid.uuid4().hex
    
    print("\n=== TEST 4 (SYNCED TIME): KIỂM TRA LẠI API SNAPSHOT ===")
    snapshot_path = "/price/FPT/trades/latest"
    signing_string4 = f"(request-target): get {snapshot_path}\ndate: {aux_date}\nnonce: {nonce}"
    sig4 = hmac.new(secret_key.encode(), signing_string4.encode(), hashlib.sha256).digest()
    encoded4 = base64.b64encode(sig4).decode().replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
    
    headers4 = {
        "X-API-Key": api_key,
        "Date": aux_date,
        "X-Aux-Date": aux_date,
        "X-Signature": f'Signature keyId="{api_key}",algorithm="hmac-sha256",headers="(request-target) date",signature="{encoded4}",nonce="{nonce}"'
    }
    resp4 = requests.get(f"https://openapi.dnse.com.vn{snapshot_path}", headers=headers4)
    print("\n=== TEST 5: SỬ DỤNG LOWERCASE HEADERS ===")
    headers5 = {
        "x-api-key": api_key,
        "date": aux_date,
        "x-aux-date": aux_date,
        "x-signature": f'Signature keyId="{api_key}",algorithm="hmac-sha256",headers="(request-target) date",signature="{encoded4}",nonce="{nonce}"'
    }
    resp5 = requests.get(f"https://openapi.dnse.com.vn{snapshot_path}", headers=headers5)
    print(f"Status Code: {resp5.status_code}")
    print(f"Response: {resp5.text}\n")
    
    print("=== TEST 6: THỬ DECODE SECRET KEY TỪ BASE64 ===")
    try:
        # Thêm padding để tránh lỗi padding của base64
        padded_secret = secret_key + "=" * ((4 - len(secret_key) % 4) % 4)
        raw_secret_bytes = base64.urlsafe_b64decode(padded_secret)
        sig6 = hmac.new(raw_secret_bytes, signing_string4.encode(), hashlib.sha256).digest()
        encoded6 = base64.b64encode(sig6).decode().replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
        headers6 = {
            "x-api-key": api_key,
            "Date": aux_date,
            "x-signature": f'Signature keyId="{api_key}",algorithm="hmac-sha256",headers="(request-target) date",signature="{encoded6}",nonce="{nonce}"'
        }
        resp6 = requests.get(f"https://openapi.dnse.com.vn{snapshot_path}", headers=headers6)
        print(f"Status Code: {resp6.status_code}")
        print(f"Response: {resp6.text}\n")
    except Exception as e:
        print(f"Lỗi khi decode secret key: {e}\n")

if __name__ == "__main__":
    test_dnse()
