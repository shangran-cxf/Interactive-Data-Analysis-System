import os
import json
import csv
import io
import re
import uuid
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

from database import (
    init_db, create_user, verify_user, get_user_by_id,
    clear_user_vehicles, insert_user_vehicles, record_upload,
    get_user_vehicles, get_user_stats, get_user_brand_sales,
    get_user_price_distribution, get_user_energy_ratio, get_user_sales_chart,
    get_all_users, get_user_uploads, get_all_uploads
)
from chart_generator import generate_chart, get_config

app = Flask(
    __name__,
    template_folder='../frontend/templates',
    static_folder='../frontend/static'
)
app.secret_key = os.urandom(24).hex()
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'csv', 'json'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "请先登录"}), 401
        return f(*args, **kwargs)
    return decorated


def get_uid():
    return session.get('user_id')


# ── Page Routes ──

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html', username=session.get('username', ''))


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/register')
def register_page():
    return render_template('register.html')


# ── Auth API ──

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({"success": False, "message": "账号和密码不能为空"}), 400
    if len(username) < 2 or len(username) > 20:
        return jsonify({"success": False, "message": "账号长度需在2-20个字符之间"}), 400
    if not re.match(r'^[\w一-鿿]+$', username):
        return jsonify({"success": False, "message": "账号仅支持中英文、数字和下划线"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "密码长度至少6位"}), 400

    ok, msg, uid = create_user(username, password)
    return jsonify({"success": ok, "message": msg}), 200 if ok else 400


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({"success": False, "message": "账号和密码不能为空"}), 400

    ok, msg, user = verify_user(username, password)
    if ok:
        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({"success": True, "message": msg, "username": user['username']})
    return jsonify({"success": False, "message": msg}), 400


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    uid = session.get('user_id')
    uname = session.get('username')
    if uid:
        clear_user_vehicles(uid)
        # Also remove user summary JSON in database folder
        db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database')
        summary_file = os.path.join(db_dir, f"user_{uname}_summary.json")
        if os.path.exists(summary_file):
            os.remove(summary_file)
    session.clear()
    return jsonify({"success": True, "message": "已退出登录"})


@app.route('/api/auth/status')
def api_auth_status():
    if 'user_id' in session:
        return jsonify({"loggedIn": True, "username": session['username']})
    return jsonify({"loggedIn": False})


# ── Data Upload & Processing ──

def clean_dataframe(df: pd.DataFrame) -> dict:
    report = {
        "original_rows": len(df),
        "missing_filled": 0,
        "outliers_detected": 0,
        "rows_removed": 0,
        "final_rows": 0
    }

    col_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl in ('brand', '品牌'): col_map[col] = 'brand'
        elif cl in ('model', '车型', '型号'): col_map[col] = 'model'
        elif cl in ('sales_volume', 'sales', '销量', '销售量', '销售辆数'): col_map[col] = 'sales_volume'
        elif cl in ('sales_price', 'price', '价格', '售价', '销售价格', '价格(万)', '价格（万）'): col_map[col] = 'sales_price'
        elif cl in ('energy_type', 'energy', 'fuel', '能源', '能源类型', '燃油类型', '动力类型'): col_map[col] = 'energy_type'
    df.rename(columns=col_map, inplace=True)

    required = ['brand', 'model', 'sales_volume', 'sales_price', 'energy_type']
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"缺少必需列: {', '.join(missing_cols)}")

    for col in ['sales_volume', 'sales_price']:
        if df[col].isna().sum() > 0:
            report['missing_filled'] += int(df[col].isna().sum())
            df[col] = df[col].fillna(df[col].median())

    df['brand'] = df['brand'].fillna('未知品牌')
    df['model'] = df['model'].fillna('未知车型')
    df['energy_type'] = df['energy_type'].fillna('油车')

    for col in ['sales_volume', 'sales_price']:
        if len(df) > 3:
            z_scores = np.abs(scipy_stats.zscore(df[col].dropna()))
            outlier_mask = z_scores > 3
            report['outliers_detected'] += int(outlier_mask.sum())
            mean_val = df[col].mean()
            std_val = df[col].std()
            upper = mean_val + 3 * std_val
            lower = max(0, mean_val - 3 * std_val)
            df[col] = df[col].clip(lower, upper)

    before = len(df)
    df = df[~df['brand'].isin(['未知品牌', ''])]
    df = df[~df['model'].isin(['未知车型', ''])]
    report['rows_removed'] = before - len(df)

    energy_map = {
        '油车': '油车', '燃油车': '油车', '汽油车': '油车', '汽油': '油车', '燃油': '油车',
        '电车': '电车', '电动': '电车', '纯电动': '电车', '新能源': '电车', '纯电': '电车',
        '混动': '混动', '油电混合': '混动', '插电混动': '混动', '插混': '混动', '混合动力': '混动',
    }
    df['energy_type'] = df['energy_type'].map(lambda x: energy_map.get(str(x).strip(), str(x).strip()))

    report['final_rows'] = len(df)
    return report, df


