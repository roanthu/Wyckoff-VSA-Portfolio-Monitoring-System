import os
os.environ["VNSTOCK_API_KEY"] = "vnstock_0b2be3bd3aad8600ceebf864181b4287"
print("Testing API Key:", os.environ["VNSTOCK_API_KEY"])


from vnstock import Quote
try:
    q = Quote(symbol='TCB')
    df = q.history(length='5b', interval='1D')
    print("API Response successful:")
    print(df.head())
except Exception as e:
    print(f"API Error: {e}")
