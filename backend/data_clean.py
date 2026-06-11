"""
汽车销售数据清洗模块
=====================
功能列表：
  ① 删除完全重复数据行
  ② 缺失值填充 — 数值列用中位数、文本分类列用众数
  ③ Z-score 异常值检测 (|Z| > 3)，异常值替换为同列中位数
  ④ 业务规整 — 销售日期统一为 datetime、能源类型文本标准化
  ⑤ 输出结构化清洗报告字典
  ⑥ DataFrame → ECharts 可用的 JSON 字典数组转换
  ⑦ 文件读取 + 清洗一站式封装（对接 app.py 上传路由）
  ⑧ 交互式清洗 — 用户自定义缺失值策略 + 异常值边界（对接前端交互面板）
"""

import os
import json
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats
from typing import Tuple, Dict, List, Any, Optional

# ──────────────────────────────────────────────
#  常量定义
# ──────────────────────────────────────────────

COLUMN_MAP = {
    'brand': 'brand', 'brands': 'brand',
    '品牌': 'brand', '汽车品牌': 'brand', '厂商': 'brand', '制造商': 'brand',
    'make': 'brand', 'manufacturer': 'brand',
    'model': 'model', 'models': 'model',
    '车型': 'model', '型号': 'model', '车名': 'model', '名称': 'model',
    'vehicle': 'model', 'name': 'model',
    'sales_volume': 'sales_volume', 'sales': 'sales_volume',
    '销量': 'sales_volume', '销售量': 'sales_volume', '销售辆数': 'sales_volume',
    '月销量': 'sales_volume', '月度销量': 'sales_volume', '销售数量': 'sales_volume',
    'volume': 'sales_volume', 'sold': 'sales_volume',
    'sales_price': 'sales_price', 'price': 'sales_price',
    '价格': 'sales_price', '售价': 'sales_price', '销售价格': 'sales_price',
    '价格(万)': 'sales_price', '价格（万）': 'sales_price', '价格(万元)': 'sales_price',
    '单价': 'sales_price', '指导价': 'sales_price', '售价(万)': 'sales_price',
    'energy_type': 'energy_type', 'energy': 'energy_type', 'fuel': 'energy_type',
    '能源': 'energy_type', '能源类型': 'energy_type', '燃油类型': 'energy_type',
    '动力类型': 'energy_type', '燃料': 'energy_type',
    'fuel_type': 'energy_type', 'powertrain': 'energy_type',
    'sale_date': 'sale_date', 'date': 'sale_date',
    '销售日期': 'sale_date', '日期': 'sale_date', '销售时间': 'sale_date',
    '日期(年/月)': 'sale_date', '月份': 'sale_date',
    'report_date': 'sale_date', 'month': 'sale_date',
}

ENERGY_TYPE_MAP = {
    '油车': '油车', '燃油车': '油车', '汽油车': '油车',
    '汽油': '油车', '燃油': '油车', '柴油': '油车',
    '柴油车': '油车', '传统燃油': '油车', '内燃机': '油车',
    'gasoline': '油车', 'diesel': '油车', 'petrol': '油车',
    '燃油版': '油车', '汽油版': '油车',
    '电车': '电车', '电动': '电车', '纯电动': '电车',
    '新能源': '电车', '纯电': '电车', '电动版': '电车',
    '电动汽车': '电车', '纯电动汽车': '电车', '新能源车': '电车',
    'electric': '电车', 'ev': '电车', 'bev': '电车',
    '混动': '混动', '油电混合': '混动', '插电混动': '混动',
    '插混': '混动', '混合动力': '混动', '混动车': '混动',
    '油电混动': '混动', '混合': '混动', '增程式': '混动',
    'hybrid': '混动', 'phev': '混动', 'plug-in': '混动',
}


# ──────────────────────────────────────────────
#  工具函数
# ──────────────────────────────────────────────

def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in COLUMN_MAP:
            renamed[col] = COLUMN_MAP[key]
    if renamed:
        df = df.rename(columns=renamed)
    return df


def _validate_columns(df: pd.DataFrame) -> List[str]:
    required = ['brand', 'model', 'sales_volume', 'sales_price', 'energy_type']
    return [c for c in required if c not in df.columns]


def _safe_to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors='coerce')


# ──────────────────────────────────────────────
#  核心清洗函数（自动模式）
# ──────────────────────────────────────────────

