"""Synthetic smoke-test calculations matching parameters.json output_names."""
from __future__ import annotations


def taster_converted_members(taster_attendees_year1: float, taster_conversion_rate: float) -> float:
    return taster_attendees_year1 * taster_conversion_rate


def total_budget_with_gate_inr(year1_budget_inr: float, month4_gate_release_inr: float) -> float:
    return year1_budget_inr + month4_gate_release_inr


def annual_instructor_payroll_inr(
    operating_weeks_per_year: float,
    instructor_hourly_rate_inr: float,
) -> float:
    return operating_weeks_per_year * instructor_hourly_rate_inr * 30
