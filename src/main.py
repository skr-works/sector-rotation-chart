import os
import json
import sys
import math
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# ==========================================
# 1. 設定と定数定義
# ==========================================

def load_secrets():
    secrets_json = os.environ.get('WP_SECRETS_JSON')
    if not secrets_json:
        print("Error: WP_SECRETS_JSON environment variable is not set.")
        sys.exit(1)
    try:
        config = json.loads(secrets_json)
        if "GITHUB_PAGES_URL" in config and not config["GITHUB_PAGES_URL"].endswith("/"):
            config["GITHUB_PAGES_URL"] += "/"
        return config
    except json.JSONDecodeError:
        print("Error: Failed to parse WP_SECRETS_JSON.")
        sys.exit(1)

# セクター定義
SECTORS = [
    {"code": "1625.T", "name": "電機・精密", "clock": 10.5, "area": "NW"},
    {"code": "1626.T", "name": "情報通信",   "clock": 11.5, "area": "NW"},
    {"code": "1619.T", "name": "建設・資材", "clock": 9.5,  "area": "NW"},
    {"code": "1622.T", "name": "自動車",     "clock": 1.5,  "area": "NE"},
    {"code": "1624.T", "name": "機械",       "clock": 0.5,  "area": "NE"},
    {"code": "1629.T", "name": "商社・卸売", "clock": 2.5,  "area": "NE"},
    {"code": "1631.T", "name": "銀行",       "clock": 4.5,  "area": "SE"},
    {"code": "1632.T", "name": "金融(除銀)", "clock": 3.5,  "area": "SE"},
    {"code": "1618.T", "name": "エネルギー", "clock": 5.5,  "area": "SE"},
    {"code": "1621.T", "name": "医薬品",     "clock": 7.5,  "area": "SW"},
    {"code": "1617.T", "name": "食品",       "clock": 6.5,  "area": "SW"},
    {"code": "1630.T", "name": "小売",       "clock": 8.5,  "area": "SW"},
]

PHASES = {
    "回復期": {"x_sign": -1, "y_sign": 1},
    "好況期": {"x_sign": 1,  "y_sign": 1},
    "後退期": {"x_sign": 1,  "y_sign": -1},
    "不況期": {"x_sign": -1, "y_sign": -1},
}

# 除外セクターの説明用HTML (テーブルデザイン)
EXCLUSION_HTML = """
<table style="width:100%; border-collapse: collapse; font-size: 0.9em; margin-top: 10px;">
  <tr style="background-color: #f2f2f2;">
    <th style="border: 1px solid #ddd; padding: 8px; text-align: left; width: 30%;">業種</th>
    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">除外理由</th>
  </tr>
  <tr>
    <td style="border: 1px solid #ddd; padding: 8px; font-weight:bold;">鉄鋼・非鉄</td>
    <td style="border: 1px solid #ddd; padding: 8px;">機械・自動車と動きが重複するため。</td>
  </tr>
  <tr>
    <td style="border: 1px solid #ddd; padding: 8px; font-weight:bold;">素材・化学</td>
    <td style="border: 1px solid #ddd; padding: 8px;">要因が複雑で方向感が定まりにくいため。</td>
  </tr>
  <tr>
    <td style="border: 1px solid #ddd; padding: 8px; font-weight:bold;">不動産</td>
    <td style="border: 1px solid #ddd; padding: 8px;">銀行（金利感応）と似ているが変動が激しすぎるため。</td>
  </tr>
  <tr>
    <td style="border: 1px solid #ddd; padding: 8px; font-weight:bold;">運輸・物流</td>
    <td style="border: 1px solid #ddd; padding: 8px;">陸運と海運が混在し、指標として不明瞭なため。</td>
  </tr>
  <tr>
    <td style="border: 1px solid #ddd; padding: 8px; font-weight:bold;">電力・ガス</td>
    <td style="border: 1px solid #ddd; padding: 8px;">今回は値動きの大きい「小売」を優先したため。</td>
  </tr>
</table>
"""

# ==========================================
# 2. 計算ロジック
# ==========================================