def clean_dataframe(df: pd.DataFrame) -> Tuple[Dict[str, Any], pd.DataFrame]:
    report: Dict[str, Any] = {
        'original_rows': len(df),
        'duplicates_removed': 0,
        'missing_filled': {},
        'outliers_handled': {},
        'final_rows': 0,
        'warnings': [],
        'columns_original': list(df.columns),
        'columns_final': [],
    }

    if df.empty:
        report['warnings'].append('输入 DataFrame 为空')
        report['final_rows'] = 0
        return report, df

    df = df.copy()
    df = _map_columns(df)
    missing = _validate_columns(df)
    if missing:
        raise ValueError(f"数据缺少必需列: {', '.join(missing)}。当前列名: {list(df.columns)}。")

    for col in ['sales_volume', 'sales_price']:
        if col in df.columns:
            df[col] = _safe_to_numeric(df[col])

    before_dedup = len(df)
    df = df.drop_duplicates()
    report['duplicates_removed'] = before_dedup - len(df)
    if report['duplicates_removed'] > 0:
        report['warnings'].append(f"删除 {report['duplicates_removed']} 行完全重复数据")

    numeric_cols = ['sales_volume', 'sales_price']
    for col in numeric_cols:
        if col in df.columns:
            missing_count = int(df[col].isna().sum())
            if missing_count > 0:
                median_val = df[col].median()
                if pd.isna(median_val):
                    median_val = 0
                df[col] = df[col].fillna(median_val)
                report['missing_filled'][col] = missing_count

    text_cols = ['brand', 'model', 'energy_type']
    for col in text_cols:
        if col in df.columns:
            missing_count = int(df[col].isna().sum())
            if missing_count > 0:
                mode_vals = df[col].mode()
                fill_val = mode_vals.iloc[0] if len(mode_vals) > 0 else '未知'
                df[col] = df[col].fillna(fill_val)
                report['missing_filled'][col] = missing_count

    if 'sale_date' in df.columns:
        missing_count = int(df['sale_date'].isna().sum())
        if missing_count > 0:
            mode_vals = df['sale_date'].mode()
            fill_val = mode_vals.iloc[0] if len(mode_vals) > 0 else '2024-01'
            df['sale_date'] = df['sale_date'].fillna(fill_val)
            report['missing_filled']['sale_date'] = missing_count

    for col in numeric_cols:
        if col in df.columns and len(df) > 3:
            df[col] = df[col].astype(float)
            series = df[col].dropna()
            if series.std() == 0:
                continue
            z_scores = np.abs(scipy_stats.zscore(series))
            outlier_mask = z_scores > 3
            outlier_count = int(outlier_mask.sum())
            if outlier_count > 0:
                median_val = float(df[col].median())
                outlier_indices = series[outlier_mask].index
                df.loc[outlier_indices, col] = median_val
                report['outliers_handled'][col] = outlier_count
                report['warnings'].append(
                    f"{col} 列检测到 {outlier_count} 个异常值 (|Z|>3)，已替换为中位数 {median_val}"
                )

    if 'energy_type' in df.columns:
        df['energy_type'] = df['energy_type'].astype(str).str.strip()
        df['energy_type'] = df['energy_type'].map(lambda x: ENERGY_TYPE_MAP.get(x, x))

    if 'sale_date' in df.columns:
        df['sale_date'] = df['sale_date'].astype(str).str.strip()

        def _parse_date(val: str):
            formats = ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y-%m', '%Y/%m', '%Y.%m',
                       '%Y年%m月', '%Y年%m月%d日', '%m/%d/%Y', '%d/%m/%Y']
            for fmt in formats:
                try:
                    return pd.to_datetime(val, format=fmt)
                except (ValueError, TypeError):
                    continue
            try:
                return pd.to_datetime(val)
            except (ValueError, TypeError):
                return pd.NaT

        df['sale_date'] = df['sale_date'].apply(_parse_date)

    before_invalid = len(df)
    df = df[~df['brand'].isin(['', '未知', 'unknown', 'Unknown', 'NaN', 'nan'])]
    df = df[~df['model'].isin(['', '未知', 'unknown', 'Unknown', 'NaN', 'nan'])]
    invalid_removed = before_invalid - len(df)
    if invalid_removed > 0:
        report['warnings'].append(f"删除 {invalid_removed} 行品牌/车型为空的无效数据")

    report['final_rows'] = len(df)
    report['columns_final'] = list(df.columns)

    total_missing = sum(report['missing_filled'].values()) if report['missing_filled'] else 0
    total_outliers = sum(report['outliers_handled'].values()) if report['outliers_handled'] else 0
    if total_missing == 0:
        report['warnings'].append('未检测到缺失值')
    if total_outliers == 0:
        report['warnings'].append('未检测到异常值')

    return report, df


