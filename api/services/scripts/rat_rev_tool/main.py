"""KPI and barrier calculations used by the integration module.

This is the reduced GitHub version of the original RAT/REV service module.
Only the models and functions called by ``module_integration.py`` are kept.
"""
from enum import Enum
import math
from typing import Dict, List, Optional

from pydantic import BaseModel, confloat, conint

from .Barriers_Disadvantages import Barriers_disadvantages
from .Economic_KPIs import Economic_KPIs
from .Environmental_KPIs import Environmental_KPIs
from .Social_KPIs import Social_KPIs
from .Technological_KPIs import Technological_KPIs
from .incentives import incentives
from .incentives_id import incentives_id


KPI_CATEGORIES = {
    "Economic_KPIs": Economic_KPIs,
    "Environmental_KPIs": Environmental_KPIs,
    "Social_KPIs": Social_KPIs,
    "Technological_KPIs": Technological_KPIs,
}


class KPICategory(str, Enum):
    economic = "Economic_KPIs"
    environmental = "Environmental_KPIs"
    social = "Social_KPIs"
    technological = "Technological_KPIs"


class ProgressStage(str, Enum):
    very_early_stage = "Very early stage"
    early_progress = "Early progress"
    midway = "Midway"
    advanced = "Advanced"
    near_completion = "Near/at completion"


class BarriersCategory(str, Enum):
    resource_scarcity = "Resource Scarcity"
    public_resistance = "Public Resistance"
    short_term_focus = "Short-Term Focus"
    regulatory_delay = "Regulatory Delay"


class KPIInput(BaseModel):
    category: KPICategory
    subcategory: str
    id: str
    current_value: Optional[confloat(ge=0)] = None
    target_value: Optional[confloat(ge=0)] = None
    progress_stage: Optional[ProgressStage] = None
    current_date: conint(ge=1)
    target_date: conint(ge=1)
    data_quality: conint(ge=1, le=5)


class KPIRequest(BaseModel):
    selected_kpis: List[KPIInput]
    a: conint(ge=3, le=5)
    b: conint(ge=3, le=5)


class BarriersInput(BaseModel):
    persona: BarriersCategory
    id: str
    likelihood: conint(ge=1, le=5)
    impact: conint(ge=1, le=5)


class BarriersRequest(BaseModel):
    selected_barriers: List[BarriersInput]


def calculate_kpi_score(current_value, target_value, current_date, target_date, data_quality, a, b):
    if current_value > target_value:
        distance = target_value / current_value
    else:
        if target_value == 0:
            raise ValueError("Target value cannot be zero when current value is zero.")
        distance = current_value / target_value
    time_adjusted_distance = distance * math.exp(-(current_date / target_date) ** a)
    return round(time_adjusted_distance * (data_quality / 5) ** (1 / b), 2)


def determine_kpi_level(score):
    if 0 <= score < 0.2:
        return "Very Low"
    if score < 0.4:
        return "Low"
    if score < 0.6:
        return "Medium"
    if score < 0.8:
        return "High"
    if score <= 1:
        return "Very High"
    return "Invalid"


def determine_risk_level(score):
    if 1 <= score < 5:
        return "Very Low"
    if score < 10:
        return "Low"
    if score < 15:
        return "Medium"
    if score < 20:
        return "High"
    if score <= 25:
        return "Very High"
    return "Invalid"


def _score_kpi(kpi, data):
    if kpi.target_date <= kpi.current_date:
        raise ValueError(
            f"target_date ({kpi.target_date}) must be greater than current_date "
            f"({kpi.current_date}) for KPI '{kpi.id}'."
        )

    if kpi.current_value is not None and kpi.target_value is not None:
        if kpi.current_value > kpi.target_value:
            distance = kpi.target_value / kpi.current_value
        else:
            if kpi.target_value == 0:
                raise ValueError("Target value cannot be zero when current value is zero.")
            distance = kpi.current_value / kpi.target_value
        score = calculate_kpi_score(
            kpi.current_value, kpi.target_value, kpi.current_date, kpi.target_date,
            kpi.data_quality, data.a, data.b,
        )
        return distance, score, "numeric"

    if kpi.progress_stage:
        stage_to_distance = {
            "Very early stage": 0.1,
            "Early progress": 0.3,
            "Midway": 0.5,
            "Advanced": 0.7,
            "Near/at completion": 0.9,
        }
        distance = stage_to_distance[kpi.progress_stage.value]
        time_adjusted_distance = distance * math.exp(-(kpi.current_date / kpi.target_date) ** data.a)
        score = round(time_adjusted_distance * (kpi.data_quality / 5) ** (1 / data.b), 2)
        return distance, score, "qualitative"

    raise ValueError(f"KPI '{kpi.id}' must provide either numeric values or a progress stage.")


def _find_kpi_entry(kpi):
    predefined_data = KPI_CATEGORIES.get(kpi.category.value, {})
    for subcat in predefined_data.values():
        if kpi.id in subcat:
            return subcat[kpi.id]
    raise ValueError(f"KPI ID '{kpi.id}' not found under category '{kpi.category.value}'.")


