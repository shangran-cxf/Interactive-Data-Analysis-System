# 汽车销售数据分析系统 - 后端服务

## 项目简介

本项目是一个基于 Flask 的汽车销售数据分析系统后端服务，提供用户认证、数据上传、数据清洗、统计分析和 AI 评估等功能。

## 技术栈

- **框架**: Flask 2.0+
- **数据库**: SQLite3
- **数据处理**: Pandas, NumPy, SciPy
- **AI 集成**: DeepSeek API
- **文件格式**: CSV, JSON, Excel

## 项目结构

```
backend/
├── app.py          # Flask 应用主文件，包含所有 API 路由
├── database.py     # 数据库操作模块
└── README.md       # 项目说明文档
```

## 功能特性

### 1. 用户认证
- 用户注册与登录
- Session 管理
- 登录状态校验

### 2. 数据上传与处理
- 支持 CSV 和 JSON 格式文件上传
- 自动编码检测（UTF-8、GBK 等）
- 数据清洗：缺失值填充、异常值检测与处理
- 数据标准化：统一能源类型分类

### 3. 数据分析
- 基础统计数据（总记录数、品牌数、平均价格等）
- 品牌销量排行
- 价格区间分布
- 能源类型占比（油车/电车/混动）
- 销量排行榜

### 4. AI 评估报告
- 基于 DeepSeek API 生成专业分析报告
- 包含数据概况、销量分析、品牌格局、价格分析、能源结构、趋势研判和策略建议
- 内置 Mock 模式，无需 API Key 也可体验

## 快速开始

### 环境要求

- Python 3.8+
- 依赖包：见下方安装步骤

### 安装依赖

```bash
cd backend
pip install flask pandas numpy scipy openpyxl requests
```

### 启动服务

```bash
python app.py
```

服务将在 `http://localhost:5000` 启动。

### 配置环境变量（可选）

如需使用 DeepSeek AI 生成报告，设置环境变量：

```bash
set DEEPSEEK_API_KEY=your_api_key_here
```

## API 接口

### 用户认证

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录 |
| `/api/auth/logout` | POST | 用户注销 |
| `/api/auth/status` | GET | 获取登录状态 |

### 数据上传

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/data/upload` | POST | 上传数据文件（CSV/JSON） |
| `/api/data/download/<filename>` | GET | 下载清洗后的 Excel 文件 |

### 数据分析

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/data/stats` | GET | 获取统计概览 |
| `/api/data/brand-sales` | GET | 获取品牌销量排行 |
| `/api/data/price-distribution` | GET | 获取价格区间分布 |
| `/api/data/energy-ratio` | GET | 获取能源类型占比 |
| `/api/data/sales-chart` | GET | 获取销量图表数据 |
| `/api/data/vehicles` | GET | 获取车辆列表 |

### AI 评估

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/ai/evaluate` | POST | 生成 AI 分析报告 |

## 数据格式要求

上传的数据文件需包含以下列（支持中英文列名）：

| 列名 | 说明 | 必填 |
|------|------|------|
| brand / 品牌 | 汽车品牌名称 | 是 |
| model / 车型 / 型号 | 车型名称 | 是 |
| sales_volume / sales / 销量 | 销售数量 | 是 |
| sales_price / price / 价格 | 销售价格（万元） | 是 |
| energy_type / energy / 能源 | 能源类型（油车/电车/混动） | 是 |

### 示例 CSV

```csv
品牌,车型,销量,价格,能源类型
丰田,卡罗拉,15000,12.5,油车
比亚迪,汉EV,8000,25.0,电车
特斯拉,Model 3,6000,28.0,电车
```

## 数据库结构

### users 表
- id: 用户ID（主键）
- username: 用户名（唯一）
- password: 密码（SHA256 哈希）
- created_at: 创建时间

### vehicles 表
- id: 记录ID（主键）
- user_id: 用户ID（外键）
- brand: 品牌
- model: 车型
- sales_volume: 销量
- sales_price: 价格
- energy_type: 能源类型
- created_at / updated_at: 时间戳

### uploads 表
- id: 记录ID（主键）
- user_id: 用户ID（外键）
- filename: 上传文件名
- record_count: 记录数
- created_at: 创建时间

## 安全特性

- 密码使用 SHA256 哈希存储
- Session 使用随机密钥加密
- 文件上传类型白名单限制
- 请求大小限制（16MB）
- 登录状态装饰器保护

## 许可证

MIT License