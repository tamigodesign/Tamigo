from __future__ import annotations

from html.parser import HTMLParser

from tamigo_intel.analysis.common import AnalysisResult, Indicator


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.title_parts: list[str] = []
        self._in_title = False
        self.images_missing_alt = 0
        self.unlabeled_inputs = 0
        self.empty_buttons = 0
        self.heading_jumps = 0
        self._heading_stack: list[int] = []
        self._button_text: list[str] = []
        self._in_button = False
        self._button_has_name = False
        self._label_fors: set[str] = set()
        self._pending_inputs: list[dict] = []
        self.links = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): (value or "") for key, value in attrs}
        if tag == "html":
            self.lang = attributes.get("lang", "")
        elif tag == "title":
            self._in_title = True
        elif tag == "img":
            if "alt" not in attributes:
                self.images_missing_alt += 1
        elif tag == "input":
            input_type = attributes.get("type", "text").lower()
            if input_type not in {"hidden", "submit", "button", "image"}:
                named = bool(attributes.get("aria-label") or attributes.get("aria-labelledby") or attributes.get("title"))
                self._pending_inputs.append({"id": attributes.get("id", ""), "named": named})
        elif tag == "label":
            if attributes.get("for"):
                self._label_fors.add(attributes["for"])
        elif tag == "button":
            self._in_button = True
            self._button_has_name = bool(attributes.get("aria-label") or attributes.get("aria-labelledby") or attributes.get("title"))
            self._button_text = []
        elif tag == "a":
            self.links += 1
            href = attributes.get("href", "")
            if href.lower().startswith(("javascript:",)) and not (attributes.get("aria-label") or ""):
                pass
        elif tag in {f"h{i}" for i in range(1, 7)}:
            level = int(tag[1])
            if self._heading_stack and level > self._heading_stack[-1] + 1:
                self.heading_jumps += 1
            self._heading_stack.append(level)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "button" and self._in_button:
            text = "".join(self._button_text).strip()
            if not text and not self._button_has_name:
                self.empty_buttons += 1
            self._in_button = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_button:
            self._button_text.append(data)

    def finish(self) -> None:
        for item in self._pending_inputs:
            if item["named"]:
                continue
            if item["id"] and item["id"] in self._label_fors:
                continue
            self.unlabeled_inputs += 1


def analyze_html(markup: str) -> AnalysisResult:
    parser = _Page()
    try:
        parser.feed(markup)
        parser.close()
        parser.finish()
    except Exception as exc:  # malformed HTML still yields what was parsed
        result = AnalysisResult(format="html", notes=f"Parser je stao: {exc}")
    else:
        result = AnalysisResult(format="html")
    title = "".join(parser.title_parts).strip()
    if not parser.lang.strip():
        result.indicators.append(
            Indicator("html", "html-lang", "Na elementu html nema jezika.", "accessibility_indicator", "3.1.1")
        )
    if not title:
        result.indicators.append(
            Indicator("html", "document-title", "Stranica nema naslov u elementu title.", "accessibility_indicator", "2.4.2")
        )
    if parser.images_missing_alt:
        result.indicators.append(
            Indicator(
                "html",
                "img-alt",
                f"Slika bez atributa alt: {parser.images_missing_alt}. Prazan alt nije računat.",
                "accessibility_indicator",
                "1.1.1",
            )
        )
    if parser.unlabeled_inputs:
        result.indicators.append(
            Indicator(
                "html",
                "input-name",
                f"Polje bez vidljive ili programske oznake: {parser.unlabeled_inputs}.",
                "accessibility_indicator",
                "4.1.2",
            )
        )
    if parser.empty_buttons:
        result.indicators.append(
            Indicator(
                "html",
                "button-name",
                f"Dugme bez teksta i bez pristupačnog imena: {parser.empty_buttons}.",
                "accessibility_indicator",
                "4.1.2",
            )
        )
    if parser.heading_jumps:
        result.indicators.append(
            Indicator(
                "html",
                "heading-jump",
                f"Preskok nivoa naslova: {parser.heading_jumps}. Ovo treba ručno proveriti.",
                "accessibility_indicator",
                "1.3.1",
            )
        )
    if not result.indicators:
        result.notes = "Nema automatskih indikatora na ovoj proveri. To ne znači da je stranica usklađena."
    return result