@app.route('/api/data/upload', methods=['POST'])
@login_required
def api_upload():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "未选择文件"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "未选择文件"}), 400

    if not allowed_file(file.filename):
        return jsonify({"success": False, "message": "仅支持 JSON 和 CSV 格式"}), 400

    uid = get_uid()
    try:
        ext = file.filename.rsplit('.', 1)[1].lower()
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        if ext == 'csv':
            for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030']:
                try:
                    df = pd.read_csv(filepath, encoding=enc)
                    break
                except (UnicodeDecodeError, Exception):
                    continue
            else:
                return jsonify({"success": False, "message": "无法解析CSV文件编码"}), 400
        else:
            df = pd.read_json(filepath)

        if df.empty:
            return jsonify({"success": False, "message": "文件内容为空"}), 400

        report, df = clean_dataframe(df)

        if df.empty:
            return jsonify({"success": False, "message": "清洗后无有效数据"}), 400

        # Store per user — replace this user's previous data
        records = df[['brand', 'model', 'sales_volume', 'sales_price', 'energy_type']].to_dict('records')
        clear_user_vehicles(uid)
        insert_user_vehicles(uid, records)
        record_upload(uid, file.filename, len(records))

        # Save user summary in database folder for browsing
        db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database')
        summary = {
            "username": session.get('username'),
            "upload_file": file.filename,
            "record_count": len(records),
            "brand_count": int(df['brand'].nunique()),
            "brands": sorted(df['brand'].unique().tolist()),
            "energy_distribution": df['energy_type'].value_counts().to_dict(),
            "avg_price": round(float(df['sales_price'].mean()), 2),
            "updated_at": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        summary_path = os.path.join(db_dir, f"user_{session.get('username')}_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # Save cleaned Excel
        excel_name = f"cleaned_{uuid.uuid4().hex[:8]}.xlsx"
        excel_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_name)
        df.to_excel(excel_path, index=False, engine='openpyxl')

        return jsonify({
            "success": True,
            "message": f"上传成功！共导入 {len(records)} 条数据",
            "report": report,
            "download_url": f"/api/data/download/{excel_name}"
        })

    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"数据处理异常: {str(e)}"}), 500


