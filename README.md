# 股票投资顾问助手

**Stock Investment Advisor** —— 基于 LangGraph 多智能体的 A 股金融分析系统。3 个分析 Agent 并行执行，自动获取实时数据，生成带质量评审的综合投资分析报告。

## 系统架构

```
用户输入（自然语言）
       │
       ▼
┌─────────────────────────────────┐
│   main.py - LangGraph 编排层     │
│                                 │
│   ┌─── 并行分析 ───────────┐    │
│   │                         │    │
│   │  基本面 Agent            │    │
│   │                         │    │
│   │  技术面 Agent            │    │
│   │                         │    │
│   │  估值 Agent              │    │
│   │                         │    │
│   └────────┬────────────────┘    │
│            ▼                     │
│   汇总 Agent (生成报告)           │
│            ▼                     │
│   评审 Agent (质量评分)  ←── 新增 │
│            │                     │
│      score≥80? ──no──→ 重试      │
│            │                     │
│           END                    │
└─────────────────────────────────┘
       │
       ▼
   Markdown 分析报告
```

## 项目结构

```
Finance/
├── Financial-MCP-Agent/       # 多智能体分析系统
│   ├── src/
│   │   ├── main.py            # 入口 + LangGraph 编排
│   │   ├── agents/
│   │   │   ├── fundamental_agent.py  # 基本面分析
│   │   │   ├── technical_agent.py    # 技术分析
│   │   │   ├── value_agent.py        # 估值分析
│   │   │   ├── summary_agent.py      # 报告汇总
│   │   │   └── reviewer_agent.py     # 质量评审 (6维度评分)
│   │   ├── tools/
│   │   │   ├── mcp_client.py         # MCP 工具加载器
│   │   │   ├── mcp_config.py         # MCP 服务器配置
│   │   │   └── openrouter_config.py  # OpenRouter API 封装
│   │   └── utils/
│   │       ├── state_definition.py   # AgentState 定义
│   │       ├── context_config.py     # 上下文窗口动态适配
│   │       ├── execution_logger.py   # 执行日志系统
│   │       ├── llm_clients.py        # 多 LLM 客户端工厂
│   │       ├── logging_config.py     # 日志配置
│   │       └── log_viewer.py         # 日志查看器
│   ├── reports/               # 生成的分析报告
│   ├── logs/                  # 执行日志
│   ├── test_extraction.py     # 股票信息提取测试
│   └── .env                   # 环境变量
│
└── a-share-mcp-is-just-i-need/  # A股数据 MCP 服务
    ├── mcp_server.py           # FastMCP 服务入口
    ├── src/
    │   ├── tools/              # 25+ 数据工具
    │   │   ├── stock_market.py # 行情数据
    │   │   ├── financial_reports.py # 财报数据
    │   │   ├── analysis.py     # 分析报告
    │   │   ├── indices.py      # 指数成分股
    │   │   ├── macro_economic.py # 宏观经济
    │   │   ├── market_overview.py # 市场总览
    │   │
    │   ├── akshare_data_source.py # AkShare 数据源
    │   └── data_source_interface.py # 数据源抽象
    └── requirements.txt
```

## 核心特性

### 3 大分析维度并行执行

| Agent | 功能 | 数据来源 |
|-------|------|----------|
| **基本面** | 盈利能力、成长性、运营效率、偿债能力 | MCP 财报工具 |
| **技术面** | 价格趋势、成交量、MA/MACD/RSI、支撑阻力 | MCP K线工具 |
| **估值** | PE/PB/PS、行业对比、历史分位、内在价值 | MCP 估值工具 |

### 智能评审 + 重试

- 6 维度评分（基本面 30% + 估值 30% + 技术 20% + 完整性 10% + 相关性 5% + 一致性 5%）
- 评分 < 80 自动重试，将扣分详情反馈给总结 Agent
- 最多 2 次生成，重试覆盖同一文件不浪费磁盘

### 上下文窗口自适应

- 自动识别模型上下文大小（支持 15+ 模型）
- 根据窗口大小动态限制数据获取量
- 从小模型（8k）到大模型（128k+）均有适配

### 全面日志追溯

- 每次执行生成独立日志目录
- 记录 Agent 输入输出、LLM 交互、工具调用
- 重试报告版本自动存档。
### 自然语言输入

- 20 组正则规则提取股票代码和公司名称
- 支持 "帮我分析一下宁德时代的财务状况" 等自然语言

## 快速开始

### 1. 安装依赖

```bash
# 安装 Agent 系统依赖
cd Financial-MCP-Agent
pip install langgraph langchain-openai langchain-core langchain-mcp-adapters python-dotenv

# 安装 MCP 服务依赖
cd ../a-share-mcp-is-just-i-need
pip install -r requirements.txt
```

### 2. 配置

```bash
cd Financial-MCP-Agent
cp .env.example .env
# 编辑 .env，填入 OPENAI_COMPATIBLE_API_KEY 等
```

### 3. 运行

```bash
cd Financial-MCP-Agent
python src/main.py
```

交互式输入或命令行：
```bash
python src/main.py --command "帮我分析一下宁德时代的财务状况"
```

## 工作流细节

```
start_node
    ├── fundamental_agent (并行)
    ├── technical_agent  (并行)
    └── value_agent      (并行)
           │
           ▼
      summarizer (报告汇总)
           │
           ▼
       reviewer (质量评审)
         ╱     ╲
   ≥80分        <80分
   (结束)      (重试一次)
                  │
                  ▼
             summarizer
                  │
                  ▼
              reviewer
                  │
                 END
```

## MCP 工具列表

### 股票数据
- `get_stock_price_realtime` - 实时行情
- `get_stock_daily_kline` - K线数据
- `get_stock_basic_info` - 基本信息
- `get_stock_historical_dividend` - 历史分红

### 财务报表
- `get_profit_data` - 盈利数据
- `get_operation_data` - 运营数据
- `get_growth_data` - 成长指标
- `get_balance_data` - 资产负债表
- `get_cash_flow_data` - 现金流量
- `get_dupont_data` - 杜邦分析
- `get_stock_report_detail` - 财报详情

### 分析工具
- `get_stock_pe_pb` - PE/PB 数据
- `get_stock_tech_indicators` - 技术指标
- `get_stock_analysis` - 预置分析报告

### 宏观与指数
- `get_deposit_rate` / `get_loan_rate` / `get_reserve_requirement_ratio` - 利率
- `get_money_supply_month` / `get_money_supply_year` - 货币供应
- `get_ss50_stocks` / `get_sz50_stocks` / `get_hs300_stocks` - 指数成分
- `get_market_overview` - 市场概览
<img width="2551" height="776" alt="image" src="https://github.com/user-attachments/assets/7dfb6859-db06-45fd-b56f-9583f55a25dc" />

## 许可证

MIT License
