"""Spec → HTML rendering.

CSS and JS live as real files under `assets/` and are inlined at render time.
That keeps them editable as first-class source while the rendered output stays a
single self-contained document, which is what makes `qsurface render` able to
emit a standalone preview file with no server behind it.

All spec-supplied text is HTML-escaped before any inline formatting is applied,
so authoring a questionnaire can never inject markup into the page.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from . import spec as spec_mod

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Inline formatting applied *after* escaping: `code`, **bold**, *italic*.
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def fmt(text: str) -> str:
    """Escape, then apply the small inline-formatting subset."""
    out = html.escape(text or "", quote=False)
    out = _CODE.sub(r"<code>\1</code>", out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return out.replace("\n\n", "<br><br>").replace("\n", "<br>")


def _asset(name: str) -> str:
    path = ASSETS / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def render(
    spec: dict,
    draft: dict | None = None,
    standalone: bool = False,
    respondent: str = "",
) -> str:
    """Render a full HTML document for the questionnaire."""
    questions = spec_mod.answerable_questions(spec)
    sections_html = "\n".join(
        _section(section, index) for index, section in enumerate(spec["sections"])
    )
    nav_html = "\n".join(
        f'<a class="nav-item" href="#section-{i}" data-section="{i}">'
        f'<span class="nav-dot"></span><span class="nav-label">{fmt(s["title"])}</span>'
        f"</a>"
        for i, s in enumerate(spec["sections"])
    )
    docs_html = ""
    if spec.get("context_docs"):
        items = "".join(
            f"<li><code>{html.escape(str(doc))}</code></li>"
            for doc in spec["context_docs"]
        )
        docs_html = (
            '<div class="context-docs"><h3>Source material</h3>'
            f"<ul>{items}</ul></div>"
        )

    bootstrap = {
        "id": spec["id"],
        "total": len(questions),
        "standalone": standalone,
        "draft": draft or {},
        "conditions": {
            q["id"]: q["show_if"] for q in questions if q.get("show_if")
        },
    }

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(spec["title"])}</title>
<style>{_asset("app.css")}</style>
</head>
<body>
<div class="progress-rail"><div class="progress-fill" id="progressFill"></div></div>

<div class="layout">
  <aside class="sidebar">
    <div class="sidebar-inner">
      <div class="brand">Question Surface</div>
      <div class="progress-readout"><span id="progressCount">0</span> of {len(questions)} answered</div>
      <nav class="nav">{nav_html}</nav>
      {docs_html}
      <div class="sidebar-foot">
        {f'<div class="respondent-note">Answering as {html.escape(respondent)}</div>' if respondent else ""}
        <div class="draft-state" id="draftState">Draft saved locally</div>
      </div>
    </div>
  </aside>

  <main class="main">
    <header class="doc-head">
      <h1>{html.escape(spec["title"])}</h1>
      {f'<div class="doc-intro">{fmt(spec["intro"])}</div>' if spec.get("intro") else ""}
      <div class="legend">
        <span class="legend-item"><span class="pip pip-req"></span>Required</span>
        <span class="legend-item"><span class="pip pip-rec"></span>Has a recommendation</span>
        <span class="legend-item"><span class="pip pip-unk"></span>Can be marked unknown</span>
      </div>
    </header>

    <form id="qform">{sections_html}</form>

    <div class="submit-bar">
      <div class="submit-summary" id="submitSummary"></div>
      <div class="submit-actions">
        <button type="button" class="btn btn-ghost" id="saveDraft">Save draft</button>
        <button type="button" class="btn btn-primary" id="submitBtn">Submit answers</button>
      </div>
    </div>
    <div class="result" id="result" hidden></div>
  </main>
</div>

<script>window.__QS__ = {json.dumps(bootstrap)};</script>
<script>{_asset("app.js")}</script>
</body>
</html>
"""


def _section(section: dict, index: int) -> str:
    body = "\n".join(_question(q) for q in section["questions"])
    intro = (
        f'<div class="section-intro">{fmt(section["intro"])}</div>'
        if section.get("intro")
        else ""
    )
    return f"""<section class="section" id="section-{index}" data-section="{index}">
  <div class="section-head">
    <div class="section-index">{index + 1:02d}</div>
    <h2>{fmt(section["title"])}</h2>
  </div>
  {intro}
  {body}
</section>"""


