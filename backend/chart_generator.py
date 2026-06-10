# -*- coding: utf-8 -*-
"""
汽车销售统计图生成模块
基于 Matplotlib 实现，支持多种自定义参数
作者: 小组合作项目 - 第二部分
"""

import os
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd


# ============================================================
# 中文字体设置 —— 确保图表能正确显示中文
# ============================================================
def setup_chinese_font():
    """自动查找并设置可用的中文字体"""
    # 常见中文字体列表 (按优先级排序)
    chinese_fonts = [
        'Microsoft YaHei', 'SimHei', 'SimSun', 'KaiTi', 'FangSong',
        'Arial Unicode MS', 'PingFang SC', 'Hiragino Sans GB',
        'WenQuanYi Micro Hei', 'WenQuanYi Zen Hei',
        'Noto Sans CJK SC', 'Source Han Sans CN'
    ]

    # 查找系统中已安装的字体
    available_fonts = {f.name for f in fm.fontManager.ttflist}
    for font in chinese_fonts:
        if font in available_fonts:
            plt.rcParams['font.sans-serif'] = [font]
            plt.rcParams['axes.unicode_minus'] = False
            return font

    # 如果都没找到，使用默认字体并尽量兼容
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    return 'Default'


# ============================================================
# 颜色主题 —— 多种配色方案供用户选择
# 注意: matplotlib 使用 (R, G, B, A) 元组，范围 0-1
# ============================================================
COLOR_THEMES = {
    'tech': {
        'name': '科技蓝',
        'bar': ['#1f77b4', '#4c9fd9', '#7bb8e0', '#a8d1e8', '#d6eaf0'],
        'line': '#ff7f0e',
        'bg': '#0f1419',
        'text': '#c8cdd4',
        'grid': (0.706, 0.784, 0.824, 0.15)
    },
    'nature': {
        'name': '自然绿',
        'bar': ['#2ca02c', '#5cb85c', '#8cc98c', '#b5dcb5', '#dcefdc'],
        'line': '#d62728',
        'bg': '#f8faf8',
        'text': '#2d3a2d',
        'grid': (0.173, 0.627, 0.173, 0.12)
    },
    'warm': {
        'name': '暖橙系',
        'bar': ['#ff7f0e', '#ffa04c', '#ffc07b', '#ffdbaa', '#fff0d6'],
        'line': '#9467bd',
        'bg': '#fffaf2',
        'text': '#5c4028',
        'grid': (1.0, 0.498, 0.055, 0.12)
    },
    'classic': {
        'name': '经典黑白',
        'bar': ['#333333', '#555555', '#777777', '#999999', '#bbbbbb'],
        'line': '#c0392b',
        'bg': '#ffffff',
        'text': '#333333',
        'grid': (0.0, 0.0, 0.0, 0.08)
    },
    'rainbow': {
        'name': '彩虹色',
        'bar': ['#e74c3c', '#e67e22', '#f1c40f', '#27ae60', '#3498db', '#9b59b6'],
        'line': '#2c3e50',
        'bg': '#ffffff',
        'text': '#333333',
        'grid': (0.0, 0.0, 0.0, 0.06)
    }
}


# ============================================================
# 图表类型定义
# ============================================================
CHART_TYPES = {
    'bar': '柱状图 (销量对比)',
    'line': '折线图 (趋势分析)',
    'bar_line': '柱线双轴图 (销量+价格)',
    'pie': '饼图 (销量占比)',
    'scatter': '散点图 (销量vs价格)',
    'horizontal_bar': '横向柱状图',
    'stacked_bar': '堆叠柱状图 (按能源类型)',
    'radar': '雷达图 (多品牌对比)'
}


