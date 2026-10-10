"""解析任务模块 (witty-log-analyzer 接入): 指定解析器的事件化分析.

与 diagnosis 模块的分工:
- diagnosis: detect() 自动探测格式, LogEntry 供规则/指标引擎 (通用诊断)
- analyze:   用户显式指定 parser_type, ParsedEvent 供事件入库/聚合/可视化 (witty 体系)
两者均沿用插件注册制约定 (模块级注册表 + @register).
"""
from app.modules.analyze.parsers import ANALYZE_PARSERS, AnalyzeParser, ParsedEvent, parser_list

__all__ = ["ANALYZE_PARSERS", "AnalyzeParser", "ParsedEvent", "parser_list"]