# ──────────────────────────────────────────────
#  交互式清洗函数
# ──────────────────────────────────────────────

def interactive_clean_dataframe(
    df: pd.DataFrame,
    config: Dict[str, Any]
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    missing_action = config.get('missing_action', 'default')
    custom_fill = config.get('custom_fill', {})
    outlier_ranges = config.get('outlier_ranges', {})

    report: Dict[str, Any] = {
        'original_rows': len(df),
        'duplicates_removed': 0,
        'missing_action': missing_action,
        'missing_dropped': 0,
        'missing_filled': {},
        'outliers_detected': 0,
        'outliers_handled': 0,
        'outliers_detail': {},
        'final_rows': 0,
        'warnings': [],
        'columns_original': list(df.columns),
        'columns_final': [],
    }

    if df.empty:
        report['warnings'].append('输入 DataFrame 为空')
        report['final_rows'] = 0
        return report, df

    df = df.copy()
    df = _map_columns(df)
    missing = _validate_columns(df)
    if missing:
        raise ValueError(f"数据缺少必需列: {', '.join(missing)}。当前列名: {list(df.columns)}。")

    for col in ['sales_volume', 'sales_price']:
        if col in df.columns:
            df[col] = _safe_to_numeric(df[col])

    before_dedup = len(df)
    df = df.drop_duplicates()
    report['duplicates_removed'] = before_dedup - len(df)
    if report['duplicates_removed'] > 0:
        report['warnings'].append(f"删除 {report['duplicates_removed']} 行完全重复数据")

    all_cols = ['brand', 'model', 'sales_volume', 'sales_price', 'energy_type']
    missing_mask = pd.Series(False, index=df.index)
    for col in all_cols:
        if col in df.columns:
            missing_mask = missing_mask | df[col].isna()
    report['missing_count_total'] = int(missing_mask.sum())

    if missing_action == 'drop':
        before = len(df)
        df = df.dropna(subset=[c for c in all_cols if c in df.columns])
        report['missing_dropped'] = before - len(df)
        if report['missing_dropped'] > 0:
            report['warnings'].append(f"舍弃 {report['missing_dropped']} 行含有缺失值的数据")
        else:
            report['warnings'].append('未检测到缺失值，无需舍弃')

    elif missing_action == 'custom':
        for col in all_cols:
            if col in df.columns:
                missing_count = int(df[col].isna().sum())
                if missing_count > 0:
                    fill_val = custom_fill.get(col)
                    if fill_val is None:
                        if col in ['sales_volume', 'sales_price']:
                            fill_val = df[col].median()
                            if pd.isna(fill_val):
                                fill_val = 0
                        else:
                            mode_vals = df[col].mode()
                            fill_val = mode_vals.iloc[0] if len(mode_vals) > 0 else '未知'
                    if col in ['sales_volume', 'sales_price']:
                        try:
                            fill_val = float(fill_val)
                        except (ValueError, TypeError):
                            fill_val = df[col].median() if not pd.isna(df[col].median()) else 0
                    df[col] = df[col].fillna(fill_val)
                    report['missing_filled'][col] = {'count': missing_count, 'value': str(fill_val)}
                    report['warnings'].append(f"{col} 列 {missing_count} 个缺失值已填充为「{fill_val}」")

    else:
        defaults = {
            'brand': '未知品牌', 'model': '未知车型',
            'sales_volume': 0, 'sales_price': 0, 'energy_type': '油车',
        }
        for col in all_cols:
            if col in df.columns:
                missing_count = int(df[col].isna().sum())
                if missing_count > 0:
                    fill_val = defaults.get(col, '未知')
                    if col in ['sales_volume', 'sales_price']:
                        try:
                            fill_val = float(fill_val)
                        except (ValueError, TypeError):
                            fill_val = 0
                    df[col] = df[col].fillna(fill_val)
                    report['missing_filled'][col] = {'count': missing_count, 'value': str(fill_val)}
                    report['warnings'].append(f"{col} 列 {missing_count} 个缺失值已填充为默认值「{fill_val}」")

    if not report['missing_filled'] and report['missing_dropped'] == 0:
        report['warnings'].append('未检测到缺失值')

    outlier_cols = ['sales_volume', 'sales_price']
    total_outliers = 0

    for col in outlier_cols:
        if col not in df.columns:
            continue
        df[col] = df[col].astype(float)
        col_range = outlier_ranges.get(col, {})

        lo = col_range.get('min')
        hi = col_range.get('max')

        if lo is not None or hi is not None:
            lo_val = float(lo) if lo is not None else -float('inf')
            hi_val = float(hi) if hi is not None else float('inf')

            outlier_mask = (df[col] < lo_val) | (df[col] > hi_val)
            outlier_count = int(outlier_mask.sum())

            if outlier_count > 0:
                report['outliers_detected'] += outlier_count
                total_outliers += outlier_count
                median_val = float(df[col].median())
                df.loc[outlier_mask, col] = median_val
                report['outliers_handled'] += outlier_count
                report['outliers_detail'][col] = {
                    'count': outlier_count,
                    'min': lo_val if lo_val != -float('inf') else '不限',
                    'max': hi_val if hi_val != float('inf') else '不限',
                    'replaced_with': median_val,
                }
                report['warnings'].append(
                    f"{col} 列检测到 {outlier_count} 个数值超出用户设定范围，已替换为中位数 {median_val}"
                )
        else:
            if len(df) > 3:
                series = df[col].dropna()
                if series.std() > 0:
                    z_scores = np.abs(scipy_stats.zscore(series))
                    outlier_mask = z_scores > 3
                    outlier_count = int(outlier_mask.sum())
                    if outlier_count > 0:
                        median_val = float(df[col].median())
                        outlier_indices = series[outlier_mask].index
                        df.loc[outlier_indices, col] = median_val
                        report['outliers_detected'] += outlier_count
                        report['outliers_handled'] += outlier_count
                        total_outliers += outlier_count
                        report['outliers_detail'][col] = {
                            'count': outlier_count,
                            'method': 'zscore',
                            'replaced_with': median_val,
                        }
                        report['warnings'].append(
                            f"{col} 列检测到 {outlier_count} 个异常值 (|Z|>3)，已替换为中位数 {median_val}"
                        )

    if total_outliers == 0:
        report['warnings'].append('未检测到异常值')

    if 'energy_type' in df.columns:
        df['energy_type'] = df['energy_type'].astype(str).str.strip()
        df['energy_type'] = df['energy_type'].map(lambda x: ENERGY_TYPE_MAP.get(x, x))

    if 'sale_date' in df.columns:
        df['sale_date'] = df['sale_date'].astype(str).str.strip()
        def _parse(val):
            for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y-%m', '%Y/%m', '%Y.%m',
                       '%Y年%m月', '%Y年%m月%d日', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    return pd.to_datetime(val, format=fmt)
                except:
                    continue
            try:
                return pd.to_datetime(val)
            except:
                return pd.NaT
        df['sale_date'] = df['sale_date'].apply(_parse)

    report['final_rows'] = len(df)
    report['columns_final'] = list(df.columns)
    return report, df


# ──────────────────────────────────────────────
#  DataFrame → ECharts 格式转换
# ──────────────────────────────────────────────

def df_to_echarts(df: pd.DataFrame) -> Dict[str, Any]:
    result = {'records': [], 'brand_sales': [], 'energy_ratio': [], 'price_bins': [], 'sales_scatter': [], 'top_models': []}
    if df.empty:
        return result
    result['records'] = df.fillna('').to_dict(orient='records')
    if 'brand' in df.columns and 'sales_volume' in df.columns:
        brand_group = df.groupby('brand')['sales_volume'].sum().sort_values(ascending=False)
        result['brand_sales'] = [{'name': b, 'value': int(v)} for b, v in brand_group.items()]
    if 'energy_type' in df.columns:
        eg = df['energy_type'].value_counts()
        result['energy_ratio'] = [{'name': k, 'value': int(v)} for k, v in eg.items()]
    if 'sales_price' in df.columns:
        prices = df['sales_price'].dropna()
        for (lo, hi), label in zip([(0,10),(10,20),(20,30),(30,50),(50,float('inf'))],
                                   ['10万以下','10-20万','20-30万','30-50万','50万以上']):
            cnt = int(((prices >= lo) & (prices < hi)).sum())
            result['price_bins'].append({'range': label, 'count': cnt, 'lo': lo, 'hi': hi if hi != float('inf') else '∞'})
    if 'sales_price' in df.columns and 'sales_volume' in df.columns:
        result['sales_scatter'] = [[float(p), int(v)] for p, v in zip(df['sales_price'].fillna(0), df['sales_volume'].fillna(0))]
    if 'brand' in df.columns and 'model' in df.columns and 'sales_volume' in df.columns:
        top = df.nlargest(10, 'sales_volume')
        result['top_models'] = top[['brand','model','sales_volume','sales_price']].to_dict(orient='records')
    return result


def df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    df_out = df.copy()
    for col in df_out.select_dtypes(include=['datetime64','datetime64[ns]','datetimetz']).columns:
        df_out[col] = df_out[col].dt.strftime('%Y-%m-%d')
    df_out = df_out.fillna('')
    return df_out.to_dict(orient='records')


# ──────────────────────────────────────────────
#  文件读取 + 清洗一站式封装
# ──────────────────────────────────────────────

def load_and_clean(filepath: str, file_type: Optional[str] = None) -> Tuple[Dict[str, Any], pd.DataFrame]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"文件不存在: {filepath}")
    if file_type is None:
        file_type = os.path.splitext(filepath)[1].lower().lstrip('.')
    file_type = file_type.lower()
    if file_type == 'csv':
        df = _read_csv_safe(filepath)
    elif file_type == 'json':
        df = _read_json_safe(filepath)
    else:
        raise ValueError(f"不支持的文件格式: .{file_type}")
    return clean_dataframe(df)