# ============================================================
# 核心: 生成图表的主函数
# ============================================================
def generate_chart(vehicle_data, params):
    """
    根据用户自定义参数生成图表

    参数:
        vehicle_data: list[dict] —— 车辆数据, 每项包含 brand, model, sales_volume, sales_price, energy_type
        params: dict —— 用户自定义参数, 包含:
            - chart_type: 图表类型
            - theme: 颜色主题
            - top_n: 显示前 N 项
            - sort_by: 排序字段 (sales_volume / sales_price / brand)
            - sort_order: 排序方式 (asc / desc)
            - title: 图表标题
            - show_value: 是否显示数值标签
            - grid_on: 是否显示网格线
            - energy_filter: 能源类型筛选 (all / 油车 / 电车 / 混动)

    返回:
        dict: { 'success': bool, 'image_base64': str, 'info': dict }
    """

    # 1. 初始化中文字体
    font_used = setup_chinese_font()

    # 2. 获取并清洗数据
    if not vehicle_data or len(vehicle_data) == 0:
        return {'success': False, 'error': '没有数据可展示', 'info': {'font': font_used}}

    df = pd.DataFrame(vehicle_data)

    # 3. 应用筛选条件
    energy_filter = params.get('energy_filter', 'all')
    if energy_filter != 'all':
        df = df[df['energy_type'] == energy_filter]

    if len(df) == 0:
        return {'success': False, 'error': '筛选条件下无数据', 'info': {'font': font_used}}

    # 4. 应用排序
    sort_by = params.get('sort_by', 'sales_volume')
    sort_order = params.get('sort_order', 'desc')
    ascending = (sort_order == 'asc')

    if sort_by == 'brand':
        df = df.sort_values('brand', ascending=ascending)
    elif sort_by == 'sales_price':
        df = df.sort_values('sales_volume', ascending=ascending)
    else:
        df = df.sort_values('sales_volume', ascending=ascending)

    # 5. 应用 Top N 限制
    top_n = int(params.get('top_n', 15))
    if top_n > 0 and top_n < len(df):
        df = df.head(top_n) if not ascending else df.tail(top_n)

    # 6. 获取颜色主题
    theme_key = params.get('theme', 'tech')
    theme = COLOR_THEMES.get(theme_key, COLOR_THEMES['tech'])

    # 7. 根据图表类型调用对应生成函数
    chart_type = params.get('chart_type', 'bar')
    title = params.get('title', '汽车销售统计图')
    show_value = params.get('show_value', True)
    grid_on = params.get('grid_on', False)

    # 创建画布
    fig, ax = plt.subplots(figsize=(11, 6), dpi=100)
    fig.patch.set_facecolor(theme['bg'])
    ax.set_facecolor(theme['bg'])

    try:
        if chart_type == 'bar':
            _plot_bar(fig, ax, df, theme, title, show_value, grid_on)
        elif chart_type == 'line':
            _plot_line(fig, ax, df, theme, title, show_value, grid_on)
        elif chart_type == 'bar_line':
            _plot_bar_line(fig, ax, df, theme, title, show_value, grid_on)
        elif chart_type == 'pie':
            _plot_pie(fig, ax, df, theme, title, show_value)
        elif chart_type == 'scatter':
            _plot_scatter(fig, ax, df, theme, title, show_value, grid_on)
        elif chart_type == 'horizontal_bar':
            _plot_horizontal_bar(fig, ax, df, theme, title, show_value, grid_on)
        elif chart_type == 'stacked_bar':
            _plot_stacked_bar(fig, ax, df, theme, title, show_value, grid_on)
        elif chart_type == 'radar':
            _plot_radar(fig, ax, df, theme, title, show_value)
        else:
            _plot_bar(fig, ax, df, theme, title, show_value, grid_on)

        # 8. 转换为 base64 图片 (供前端网页展示)
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format='png', bbox_inches='tight', facecolor=theme['bg'])
        plt.close(fig)
        buf.seek(0)
        image_base64 = base64.b64encode(buf.read()).decode('utf-8')

        # 9. 返回结果与统计信息
        info = {
            'font_used': font_used,
            'chart_type': chart_type,
            'theme': theme['name'],
            'data_count': len(df),
            'total_sales': int(df['sales_volume'].sum()),
            'avg_price': round(df['sales_price'].mean(), 2),
            'title': title
        }

        return {'success': True, 'image_base64': image_base64, 'info': info}

    except Exception as e:
        plt.close(fig)
        return {'success': False, 'error': f'图表生成失败: {str(e)}', 'info': {'font': font_used}}


# ============================================================
# 以下为各类图表的具体绘制函数
# ============================================================

def _apply_common_style(ax, theme, title, grid_on):
    """应用通用样式 (标题, 颜色, 网格)"""
    ax.set_title(title, color=theme['text'], fontsize=15, fontweight='bold', pad=15)
    ax.tick_params(axis='x', colors=theme['text'], labelsize=9)
    ax.tick_params(axis='y', colors=theme['text'], labelsize=9)
    grid_color = theme['grid']
    for spine in ax.spines.values():
        spine.set_color(grid_color[:3] if isinstance(grid_color, tuple) else grid_color)
    if grid_on:
        ax.grid(True, alpha=0.3, color=grid_color[:3] if isinstance(grid_color, tuple) else grid_color, linestyle='--')


