from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

from tamigo_intel.analysis.common import AnalysisResult, Indicator
from tamigo_intel.analysis.html_check import analyze_html

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
}


def analyze_epub(path: Path) -> AnalysisResult:
    result = AnalysisResult(format="epub")
    if not zipfile.is_zipfile(path):
        result.indicators.append(Indicator("epub-structure", "epub-zip", "Fajl nije ZIP paket.", "structure"))
        return result
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        if "mimetype" not in names:
            result.indicators.append(Indicator("epub-structure", "epub-mimetype", "Nema datoteke mimetype.", "structure"))
        else:
            mimetype = package.read("mimetype").decode("utf-8", "replace").strip()
            if mimetype != "application/epub+zip":
                result.indicators.append(
                    Indicator("epub-structure", "epub-mimetype-value", f"mimetype je {mimetype!r}.", "structure")
                )
        if "META-INF/container.xml" not in names:
            result.indicators.append(
                Indicator("epub-structure", "epub-container", "Nema META-INF/container.xml.", "structure")
            )
            return result
        container = ElementTree.fromstring(package.read("META-INF/container.xml"))
        rootfile = container.find(".//container:rootfile", NS)
        opf_path = rootfile.get("full-path") if rootfile is not None else ""
        if not opf_path or opf_path not in names:
            result.indicators.append(Indicator("epub-structure", "epub-opf", "OPF nije pronađen.", "structure"))
            return result
        opf = ElementTree.fromstring(package.read(opf_path))
        languages = [node.text or "" for node in opf.findall(".//dc:language", NS)]
        if not any(lang.strip() for lang in languages):
            result.indicators.append(
                Indicator("epub", "epub-language", "U OPF nema dc:language.", "accessibility_indicator", "3.1.1")
            )
        metadata_text = ElementTree.tostring(opf, encoding="unicode").lower()
        if "schema:accessmode" not in metadata_text and "schema:accessibilitysummary" not in metadata_text:
            result.indicators.append(
                Indicator(
                    "epub",
                    "epub-a11y-metadata",
                    "Nema schema:accessMode ni accessibilitySummary. To je metapodatak, ne dokaz o sadržaju.",
                    "accessibility_indicator",
                    "EPUB Accessibility",
                )
            )
        properties = " ".join((item.get("properties") or "") for item in opf.findall(".//opf:item", NS))
        if "nav" not in properties.split():
            result.indicators.append(
                Indicator("epub", "epub-nav", "U manifestu nema stavke sa properties=nav.", "accessibility_indicator")
            )
        base = str(Path(opf_path).parent)
        for item in opf.findall(".//opf:item", NS):
            href = item.get("href") or ""
            media = item.get("media-type") or ""
            if "html" not in media:
                continue
            full = href if base in {"", "."} else str(Path(base) / href)
            full = full.replace("\\", "/")
            if full not in names:
                continue
            markup = package.read(full).decode("utf-8", "replace")
            page = analyze_html(markup)
            for indicator in page.indicators:
                if indicator.rule_id == "img-alt":
                    result.indicators.append(
                        Indicator("epub", "epub-img-alt", f"{full}: {indicator.summary}", "accessibility_indicator", "1.1.1")
                    )
    result.notes = "EPUBCheck i DAISY Ace nisu pokrenuti. Ovo je strukturni i metapodatkovni pregled."
    return result
