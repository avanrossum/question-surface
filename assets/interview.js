/* Interview mode — client.
   Long-polls for the next question, posts answers, and shows exactly one of
   four states: asking, processing, done, lost. Nothing here may leave the
   respondent watching an animation the agent is never going to end. */

(function () {
  "use strict";

  var CFG = window.__IV__ || {};
  var DRAFT_KEY = "qsurface:iv:" + CFG.id;
  var after = CFG.answered || 0;
  var current = null;
  var selected = [];
  var failures = 0;
  var stopped = false;

  var states = {
    asking: document.getElementById("stateAsking"),
    processing: document.getElementById("stateProcessing"),
    done: document.getElementById("stateDone"),
    lost: document.getElementById("stateLost")
  };
  var promptEl = document.getElementById("ivPrompt");
  var whyEl = document.getElementById("ivWhy");
  var seqEl = document.getElementById("ivSeq");
  var answerEl = document.getElementById("ivAnswer");
  var chipsEl = document.getElementById("ivChips");
  var sendBtn = document.getElementById("ivSend");
  var skipBtn = document.getElementById("ivSkip");
  var historyEl = document.getElementById("ivHistory");
  var doneBody = document.getElementById("ivDoneBody");

  function setState(name) {
    Object.keys(states).forEach(function (key) {
      if (states[key]) states[key].classList.toggle("is-active", key === name);
    });
  }

  /* The waiting state is entered for two different reasons and must say which.
     On load nothing has been said yet, so "reading your answer" would be a
     claim about an answer that does not exist. */
  var PROCESSING_COPY = {
    start: {
      primary: "Standing by…",
      secondary: "Getting the first question ready.",
      longWait: "Still getting started."
    },
    resume: {
      primary: "Standing by…",
      secondary: "Waiting for the next question.",
      longWait: "Still waiting. The agent may be working on something else."
    },
    reading: {
      primary: "Reading your answer…",
      secondary: "Working out what to ask next.",
      longWait: "Still reading. Longer answers take a moment."
    }
  };

  function setProcessingCopy(kind) {
    var copy = PROCESSING_COPY[kind] || PROCESSING_COPY.reading;
    var primary = document.getElementById("ivProcPrimary");
    var secA = document.getElementById("ivProcSecA");
    var secB = document.getElementById("ivProcSecB");
    if (primary) primary.textContent = copy.primary;
    if (secA) secA.textContent = copy.secondary;
    if (secB) secB.textContent = copy.longWait;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* ---------- history ---------- */

  function appendHistory(exchange) {
    var row = document.createElement("div");
    row.className = "iv-exchange" + (exchange.skipped ? " is-skipped" : "");
    var picked = (exchange.selected || []).map(function (option) {
      return '<span class="iv-picked">' + escapeHtml(option) + "</span>";
    }).join("");
    row.innerHTML =
      '<div class="iv-q">' + escapeHtml(exchange.prompt) + "</div>" +
      (picked ? '<div class="iv-a-picks">' + picked + "</div>" : "") +
      (exchange.skipped || exchange.answer
        ? '<div class="iv-a">' +
          escapeHtml(exchange.skipped ? "Skipped." : exchange.answer) + "</div>"
        : "");
    historyEl.appendChild(row);
  }

  /* ---------- drafts ---------- */

  function saveDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        seq: current ? current.seq : 0, text: answerEl.value, selected: selected
      }));
    } catch (err) { /* private browsing */ }
  }

  function restoreDraft(seq) {
    try {
      var saved = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
      if (!saved || saved.seq !== seq) return;
      if (saved.text) answerEl.value = saved.text;
      (saved.selected || []).forEach(function (option) {
        if (selected.indexOf(option) === -1) selected.push(option);
        Array.prototype.forEach.call(chipsEl.children, function (chip) {
          if (chip.textContent === option) {
            chip.classList.add("is-selected");
            chip.setAttribute("aria-pressed", "true");
          }
        });
      });
    } catch (err) { /* private browsing */ }
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (err) {}
  }

  /* ---------- asking ---------- */

  function showQuestion(question) {
    current = question;
    after = question.seq;
    seqEl.textContent = "Question " + question.seq;
    promptEl.textContent = question.prompt;
    whyEl.textContent = question.why || "";
    whyEl.hidden = !question.why;
    answerEl.value = "";
    answerEl.placeholder = question.placeholder || "Take as much room as you need.";

    // Options are a selection in their own right, recorded separately from
    // whatever gets typed. Pasting the label into the box loses which one was
    // picked the moment the respondent edits the sentence around it.
    // Built before the draft is restored, since restoring marks chips.
    selected = [];
    chipsEl.innerHTML = "";
    var options = question.options || [];
    chipsEl.hidden = options.length === 0;
    options.forEach(function (option) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "iv-chip";
      button.textContent = option;
      button.setAttribute("aria-pressed", "false");
      button.addEventListener("click", function () {
        var at = selected.indexOf(option);
        if (at === -1) selected.push(option);
        else selected.splice(at, 1);
        var on = selected.indexOf(option) !== -1;
        button.classList.toggle("is-selected", on);
        button.setAttribute("aria-pressed", on ? "true" : "false");
        answerEl.focus();
        saveDraft();
      });
      chipsEl.appendChild(button);
    });

    showContext(question.context_html);
    restoreDraft(question.seq);

    sendBtn.disabled = false;
    skipBtn.disabled = false;
    setState("asking");
    measureContext();
    answerEl.focus();
  }

  /* ---------- additional context ----------
     The reasoning behind a question — the comparison table, the tradeoff, the
     thing that would otherwise be said in chat where it is easy to miss.
     Clamped to four lines so a long briefing never buries the question it is
     supporting. The HTML is built server-side from an escaped subset. */

  function showContext(html) {
    var box = document.getElementById("ivContext");
    var body = document.getElementById("ivContextBody");
    var more = document.getElementById("ivContextMore");
    if (!box || !body || !more) return;

    if (!html) {
      box.hidden = true;
      body.innerHTML = "";
      return;
    }
    body.innerHTML = html;
    body.classList.add("is-clamped");
    more.textContent = "Read more";
    more.hidden = true;
    box.hidden = false;
  }

  /* Whether anything is actually hidden can only be measured once the card is
     on screen. Called after the state switches: while the card is display:none
     both heights read zero, the content looks like it fits, and the toggle
     never appears. */
  function measureContext() {
    var box = document.getElementById("ivContext");
    var body = document.getElementById("ivContextBody");
    var more = document.getElementById("ivContextMore");
    if (!box || !body || !more || box.hidden) return;
    more.hidden = body.scrollHeight <= body.clientHeight + 2;
  }

  (function wireContextToggle() {
    var body = document.getElementById("ivContextBody");
    var more = document.getElementById("ivContextMore");
    if (!body || !more) return;
    more.addEventListener("click", function () {
      var clamped = body.classList.toggle("is-clamped");
      more.textContent = clamped ? "Read more" : "Show less";
    });
  })();

  function send(skipped) {
    if (!current) return;
    var text = skipped ? "" : answerEl.value.trim();
    var picks = skipped ? [] : selected.slice();
    if (!skipped && !text && !picks.length) {
      answerEl.focus();
      return;
    }
    sendBtn.disabled = true;
    skipBtn.disabled = true;

    var exchange = {
      prompt: current.prompt, answer: text, selected: picks, skipped: !!skipped
    };
    var seq = current.seq;
    current = null;
    setProcessingCopy("reading");
    setState("processing");

    fetch("/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seq: seq, answer: text, selected: picks, skipped: !!skipped
      })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (!data.ok) throw new Error("answer rejected");
      clearDraft();
      appendHistory(exchange);
    }).catch(function () {
      // The answer did not land. Put them back on the question with their
      // words intact rather than pretending it was received.
      current = { seq: seq, prompt: exchange.prompt, why: whyEl.textContent };
      answerEl.value = text;
      selected = picks;
      sendBtn.disabled = false;
      skipBtn.disabled = false;
      setState("asking");
    });
  }

  /* ---------- polling ---------- */

  // The server normally holds a poll open for ~20s, so re-polling on return is
  // paced by that. Never depend on it: anything that answers immediately — a
  // proxy, a short server timeout, a stubbed transport — would otherwise turn
  // this into a busy loop that pins a core.
  var MIN_POLL_GAP = 250;

  function repoll(startedAt) {
    var elapsed = Date.now() - startedAt;
    setTimeout(poll, elapsed >= MIN_POLL_GAP ? 0 : MIN_POLL_GAP - elapsed);
  }

  // Exactly one poll may be in flight. Without this, anything that kicks the
  // loop while it is already running forks a second one, and every fork ends
  // up calling finish() — which is how a closing summary once printed six
  // times, one per answer that had spawned a loop.
  var polling = false;

  function poll() {
    if (stopped || polling) return;
    polling = true;
    var startedAt = Date.now();
    fetch("/poll?after=" + encodeURIComponent(after))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        polling = false;
        failures = 0;
        if (data.done) {
          finish(data.summary);
          return;
        }
        if (data.question) {
          showQuestion(data.question);
        }
        repoll(startedAt);         // waiting, or watching for the next question
      })
      .catch(function () {
        polling = false;
        failures++;
        // A long-poll can be cut by a sleeping laptop or a restarted network,
        // so one failure means nothing. Several in a row means the agent is
        // gone, and saying so beats animating forever.
        if (failures >= 4) {
          setState("lost");
          stopped = true;
          return;
        }
        setTimeout(poll, 1500 * failures);
      });
  }

  var finished = false;

  function finish(summary) {
    if (finished) return;
    finished = true;
    stopped = true;
    clearDraft();
    if (summary) {
      var note = document.createElement("p");
      note.className = "iv-summary";
      note.textContent = summary;
      doneBody.appendChild(note);
    }
    setState("done");
  }

  /* ---------- dictation nudge ---------- */

  function dictationHint() {
    var box = document.getElementById("ivDictate");
    if (!box) return;
    try {
      if (localStorage.getItem("qsurface:dictate-dismissed") === "1") return;
    } catch (err) { /* private browsing */ }

    var platform = (navigator.platform || navigator.userAgent || "").toLowerCase();
    var hint = "";
    if (platform.indexOf("mac") !== -1) {
      hint = "Prefer to talk? Press the microphone key, or Fn twice, to dictate.";
    } else if (platform.indexOf("win") !== -1) {
      hint = "Prefer to talk? Press Windows + H to dictate.";
    }
    if (!hint) return;                 // no reliable local dictation to point at

    box.querySelector("span").textContent = hint;
    box.hidden = false;
    box.querySelector("button").addEventListener("click", function () {
      box.hidden = true;
      try { localStorage.setItem("qsurface:dictate-dismissed", "1"); } catch (err) {}
    });
  }

  /* ---------- wiring ---------- */

  sendBtn.addEventListener("click", function () { send(false); });
  skipBtn.addEventListener("click", function () { send(true); });
  answerEl.addEventListener("input", saveDraft);
  answerEl.addEventListener("keydown", function (ev) {
    if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") send(false);
  });

  (CFG.exchanges || []).forEach(appendHistory);
  dictationHint();
  setProcessingCopy(after > 0 ? "resume" : "start");
  setState("processing");
  poll();
})();