def _plot_bar(fig, ax, df, theme, title, show_value, grid_on):
    """柱状图: 展示各车型销量"""
    labels = [f"{row.brand[:4]}{row.model[:6]}" for _, row in df.iterrows()]
    x = range(len(labels))
    bars = ax.bar(x, df['sales_volume'], color=theme['bar'][0], edgecolor='none', width=0.7, alpha=0.9)

    # 为每个柱子设置不同颜色
    for i, bar in enumerate(bars):
        bar.set_facecolor(theme['bar'][i % len(theme['bar'])])

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=35, ha='right')
    ax.set_ylabel('销售辆数', color=theme['text'])

    if show_value:
        for i, v in enumerate(df['sales_volume']):
            ax.text(i, v, f'{int(v):,}', ha='center', va='bottom', fontsize=8, color=theme['text'])

    _apply_common_style(ax, theme, title, grid_on)


def _plot_line(fig, ax, df, theme, title, show_value, grid_on):
    """折线图: 展示销量趋势"""
    labels = [f"{row.brand[:4]}{row.model[:6]}" for _, row in df.iterrows()]
    x = range(len(labels))

    ax.plot(x, df['sales_volume'], color=theme['line'], linewidth=2.5, marker='o',
            markersize=7, markerfacecolor=theme['bar'][0], markeredgecolor='white', markeredgewidth=1.5)

    ax.fill_between(x, df['sales_volume'], alpha=0.2, color=theme['line'])

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=35, ha='right')
    ax.set_ylabel('销售辆数', color=theme['text'])

    if show_value:
        for i, v in enumerate(df['sales_volume']):
            ax.annotate(f'{int(v):,}', xy=(i, v), xytext=(0, 8), textcoords='offset points',
                       ha='center', fontsize=8, color=theme['text'])

    _apply_common_style(ax, theme, title, grid_on)


def _plot_bar_line(fig, ax, df, theme, title, show_value, grid_on):
    """柱线双轴图: 柱子=销量, 折线=价格"""
    labels = [f"{row.brand[:4]}{row.model[:6]}" for _, row in df.iterrows()]
    x = range(len(labels))

    # 柱状图: 销量
    bars = ax.bar(x, df['sales_volume'], color=theme['bar'][0], width=0.6, alpha=0.85, label='销售辆数')
    for i, bar in enumerate(bars):
        bar.set_facecolor(theme['bar'][i % len(theme['bar'])])
    ax.set_xlabel('车型')
    ax.set_ylabel('销售辆数', color=theme['text'])
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=35, ha='right')

    # 折线图: 价格 (右侧坐标轴)
    ax2 = ax.twinx()
    ax2.plot(x, df['sales_price'], color=theme['line'], linewidth=2, marker='s',
             markersize=6, label='价格(万元)')
    ax2.set_ylabel('价格(万元)', color=theme['line'])
    ax2.tick_params(axis='y', colors=theme['line'], labelsize=9)
    grid_color = theme['grid']
    for spine in ax2.spines.values():
        spine.set_color(grid_color[:3] if isinstance(grid_color, tuple) else grid_color)

    if show_value:
        for i, v in enumerate(df['sales_volume']):
            ax.text(i, v, f'{int(v):,}', ha='center', va='bottom', fontsize=7, color=theme['text'])
        for i, v in enumerate(df['sales_price']):
            ax2.annotate(f'{v}万', xy=(i, v), xytext=(0, 8), textcoords='offset points',
                        ha='center', fontsize=7, color=theme['line'])

    # 图例
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=9)

    _apply_common_style(ax, theme, title, grid_on)


