"""Spec → HTML rendering.

CSS and JS live as real files under `assets/` and are inlined at render time.
That keeps them editable as first-class source while the rendered output stays a
single self-contained document, which is what makes `docket render` able to
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
from . import store

ASSETS = Path(__file__).resolve().parent / "assets"

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


_DIVIDER_CELL = re.compile(r"^:?-{2,}:?$")


def rich(text: str) -> str:
    """A small block-level markdown subset for agent-written context.

    `fmt` handles one line of inline formatting, which is enough for a prompt
    and not enough for a briefing. Context blocks carry the reasoning an agent
    would otherwise put in a chat message, and that reasoning is frequently a
    comparison table or a list. Supported: paragraphs, `-`/`*` bullets, and
    pipe tables. Everything goes through `fmt` first, so it is escaped before
    any markup is added.
    """
    lines = (text or "").replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    index = 0

    def is_row(line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1

    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    def is_bullet(line: str) -> bool:
        return line.lstrip().startswith(("- ", "* "))

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if (
            is_row(line)
            and index + 1 < len(lines)
            and is_row(lines[index + 1])
            and all(_DIVIDER_CELL.match(c) for c in cells(lines[index + 1]) if c)
        ):
            header = cells(line)
            index += 2
            body = []
            while index < len(lines) and is_row(lines[index]):
                body.append(cells(lines[index]))
                index += 1
            head = "".join(f"<th>{fmt(c)}</th>" for c in header)
            rows = "".join(
                "<tr>" + "".join(f"<td>{fmt(c)}</td>" for c in row) + "</tr>"
                for row in body
            )
            blocks.append(
                f'<table class="ctx-table"><thead><tr>{head}</tr></thead>'
                f"<tbody>{rows}</tbody></table>"
            )
            continue

        if is_bullet(line):
            items = []
            while index < len(lines) and is_bullet(lines[index]):
                items.append(fmt(lines[index].lstrip()[2:]))
                index += 1
            blocks.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            continue

        # Consume the first line unconditionally. A pipe row with no divider
        # under it matches no block above and is not a paragraph start either,
        # so testing before consuming leaves the cursor where it was and spins.
        para = [lines[index]]
        index += 1
        while (
            index < len(lines)
            and lines[index].strip()
            and not is_row(lines[index])
            and not is_bullet(lines[index])
        ):
            para.append(lines[index])
            index += 1
        blocks.append("<p>" + fmt("\n".join(para)) + "</p>")

    return "".join(blocks)


def _asset(name: str) -> str:
    path = ASSETS / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def render(
    spec: dict,
    draft: dict | None = None,
    standalone: bool = False,
    respondent: str = "",
    prior: dict | None = None,
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

    prior_html = _prior(prior)

    # Pointless in a standalone preview, which has no server to submit to.
    close_toggle = (
        ""
        if standalone
        else """<label class="close-toggle">
          <input type="checkbox" id="closeOnSubmit">
          <span>Close this tab when I submit</span>
        </label>"""
    )

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
      <div class="brand">Docket</div>
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

    {prior_html}

    <form id="qform">{sections_html}</form>

    <div class="submit-bar">
      <div class="submit-left">
        <div class="submit-summary" id="submitSummary"></div>
        {close_toggle}
      </div>
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


def interview_page(record: dict) -> str:
    """The one-question-at-a-time page.

    Four states live in the document at once and exactly one is shown, so a
    transition never waits on a network round trip to have something to
    display. `app.css` is inlined for the palette and buttons; everything
    interview-specific is in `interview.css`.
    """
    bootstrap = {
        "id": record["id"],
        "answered": len(record.get("exchanges", [])),
        "exchanges": [
            {
                "prompt": e.get("prompt", ""),
                "answer": e.get("answer", ""),
                "skipped": bool(e.get("skipped")),
            }
            for e in record.get("exchanges", [])
        ],
    }
    meta = [f"Answering as {html.escape(record.get('respondent') or 'you')}"]
    if record.get("domain"):
        meta.append(html.escape(record["domain"]))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(record["title"])}</title>
<style>{_asset("app.css")}
{_asset("interview.css")}</style>
</head>
<body>
<div class="iv-layout">
  <header class="iv-head">
    <div class="iv-kicker">Interview</div>
    <h1>{html.escape(record["title"])}</h1>
    <div class="iv-meta">{"".join(f"<span>{part}</span>" for part in meta)}</div>
  </header>

  <div class="iv-history" id="ivHistory"></div>

  <div class="iv-state" id="stateAsking">
    <div class="iv-card">
      <div class="iv-seq" id="ivSeq"></div>
      <div class="iv-prompt" id="ivPrompt"></div>
      <div class="iv-why" id="ivWhy" hidden></div>
      <div class="iv-context" id="ivContext" hidden>
        <div class="iv-context-head">Additional context</div>
        <div class="iv-context-body is-clamped" id="ivContextBody"></div>
        <button type="button" class="iv-context-more" id="ivContextMore" hidden>Read more</button>
      </div>
      <div class="iv-chips" id="ivChips" hidden></div>
      <textarea class="iv-answer" id="ivAnswer" rows="6"></textarea>
      <div class="iv-dictate" id="ivDictate" hidden>
        <span></span><button type="button">dismiss</button>
      </div>
      <div class="iv-actions">
        <span class="iv-hint"><kbd>⌘</kbd>/<kbd>Ctrl</kbd>+<kbd>Enter</kbd> to send</span>
        <button type="button" class="btn btn-ghost" id="ivSkip">Skip</button>
        <button type="button" class="btn btn-primary" id="ivSend">Send answer</button>
      </div>
    </div>
  </div>

  <div class="iv-state" id="stateProcessing">
    <div class="iv-card iv-processing">
      <div class="iv-mark" aria-hidden="true">
        <div class="iv-mark-rule"></div>
        <div class="iv-mark-caret"></div>
        <div class="iv-mark-lines">
          <span style="--w:100%"></span>
          <span style="--w:94%"></span>
          <span style="--w:100%"></span>
          <span style="--w:97%"></span>
          <span style="--w:71%"></span>
        </div>
      </div>
      <div class="iv-copy" role="status" aria-live="polite">
        <p class="iv-primary" id="ivProcPrimary">Standing by&hellip;</p>
        <div class="iv-secstack">
          <p class="iv-secondary iv-sec-a" id="ivProcSecA">Getting the first question ready.</p>
          <p class="iv-secondary iv-sec-b" id="ivProcSecB">Still getting started.</p>
        </div>
      </div>
    </div>
  </div>

  <div class="iv-state" id="stateOffer">
    <div class="iv-card iv-offer">
      <div class="iv-offer-kicker">Interview complete</div>
      <h2 id="ivOfferTitle"></h2>
      <p class="iv-offer-body" id="ivOfferBody"></p>
      <div class="iv-offer-actions">
        <button type="button" class="btn btn-ghost" id="ivOfferSkip">No thanks</button>
        <button type="button" class="btn btn-primary" id="ivOfferTake">
          Answer them — <span id="ivOfferCount"></span>
        </button>
      </div>
      <p class="iv-offer-note">The transcript is already saved either way.</p>
    </div>
  </div>

  <div class="iv-state" id="stateDone">
    <div class="iv-card iv-done">
      <h2>Interview complete</h2>
      <div id="ivDoneBody">
        <p>The transcript is saved. You can close this tab.</p>
      </div>
    </div>
  </div>

  <div class="iv-state" id="stateLost">
    <div class="iv-card iv-lost">
      <h2>Lost contact with the agent</h2>
      <p>Every answer you already sent is saved to the transcript. The session
      that was asking the questions has stopped responding, so nothing more is
      coming — you can close this tab.</p>
    </div>
  </div>
</div>

<script>window.__IV__ = {json.dumps(bootstrap)};</script>
<script>{_asset("interview.js")}</script>
</body>
</html>
"""