def get_market_data():
    tickers = [s["code"] for s in SECTORS]
    print(f"Fetching data for {len(tickers)} sectors...")
    df = yf.download(tickers, period="2y", interval="1d", progress=False)['Close']
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.ffill().bfill()
    last_date = df.index[-1]
    print(f"Latest data date: {last_date.strftime('%Y-%m-%d')}")
    return df

def clock_to_rad(clock_hour):
    degree = 90 - (clock_hour * 30)
    return math.radians(degree)

def calculate_vector(df, target_date):
    data_until = df[df.index <= target_date]
    if len(data_until) < 200:
        return None, None
    current_prices = data_until.iloc[-1]
    ma200 = data_until.iloc[-200:].mean()
    deviations = (current_prices - ma200) / ma200 * 100
    
    total_x = 0
    total_y = 0
    for sector in SECTORS:
        code = sector["code"]
        if code not in deviations: continue
        strength = deviations[code]
        rad = clock_to_rad(sector["clock"])
        x = strength * math.cos(rad)
        y = strength * math.sin(rad)
        total_x += x
        total_y += y
        
    scale_factor = 4.0 
    return total_x / scale_factor, total_y / scale_factor

# ==========================================
# 3. HTML生成 (GitHub Pages用)
# ==========================================

def create_standalone_html(history_points, current_point, last_date_str):
    """
    GitHub Pagesで表示するためのHTML。
    """
    history_json = json.dumps(history_points)
    current_json = json.dumps([current_point])
    
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sector Cycle Chart</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #fff; }}
        .chart-container {{ position: relative; width: 100vw; max-width: 600px; aspect-ratio: 1; }}
        canvas {{ width: 100% !important; height: 100% !important; }}
    </style>