def _plot_pie(fig, ax, df, theme, title, show_value):
    """饼图: 展示各车型销量占比"""
    sizes = df['sales_volume'].values
    labels = [f"{row.brand[:4]}{row.model[:6]}" for _, row in df.iterrows()]
    colors = [theme['bar'][i % len(theme['bar'])] for i in range(len(sizes))]

    # 销量太少的合并到"其他"
    total = sizes.sum()
    threshold = total * 0.02
    main_sizes, main_labels, main_colors = [], [], []
    other_size = 0

    for i, s in enumerate(sizes):
        if s >= threshold:
            main_sizes.append(int(s))
            main_labels.append(labels[i])
            main_colors.append(colors[i])
        else:
            other_size += int(s)

    if other_size > 0:
        main_sizes.append(other_size)
        main_labels.append('其他')
        main_colors.append('#888888')

    wedges, texts, autotexts = ax.pie(
        main_sizes, labels=main_labels, colors=main_colors,
        autopct='%1.1f%%' if show_value else '',
        startangle=90, pctdistance=0.75,
        wedgeprops=dict(width=0.5, edgecolor=theme['bg'], lw=2)
    )

    for t in texts:
        t.set_color(theme['text'])
        t.set_fontsize(9)
    for t in autotexts:
        t.set_color('white')
        t.set_fontsize(8)
        t.set_fontweight('bold')

    ax.set_title(title, color=theme['text'], fontsize=15, fontweight='bold', pad=15)


def _plot_scatter(fig, ax, df, theme, title, show_value, grid_on):
    """散点图: X=价格, Y=销量, 气泡大小=价格权重"""
    prices = df['sales_price'].values
    volumes = df['sales_volume'].values
    labels = [f"{row.brand[:4]}{row.model[:6]}" for _, row in df.iterrows()]

    # 气泡大小 (归一化到合理范围)
    sizes = (prices / prices.max()) * 400 + 50

    colors_scatter = [theme['bar'][i % len(theme['bar'])] for i in range(len(prices))]

    scatter = ax.scatter(prices, volumes, s=sizes, c=colors_scatter,
                        alpha=0.75, edgecolors='white', linewidths=1.2, zorder=5)

    ax.set_xlabel('价格(万元)', color=theme['text'])
    ax.set_ylabel('销售辆数', color=theme['text'])

    if show_value:
        for i, (p, v, label) in enumerate(zip(prices, volumes, labels)):
            ax.annotate(label, xy=(p, v), xytext=(5, 5), textcoords='offset points',
                       fontsize=7, color=theme['text'], alpha=0.8)

    _apply_common_style(ax, theme, title, grid_on)


def _plot_horizontal_bar(fig, ax, df, theme, title, show_value, grid_on):
    """横向柱状图: 便于品牌排名展示"""
    df_sorted = df.sort_values('sales_volume', ascending=True)
    labels = [f"{row.brand[:4]}{row.model[:6]}" for _, row in df_sorted.iterrows()]
    y = range(len(labels))

    bars = ax.barh(y, df_sorted['sales_volume'], height=0.7, alpha=0.9)
    for i, bar in enumerate(bars):
        bar.set_facecolor(theme['bar'][i % len(theme['bar'])])

    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel('销售辆数', color=theme['text'])

    if show_value:
        for i, v in enumerate(df_sorted['sales_volume']):
            ax.text(v, i, f' {int(v):,}', va='center', fontsize=9, color=theme['text'])

    _apply_common_style(ax, theme, title, grid_on)


def _plot_stacked_bar(fig, ax, df, theme, title, show_value, grid_on):
    """堆叠柱状图: 按能源类型分组展示各品牌销量"""
    # 按品牌聚合, 再按能源类型堆叠
    df_agg = df.groupby(['brand', 'energy_type'])['sales_volume'].sum().unstack(fill_value=0)

    brands = df_agg.index.tolist()
    energy_types = df_agg.columns.tolist()
    x = range(len(brands))

    bottom = np.zeros(len(brands))
    for i, energy in enumerate(energy_types):
        values = df_agg[energy].values
        bars = ax.bar(x, values, bottom=bottom, label=energy,
                     color=theme['bar'][i % len(theme['bar'])], alpha=0.85, width=0.6)
        bottom += values

    ax.set_xticks(list(x))
    ax.set_xticklabels([b[:6] for b in brands], rotation=25, ha='right')
    ax.set_ylabel('销售辆数', color=theme['text'])
    ax.legend(loc='upper right', fontsize=9)

    if show_value:
        for i, total in enumerate(bottom):
            if total > 0:
                ax.text(i, total, f'{int(total):,}', ha='center', va='bottom', fontsize=8, color=theme['text'])

    _apply_common_style(ax, theme, title, grid_on)


