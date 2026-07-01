import os
import datetime
import json
from src.market_api_adapter import create_market_data_provider

def load_env_file():
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

def main():
    load_env_file()
    print("Connecting to DNSE API...")
    provider = create_market_data_provider("dnse")
    
    ticker = "FPT"  # Có thể đổi mã khác tại đây
    now = datetime.datetime.now()
    start = now - datetime.timedelta(days=60) # Lấy dữ liệu 2 tháng gần nhất
    
    print(f"Downloading 1D candles for {ticker}...")
    df = provider.get_daily_history(ticker, lookback_days=60)
    
    if df.empty:
        print("No data.")
        return
        
    # Ép kiểu dữ liệu để đẩy vào thư viện Chart
    chart_data = []
    for index, row in df.iterrows():
        chart_data.append({
            "time": row["time"].strftime("%Y-%m-%d"),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"])
        })
        
    # Tạo mã HTML nhúng thư viện Lightweight Charts (chuẩn TradingView)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Biểu đồ {ticker} - DNSE API</title>
        <script src="https://unpkg.com/lightweight-charts@3.8.0/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            body {{ margin: 0; padding: 20px; font-family: sans-serif; background: #131722; color: #d1d4dc; }}
            h2 {{ text-align: center; font-weight: normal; }}
            #chart {{ width: 100%; height: 600px; border: 1px solid #2B2B43; border-radius: 8px; overflow: hidden; }}
            .footer {{ text-align: center; margin-top: 15px; color: #787b86; }}
        </style>
    </head>
    <body>
        <h2>Biểu đồ Nến Nhật - Mã: <strong style="color: #2962FF">{ticker}</strong> (Nguồn: DNSE OpenAPI)</h2>
        <div id="chart"></div>
        <div class="footer">Hãy đối chiếu biểu đồ này với App EntradeX hoặc FireAnt để kiểm chứng nhé!</div>
        <script>
            const chartData = {json.dumps(chart_data)};
            const chartContainer = document.getElementById('chart');
            const chart = LightweightCharts.createChart(chartContainer, {{
                width: chartContainer.clientWidth,
                height: 600,
                layout: {{
                    background: {{ type: 'solid', color: '#131722' }},
                    textColor: '#d1d4dc',
                }},
                grid: {{
                    vertLines: {{ color: '#2B2B43' }},
                    horzLines: {{ color: '#2B2B43' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                }},
                rightPriceScale: {{
                    borderColor: '#2B2B43',
                }},
                timeScale: {{
                    borderColor: '#2B2B43',
                }},
            }});
            
            const candlestickSeries = chart.addCandlestickSeries({{
                upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
                wickUpColor: '#26a69a', wickDownColor: '#ef5350'
            }});
            
            candlestickSeries.setData(chartData);
            chart.timeScale().fitContent();
        </script>
    </body>
    </html>
    """
    
    # Ghi ra file HTML
    with open("chart.html", "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"Downloaded {len(chart_data)} candles successfully!")
    print("Created chart.html!")

if __name__ == "__main__":
    main()