</head>
<body>
    <div class="chart-container">
        <canvas id="sectorCycleChart"></canvas>
    </div>
    <script>
    document.addEventListener("DOMContentLoaded", function() {{
        var ctx = document.getElementById('sectorCycleChart');
        
        // 四隅に表示するセクターリスト
        const sectorLabels = {{
            NW: ["電機・精密", "情報通信", "建設・資材"],
            NE: ["自動車", "機械", "商社・卸売"],
            SE: ["銀行", "金融(除)", "エネルギー"],
            SW: ["医薬品", "食品", "小売"]
        }};

        var bgPlugin = {{
            id: 'bgPlugin',
            beforeDraw: function(chart) {{
                var ctx = chart.ctx;
                var ca = chart.chartArea;
                var x = chart.scales.x;
                var y = chart.scales.y;
                var midX = x.getPixelForValue(0);
                var midY = y.getPixelForValue(0);
                
                ctx.save();
                
                // --- 背景色の描画 ---
                // 北西 (回復): 芽吹き、若草色/シアン系
                ctx.fillStyle = 'rgba(225, 250, 240, 0.5)';
                ctx.fillRect(ca.left, ca.top, midX - ca.left, midY - ca.top);
                
                // 北東 (好況): 過熱、赤/オレンジ系
                ctx.fillStyle = 'rgba(255, 235, 235, 0.5)';
                ctx.fillRect(midX, ca.top, ca.left + ca.width - midX, midY - ca.top);
                
                // 南東 (後退): 警戒、黄色/アンバー系
                ctx.fillStyle = 'rgba(255, 252, 230, 0.5)';
                ctx.fillRect(midX, midY, ca.left + ca.width - midX, ca.top + ca.height - midY);
                
                // 南西 (不況): 冷え込み、青紫/グレー系
                ctx.fillStyle = 'rgba(235, 235, 250, 0.5)';
                ctx.fillRect(ca.left, midY, midX - ca.left, ca.top + ca.height - midY);
                
                // --- 十字線の描画 (少し濃く) ---
                ctx.strokeStyle = 'rgba(0,0,0,0.2)';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(midX, ca.top); ctx.lineTo(midX, ca.bottom);
                ctx.moveTo(ca.left, midY); ctx.lineTo(ca.right, midY);
                ctx.stroke();

                // --- テキスト描画設定 ---
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                
                // エリア名 (中央寄り)
                ctx.font = 'bold 16px sans-serif';
                ctx.fillStyle = 'rgba(0,0,0,0.4)';
                ctx.fillText('回復期', (ca.left + midX)/2, (ca.top + midY)/2);
                ctx.fillText('好況期', (midX + ca.right)/2, (ca.top + midY)/2);
                ctx.fillText('後退期', (midX + ca.right)/2, (midY + ca.bottom)/2);
                ctx.fillText('不況期', (ca.left + midX)/2, (midY + ca.bottom)/2);

                // --- 四隅の業種名描画 ---
                ctx.font = '10px sans-serif';
                ctx.fillStyle = 'rgba(0,0,0,0.5)';
                var pad = 10;
                var lineHeight = 12;

                // NW (左上)
                ctx.textAlign = 'left';
                ctx.textBaseline = 'top';
                sectorLabels.NW.forEach((text, i) => {{
                    ctx.fillText(text, ca.left + pad, ca.top + pad + (i * lineHeight));
                }});

                // NE (右上)
                ctx.textAlign = 'right';
                sectorLabels.NE.forEach((text, i) => {{
                    ctx.fillText(text, ca.right - pad, ca.top + pad + (i * lineHeight));
                }});

                // SE (右下)
                ctx.textAlign = 'right';
                ctx.textBaseline = 'bottom';
                sectorLabels.SE.slice().reverse().forEach((text, i) => {{
                    ctx.fillText(text, ca.right - pad, ca.bottom - pad - (i * lineHeight));
                }});

                // SW (左下)
                ctx.textAlign = 'left';
                ctx.textBaseline = 'bottom';
                sectorLabels.SW.slice().reverse().forEach((text, i) => {{
                    ctx.fillText(text, ca.left + pad, ca.bottom - pad - (i * lineHeight));
                }});

                ctx.restore();
            }}
        }};

        new Chart(ctx, {{
            type: 'scatter',
            data: {{
                datasets: [
                    {{
                        // 軌跡
                        label: '軌跡',
                        data: {history_json},
                        borderWidth: 2,
                        pointRadius: 0,
                        showLine: true,
                        segment: {{
                            borderColor: function(ctx) {{
                                var count = ctx.chart.data.datasets[0].data.length;
                                var val = ctx.p1DataIndex / count;
                                var alpha = 0.1 + (0.9 * val);
                                return 'rgba(80, 80, 80, ' + alpha + ')';
                            }}
                        }},
                        order: 2
                    }},
                    {{
                        // 現在地点
                        label: '現在',
                        data: {current_json},
                        backgroundColor: 'rgba(255, 0, 0, 1)',
                        borderColor: '#fff',
                        borderWidth: 2,
                        pointRadius: 8,
                        pointHoverRadius: 10,
                        order: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ 
                        min: -25, max: 25,
                        grid: {{
                            display: true, // グリッド表示ON
                            color: 'rgba(0, 0, 0, 0.05)', // 薄いグレー
                            drawTicks: false
                        }}, 
                        ticks: {{display: false}} 
                    }},
                    y: {{ 
                        min: -25, max: 25,
                        grid: {{
                            display: true, // グリッド表示ON
                            color: 'rgba(0, 0, 0, 0.05)', // 薄いグレー
                            drawTicks: false
                        }}, 
                        ticks: {{display: false}} 
                    }}
                }},
                plugins: {{ legend: {{display: false}}, tooltip: {{enabled: false}} }}
            }},
            plugins: [bgPlugin]
        }});
    }});
    </script>