def _plot_radar(fig, ax, df, theme, title, show_value):
    """雷达图: 展示品牌多维度指标 (销量, 价格等归一化后)"""
    # 先关闭原 ax, 创建极坐标 ax
    ax.remove()
    ax_radar = fig.add_subplot(111, projection='polar')
    ax_radar.set_facecolor(theme['bg'])

    # 按品牌聚合
    brand_stats = df.groupby('brand').agg({
        'sales_volume': 'sum',
        'sales_price': 'mean',
        'model': 'count'
    }).reset_index()
    brand_stats.columns = ['brand', 'total_sales', 'avg_price', 'model_count']

    # 取 Top 6 品牌
    brand_stats = brand_stats.sort_values('total_sales', ascending=False).head(6)

    if len(brand_stats) < 3:
        ax_radar.text(0.5, 0.5, '品牌数量不足\n无法绘制雷达图', ha='center', va='center',
                     transform=ax_radar.transAxes, color=theme['text'], fontsize=12)
        ax_radar.set_title(title, color=theme['text'], fontsize=15, fontweight='bold', pad=15)
        return

    # 定义指标维度 (归一化到 0-100)
    categories = ['总销量', '平均价格', '车型数量', '性价比指数']

    def normalize(series):
        if series.max() == series.min():
            return [50] * len(series)
        return ((series - series.min()) / (series.max() - series.min()) * 100).tolist()

    # 为每个品牌计算 4 个指标
    brands_data = []
    for _, row in brand_stats.iterrows():
        # 性价比指数: 销量 / 价格 (越高表示性价比越好)
        value_index = row['total_sales'] / row['avg_price'] if row['avg_price'] > 0 else 0
        brands_data.append([row['total_sales'], row['avg_price'], row['model_count'], value_index])

    brands_array = np.array(brands_data)

    # 归一化每列
    normed = np.zeros_like(brands_array, dtype=float)
    for col in range(brands_array.shape[1]):
        col_data = brands_array[:, col]
        if col_data.max() != col_data.min():
            normed[:, col] = (col_data - col_data.min()) / (col_data.max() - col_data.min()) * 80 + 20
        else:
            normed[:, col] = 50

    # 设置极坐标角度
    angles = [n / float(len(categories)) * 2 * np.pi for n in range(len(categories))]
    angles += angles[:1]  # 闭合

    # 绘制每个品牌的雷达线
    for i, (brand, data) in enumerate(zip(brand_stats['brand'], normed)):
        data_closed = list(data) + [data[0]]
        color = theme['bar'][i % len(theme['bar'])]
        ax_radar.plot(angles, data_closed, color=color, linewidth=2, label=brand[:8], marker='o', markersize=5)
        ax_radar.fill(angles, data_closed, color=color, alpha=0.15)

    # 设置标签
    ax_radar.set_xticks(angles[:-1])
    ax_radar.set_xticklabels(categories, color=theme['text'], fontsize=10)
    ax_radar.set_ylim(0, 110)
    ax_radar.set_yticks([25, 50, 75, 100])
    ax_radar.set_yticklabels(['', '', '', ''], color=theme['text'])
    grid_color = theme['grid']
    spine_color = grid_color[:3] if isinstance(grid_color, tuple) else grid_color
    ax_radar.grid(color=spine_color, alpha=0.4)
    ax_radar.spines['polar'].set_color(spine_color)

    ax_radar.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=9,
                   frameon=False, labelcolor=theme['text'])
    ax_radar.set_title(title, color=theme['text'], fontsize=15, fontweight='bold', pad=20)


# ============================================================
# 获取可用参数配置 (供前端下拉菜单使用)
# ============================================================
def get_config():
    """返回图表配置信息供前端构建 UI"""
    return {
        'chart_types': CHART_TYPES,
        'themes': {k: v['name'] for k, v in COLOR_THEMES.items()},
        'sort_fields': {
            'sales_volume': '按销量',
            'sales_price': '按价格',
            'brand': '按品牌'
        },
        'energy_filters': {
            'all': '全部能源类型',
            '油车': '仅油车',
            '电车': '仅电车',
            '混动': '仅混动'
        },
        'default_params': {
            'chart_type': 'bar',
            'theme': 'tech',
            'top_n': 15,
            'sort_by': 'sales_volume',
            'sort_order': 'desc',
            'title': '汽车销售统计图',
            'show_value': True,
            'grid_on': True,
            'energy_filter': 'all'
        }
    }
