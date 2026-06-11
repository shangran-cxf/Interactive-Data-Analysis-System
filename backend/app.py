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

from database import (
    init_db, create_user, verify_user, get_user_by_id,
    clear_user_vehicles, insert_user_vehicles, record_upload,
    get_user_vehicles, get_user_stats, get_user_brand_sales,
    get_user_price_distribution, get_user_energy_ratio, get_user_sales_chart,
    get_all_users, get_user_uploads, get_all_uploads,
    archive_upload_vehicles, set_active_upload, get_active_upload_id,
    activate_upload, delete_upload
)
from ml.predictor import SalesPredictor
from ml.correlation import CorrelationAnalyzer
from ml.cluster import MarketSegmenter
from chart_generator import generate_chart, get_config
from data_clean import clean_dataframe, interactive_clean_dataframe, load_and_clean, df_to_echarts, df_to_records

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
        # 恢复上次正在分析的历史批次（登出会清空 vehicles，此处从归档还原）
        active_id = get_active_upload_id(user['id'])
        if active_id:
            restored, _, records = activate_upload(user['id'], active_id)
            if restored:
                write_user_summary(user['username'], records)
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
# 数据清洗统一由 data_clean.py 处理
# clean_dataframe()              — 核心清洗函数（自动模式）
# interactive_clean_dataframe()  — 交互式清洗（用户自定义策略/缺失值+异常边界）
# load_and_clean()               — 文件读取 + 清洗一站式封装
# df_to_echarts()                — DataFrame → ECharts 前端格式
# df_to_records()                — DataFrame → 前端 dict 列表


@app.route('/api/data/interactive-clean', methods=['POST'])
@login_required
def api_interactive_clean():
    """交互式清洗 API — 前端交互面板提交自定义清洗策略"""
    uid = get_uid()
    vehicles = get_user_vehicles(uid)
    if not vehicles:
        return jsonify({"success": False, "message": "当前无车辆数据，请先上传文件"}), 400

    data = request.get_json()
    if not data or 'config' not in data:
        return jsonify({"success": False, "message": "缺少清洗配置"}), 400

    config = data['config']

    try:
        df = pd.DataFrame(vehicles)
    except Exception as e:
        return jsonify({"success": False, "message": f"构造数据失败: {str(e)}"}), 500

    try:
        report, df_clean = interactive_clean_dataframe(df, config)

        if df_clean.empty:
            return jsonify({"success": False, "message": "清洗后无有效数据"}), 400

        # 更新数据库
        records = df_to_records(df_clean)
        clear_user_vehicles(uid)
        insert_user_vehicles(uid, records)

        # 生成 echarts 数据供前端刷新
        echarts_data = df_to_echarts(df_clean)
        # 更新摘要
        write_user_summary(session.get('username'), records)

        return jsonify({
            "success": True,
            "message": f"交互式清洗完成！最终 {len(records)} 条数据",
            "report": report,
            "echarts": echarts_data,
        })

    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"清洗异常: {str(e)}"}), 500


