"""
Reviewer Agent: Reviews the summary report and scores it across 6 dimensions.
评审 Agent：对总结报告进行多维度质量评分。
"""
import os
import json
import time
import re
from typing import Dict, Any
from langchain_openai import ChatOpenAI

from src.utils.state_definition import AgentState
from src.utils.logging_config import setup_logger, ERROR_ICON, SUCCESS_ICON, WAIT_ICON
from src.utils.execution_logger import get_execution_logger

logger = setup_logger(__name__)

SYSTEM_PROMPT = """\
你是金融报告质量评审专家，负责对A股上市公司分析报告进行客观评分。

**评分维度（总分100分）：**

1. 基本面覆盖度 (30分)
   - 盈利能力：毛利率、净利率、ROE、EPS等数据和分析
   - 成长性：营收/利润增速、增长驱动力
   - 运营效率：周转率、现金流质量
   - 偿债能力：资产负债率、流动/速动比率
   - 满分30分：以上全部覆盖且有具体数据支撑
   - 酌情扣分：缺某一项扣5-8分，数据空洞扣3-5分

2. 估值覆盖度 (30分)
   - 相对估值：PE、PB、PS、EV/EBITDA等指标
   - 行业对比：与同行业横向比较
   - 历史分位：与自身历史估值区间对比
   - 内在价值：目标价测算或合理估值区间
   - 满分30分：以上全部覆盖且有合理测算
   - 酌情扣分：缺某一项扣5-8分，测算不合理扣3-5分

3. 技术面覆盖度 (20分)
   - 价格趋势：近期K线趋势判断
   - 成交量分析：量价关系分析
   - 技术指标：MA/MACD/RSI/布林带等至少覆盖2项
   - 支撑阻力位：具体的数值点位
   - 满分20分：以上全部覆盖且有数据分析
   - 酌情扣分：技术数据缺失但做了推演的扣5-8分，完全缺失扣10-15分

4. 信息完整性 (10分)
   - 报告必须包含9个章节：执行摘要、公司概况、基本面分析、技术分析、
     估值分析、综合评估、风险因素、投资建议、附录
   - 满分10分：9个章节齐全
   - 每缺1个章节扣1.5分

5. 答案相关性 (5分)
   - 报告是否针对用户原始查询
   - 满分5分：高度相关，针对具体问题深入分析
   - 酌情扣分：泛泛而谈扣2-3分

6. 逻辑一致性 (5分)
   - 各维度结论是否自洽
   - 有无自相矛盾的表述
   - 满分5分：逻辑严密，前后一致
   - 酌情扣分：发现矛盾扣2-3分，严重矛盾扣4-5分

**重要规则：**
- 技术面数据缺失时（如API报错），如实扣分，不要因"数据获取困难"而放水
- 评分必须基于报告实际内容，不要因为"内容多"就给高分，要看质量
- 每个维度都要给出具体的扣分理由
- 总分必须等于各维度得分之和
- 如果总分>=80分，pass为true；否则为false

**输出格式要求（必须严格遵守）：**
你必须输出一个合法的JSON对象，包含以下所有字段，不要输出任何其他文字、markdown标记或解释：
- fundamental_score: 数字，0-30
- value_score: 数字，0-30
- technical_score: 数字，0-20
- completeness_score: 数字，0-10
- relevance_score: 数字，0-5
- consistency_score: 数字，0-5
- total_score: 数字，0-100（=上面6项之和）
- pass: 布尔值（total_score>=80为true）
- detailed_feedback: 字符串，各维度的具体扣分原因和改进建议
- section_coverage: 对象，包含10个布尔字段表示章节覆盖情况

JSON格式示例：
{"fundamental_score":25,"value_score":22,"technical_score":15,"completeness_score":8,"relevance_score":4,"consistency_score":4,"total_score":78,"pass":false,"detailed_feedback":"基本面缺少杜邦分解，扣5分。","section_coverage":{"executive_summary":true,"company_overview":true,"fundamental_analysis":true,"technical_analysis":true,"valuation_analysis":true,"comprehensive_assessment":true,"risk_factors":true,"investment_recommendation":true,"appendix":true}}\
"""