</body>
</html>"""
    return html

def generate_wp_content(config, last_date_str, current_phase):
    """WordPress用のHTML (UI改善版)"""
    pages_url = config.get("GITHUB_PAGES_URL", "#")
    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    iframe_src = f"{pages_url}index.html?v={timestamp}"

    style_details = """
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 10px;
    background-color: #f9f9f9;
    cursor: pointer;
    """
    
    style_summary = """
    font-weight: bold;
    color: #333;
    outline: none;
    """

    wp_html = f"""
    <h3>日本市場 セクターローテーション  {last_date_str})</h3>
    <p>現在の重心は<strong>【{current_phase}】</strong>エリアにあります。<br>
    代表的な12業種の株価モメンタムを解析し、過去365日分の軌跡で景気の循環を描画しています。</p>
    <div style="width: 100%; max-width: 600px; aspect-ratio: 1; margin: 0 auto; border: 1px solid #eee; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
        <iframe src="{iframe_src}" width="100%" height="100%" style="border:none; display:block;" title="Sector Cycle Chart"></iframe>
    </div>
    <div style="height:20px" aria-hidden="true" class="wp-block-spacer"></div>
    <details class="wp-block-details" style="{style_details}">
    <summary style="{style_summary}">▼ 採用セクターとロジック解説（クリックで開閉）</summary>
    
    <div style="margin-top: 15px; font-size: 0.95em; color: #444;">
        <h4 style="font-size: 1.1em; border-bottom: 2px solid #eee; padding-bottom: 5px;">1. 採用セクター (12業種)</h4>
        <p>動きが素直で、各局面を代表する以下の12業種を選抜して計算しています。</p>
        <ul style="margin-top: 5px;">
            <li><strong style="color:#008b8b;">回復期 (北西):</strong> 電機・精密、情報通信、建設・資材</li>
            <li><strong style="color:#cd5c5c;">好況期 (北東):</strong> 自動車、機械、商社・卸売</li>
            <li><strong style="color:#daa520;">後退期 (南東):</strong> 銀行、金融(除銀)、エネルギー</li>
            <li><strong style="color:#483d8b;">不況期 (南西):</strong> 医薬品、食品、小売</li>
        </ul>

        <h4 style="font-size: 1.1em; border-bottom: 2px solid #eee; padding-bottom: 5px; margin-top: 20px;">2. 除外セクター (5業種)</h4>
        <p>ノイズを排除するため、以下は計算に含めていません。</p>
        {EXCLUSION_HTML}

        <h4 style="font-size: 1.1em; border-bottom: 2px solid #eee; padding-bottom: 5px; margin-top: 20px;">3. 計算ロジック</h4>
        <p>各業種の「200日移動平均線からの乖離率」を物理的な『重さ』と見なし、それらが円周上で綱引きをした結果（重心）を表示しています。<br>
        中心から離れるほどトレンドが強く、中心に近いほど方向感がないことを意味します。</p>
    </div>
    </details>
    """
    return wp_html

# ==========================================
# 4. メイン処理
# ==========================================

def main():
    config = load_secrets()
    df = get_market_data()
    latest_date = df.index[-1]
    last_date_str = latest_date.strftime('%Y年%m月%d日')
    
    # 軌跡計算 (365日前から10日刻み)
    history_points = []
    end_date = latest_date
    start_date = end_date - timedelta(days=365)
    dates = pd.date_range(start=start_date, end=end_date, freq='10D')
    
    for d in dates:
        if d not in df.index:
            past_matches = df.index[df.index <= d]
            if len(past_matches) == 0: continue
            valid_date = past_matches[-1]
        else:
            valid_date = d  
        x, y = calculate_vector(df, valid_date)
        if x is not None:
            history_points.append({"x": round(x, 2), "y": round(y, 2)})
            
    # 現在地計算
    curr_x, curr_y = calculate_vector(df, latest_date)
    if curr_x is None:
        print("Error: Calculation failed.")
        return

    current_point = {"x": round(curr_x, 2), "y": round(curr_y, 2)}
    
    # ★修正ポイント: 現在地を軌跡の最後に追加してつなげる
    history_points.append(current_point)

    # フェーズ判定
    current_phase = "不明"
    c_x_sign = 1 if curr_x >= 0 else -1
    c_y_sign = 1 if curr_y >= 0 else -1
    for name, signs in PHASES.items():
        if signs["x_sign"] == c_x_sign and signs["y_sign"] == c_y_sign:
            current_phase = name
            break
            
    print(f"Current Phase: {current_phase}")

    # GitHub Pages用HTML生成
    chart_html = create_standalone_html(history_points, current_point, last_date_str)
    
    output_dir = "public"
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(chart_html)
    print(f"Generated public/index.html")

    # WordPress更新
    wp_content = generate_wp_content(config, last_date_str, current_phase)
    
    wp_url = f"{config['WP_URL']}/wp-json/wp/v2/pages/{config['WP_PAGE_ID']}"
    auth = (config['WP_USER'], config['WP_PASSWORD'])
    payload = {'content': wp_content}
    
    print(f"Updating WordPress Page ID: {config['WP_PAGE_ID']}...")
    try:
        response = requests.post(wp_url, json=payload, auth=auth)
        response.raise_for_status()
        print("Success! WordPress updated.")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
