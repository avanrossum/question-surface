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

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* ---------- history ---------- */

  function appendHistory(exchange) {
    var row = document.createElement("div");
    row.className = "iv-exchange" + (exchange.skipped ? " is-skipped" : "");
    row.innerHTML =
      '<div class="iv-q">' + escapeHtml(exchange.prompt) + "</div>" +
      '<div class="iv-a">' +
      escapeHtml(exchange.skipped ? "Skipped." : exchange.answer) +
      "</div>";
    historyEl.appendChild(row);
  }

  /* ---------- drafts ---------- */

  function saveDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        seq: current ? current.seq : 0, text: answerEl.value
      }));
    } catch (err) { /* private browsing */ }
  }

  function restoreDraft(seq) {
    try {
      var saved = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
      if (saved && saved.seq === seq && saved.text) answerEl.value = saved.text;
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
    restoreDraft(question.seq);

    chipsEl.innerHTML = "";
    var options = question.options || [];
    chipsEl.hidden = options.length === 0;
    options.forEach(function (option) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "iv-chip";
      button.textContent = option;
      button.addEventListener("click", function () {
        answerEl.value = answerEl.value
          ? answerEl.value.replace(/\s*$/, "") + "\n" + option
          : option;
        answerEl.focus();
        saveDraft();
      });
      chipsEl.appendChild(button);
    });

    sendBtn.disabled = false;
    skipBtn.disabled = false;
    setState("asking");
    answerEl.focus();
  }

  function send(skipped) {
    if (!current) return;
    var text = skipped ? "" : answerEl.value.trim();
    if (!skipped && !text) {
      answerEl.focus();
      return;
    }
    sendBtn.disabled = true;
    skipBtn.disabled = true;

    var exchange = {
      prompt: current.prompt, answer: text, skipped: !!skipped
    };
    var seq = current.seq;
    current = null;
    setState("processing");

    fetch("/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seq: seq, answer: text, skipped: !!skipped })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (!data.ok) throw new Error("answer rejected");
      clearDraft();
      appendHistory(exchange);
      poll();
    }).catch(function () {
      // The answer did not land. Put them back on the question with their
      // words intact rather than pretending it was received.
      current = { seq: seq, prompt: exchange.prompt, why: whyEl.textContent };
      answerEl.value = text;
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

  function poll() {
    if (stopped) return;
    var startedAt = Date.now();
    fetch("/poll?after=" + encodeURIComponent(after))
      .then(function (r) { return r.json(); })
      .then(function (data) {
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

  function finish(summary) {
    stopped = true;
    clearDraft();
    if (summary) {
      var note = document.createElement("p");
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
  setState("processing");
  poll();
})();
