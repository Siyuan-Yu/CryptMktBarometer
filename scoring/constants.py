"""
计分常量：分项权重、关键词分类
"""

# 分项满分（合计 100）
WEIGHT_MACRO = 40
WEIGHT_REGULATION = 20
WEIGHT_FUNDING = 25
WEIGHT_FUNDAMENTALS = 15

# 监管类资讯关键词（标题匹配）
REGULATION_KEYWORDS = (
    "sec",
    "etf",
    "regulation",
    "regulatory",
    "lawsuit",
    "sue",
    "ban",
    "banned",
    "approval",
    "approved",
    "congress",
    "senate",
    "cftc",
    "fca",
    "legislation",
    "bill",
    "enforcement",
    "fine",
    "settlement",
    "license",
    "licence",
    "compliance",
    "监管",
    "法案",
    "起诉",
)

# 基本面（ETH/SOL 生态）资讯关键词
FUNDAMENTALS_KEYWORDS = (
    "ethereum",
    "eth ",
    " eth",
    "solana",
    " sol ",
    "staking",
    "stake",
    "validator",
    "defi",
    "layer 2",
    "l2",
    "upgrade",
    "mainnet",
    "hack",
    "exploit",
    "bridge",
    "sol",
    "质押",
    "以太坊",
)