def calculate_kpi_scores(data: KPIRequest):
    category_scores: Dict[str, Dict] = {}
    seen_ids = set()

    for kpi in data.selected_kpis:
        if kpi.id in seen_ids:
            raise ValueError(f"Duplicate KPI ID found: '{kpi.id}'.")
        seen_ids.add(kpi.id)
        kpi_entry = _find_kpi_entry(kpi)
        distance, score, mode = _score_kpi(kpi, data)

        category = kpi.category.value
        category_scores.setdefault(category, {"scores": [], "kpis": []})
        category_scores[category]["scores"].append(score)
        category_scores[category]["kpis"].append({
            "id": kpi.id,
            "name": kpi_entry.get("Name", ""),
            "mode": mode,
            "progress_stage": kpi.progress_stage.value if kpi.progress_stage else None,
            "progress (%)": round(distance * 100, 2),
            "score": score,
            "start_date": kpi.current_date,
            "end_date": kpi.target_date,
        })

    result = {}
    for category, values in category_scores.items():
        avg_score = round(sum(values["scores"]) / len(values["scores"]), 2)
        result[category] = {
            "score": avg_score,
            "level": determine_kpi_level(avg_score),
            "kpis": values["kpis"],
        }
    return {"category_scores": result}


def calculate_kpi_scores_primary_use(data: KPIRequest):
    primary_use_scores: Dict[str, Dict] = {}
    seen_ids = set()

    for kpi in data.selected_kpis:
        if kpi.id in seen_ids:
            raise ValueError(f"Duplicate KPI ID found: '{kpi.id}'.")
        seen_ids.add(kpi.id)
        kpi_entry = _find_kpi_entry(kpi)
        distance, score, mode = _score_kpi(kpi, data)
        primary_use = kpi_entry.get("Primary use")
        if not primary_use:
            raise ValueError(f"KPI '{kpi.id}' does not have a defined 'Primary use'.")

        primary_use_scores.setdefault(primary_use, {"scores": [], "kpis": []})
        primary_use_scores[primary_use]["scores"].append(score)
        primary_use_scores[primary_use]["kpis"].append({
            "id": kpi.id,
            "name": kpi_entry.get("Name", ""),
            "mode": mode,
            "progress_stage": kpi.progress_stage.value if kpi.progress_stage else None,
            "progress (%)": round(distance * 100, 2),
            "score": score,
            "start_date": kpi.current_date,
            "end_date": kpi.target_date,
        })

    result = {}
    for primary_use, values in primary_use_scores.items():
        avg_score = round(sum(values["scores"]) / len(values["scores"]), 2)
        result[primary_use] = {
            "score": avg_score,
            "level": determine_kpi_level(avg_score),
            "kpis": values["kpis"],
        }
    return {"primary_use_scores": result}


barrier_to_incentive_ids = {item["barrier"].strip(): item["incentives"] for item in incentives_id}
id_to_incentive = {item["id"]: item for item in incentives}


def calculate_barriers_scores(data: BarriersRequest):
    seen_ids = set()
    category_data = {}

    for barrier in data.selected_barriers:
        persona = barrier.persona.value
        barrier_id = barrier.id
        if barrier_id in seen_ids:
            raise ValueError(f"Duplicate barrier ID: {barrier_id}")
        seen_ids.add(barrier_id)
        if persona not in Barriers_disadvantages or barrier_id not in Barriers_disadvantages[persona]:
            raise ValueError(f"Barrier ID '{barrier_id}' not in persona '{persona}'")

        description = Barriers_disadvantages[persona][barrier_id]
        score = barrier.likelihood * barrier.impact
        category_data.setdefault(persona, {
            "sum_numerator": 0.0,
            "sum_likelihood": 0.0,
            "sum_impact": 0.0,
        })
        cat = category_data[persona]
        cat["sum_numerator"] += score
        cat["sum_likelihood"] += barrier.likelihood
        cat["sum_impact"] += barrier.impact
        matched_ids = barrier_to_incentive_ids.get(description.strip(), [])
        cat[barrier_id] = {
            "description": description,
            "likelihood": barrier.likelihood,
            "impact": barrier.impact,
            "incentives": [id_to_incentive[i] for i in matched_ids if i in id_to_incentive],
        }

    result = {}
    for persona, values in category_data.items():
        numerator = values.pop("sum_numerator")
        sum_likelihood = values.pop("sum_likelihood")
        sum_impact = values.pop("sum_impact")
        a = numerator / sum_impact if sum_impact else 0.0
        b = numerator / sum_likelihood if sum_likelihood else 0.0
        c = a * b
        values["Persona impact"] = round(a, 2)
        values["Persona likelihood"] = round(b, 2)
        values["Persona Risk score"] = round(c, 2)
        values["Risk level"] = determine_risk_level(c)
        result[persona] = values
    return result