def write_user_summary(username: str, records: list) -> dict:
    """根据当前生效的明细数据，写出 database/user_<用户名>_summary.json 摘要快照。"""
    db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database')
    sdf = pd.DataFrame(records)
    summary = {
        "username": username,
        "record_count": len(records),
        "brand_count": int(sdf['brand'].nunique()),
        "brands": sorted(sdf['brand'].unique().tolist()),
        "energy_distribution": sdf['energy_type'].value_counts().to_dict(),
        "avg_price": round(float(sdf['sales_price'].mean()), 2),
        "updated_at": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    summary_path = os.path.join(db_dir, f"user_{username}_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


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

        # Store per user — 归档为历史批次，并设为当前生效数据
        # 确保 sales_volume 和 sales_price 是纯数值类型，兼容数据库 schema
        df['sales_volume'] = df['sales_volume'].fillna(0).astype(int)
        df['sales_price'] = df['sales_price'].fillna(0).round(2)
        records = df[['brand', 'model', 'sales_volume', 'sales_price', 'energy_type']].to_dict('records')
        upload_id = record_upload(uid, file.filename, len(records))
        archive_upload_vehicles(upload_id, records)   # 历史归档（可回溯）
        clear_user_vehicles(uid)
        insert_user_vehicles(uid, records)            # 当前分析视图
        set_active_upload(uid, upload_id)             # 标记为 active 批次

        # Save user summary in database folder for browsing
        write_user_summary(session.get('username'), records)

        # Save cleaned Excel
        excel_name = f"cleaned_{uuid.uuid4().hex[:8]}.xlsx"
        excel_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_name)
        df.to_excel(excel_path, index=False, engine='openpyxl')

        # 构造前端兼容的清洗报告
        def _compat_report(r):
            missing_total = sum(
                v if isinstance(v, (int, float)) else (v.get('count', 0) if isinstance(v, dict) else 0)
                for v in r.get('missing_filled', {}).values()
            ) if isinstance(r.get('missing_filled'), dict) else (r.get('missing_filled', 0) or 0)
            outliers_total = sum(
                v if isinstance(v, (int, float)) else (v.get('count', 0) if isinstance(v, dict) else 0)
                for v in r.get('outliers_handled', {}).values()
            ) if isinstance(r.get('outliers_handled'), dict) else (r.get('outliers_detected', 0) or 0)
            return {
                "original_rows": r.get('original_rows', len(records)),
                "missing_filled": int(missing_total),
                "outliers_detected": int(outliers_total),
                "rows_removed": int(r.get('duplicates_removed', 0)),
                "final_rows": r.get('final_rows', len(records)),
            }

        return jsonify({
            "success": True,
            "message": f"上传成功！共导入 {len(records)} 条数据",
            "report": _compat_report(report),
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


# ── 上传历史记录管理（列表 / 切换 / 删除） ──

@app.route('/api/data/uploads')
@login_required
def api_data_uploads():
    """返回当前用户的上传历史列表（含 is_active / archived_count）。"""
    return jsonify(get_user_uploads(get_uid()))


@app.route('/api/data/uploads/<int:upload_id>/activate', methods=['POST'])
@login_required
def api_activate_upload(upload_id):
    """把某条历史上传切换为当前分析数据。"""
    uid = get_uid()
    ok, msg, records = activate_upload(uid, upload_id)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400
    write_user_summary(session.get('username'), records)
    return jsonify({"success": True, "message": msg, "record_count": len(records)})


@app.route('/api/data/uploads/<int:upload_id>', methods=['DELETE'])
@login_required
def api_delete_upload(upload_id):
    """删除一条上传历史及其归档明细。"""
    ok, msg = delete_upload(get_uid(), upload_id)
    return jsonify({"success": ok, "message": msg}), (200 if ok else 400)


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


def _get_user_vehicles():
    user_id = session.get('user_id')
    if not user_id:
        return None, None
    vehicles = get_user_vehicles(user_id)
    return user_id, vehicles

@app.route('/api/ml/model-info', methods=['GET'])
def ml_model_info():
    user_id, vehicles = _get_user_vehicles()
    if user_id is None:
        return jsonify({'success': False, 'error': '未登录'}), 401
    predictor = SalesPredictor(user_id)
    return jsonify(predictor.get_model_info())

@app.route('/api/ml/retrain', methods=['POST'])
def ml_retrain():
    user_id, vehicles = _get_user_vehicles()
    if user_id is None:
        return jsonify({'success': False, 'error': '未登录'}), 401
    if not vehicles:
        return jsonify({'success': False, 'error': '暂无数据'}), 400
    predictor = SalesPredictor(user_id)
    result = predictor.train(vehicles)
    return jsonify(result)

@app.route('/api/ml/predict', methods=['POST'])
def ml_predict():
    user_id, vehicles = _get_user_vehicles()
    if user_id is None:
        return jsonify({'success': False, 'error': '未登录'}), 401
    data = request.get_json() or {}
    price       = data.get('price')
    energy_type = data.get('energyType', '油车')
    month       = data.get('month')
    if price is None:
        return jsonify({'success': False, 'error': '缺少 price 参数'}), 400
    predictor = SalesPredictor(user_id)
    if not predictor.model and vehicles:
        predictor.train(vehicles)
    return jsonify(predictor.predict(float(price), energy_type, month))

@app.route('/api/ml/correlation', methods=['GET'])
def ml_correlation():
    user_id, vehicles = _get_user_vehicles()
    if user_id is None:
        return jsonify({'success': False, 'error': '未登录'}), 401
    if not vehicles:
        return jsonify({'success': False, 'error': '暂无数据'}), 400
    stratify = request.args.get('stratify')
    analyzer = CorrelationAnalyzer(vehicles)
    return jsonify({'success': True, **analyzer.analyze(stratify)})

@app.route('/api/ml/cluster', methods=['GET'])
def ml_cluster():
    user_id, vehicles = _get_user_vehicles()
    if user_id is None:
        return jsonify({'success': False, 'error': '未登录'}), 401
    if not vehicles:
        return jsonify({'success': False, 'error': '暂无数据'}), 400
    k = int(request.args.get('k', 3))
    segmenter = MarketSegmenter(vehicles)
    return jsonify(segmenter.segment(k))



if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5001)
