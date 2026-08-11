import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shuttlecube.application.operations.model_client import ModelClient, ModelRequest
from shuttlecube.domain.operations.models import OperationsReportSnapshot

PROMPT_VERSION = 1


class NarrativeStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_template: str = Field(min_length=1, max_length=2000)
    metric_refs: list[str] = Field(default_factory=list, max_length=12)
    anomaly_ids: list[str] = Field(default_factory=list, max_length=12)


class RecommendationDraft(NarrativeStatement):
    priority: Literal["low", "medium", "high"]


class ReportNarrativeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: NarrativeStatement
    anomaly_explanations: list[NarrativeStatement] = Field(default_factory=list, max_length=12)
    recommendations: list[RecommendationDraft] = Field(default_factory=list, max_length=12)


def _metric_map(snapshot: OperationsReportSnapshot) -> dict[str, dict[str, object]]:
    return {
        str(item["metric_ref"]): item
        for item in snapshot.metrics
        if isinstance(item, dict) and item.get("metric_ref")
    }


def _format_metric(metric: dict[str, object]) -> str:
    value = str(metric.get("value", "0"))
    precision = int(metric.get("display_precision", 2))
    unit = metric.get("unit")
    try:
        number = float(value)
    except ValueError:
        return value
    if unit == "cny":
        return f"¥{number:,.{precision}f}"
    if unit == "ratio":
        return f"{number * 100:.{precision}f}%"
    if unit == "hour":
        return f"{number:.{precision}f} 小时"
    if unit == "lesson_unit":
        return f"{number:.{precision}f} 课时"
    return f"{number:.{precision}f}"


def _render_statement(
    statement: NarrativeStatement,
    *,
    metrics: dict[str, dict[str, object]],
    anomalies: set[str],
) -> str:
    if any(ref not in metrics for ref in statement.metric_refs):
        raise ValueError("narrative referenced an unknown metric")
    if any(anomaly_id not in anomalies for anomaly_id in statement.anomaly_ids):
        raise ValueError("narrative referenced an unknown anomaly")
    text_without_placeholders = statement.text_template
    for ref in statement.metric_refs:
        token = "{{" + ref + "}}"
        if token not in text_without_placeholders:
            raise ValueError("every metric reference must have a template placeholder")
        text_without_placeholders = text_without_placeholders.replace(token, "")
    if re.search(r"\d", text_without_placeholders):
        raise ValueError("model narrative cannot introduce literal numbers")
    rendered = statement.text_template
    for ref in statement.metric_refs:
        rendered = rendered.replace("{{" + ref + "}}", _format_metric(metrics[ref]))
    return rendered


def generate_report_narrative(
    snapshot: OperationsReportSnapshot,
    *,
    model_client: ModelClient,
    model_profile: str,
) -> tuple[dict[str, object], dict[str, int], dict[str, object]]:
    metrics = _metric_map(snapshot)
    anomaly_ids = {
        str(item["anomaly_id"])
        for item in snapshot.anomalies
        if isinstance(item, dict) and item.get("anomaly_id")
    }
    request = ModelRequest(
        workflow_key="operations.report_narrative.v1",
        prompt_version=PROMPT_VERSION,
        system_instruction=(
            "解释给定经营报告快照。不得计算、改写或补充任何数字和异常；"
            "数字只能使用 {{metric_ref}} 占位符并同时列入 metric_refs。"
            "建议只能是人工复核、跟进或规划建议，不得声称已改价、退款、扣课时或改排期。"
        ),
        input_data={
            "snapshot_id": snapshot.id,
            "evidence_hash": snapshot.evidence_hash,
            "metrics": snapshot.metrics,
            "anomalies": snapshot.anomalies,
            "breakdowns": snapshot.breakdowns,
            "caveats": snapshot.caveats or [],
        },
        output_schema=ReportNarrativeDraft,
        model_profile=model_profile,
    )
    response = model_client.generate(request)
    draft = ReportNarrativeDraft.model_validate(response.output)
    summary = _render_statement(draft.summary, metrics=metrics, anomalies=anomaly_ids)
    explanations = [
        {
            "text": _render_statement(item, metrics=metrics, anomalies=anomaly_ids),
            "metric_refs": item.metric_refs,
            "anomaly_ids": item.anomaly_ids,
        }
        for item in draft.anomaly_explanations
    ]
    forbidden = ("自动退款", "直接退款", "自动改价", "直接改价", "扣课时", "自动排课", "已执行")
    recommendations: list[dict[str, object]] = []
    for item in draft.recommendations:
        rendered = _render_statement(item, metrics=metrics, anomalies=anomaly_ids)
        if any(fragment in rendered for fragment in forbidden):
            raise ValueError("narrative recommendation crossed a controlled action boundary")
        recommendations.append(
            {
                "text": rendered,
                "priority": item.priority,
                "metric_refs": item.metric_refs,
                "anomaly_ids": item.anomaly_ids,
            }
        )
    return (
        {
            "summary": summary,
            "anomaly_explanations": explanations,
            "recommendations": recommendations,
        },
        response.usage,
        response.provider_metadata,
    )