def parse_score_json(content: str) -> Dict[str, Any]:
    """解析LLM返回的JSON评分结果，兼容多种格式"""
    expected_sections = [
        "executive_summary", "company_overview", "fundamental_analysis",
        "technical_analysis", "valuation_analysis",
        "comprehensive_assessment", "risk_factors",
        "investment_recommendation", "appendix"
    ]

    # 尝试从markdown代码块中提取JSON
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        content = json_match.group(0)

    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON解析失败，尝试清理后重试: {e}")
        cleaned = re.sub(r'[^\x20-\x7E]', '', content)
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error(f"清理后仍然无法解析JSON: {content[:300]}")
            return _default_failed_review(expected_sections)

    # 兼容格式1: 嵌套结构 {"score": 78, "details": {"基本面覆盖度": {"score": 28, ...}}}
    if "score" in result and "details" in result and "fundamental_score" not in result:
        logger.info("检测到嵌套评分格式，正在转换...")
        details = result.get("details", {})
        # 中文键映射
        key_map = {
            "基本面覆盖度": "fundamental_score",
            "估值覆盖度": "value_score",
            "技术面覆盖度": "technical_score",
            "信息完整性": "completeness_score",
            "答案相关性": "relevance_score",
            "逻辑一致性": "consistency_score",
        }
        for cn_key, en_key in key_map.items():
            if cn_key in details:
                detail = details[cn_key]
                if isinstance(detail, dict):
                    result[en_key] = detail.get("score", 0)
                else:
                    result[en_key] = detail
            else:
                result[en_key] = 0

        if "score" in result:
            result["total_score"] = result["score"]
        elif "total_score" not in result:
            result["total_score"] = sum(result.get(k, 0) for k in key_map.values())

        if "pass" not in result:
            result["pass"] = result.get("total_score", 0) >= 80

        if "detailed_feedback" not in result:
            reasons = []
            for cn_key, en_key in key_map.items():
                if cn_key in details and isinstance(details[cn_key], dict):
                    reason = details[cn_key].get("reason", "")
                    if reason:
                        reasons.append(f"{cn_key}: {reason}")
            result["detailed_feedback"] = "; ".join(reasons) if reasons else str(result.get("detailed_feedback", ""))

        if "section_coverage" not in result:
            result["section_coverage"] = {}

    # 标准化字段
    required_fields = [
        "fundamental_score", "value_score", "technical_score",
        "completeness_score", "relevance_score", "consistency_score",
        "total_score", "pass", "detailed_feedback", "section_coverage"
    ]
    for field in required_fields:
        if field not in result:
            logger.warning(f"评审JSON缺少字段: {field}")
            result[field] = None if field != "total_score" else 0

    # 验证分数范围
    score_fields = {
        "fundamental_score": (0, 30),
        "value_score": (0, 30),
        "technical_score": (0, 20),
        "completeness_score": (0, 10),
        "relevance_score": (0, 5),
        "consistency_score": (0, 5),
    }
    for field, (lo, hi) in score_fields.items():
        val = result.get(field, 0)
        try:
            result[field] = max(lo, min(hi, int(float(val))))
        except (ValueError, TypeError):
            result[field] = 0

    # 计算总分
    result["total_score"] = sum(
        result.get(f, 0) for f in score_fields.keys()
    )
    result["pass"] = result["total_score"] >= 80

    # 验证section_coverage
    coverage = result.get("section_coverage")
    if not isinstance(coverage, dict):
        coverage = {s: False for s in expected_sections}
        logger.warning("section_coverage不是dict，已重置")
    else:
        for section in expected_sections:
            if section not in coverage:
                coverage[section] = False
    result["section_coverage"] = coverage

    return result


def _default_failed_review(expected_sections: list) -> Dict[str, Any]:
    """评审失败时返回默认低分结果"""
    return {
        "fundamental_score": 0, "value_score": 0, "technical_score": 0,
        "completeness_score": 0, "relevance_score": 0, "consistency_score": 0,
        "total_score": 0, "pass": False,
        "detailed_feedback": "评审系统JSON解析失败，报告质量未知",
        "section_coverage": {s: False for s in expected_sections}
    }