@app.route('/api/data/download/<filename>')
@login_required
def api_download(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(filepath, as_attachment=True, download_name=filename)


# ── Data Analysis APIs (per-user) ──

@app.route('/api/data/stats')
@login_required
def api_stats():
    return jsonify(get_user_stats(get_uid()))


@app.route('/api/data/brand-sales')
@login_required
def api_brand_sales():
    return jsonify(get_user_brand_sales(get_uid()))


@app.route('/api/data/price-distribution')
@login_required
def api_price_distribution():
    return jsonify(get_user_price_distribution(get_uid()))


@app.route('/api/data/energy-ratio')
@login_required
def api_energy_ratio():
    return jsonify(get_user_energy_ratio(get_uid()))


@app.route('/api/data/sales-chart')
@login_required
def api_sales_chart():
    return jsonify(get_user_sales_chart(get_uid()))


@app.route('/api/data/vehicles')
@login_required
def api_vehicles():
    return jsonify(get_user_vehicles(get_uid()))


# ── Matplotlib 汽车销售统计图 API (第二部分) ──

@app.route('/api/chart/config')
@login_required
def api_chart_config():
    """返回图表参数配置 (图表类型, 颜色主题等)"""
    return jsonify(get_config())


@app.route('/api/chart/generate', methods=['POST'])
@login_required
def api_chart_generate():
    """
    根据用户自定义参数, 使用 Matplotlib 生成汽车销售统计图
    请求体 (JSON):
        {
            "chart_type": "bar|line|bar_line|pie|scatter|horizontal_bar|stacked_bar|radar",
            "theme": "tech|nature|warm|classic|rainbow",
            "top_n": 15,
            "sort_by": "sales_volume|sales_price|brand",
            "sort_order": "asc|desc",
            "title": "自定义标题",
            "show_value": true,
            "grid_on": true,
            "energy_filter": "all|油车|电车|混动"
        }
    返回:
        { "success": true, "image_base64": "data:image/png;base64,...", "info": {...} }
    """
    uid = get_uid()
    try:
        # 获取用户车辆数据
        vehicles = get_user_vehicles(uid)
        if not vehicles:
            return jsonify({"success": False, "error": "请先上传数据"}), 400

        # 解析用户自定义参数
        params = request.get_json(force=True, silent=True) or {}
        # 确保布尔值正确解析
        for key in ['show_value', 'grid_on']:
            if key in params:
                params[key] = bool(params[key])

        # 生成图表
        result = generate_chart(vehicles, params)

        if result['success']:
            return jsonify({
                "success": True,
                "image_base64": f"data:image/png;base64,{result['image_base64']}",
                "info": result['info']
            })
        else:
            return jsonify({
                "success": False,
                "message": result.get('error', '图表生成失败'),
                "info": result.get('info', {})
            }), 400

    except Exception as e:
        return jsonify({"success": False, "message": f"服务器异常: {str(e)}"}), 500


# ── AI Evaluation ──

def generate_mock_ai_report(stats: dict, brand_sales: list, price_dist: list, energy: dict) -> str:
    total = stats['totalVehicles']
    top_car = stats['topSalesCar']
    top_model = stats['topSalesModel']
    top_brand = stats['topBrandByModels']
    avg_price = stats['avgPrice']
    oil_r = stats['oilRatio']
    elec_r = stats['electricRatio']
    hyb_r = stats['hybridRatio']

    brand_str = ", ".join([f"{b['brand']}({b['sales']}辆)" for b in brand_sales[:5]])
    price_str = ", ".join([f"{p['range']}({p['count']}款)" for p in price_dist if p['count'] > 0])

    return f"""## 汽车销售数据综合分析报告

### 一、数据概况
本次分析共覆盖 {total} 条车辆销售记录，涉及 {stats['brandCount']} 个汽车品牌。

### 二、销量分析
- **销量冠军**: {top_car}，表现最为突出
- **最畅销车型类别**: {top_model}
- **车型矩阵最丰富品牌**: {top_brand}，产品线覆盖最广

### 三、品牌格局
销量排名前五品牌为: {brand_str}。头部品牌集中度较高，呈现明显的马太效应。

### 四、价格分析
- **平均售价**: {avg_price}万元
- **价格分布**: {price_str}
- 整体市场价格带分布合理，覆盖经济型到豪华型各细分市场。

### 五、能源结构
- 燃油车占比: {oil_r}%
- 电动车占比: {elec_r}%
- 混动车型占比: {hyb_r}%

### 六、趋势研判
{'当前新能源渗透率已达' + str(round(elec_r + hyb_r, 1)) + '%，市场正加速向电动化转型。' if (elec_r + hyb_r) > 30 else '传统燃油车仍占据主导地位，但新能源转型趋势明显。'}

### 七、建议
1. 重点关注{top_brand}品牌动向，其产品策略对市场影响较大
2. {avg_price}万元价位段为兵家必争之地，建议加强该区间产品布局
3. {'抓住新能源转型窗口期，加大电动化投入' if (elec_r + hyb_r) < 50 else '新能源已成主流，需关注充电基础设施配套及二手车残值管理'}"""


@app.route('/api/ai/evaluate', methods=['POST'])
@login_required
def api_ai_evaluate():
    uid = get_uid()
    stats = get_user_stats(uid)
    if stats['totalVehicles'] == 0:
        return jsonify({"success": False, "message": "请先上传数据"}), 400

    brand_sales = get_user_brand_sales(uid)
    price_dist = get_user_price_distribution(uid)
    energy = get_user_energy_ratio(uid)

    api_key = os.environ.get('DEEPSEEK_API_KEY', 'sk-e544c4cc53e545e09ba7888d338f6c08')
    if api_key:
        try:
            import requests
            prompt = f"""你是一位资深的汽车行业数据分析师。请根据以下数据生成一份专业的数据分析报告（500字左右，使用Markdown格式）：

**基础数据**：总记录{stats['totalVehicles']}条，{stats['brandCount']}个品牌
**销量冠军**：{stats['topSalesCar']}
**最畅销车型**：{stats['topSalesModel']}
**车型最多品牌**：{stats['topBrandByModels']}
**平均售价**：{stats['avgPrice']}万元
**品牌销量排行**：{json.dumps(brand_sales[:10], ensure_ascii=False)}
**价格区间分布**：{json.dumps(price_dist, ensure_ascii=False)}
**能源结构**：油车{energy['oil']}%、电车{energy['electric']}%、混动{energy['hybrid']}%

请包含：数据概况、销量分析、品牌格局、价格分析、能源结构、趋势研判、策略建议等板块。"""

            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "你是一位专业的汽车行业数据分析师。请用中文回复，使用Markdown格式。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000
                },
                timeout=30
            )
            if resp.status_code == 200:
                report = resp.json()['choices'][0]['message']['content']
                return jsonify({"success": True, "report": report, "source": "deepseek"})
        except Exception:
            pass

    report = generate_mock_ai_report(stats, brand_sales, price_dist, energy)
    return jsonify({"success": True, "report": report, "source": "mock"})


# ── Init ──

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
