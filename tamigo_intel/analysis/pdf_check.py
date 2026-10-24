from __future__ import annotations

from pathlib import Path

from tamigo_intel.analysis.common import AnalysisResult, Indicator


def analyze_pdf(path: Path) -> AnalysisResult:
    result = AnalysisResult(format="pdf")
    try:
        from pypdf import PdfReader
    except ImportError:
        result.notes = "pypdf nije instaliran. PDF provera nije pokrenuta."
        result.conformance = "not_run"
        return result
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        result.indicators.append(
            Indicator("pypdf", "pdf-open", f"PDF nije pročitan: {exc}", "tool_error")
        )
        result.conformance = "not_run"
        return result
    root = reader.trailer.get("/Root", {})
    mark = root.get("/MarkInfo") if hasattr(root, "get") else None
    marked = False
    if mark is not None:
        try:
            marked = bool(mark.get("/Marked"))
        except Exception:
            marked = False
    lang = ""
    try:
        lang = str(root.get("/Lang") or "")
    except Exception:
        lang = ""
    title = ""
    if reader.metadata:
        title = str(reader.metadata.get("/Title") or "")
    if not marked:
        result.indicators.append(
            Indicator(
                "pypdf",
                "pdf-unmarked",
                "Katalog nema MarkInfo/Marked true. Dokument nije označen kao tagovan.",
                "accessibility_indicator",
                "PDF/UA",
                "Jedan automatski uslov nije dokaz da je ceo PDF nepristupačan.",
            )
        )
    if not lang:
        result.indicators.append(
            Indicator("pypdf", "pdf-lang", "U katalogu nema /Lang.", "accessibility_indicator", "3.1.1")
        )
    if not title.strip():
        result.indicators.append(
            Indicator("pypdf", "pdf-title", "U info rečniku nema naslova.", "accessibility_indicator", "2.4.2")
        )
    extracted = ""
    try:
        if reader.pages:
            extracted = reader.pages[0].extract_text() or ""
    except Exception:
        extracted = ""
    if reader.pages and not extracted.strip():
        result.indicators.append(
            Indicator(
                "pypdf",
                "pdf-no-text",
                "Sa prve strane nije izvučen tekst. Dokument može biti skeniran. Treba ručno proveriti.",
                "accessibility_indicator",
            )
        )
    result.notes = (
        f"Strana: {len(reader.pages)}. Kontrast, redosled čitanja i tabele ovim alatom nisu proveravani. "
        "PAC i veraPDF nisu ugrađeni."
    )
    return result
