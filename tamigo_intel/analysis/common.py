from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Indicator:
    tool: str
    rule_id: str
    summary: str
    status: str
    wcag_hint: str = ""
    details: str = ""


@dataclass
class AnalysisResult:
    format: str
    conformance: str = "not_determined"
    indicators: list[Indicator] = field(default_factory=list)
    limitations: str = (
        "Automatska provera nije potvrda WCAG, PDF/UA ni EPUB Accessibility usklađenosti. "
        "Tastatura, čitač ekrana i smisao alternativnog teksta traže ručnu proveru."
    )
    notes: str = ""