async def review_agent(state: AgentState) -> Dict[str, Any]:
    """
    评审总结报告的质量，返回评分详情和评分结果。
    """
    logger.info(f"{WAIT_ICON} ReviewAgent: Starting report review.")

    execution_logger = get_execution_logger()
    agent_name = "reviewer"
    agent_start_time = time.time()

    current_data = state.get("data", {})
    messages = state.get("messages", [])

    final_report = current_data.get("final_report", "")
    user_query = current_data.get("query", "")
    company_name = current_data.get("company_name", "Unknown")
    stock_code = current_data.get("stock_code", "Unknown")

    if not final_report or final_report.strip() == "":
        logger.error(f"{ERROR_ICON} ReviewAgent: No final report to review.")
        return {
            "data": current_data,
            "messages": messages,
            "review_scores": {
                "total_score": 0, "pass": False,
                "detailed_feedback": "报告内容为空，无法评审"
            }
        }

    # 获取评审模型配置
    api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY")
    base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL")
    model_name = os.getenv("OPENAI_COMPATIBLE_MODEL", "agnes-2.0-flash")

    if not all([api_key, base_url]):
        logger.error(f"{ERROR_ICON} ReviewAgent: Missing API configuration.")
        return {
            "data": current_data,
            "messages": messages,
            "review_scores": {"total_score": 0, "pass": False, "detailed_feedback": "API配置缺失"}
        }

    # 构造评审prompt
    review_user_prompt = f"""\
请评审以下关于{company_name}({stock_code})的金融分析报告。

【原始用户查询】
{user_query}

【分析报告】
{final_report}
"""

    review_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": review_user_prompt}
    ]

    # 调用评审模型
    logger.info(f"{WAIT_ICON} ReviewAgent: Calling LLM for review using {model_name}...")
    model_config = {
        "model": model_name,
        "temperature": 0,
        "max_tokens": 2000,
    }

    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        max_tokens=2000,
    )

    llm_start_time = time.time()
    llm_message = await llm.ainvoke(review_messages)
    review_content = llm_message.content
    llm_execution_time = time.time() - llm_start_time

    # 记录LLM交互
    execution_logger.log_llm_interaction(
        agent_name=agent_name,
        interaction_type="review",
        input_messages=review_messages,
        output_content=review_content,
        model_config=model_config,
        execution_time=llm_execution_time,
    )

    # 解析评分
    review_scores = parse_score_json(review_content)

    logger.info(
        f"{SUCCESS_ICON} ReviewAgent: Review complete. "
        f"Total score: {review_scores['total_score']}/100, "
        f"Pass: {review_scores['pass']}"
    )
    logger.debug(f"Review scores detail: {json.dumps(review_scores, ensure_ascii=False, indent=2)}")

    # 返回更新后的状态
    total_execution_time = time.time() - agent_start_time
    execution_logger.log_agent_complete(agent_name, {
        "total_score": review_scores["total_score"],
        "pass": review_scores["pass"],
        "report_length": len(final_report),
    }, total_execution_time, True)

    return {
        "data": current_data,
        "messages": messages,
        "review_scores": review_scores,
        "review_attempts": state.get("review_attempts", 0),
    }


# ========== 本地测试 ==========
async def test_reviewer_agent():
    """评审Agent的测试函数"""
    # 读取一份已有的报告（相对路径）
    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "reports", "report_宁德时代_300750_20260616_205210.md"
    )

    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            report_text = f.read()
    else:
        report_text = "测试报告内容"

    test_state = AgentState(
        messages=[],
        data={
            "query": "帮我分析一下宁德时代的财务状况",
            "stock_code": "sz.300750",
            "company_name": "宁德时代",
            "final_report": report_text,
        },
        metadata={},
        review_scores={},
        review_attempts=0,
    )

    result = await review_agent(test_state)
    scores = result.get("review_scores", {})
    print(f"\n{'='*60}")
    print(f"评审结果: {scores.get('total_score', 0)}/100")
    print(f"通过: {scores.get('pass', False)}")
    print(f"详细反馈: {scores.get('detailed_feedback', '')}")
    print(f"{'='*60}")

    return result


if __name__ == "__main__":
    asyncio.run(test_reviewer_agent())