def _read_csv_safe(filepath: str) -> pd.DataFrame:
    for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
        try:
            df = pd.read_csv(filepath, encoding=enc)
            if df.empty:
                raise ValueError("CSV 文件内容为空")
            return df
        except (UnicodeDecodeError, Exception):
            continue
    raise ValueError("无法解析 CSV 文件（尝试了 utf-8/gbk 等编码）")


def _read_json_safe(filepath: str) -> pd.DataFrame:
    for enc in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030']:
        try:
            df = pd.read_json(filepath, encoding=enc)
            if df.empty:
                raise ValueError("JSON 文件内容为空")
            return df
        except (ValueError, UnicodeDecodeError):
            continue
    for enc in ['utf-8', 'utf-8-sig', 'gbk']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                lines = [line.strip() for line in f if line.strip()]
            if not lines:
                raise ValueError("JSON 文件内容为空")
            if lines[0].startswith('['):
                data = json.loads(''.join(lines))
            else:
                data = [json.loads(line) for line in lines]
            df = pd.DataFrame(data)
            if df.empty:
                raise ValueError("JSON 文件内容为空")
            return df
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            continue
    raise ValueError("无法解析 JSON 文件")


# ──────────────────────────────────────────────
#  测试入口
# ──────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  汽车销售数据清洗模块 — 独立测试")
    print("=" * 60)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_files = [
        os.path.join(base_dir, 'data', 'sample_cars.csv'),
        os.path.join(base_dir, 'data', 'sample_cars.json'),
    ]

    for fp in test_files:
        if not os.path.exists(fp):
            print(f"\n[跳过] 文件不存在: {fp}")
            continue
        print(f"\n{'─' * 60}")
        print(f"测试文件: {os.path.basename(fp)}")
        try:
            report, df_clean = load_and_clean(fp)
            print(f"\n📊 清洗报告:")
            print(f"  原始行数:        {report['original_rows']}")
            print(f"  删除重复行:      {report['duplicates_removed']}")
            print(f"  缺失值填充:      {report['missing_filled']}")
            print(f"  异常值处理:      {report['outliers_handled']}")
            print(f"  最终行数:        {report['final_rows']}")
            for w in report.get('warnings', []):
                print(f"  ⚠ {w}")
            print(f"\n📋 清洗后前 5 行:")
            print(df_clean.head().to_string(index=False))
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print("  测试完成")