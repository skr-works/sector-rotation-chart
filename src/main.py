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

# 1つのSecret (JSON形式) から設定を読み込む関数
def load_secrets():
    # GitHub Actions側で 'WP_SECRETS_JSON' という環境変数にJSON文字列が入っている前提
    secrets_json = os.environ.get('WP_SECRETS_JSON')
    if not secrets_json:
        print("Error: WP_SECRETS_JSON environment variable is not set.")
        sys.exit(1)
    
    try:
        config = json.loads(secrets_json)
        return config
    except json.JSONDecodeError:
        print("Error: Failed to parse WP_SECRETS_JSON. Ensure it is valid JSON.")
        sys.exit(1)

# セクター定義 (北西スタート・時計回り)
SECTORS = [
    # --- 北西: 回復期 (Recovery) 9時-12時 ---
    {"code": "1625.T", "name": "電機・精密", "clock": 10.5}, # ハイテク
    {"code": "1626.T", "name": "情報通信",   "clock": 11.5}, # 通信
    {"code": "1619.T", "name": "建設・資材", "clock": 9.5},  # 回復初期

    # --- 北東: 好況期 (Boom) 12時-3時 ---
    {"code": "1622.T", "name": "自動車",     "clock": 1.5},  # 輸出
    {"code": "1624.T", "name": "機械",       "clock": 0.5},  # 設備投資
    {"code": "1629.T", "name": "商社・卸売", "clock": 2.5},  # バフェット

    # --- 南東: 後退期 (Slowdown) 3時-6時 ---
    {"code": "1631.T", "name": "銀行",       "clock": 4.5},  # 金利高
    {"code": "1632.T", "name": "金融(除銀)", "clock": 3.5},  # 金融
    {"code": "1618.T", "name": "エネルギー", "clock": 5.5},  # インフレ

    # --- 南西: 不況期 (Recession) 6時-9時 ---
    {"code": "1621.T", "name": "医薬品",     "clock": 7.5},  # ディフェンシブ
    {"code": "1617.T", "name": "食品",       "clock": 6.5},  # 必需品
    {"code": "1630.T", "name": "小売",       "clock": 8.5},  # 内需
]

# 象限の名称定義 (判定用)
PHASES = {
    "回復期": {"x_sign": -1, "y_sign": 1},  # 北西
    "好況期": {"x_sign": 1,  "y_sign": 1},  # 北東
    "後退期": {"x_sign": 1,  "y_sign": -1}, # 南東
    "不況期": {"x_sign": -1, "y_sign": -1}, # 南西
}

# 指定された除外セクターの説明テキスト
EXCLUSION_TEXT = """
<dl>
<dt>鉄鋼・非鉄</dt>
<dd>機械・自動車と動きが重複するため。</dd>
<dt>素材・化学</dt>
<dd>要因が複雑で方向感が定まりにくいため。</dd>
<dt>不動産</dt>
<dd>銀行（金利感応）と似ているが変動が激しすぎるため。</dd>
<dt>運輸・物流</dt>
<dd>陸運と海運が混在し、指標として不明瞭なため。</dd>
<dt>電力・ガス</dt>
<dd>(※もし12種に入れるなら小売と交代だが、今回は値動きの大きい小売を優先)</dd>
</dl>
"""

# ==========================================
# 2. 計算ロジック
# ==========================================

def get_market_data():
    """Yahoo Financeから過去2年分の株価を取得"""
    tickers = [s["code"] for s in SECTORS]
    print(f"Fetching data for {len(tickers)} sectors...")
    
    # 2年分取得 (200MA計算のため)
    df = yf.download(tickers, period="2y", interval="1d", progress=False)['Close']
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df.ffill().bfill()
    last_date = df.index[-1]
    print(f"Latest data date: {last_date.strftime('%Y-%m-%d')}")
    
    return df

def clock_to_rad(clock_hour):
    """時計の時針位置(0-12)を数学的なラジアン角に変換"""
    degree = 90 - (clock_hour * 30)
    return math.radians(degree)

def calculate_vector(df, target_date):
    """特定の日付時点での合成ベクトル(X, Y)を計算"""
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
        if code not in deviations:
            continue
            
        strength = deviations[code]
        rad = clock_to_rad(sector["clock"])
        
        x = strength * math.cos(rad)
        y = strength * math.sin(rad)
        
        total_x += x
        total_y += y
        
    scale_factor = 4.0 
    return total_x / scale_factor, total_y / scale_factor

