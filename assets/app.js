/* Question Surface — form behaviour.
   No dependencies. Answers live in a single `state` object keyed by question id;
   every interaction funnels through setValue() so conditionals, progress and
   draft persistence all update from one place. */

(function () {
  "use strict";

  var CFG = window.__QS__ || {};
  var STORAGE_KEY = "qsurface:" + CFG.id;
  var state = {};
  var draftTimer = null;

  var form = document.getElementById("qform");
  var progressFill = document.getElementById("progressFill");
  var progressCount = document.getElementById("progressCount");
  var submitSummary = document.getElementById("submitSummary");
  var submitBtn = document.getElementById("submitBtn");
  var saveDraftBtn = document.getElementById("saveDraft");
  var draftState = document.getElementById("draftState");
  var result = document.getElementById("result");

  function entry(qid) {
    if (!state[qid]) state[qid] = { value: null, unknown: false, notes: "" };
    return state[qid];
  }

  /* ---------- reading + writing ---------- */

  function setValue(qid, value) {
    entry(qid).value = value;
    onChange();
  }

  function questionEl(qid) {
    return form.querySelector('.q[data-qid="' + CSS.escape(qid) + '"]');
  }

  function isEmpty(value) {
    return value === null || value === undefined || value === "" ||
      (Array.isArray(value) && value.length === 0);
  }

  /* ---------- conditionals ---------- */

  function conditionMet(cond) {
    var target = state[cond.question];
    var value = target ? target.value : null;
    if ("answered" in cond) {
      return cond.answered ? !isEmpty(value) : isEmpty(value);
    }
    if ("equals" in cond) return String(value) === String(cond.equals);
    if ("not_equals" in cond) return String(value) !== String(cond.not_equals);
    if ("includes" in cond) {
      return Array.isArray(value) && value.indexOf(cond.includes) !== -1;
    }
    if ("any_of" in cond) {
      var wanted = cond.any_of || [];
      if (Array.isArray(value)) {
        return value.some(function (v) { return wanted.indexOf(v) !== -1; });
      }
      return wanted.indexOf(value) !== -1;
    }
    return true;
  }

  function applyConditionals() {
    Object.keys(CFG.conditions || {}).forEach(function (qid) {
      var el = questionEl(qid);
      if (!el) return;
      var show = conditionMet(CFG.conditions[qid]);
      el.hidden = !show;
      // A hidden question must not count as unanswered, and must not carry a
      // stale answer from before the branch was taken away — in the state or
      // on the control. Clearing only the state leaves a radio still visibly
      // checked if the branch comes back, so the respondent sees a filled-in
      // answer that submit reports as blank.
      if (!show) clearEntry(qid, el);
    });
  }

  function clearEntry(qid, el) {
    var e = state[qid];
    if (!e) return;
    if (isEmpty(e.value) && !e.unknown && !e.notes) return;
    e.value = null;
    e.unknown = false;
    e.notes = "";
    delete e.reordered;
    clearControl(el);
  }

  function clearControl(el) {
    el.querySelectorAll("input.qs-input").forEach(function (input) {
      if (input.type === "radio" || input.type === "checkbox") input.checked = false;
      else input.value = "";
    });
    el.querySelectorAll("textarea.qs-input").forEach(function (input) {
      input.value = "";
    });
    el.querySelectorAll(".scale-btn").forEach(function (btn) {
      btn.classList.remove("selected");
    });
    var unknownBox = el.querySelector(".qs-unknown");
    if (unknownBox) unknownBox.checked = false;
    var notesBox = el.querySelector(".qs-notes");
    if (notesBox) notesBox.value = "";
  }

  function visibleQuestions() {
    return Array.prototype.filter.call(form.querySelectorAll(".q"), function (el) {
      return !el.hidden;
    });
  }

  /* ---------- progress ---------- */

  function onChange() {
    applyConditionals();
    seedRanks();
    paint();
    queueDraft();
  }

  /* ---------- rank seeding ----------
     A rank question renders a complete ordering the moment it appears, so an
     untouched list already reads as an answer. Counting it blank forces a
     respondent who agrees with the presented order to drag something to prove
     it. Record the presented order instead, and carry `reordered` so the
     reader can still tell acceptance from inattention. */

  function orderOf(list) {
    return Array.prototype.map.call(
      list.querySelectorAll(".rank-item"), function (item) { return item.dataset.value; }
    );
  }

  function seedRanks() {
    form.querySelectorAll(".rank-list").forEach(function (list) {
      var el = list.closest(".q");
      if (el && el.hidden) return;
      var e = entry(list.dataset.qid);
      if (!isEmpty(e.value)) return;
      e.value = orderOf(list);
      e.reordered = false;
    });
  }

  function paint() {
    var visible = visibleQuestions();
    var answered = 0;
    var missingRequired = 0;

    visible.forEach(function (el) {
      var qid = el.dataset.qid;
      var e = entry(qid);
      var done = e.unknown || !isEmpty(e.value);
      el.classList.toggle("answered", done);
      el.classList.toggle("is-unknown", !!e.unknown);
      if (done) answered++;
      else if (el.dataset.required === "true") missingRequired++;
      if (!done) el.classList.remove("missing");
    });

    var pct = visible.length ? (answered / visible.length) * 100 : 0;
    progressFill.style.width = pct + "%";
    progressCount.textContent = answered;

    var unknowns = visible.filter(function (el) {
      return entry(el.dataset.qid).unknown;
    }).length;

    var bits = [answered + " of " + visible.length + " answered"];
    if (unknowns) bits.push(unknowns + " flagged unknown");
    if (missingRequired) bits.push(missingRequired + " required still blank");
    submitSummary.textContent = bits.join(" · ");

    document.querySelectorAll(".section").forEach(function (section) {
      var qs = Array.prototype.filter.call(section.querySelectorAll(".q"), function (el) {
        return !el.hidden;
      });
      var allDone = qs.length > 0 && qs.every(function (el) {
        return el.classList.contains("answered");
      });
      var nav = document.querySelector('.nav-item[data-section="' + section.dataset.section + '"]');
      if (nav) nav.classList.toggle("done", allDone);
    });
  }

  /* ---------- drafts ---------- */

  function queueDraft() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload()));
    } catch (err) { /* private browsing — server draft still covers us */ }

    if (CFG.standalone) return;
    draftState.textContent = "Saving draft…";
    draftState.classList.add("saving");
    clearTimeout(draftTimer);
    draftTimer = setTimeout(function () {
      fetch("/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: CFG.id, payload: payload() })
      }).then(function () {
        draftState.textContent = "Draft saved " + new Date().toLocaleTimeString();
      }).catch(function () {
        draftState.textContent = "Draft saved locally only";
      }).finally(function () {
        draftState.classList.remove("saving");
      });
    }, 1200);
  }

  function payload() {
    var out = {};
    Object.keys(state).forEach(function (qid) {
      var e = state[qid];
      if (isEmpty(e.value) && !e.unknown && !e.notes) return;
      out[qid] = { value: e.value, unknown: e.unknown, notes: e.notes };
      if (e.reordered !== undefined) out[qid].reordered = e.reordered;
    });
    return out;
  }

  function restore(saved) {
    if (!saved) return;
    Object.keys(saved).forEach(function (qid) {
      if (qid.indexOf("__") === 0) return;
      var el = questionEl(qid);
      if (!el) return;
      var s = saved[qid] || {};
      var e = entry(qid);
      e.value = s.value === undefined ? null : s.value;
      e.unknown = !!s.unknown;
      e.notes = s.notes || "";
      if (s.reordered !== undefined) e.reordered = !!s.reordered;

      var unknownBox = el.querySelector(".qs-unknown");
      if (unknownBox) unknownBox.checked = e.unknown;
      var notesBox = el.querySelector(".qs-notes");
      if (notesBox) notesBox.value = e.notes;
      paintControl(el, e.value);
    });
  }

  function paintControl(el, value) {
    var type = el.dataset.type;
    if (isEmpty(value)) return;

    if (type === "single") {
      var radio = el.querySelector('input[value="' + CSS.escape(String(value)) + '"]');
      if (radio) radio.checked = true;
    } else if (type === "multi") {
      (value || []).forEach(function (v) {
        var box = el.querySelector('input[value="' + CSS.escape(String(v)) + '"]');
        if (box) box.checked = true;
      });
    } else if (type === "scale") {
      el.querySelectorAll(".scale-btn").forEach(function (btn) {
        btn.classList.toggle("selected", btn.dataset.value === String(value));
      });
    } else if (type === "rank") {
      var list = el.querySelector(".rank-list");
      (value || []).slice().reverse().forEach(function (v) {
        var item = list.querySelector('[data-value="' + CSS.escape(String(v)) + '"]');
        if (item) list.insertBefore(item, list.firstChild);
      });
      renumber(list);
    } else {
      var input = el.querySelector(".text-input");
      if (input) input.value = value;
    }
  }

  /* ---------- wiring ---------- */

  form.addEventListener("change", function (ev) {
    var t = ev.target;
    if (t.classList.contains("qs-unknown")) {
      entry(t.dataset.qid).unknown = t.checked;
      onChange();
      return;
    }
    if (t.type === "radio" && t.classList.contains("qs-input")) {
      setValue(t.dataset.qid, t.value);
      return;
    }
    if (t.type === "checkbox" && t.classList.contains("qs-input")) {
      var qid = t.dataset.qid;
      var el = questionEl(qid);
      var picked = Array.prototype.map.call(
        el.querySelectorAll("input:checked"), function (i) { return i.value; }
      );
      setValue(qid, picked);
      return;
    }
    if (t.classList.contains("text-input")) setValue(t.dataset.qid, t.value);
  });

  form.addEventListener("input", function (ev) {
    var t = ev.target;
    if (t.classList.contains("qs-notes")) {
      entry(t.dataset.qid).notes = t.value;
      queueDraft();
    } else if (t.classList.contains("text-input")) {
      setValue(t.dataset.qid, t.value);
    }
  });

  form.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".scale-btn");
    if (!btn) return;
    var scale = btn.closest(".scale");
    scale.querySelectorAll(".scale-btn").forEach(function (b) {
      b.classList.toggle("selected", b === btn);
    });
    setValue(scale.dataset.qid, Number(btn.dataset.value));
  });

  /* ---------- rank drag + drop ---------- */

  function renumber(list) {
    list.querySelectorAll(".rank-item").forEach(function (item, i) {
      item.querySelector(".rank-num").textContent = i + 1;
    });
  }

  form.querySelectorAll(".rank-list").forEach(function (list) {
    renumber(list);
    var dragging = null;

    list.addEventListener("dragstart", function (ev) {
      dragging = ev.target.closest(".rank-item");
      if (dragging) dragging.classList.add("dragging");
    });

    list.addEventListener("dragend", function () {
      if (!dragging) return;
      dragging.classList.remove("dragging");
      dragging = null;
      renumber(list);
      commitRank(list);
    });

    list.addEventListener("dragover", function (ev) {
      ev.preventDefault();
      if (!dragging) return;
      var after = null;
      var items = Array.prototype.filter.call(
        list.querySelectorAll(".rank-item:not(.dragging)"),
        function () { return true; }
      );
      for (var i = 0; i < items.length; i++) {
        var box = items[i].getBoundingClientRect();
        if (ev.clientY < box.top + box.height / 2) { after = items[i]; break; }
      }
      if (after) list.insertBefore(dragging, after);
      else list.appendChild(dragging);
    });

  });

  function commitRank(list) {
    var qid = list.dataset.qid;
    entry(qid).reordered = true;
    setValue(qid, orderOf(list));
  }

  /* ---------- submit ---------- */

  function submit() {
    var missing = visibleQuestions().filter(function (el) {
      if (el.dataset.required !== "true") return false;
      var e = entry(el.dataset.qid);
      return !e.unknown && isEmpty(e.value);
    });

    if (missing.length) {
      missing.forEach(function (el) { el.classList.add("missing"); });
      missing[0].scrollIntoView({ behavior: "smooth", block: "center" });
      show("error", "<h2>" + missing.length + " required question" +
        (missing.length === 1 ? "" : "s") + " still blank</h2>" +
        "<p>Answer them, or tick <em>Don't know</em> to flag for research.</p>");
      return;
    }

    if (CFG.standalone) {
      show("ok", "<h2>Preview mode</h2><p>This is a standalone render with no " +
        "server behind it. Run <code>qsurface serve</code> to capture answers.</p>" +
        "<pre>" + escapeHtml(JSON.stringify(payload(), null, 2)) + "</pre>");
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting…";

    fetch("/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: CFG.id, payload: payload() })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (!data.ok) throw new Error(data.error || "submit failed");
      try { localStorage.removeItem(STORAGE_KEY); } catch (err) {}
      show("ok", "<h2>Answers recorded</h2><p>Written to:</p><p><code>" +
        escapeHtml(data.json) + "</code><br><code>" + escapeHtml(data.markdown) +
        "</code></p><p>You can close this tab — the terminal has the path.</p>");
      submitBtn.textContent = "Submitted";
      document.querySelector(".submit-actions").style.opacity = ".5";
    }).catch(function (err) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit answers";
      show("error", "<h2>Submit failed</h2><p>" + escapeHtml(String(err)) +
        "</p><p>Your draft is saved — retry, or copy the JSON from the terminal.</p>");
    });
  }

  function show(kind, html) {
    result.hidden = false;
    result.className = "result" + (kind === "error" ? " error" : "");
    result.innerHTML = html;
    result.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  submitBtn.addEventListener("click", submit);
  saveDraftBtn.addEventListener("click", function () {
    queueDraft();
    draftState.textContent = "Draft saved " + new Date().toLocaleTimeString();
  });

  /* ---------- section nav highlight ---------- */

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      document.querySelectorAll(".nav-item").forEach(function (n) {
        n.classList.toggle("active", n.dataset.section === e.target.dataset.section);
      });
    });
  }, { rootMargin: "-10% 0px -70% 0px" });

  document.querySelectorAll(".section").forEach(function (s) { observer.observe(s); });

  /* ---------- boot ---------- */

  var local = null;
  try { local = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); } catch (err) {}
  restore(Object.keys(CFG.draft || {}).length ? CFG.draft : local);
  onChange();
})();