def _prior(prior: dict | None) -> str:
    """Read-only panel of what an earlier round already settled.

    A follow-up questionnaire whose respondent cannot see the previous answers
    makes them reconstruct the decisions from memory, which is the failure this
    tool exists to remove. Skipped and unanswered entries are left out — only
    what was actually decided is worth restating.
    """
    if not prior:
        return ""

    rows = []
    if prior.get("kind") == "interview":
        # A distilled questionnaire follows the interview it came from, so the
        # respondent can see what they already said rather than recalling it.
        for exchange in prior.get("exchanges", []):
            if exchange.get("skipped"):
                continue
            said = " · ".join(exchange.get("selected") or [])
            if exchange.get("answer"):
                said = f"{said} — {exchange['answer']}" if said else exchange["answer"]
            if not said:
                continue
            rows.append(
                f'<div class="prior-row"><div class="prior-q">'
                f'{fmt(exchange["prompt"])}</div>'
                f'<div class="prior-a">{fmt(said)}</div></div>'
            )
    else:
        for entry in prior.get("answers", {}).values():
            if entry.get("skipped") or entry.get("value") in (None, "", []):
                if not entry.get("unknown"):
                    continue
            rows.append(
                f'<div class="prior-row"><div class="prior-q">{fmt(entry["prompt"])}</div>'
                f'<div class="prior-a">{fmt(store.format_value(entry))}</div></div>'
            )
    if not rows:
        return ""

    when = html.escape(str(prior.get("submitted_at", "")))
    title = html.escape(str(prior.get("title", prior.get("questionnaire_id", ""))))
    return (
        '<details class="prior" open><summary>Already decided'
        f' — <span class="prior-src">{title}, {when}</span></summary>'
        f'<div class="prior-body">{"".join(rows)}</div></details>'
    )


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
