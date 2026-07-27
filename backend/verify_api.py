import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_endpoint(name, url):
    print(f"Testing {name} ({url})...", end=" ")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print("✅ 200 OK")
            return True
        else:
            print(f"❌ FAILED with {response.status_code}: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ CRASH: {str(e)}")
        return False

def main():
    print("--- Starting Backend API Verification ---")
    
    success = True
    
    # Test 1: Health Check
    success &= test_endpoint("Health Check", f"{BASE_URL}/health")
    
    # Test 2: Compare Search (Tests insights/compare shared logic)
    success &= test_endpoint("Compare Search (HDFC)", f"{BASE_URL}/compare/search?q=HDFC")
    
    # Test 3: Compare Peers (Tests complex logic and tab_common imports)
    success &= test_endpoint("Compare Peers (120828)", f"{BASE_URL}/compare/peers?ticker=120828")

    print("---------------------------------------")
    if success:
        print("✅ ALL TESTS PASSED! Backend is functionally stable.")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED! Backend has issues.")
        sys.exit(1)

if __name__ == "__main__":
    main()