def _question(question: dict) -> str:
    if question["type"] == "info":
        return f'<div class="info-block">{fmt(question["prompt"])}</div>'

    qid = html.escape(question["id"])
    condition = (
        f" data-show-if='{html.escape(json.dumps(question['show_if']), quote=True)}'"
        if question.get("show_if")
        else ""
    )

    pips = ""
    if question.get("required"):
        pips += '<span class="pip pip-req" title="Required"></span>'
    if question.get("recommend") is not None:
        pips += '<span class="pip pip-rec" title="Has a recommendation"></span>'
    if question.get("allow_unknown"):
        pips += '<span class="pip pip-unk" title="Can be marked unknown"></span>'

    why = (
        f'<div class="q-why">{fmt(question["why"])}</div>' if question.get("why") else ""
    )
    control = _control(question)

    unknown = ""
    if question.get("allow_unknown"):
        unknown = f"""<label class="unknown-toggle">
      <input type="checkbox" class="qs-unknown" data-qid="{qid}">
      <span>Don't know — flag for research</span>
    </label>"""

    notes = ""
    if question.get("notes"):
        notes = f"""<div class="notes-wrap">
      <textarea class="qs-notes" data-qid="{qid}" rows="2"
        placeholder="Notes, caveats, or the reasoning behind this answer"></textarea>
    </div>"""

    return f"""<div class="q" data-qid="{qid}" data-type="{question["type"]}"
     data-required="{str(bool(question.get("required"))).lower()}"{condition}>
  <div class="q-head">
    <div class="q-prompt">{fmt(question["prompt"])}</div>
    <div class="q-pips">{pips}</div>
  </div>
  {why}
  <div class="q-control">{control}</div>
  <div class="q-meta">{unknown}{notes}</div>
</div>"""


def _control(question: dict) -> str:
    qtype = question["type"]
    qid = html.escape(question["id"])
    placeholder = html.escape(question.get("placeholder") or "", quote=True)

    if qtype in ("single", "multi"):
        return _options(question, qid, multiple=qtype == "multi")

    if qtype == "rank":
        items = "".join(
            f'<li class="rank-item" draggable="true" data-value="{html.escape(str(o["value"]), quote=True)}">'
            f'<span class="rank-grip">⠿</span><span class="rank-num"></span>'
            f'<span class="rank-label">{fmt(o["label"])}</span></li>'
            for o in question["options"]
        )
        return (
            f'<ol class="rank-list qs-input" data-qid="{qid}">{items}</ol>'
            '<div class="rank-hint">Drag to order — most important first. '
            "The order shown is recorded unless you change it.</div>"
        )

    if qtype == "scale":
        low, high = question["min"], question["max"]
        buttons = "".join(
            f'<button type="button" class="scale-btn" data-value="{n}">{n}</button>'
            for n in range(low, high + 1)
        )
        labels = ""
        if question.get("min_label") or question.get("max_label"):
            labels = (
                f'<div class="scale-labels"><span>{fmt(question.get("min_label", ""))}</span>'
                f'<span>{fmt(question.get("max_label", ""))}</span></div>'
            )
        return f'<div class="scale qs-input" data-qid="{qid}">{buttons}</div>{labels}'

    if qtype == "longtext":
        return (
            f'<textarea class="qs-input text-input" data-qid="{qid}" rows="5" '
            f'placeholder="{placeholder}"></textarea>'
        )

    input_type = {"number": "number", "date": "date"}.get(qtype, "text")
    return (
        f'<input type="{input_type}" class="qs-input text-input" data-qid="{qid}" '
        f'placeholder="{placeholder}">'
    )


def _options(question: dict, qid: str, multiple: bool) -> str:
    recommend = question.get("recommend")
    wanted = (
        recommend if isinstance(recommend, list) else [recommend] if recommend else []
    )
    kind = "checkbox" if multiple else "radio"
    rows = []
    for option in question["options"]:
        value = html.escape(str(option["value"]), quote=True)
        detail = (
            f'<span class="opt-detail">{fmt(option["detail"])}</span>'
            if option.get("detail")
            else ""
        )
        tag = (
            '<span class="opt-rec">recommended</span>'
            if option["value"] in wanted
            else ""
        )
        rows.append(
            f'<label class="opt">'
            f'<input type="{kind}" class="qs-input" data-qid="{qid}" '
            f'name="q-{qid}" value="{value}">'
            f'<span class="opt-body"><span class="opt-label">{fmt(option["label"])}{tag}</span>'
            f"{detail}</span></label>"
        )
    css = "opts opts-multi" if multiple else "opts"
    return f'<div class="{css}">{"".join(rows)}</div>'
