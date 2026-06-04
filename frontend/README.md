# 前端项目说明

## 项目概述

汽车数据可视化平台前端应用，基于 Flask 框架构建，使用 ECharts 实现数据图表展示。

## 技术栈

- **后端框架**: Flask (Jinja2 模板引擎)
- **图表库**: ECharts 5.4.3
- **样式**: CSS3 (深色主题)
- **字体**: Noto Sans SC

## 目录结构

```
frontend/
├── static/
│   ├── css/
│   │   ├── auth.css          # 登录/注册页面样式
│   │   └── dashboard.css     # 数据看板页面样式
│   └── js/
│       └── dashboard.js       # 数据看板交互逻辑
└── templates/
    ├── login.html            # 登录页面
    ├── register.html          # 注册页面
    └── dashboard.html         # 数据看板主页面
```

## 页面说明

### 1. 登录页面 (login.html)

用户登录入口，包含用户名和密码验证表单。

### 2. 注册页面 (register.html)

新用户注册入口，包含用户名、密码和确认密码字段。

### 3. 数据看板页面 (dashboard.html)

系统核心页面，包含以下功能模块：

#### 主要功能

| 模块 | 描述 |
|-----|------|
| **数据上传** | 支持 CSV/JSON 格式文件上传，自动进行数据清洗 |
| **汽车销售统计图** | 柱状图与折线图组合，展示车型销量与价格走势 |
| **数据总体评价** | 显示车辆总数、销量冠军、最高销售额等统计指标 |
| **能源类型分布** | 展示油车、电车、混动车型占比 |
| **品牌销量排行** | 显示销量前 7 名的汽车品牌排名 |
| **品牌销量占比** | 玫瑰图展示各品牌销量占比 |
| **价格占比分析** | 水平柱状图和环形图展示价格区间分布 |
| **AI 评价** | 调用后端 AI 接口生成数据分析报告 |

#### 图表交互功能

- **柱状图/折线图切换**: 点击按钮切换图表显示模式
- **车型筛选**: 支持多选车型进行数据过滤
- **数据缩放**: 当数据量超过 18 条时自动显示缩放滑块
- **自动旋转**: 饼图和环形图支持自动高亮旋转效果

## 核心文件说明

### dashboard.js

主要 JavaScript 逻辑文件，包含以下功能：

#### 图表初始化

```javascript
initAllCharts()  // 初始化四个 ECharts 实例
```

#### 图表更新函数

- `updateSalesChart(data)` - 更新销售趋势组合图
- `updateBrandPie(data)` - 更新品牌销量饼图
- `updatePriceCharts(data)` - 更新价格分布图表
- `updateStats(stats)` - 更新统计数据
- `updateBrandRanking(data)` - 更新品牌排行榜

#### 数据请求

- `refreshAllData()` - 并行请求所有数据接口并更新图表
- `requestAI()` - 调用 AI 分析接口

#### 文件上传

- `handleFile(file)` - 处理上传的 CSV/JSON 文件
- `showReport(report, downloadUrl)` - 显示数据清洗报告

### dashboard.css

深色科技风格主题设计，主要特性：

- 深蓝色背景 (`#0a1a30`)
- 半透明卡片设计
- 毛玻璃效果 (`backdrop-filter: blur`)
- 科技感边框装饰
- 响应式布局适配

## 数据格式要求

### 上传 CSV 格式

```csv
brand,model,sales_volume,sales_price,energy_type
比亚迪,秦PLUS,30000,10.5,电车
特斯拉,Model Y,50000,26.0,电车
```

### 上传 JSON 格式

```json
[
  {
    "brand": "比亚迪",
    "model": "秦PLUS",
    "sales_volume": 30000,
    "sales_price": 10.5,
    "energy_type": "电车"
  }
]
```

## API 接口

前端通过 `/api/*` 路径调用后端接口：

| 接口路径 | 方法 | 功能 |
|---------|------|------|
| `/api/auth/login` | POST | 用户登录 |
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/logout` | POST | 用户登出 |
| `/api/data/upload` | POST | 上传数据文件 |
| `/api/data/stats` | GET | 获取统计数据 |
| `/api/data/brand-sales` | GET | 获取品牌销量 |
| `/api/data/price-distribution` | GET | 获取价格分布 |
| `/api/data/energy-ratio` | GET | 获取能源类型占比 |
| `/api/data/sales-chart` | GET | 获取图表数据 |
| `/api/ai/evaluate` | POST | 获取 AI 分析报告 |

## 运行方式

1. 确保后端服务已启动（默认端口 5000）
2. 在浏览器中访问登录页面
3. 登录后进入数据看板页面

## 浏览器兼容性

- Chrome 80+
- Firefox 75+
- Edge 80+
- Safari 13+

## 第三方依赖

- ECharts 5.4.3 (CDN: jsdelivr)
- Google Fonts: Noto Sans SC
