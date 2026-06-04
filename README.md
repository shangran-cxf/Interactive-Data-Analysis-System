# Interactive Data Analysis System — 汽车数据可视化大屏


hello world!

基于 Flask + ECharts 的汽车销售数据可视化分析平台，采用科幻科技风格设计。

## 功能特性

- **用户认证** — 注册/登录，SHA-256 密码哈希，Session 会话管理
- **数据上传** — 支持 JSON/CSV 文件上传，自动数据清洗（缺失值填充、Z-score 异常值检测）
- **多维图表** — 柱状图+折线图组合、品牌销量饼图、价格分布柱状图+环形图
- **统计总览** — 6 项核心指标卡片 + 能源类型分布 + 品牌销量排行
- **AI 分析** — 基于本地数据自动生成分析报告；配置 `DEEPSEEK_API_KEY` 可启用 DeepSeek API

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务
cd backend
python app.py

# 3. 浏览器访问
# http://localhost:5000
```

## 使用流程

1. 访问 `/register` 注册账号
2. 登录后进入主控面板
3. 上传数据文件（`data/` 目录下有示例数据）
4. 查看统计指标和可视化图表
5. 点击 AI 评价板块的 GENERATE 按钮生成分析报告

## 示例数据

项目内置两份示例数据用于测试：

| 文件 | 格式 | 记录数 | 说明 |
|------|------|--------|------|
| `data/sample_cars.json` | JSON | 46 条 | 国内主流车型销售数据 |
| `data/sample_cars.csv` | CSV | 45 条 | 扩充品牌覆盖的测试数据 |

### 数据字段

| 字段 | 说明 |
|------|------|
| 品牌 | 车辆品牌（如比亚迪、特斯拉） |
| 车型 | 具体车型名称 |
| 销量 | 月度销售辆数 |
| 价格 | 销售价格（万元） |
| 能源类型 | 油车 / 电车 / 混动 |

## 项目结构

```
├── backend/
│   ├── app.py              # Flask 应用入口
│   └── database.py         # 数据库操作层
├── frontend/
│   ├── templates/
│   │   ├── login.html      # 登录页
│   │   ├── register.html   # 注册页
│   │   └── dashboard.html  # 主控面板
│   └── static/
│       ├── css/
│       │   ├── auth.css     # 认证页样式
│       │   └── dashboard.css
│       └── js/
│           └── dashboard.js # 图表与交互逻辑
├── data/                   # 示例数据
├── database/               # SQLite 数据库（自动创建）
├── uploads/                # 上传文件暂存
└── requirements.txt
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask 2.3+ |
| 数据库 | SQLite |
| 数据处理 | Pandas + NumPy + SciPy |
| 可视化 | ECharts 5.4.3 |
| 样式 | 科幻科技风（深色主题、玻璃态、发光边框） |
| AI 接口 | DeepSeek API（可选） |

## 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
