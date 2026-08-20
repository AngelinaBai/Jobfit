from __future__ import annotations

from jobfit.connectors.ashby import AshbyConnector
from jobfit.connectors.greenhouse import GreenhouseConnector
from jobfit.connectors.career_page import CareerPageConnector
from jobfit.connectors.lever import LeverConnector


def build_connector(source_type: str, *, timeout_seconds: float):
    if source_type == "greenhouse":
        return GreenhouseConnector(timeout_seconds=timeout_seconds)
    if source_type == "lever":
        return LeverConnector(timeout_seconds=timeout_seconds)
    if source_type == "ashby":
        return AshbyConnector(timeout_seconds=timeout_seconds)
    if source_type == "career_page":
        return CareerPageConnector(timeout_seconds=timeout_seconds)
    raise ValueError(f"Unsupported source type: {source_type}")