def generate_chart_html(history_points, current_point, last_date_str, current_phase):
    """Chart.jsを含むHTMLコンテンツを生成"""
    
    # データのJSON化
    history_json = json.dumps(history_points)
    current_json = json.dumps([current_point])
    
    # チャートIDを一意にする（念のため）
    chart_id = "sectorCycleChart"
    
    html = f"""
    <h3>日本市場 景気サイクルチャート ({last_date_str})</h3>
    <p>現在の重心は<strong>【{current_phase}】</strong>エリアにあります。<br>
    代表的な12業種の株価モメンタムを解析し、景気の循環を描画しています。</p>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <div class="chart-container" style="position: relative; width: 100%; max-width: 600px; margin: 0 auto; aspect-ratio: 1;">
        <canvas id="{chart_id}"></canvas>
    </div>

    <script>
    (function() {{
        const ctx = document.getElementById('{chart_id}').getContext('2d');
        
        // 背景エリア描画プラグイン
        const bgPlugin = {{
            id: 'bgPlugin',
            beforeDraw: (chart) => {{
                const {{ctx, chartArea: {{left, top, width, height}}, scales: {{x, y}}}} = chart;
                const midX = x.getPixelForValue(0);
                const midY = y.getPixelForValue(0);
                
                ctx.save();
                
                // 北西 (回復) - 左上
                ctx.fillStyle = 'rgba(230, 247, 255, 0.4)'; 
                ctx.fillRect(left, top, midX - left, midY - top);
                // 北東 (好況) - 右上
                ctx.fillStyle = 'rgba(255, 240, 240, 0.4)';
                ctx.fillRect(midX, top, left + width - midX, midY - top);
                // 南東 (後退) - 右下
                ctx.fillStyle = 'rgba(255, 251, 230, 0.4)';
                ctx.fillRect(midX, midY, left + width - midX, top + height - midY);
                // 南西 (不況) - 左下
                ctx.fillStyle = 'rgba(240, 240, 240, 0.4)';
                ctx.fillRect(left, midY, midX - left, top + height - midY);
                
                // テキスト描画設定
                ctx.font = 'bold 14px sans-serif';
                ctx.fillStyle = 'rgba(0,0,0,0.5)';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                
                // エリア名配置
                ctx.fillText('回復期', (left + midX)/2, (top + midY)/2);
                ctx.fillText('好況期', (midX + left + width)/2, (top + midY)/2);
                ctx.fillText('後退期', (midX + left + width)/2, (midY + top + height)/2);
                ctx.fillText('不況期', (left + midX)/2, (midY + top + height)/2);
                
                ctx.restore();
            }}
        }};

        new Chart(ctx, {{
            type: 'scatter',
            data: {{
                datasets: [
                    {{
                        label: '軌跡 (過去1年)',
                        data: {history_json},
                        backgroundColor: 'rgba(100, 100, 100, 0.5)',
                        borderColor: 'rgba(100, 100, 100, 0.5)',
                        borderWidth: 1,
                        pointRadius: 2,
                        showLine: true,
                        order: 2
                    }},
                    {{
                        label: '現在',
                        data: {current_json},
                        backgroundColor: 'rgba(255, 0, 0, 1)',
                        pointRadius: 8,
                        pointHoverRadius: 10,
                        order: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false, // container側で比率制御するためfalse
                scales: {{
                    x: {{
                        min: -25, max: 25,
                        grid: {{ drawTicks: false }},
                        ticks: {{ display: false }}
                    }},
                    y: {{
                        min: -25, max: 25,
                        grid: {{ drawTicks: false }},
                        ticks: {{ display: false }}
                    }}
                }},
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{ enabled: false }} 
                }}
            }},
            plugins: [bgPlugin]
        }});
    }})();
    </script>
    <details class="wp-block-details">
    <summary>採用セクターとロジック解説</summary>
    
    <h4>1. 採用セクター (12業種)</h4>
    <p>動きが素直で、各局面を代表する以下の12業種を選抜して計算しています。</p>
    <ul>
        <li><strong>回復期エリア:</strong> 電機・精密、情報通信、建設・資材</li>
        <li><strong>好況期エリア:</strong> 自動車、機械、商社・卸売</li>
        <li><strong>後退期エリア:</strong> 銀行、金融(除銀)、エネルギー</li>
        <li><strong>不況期エリア:</strong> 医薬品、食品、小売</li>
    </ul>

    <h4>2. 除外セクター (5業種)</h4>
    <p>ノイズを排除するため、以下は計算に含めていません。</p>
    {EXCLUSION_TEXT}

    <h4>3. 計算ロジック</h4>
    <p>各業種の「200日移動平均線からの乖離率」を物理的な『重さ』と見なし、それらが円周上で綱引きをした結果（重心）を表示しています。中心から離れるほどトレンドが強く、中心に近いほど方向感がないことを意味します。</p>
    </details>
    <p style="text-align:right; font-size:0.8em; color:#999; margin-top:20px;">最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    """
    return html

# ==========================================
# 3. メイン処理
# ==========================================

def main():
    config = load_secrets()
    df = get_market_data()
    latest_date = df.index[-1]
    
    # 軌跡データの計算 (過去365日, 10日刻み)
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
            
    # 現在地点の計算
    curr_x, curr_y = calculate_vector(df, latest_date)
    if curr_x is None:
        print("Error: Calculation failed due to insufficient data.")
        return

    current_point = {"x": round(curr_x, 2), "y": round(curr_y, 2)}
    
    # フェーズ判定
    current_phase = "不明"
    c_x_sign = 1 if curr_x >= 0 else -1
    c_y_sign = 1 if curr_y >= 0 else -1
    
    for name, signs in PHASES.items():
        if signs["x_sign"] == c_x_sign and signs["y_sign"] == c_y_sign:
            current_phase = name
            break
            
    print(f"Current Phase: {current_phase} (x={curr_x:.2f}, y={curr_y:.2f})")

    # HTML生成
    html_content = generate_chart_html(
        history_points, 
        current_point, 
        latest_date.strftime('%Y年%m月%d日'),
        current_phase
    )
    
    # WordPress更新
    wp_url = f"{config['WP_URL']}/wp-json/wp/v2/pages/{config['WP_PAGE_ID']}"
    auth = (config['WP_USER'], config['WP_PASSWORD'])
    
    payload = {
        'content': html_content
    }
    
    print(f"Updating WordPress Page ID: {config['WP_PAGE_ID']}...")
    try:
        response = requests.post(wp_url, json=payload, auth=auth)
        response.raise_for_status()
        print("Success! Page updated.")
    except requests.exceptions.RequestException as e:
        print(f"Error updating WordPress: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(e.response.text)
        sys.exit(1)

if __name__ == "__main__":
    main()
