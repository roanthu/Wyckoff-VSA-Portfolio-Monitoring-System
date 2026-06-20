"""
API Test Script - Debug TCBS OpenAPI connectivity and authentication
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TCBS_API_KEY")
BASE_URL = os.getenv("TCBS_API_BASE_URL", "https://openapi.tcbs.com.vn")

def print_result(title, success, data):
    status = "✅ SUCCESS" if success else "❌ FAILED"
    print(f"\n{'='*60}")
    print(f"{status}: {title}")
    print(f"{'='*60}")
    print(data)

def test_headers():
    """Test 1: Check headers and API key"""
    print_result(
        "API Configuration",
        True,
        f"API Key: {API_KEY[:20]}{'...' if API_KEY else 'NOT SET'}\n"
        f"Base URL: {BASE_URL}\n"
        f"Headers: {{'Authorization': 'Bearer {API_KEY[:10]}...'}}"
    )

def test_snapshot():
    """Test 2: Get snapshot (price data)"""
    url = f"{BASE_URL}/tartarus/v1/tickerCommons"
    params = {"symbols": "TCB,HPG,SSI"}
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        success = resp.status_code == 200
        data = resp.json() if success else f"Status: {resp.status_code}\n{resp.text}"
        print_result("Snapshot API (tartarus/v1/tickerCommons)", success, data)
        return success
    except Exception as e:
        print_result("Snapshot API", False, str(e))
        return False

def test_history():
    """Test 3: Get trade history"""
    url = f"{BASE_URL}/nyx/v1/intraday/TCB/his/paging"
    params = {"page": 0, "size": 10}
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        success = resp.status_code == 200
        data = resp.json() if success else f"Status: {resp.status_code}\n{resp.text}"
        print_result("History API (nyx/v1/intraday/.../his/paging)", success, data)
        return success
    except Exception as e:
        print_result("History API", False, str(e))
        return False

def test_bsa():
    """Test 4: Get buy-sell aggregates"""
    url = f"{BASE_URL}/nyx/v1/intraday/TCB/bsa-ext"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        success = resp.status_code == 200
        data = resp.json() if success else f"Status: {resp.status_code}\n{resp.text}"
        print_result("BSA API (nyx/v1/intraday/.../bsa-ext)", success, data)
        return success
    except Exception as e:
        print_result("BSA API", False, str(e))
        return False

def test_without_auth():
    """Test 5: Try without authorization (should fail)"""
    url = f"{BASE_URL}/tartarus/v1/tickerCommons"
    params = {"symbols": "TCB"}
    
    try:
        resp = requests.get(url, params=params, timeout=5)
        print_result(
            "No Auth (should be 401)",
            resp.status_code == 401,
            f"Status: {resp.status_code}"
        )
    except Exception as e:
        print_result("No Auth Test", False, str(e))

if __name__ == "__main__":
    print("\n" + "="*60)
    print("TCBS API DEBUG TEST")
    print("="*60)
    
    # Check config
    if not API_KEY:
        print("❌ ERROR: TCBS_API_KEY not set in .env!")
        print("   Please set TCBS_API_KEY in .env file")
        exit(1)
    
    test_headers()
    
    # Run all tests
    results = {
        "Snapshot": test_snapshot(),
        "History": test_history(),
        "BSA": test_bsa(),
    }
    
    test_without_auth()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    passed = sum(results.values())
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == 0:
        print("\n💡 TROUBLESHOOTING:")
        print("1. Check API key: https://oas.tcbs.com.vn/docs")
        print("2. Verify Bearer token format")
        print("3. Check endpoint URLs match your TCBS region")
        print("4. Test with curl:")
        print(f"   curl -H 'Authorization: Bearer {API_KEY}' \\")
        print(f"   '{BASE_URL}/tartarus/v1/tickerCommons?symbols=TCB'")
