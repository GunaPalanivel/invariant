(function () {
  const data = window.INVARIANT_RUNS || { runs: [] };
  const STAGES = ["intake", "contract", "generate", "verify", "publish"];

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function outcomeClass(run) {
    const o = run.outcome;
    if (o === "complete") return "pass";
    if (o === "unknown") return "unknown";
    return "fail";
  }

  function pipMark(status) {
    if (status === "pass" || status === "published") return "✓";
    if (status === "fail" || status === "failed") return "×";
    if (status === "warn" || status === "unknown" || status === "pending") return "!";
    return "·";
  }

  function pipClass(status) {
    if (status === "pass" || status === "published") return "pass";
    if (status === "fail" || status === "failed") return "fail";
    if (status === "unknown" || status === "warn" || status === "pending") return "unknown";
    return "run";
  }

  function formatUpdated(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return { date: iso, time: "" };
    return {
      date: d.toISOString().slice(0, 10),
      time: d.toISOString().slice(11, 19) + " UTC",
    };
  }

  function copyText(text) {
    if (navigator.clipboard) navigator.clipboard.writeText(text);
  }

  function applyTableMode() {
    const scroller = document.querySelector(".table-scroll");
    if (!scroller) return;
    const w = window.innerWidth;
    if (w >= 1100) scroller.dataset.mode = "full";
    else if (w >= 768) scroller.dataset.mode = "pane";
    else scroller.dataset.mode = "cards";
  }

  function renderRuns() {
    const tbody = $("#runs-body");
    const cards = $("#run-cards");
    if (!tbody) return;
    const q = ($("#search") && $("#search").value || "").toLowerCase();
    const outcome = $("#outcome-filter") && $("#outcome-filter").value;
    const pageSize = Number($("#page-size") && $("#page-size").value) || 50;
    const page = Number(document.body.dataset.page || "1");
    let rows = data.runs.slice();
    if (q) {
      rows = rows.filter((r) => (r.incident_title + r.run_id).toLowerCase().includes(q));
    }
    if (outcome && outcome !== "all") {
      rows = rows.filter((r) => r.outcome === outcome);
    }
    const total = rows.length;
    const start = (page - 1) * pageSize;
    const pageRows = rows.slice(start, start + pageSize);
    $("#count-note").textContent = `${pageRows.length} on this page · ${total} total`;
    const range = total === 0 ? "0–0 of 0" : `${start + 1}–${start + pageRows.length} of ${total}`;
    document.querySelectorAll("[data-range]").forEach((el) => { el.textContent = range; });
    tbody.innerHTML = "";
    cards.innerHTML = "";
    pageRows.forEach((run) => {
      const upd = formatUpdated(run.updated);
      const stripe = outcomeClass(run);
      const tr = document.createElement("tr");
      tr.className = "stripe " + stripe;
      tr.addEventListener("click", () => { location.href = "run.html?id=" + encodeURIComponent(run.run_id); });
      const pips = STAGES.map((s) => {
        const st = run.stages[s];
        return `<span class="pip ${pipClass(st)}" title="${s}">${pipMark(st)}</span>`;
      }).join("");
      tr.innerHTML = `
        <td><div class="incident-title">${run.incident_title}</div><div class="mono">${run.run_id}</div></td>
        <td><div>${upd.date}</div><div class="mono">${upd.time}</div></td>
        <td><div>${run.destination}</div><div class="mono">${run.operation_id}</div></td>
        <td><div class="pips">${pips}</div></td>
        <td>${run.outcome}</td>
        <td>${run.next_action}</td>`;
      tbody.appendChild(tr);
      const card = document.createElement("article");
      card.className = "card stripe " + stripe;
      card.style.setProperty("--stripe", stripe === "pass" ? "#059669" : stripe === "unknown" ? "#d97706" : "#dc2626");
      card.innerHTML = `<h2>${run.incident_title}</h2>
        <div class="mono">${run.run_id}</div>
        <p>${upd.date} ${upd.time}</p>
        <p>${run.destination} · <span class="mono">${run.operation_id}</span></p>
        <div class="pips">${pips}</div>
        <p>Outcome: ${run.outcome}</p>
        <p>${run.next_action}</p>`;
      card.addEventListener("click", () => { location.href = "run.html?id=" + encodeURIComponent(run.run_id); });
      cards.appendChild(card);
    });
    const pages = Math.max(1, Math.ceil(total / pageSize));
    document.querySelectorAll("[data-pages]").forEach((el) => {
      el.innerHTML = "";
      for (let i = 1; i <= pages; i += 1) {
        const b = document.createElement("button");
        b.textContent = String(i);
        if (i === page) b.className = "current";
        b.addEventListener("click", () => { document.body.dataset.page = String(i); renderRuns(); });
        el.appendChild(b);
      }
    });
  }

  function bindRuns() {
    applyTableMode();
    window.addEventListener("resize", applyTableMode);
    ["search", "outcome-filter", "page-size"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("input", () => { document.body.dataset.page = "1"; renderRuns(); });
      if (el) el.addEventListener("change", () => { document.body.dataset.page = "1"; renderRuns(); });
    });
    document.querySelectorAll("[data-prev]").forEach((b) => b.addEventListener("click", () => {
      document.body.dataset.page = String(Math.max(1, Number(document.body.dataset.page || "1") - 1));
      renderRuns();
    }));
    document.querySelectorAll("[data-next]").forEach((b) => b.addEventListener("click", () => {
      document.body.dataset.page = String(Number(document.body.dataset.page || "1") + 1);
      renderRuns();
    }));
    renderRuns();
  }

  function param(name) {
    return new URLSearchParams(location.search).get(name);
  }

  function renderStage(run, name) {
    const root = $("#stage-panel");
    if (name === "intake") {
      root.innerHTML = `<div class="panel">
        <p class="eyebrow">// Intake</p>
        <p>${run.intake.thread_excerpt}</p>
        <p>Linear: <span class="mono">${run.intake.linear_issue_id}</span></p>
        <p>Repo: <span class="mono">${run.intake.authorized_repo}</span></p>
        <p>Timestamps: <span class="mono">${(run.intake.source_timestamps || []).join(", ")}</span></p>
        <p>${run.intake.fault_label}</p>
      </div>`;
      return;
    }
    if (name === "contract") {
      const c = run.contract;
      const spans = (c.source_spans || []).map((s) => {
        const cls = s.grounded ? "" : "ungrounded";
        const chip = s.grounded ? "Accept" : "Ungrounded";
        return `<div class="acc-row ${cls}"><button type="button"><span>${s.field} · ${s.source} ${s.locator || ""}</span><span class="chip ${s.grounded ? "ok" : "unk"}">${chip}</span></button><div class="hidden"><p>${s.excerpt}</p></div></div>`;
      }).join("");
      root.innerHTML = `<div class="grid-2">
        <div class="panel"><p class="eyebrow">// Intended behavior</p>
          <p>Destination: <span class="mono">${c.destination}</span></p>
          <p>Operation: <span class="mono">${c.operation_id}</span></p>
          <p>Content: ${c.content}</p>
          <p>${c.completion_rule}</p>
        </div>
        <div class="panel"><p class="eyebrow">// Grounded sources</p><div class="accordion">${spans}</div></div>
      </div>
      <div class="panel" style="margin-top:12px"><p class="eyebrow">// Contract</p>
        <pre class="mono">${JSON.stringify({
          destination: c.destination,
          operation_id: c.operation_id,
          content: c.content,
          completion_rule: c.completion_rule,
          read_status: ["confirmed_present", "confirmed_absent_under_contract", "unknown"],
          contract_hash: c.contract_hash,
        }, null, 2)}</pre>
      </div>`;
      root.querySelectorAll(".acc-row button").forEach((btn) => {
        btn.addEventListener("click", () => btn.nextElementSibling.classList.toggle("hidden"));
      });
      return;
    }
    if (name === "generate") {
      const     g = run.generate;
      root.innerHTML = `<div class="panel">
        <p class="eyebrow">// Generate</p>
        <p>Origin: <span class="badge">${g.test_origin}</span> <span class="badge">${g.generation_origin || "disclosed_template"}</span></p>
        <p>Hash: <span class="mono">${g.hash}</span></p>
        <p>AUT entrypoint: <span class="mono">${g.aut_entrypoint}</span></p>
        <p>${g.invalid_test ? "invalid_test: generation did not produce a runnable pack; labeled template used." : (g.generation_reason || "Runnable pack produced.")}</p>
      </div>`;
      return;
    }
    if (name === "verify") {
      const v = run.verify;
      const hero = v.hero || {};
      const cells = v.comparison.map((cell, idx) => {
        const rc = cell.result_class;
        const chip = rc === "intended_assertion_failed" ? "bad" : rc === "intended_assertion_passed" ? "ok" : "unk";
        const outcomeChip = cell.application_outcome === "unknown" ? "unk" : cell.application_outcome === "complete" ? "ok" : "bad";
        const heroCls = idx === 0 ? " hero" : "";
        const kicker = idx === 0 && hero.kicker ? `<p class="hero-kicker">${hero.kicker}</p>` : "";
        return `<div class="panel${heroCls}"><h3>${cell.label}</h3>
          ${kicker}
          <p>${cell.title}</p>
          <p class="mono">${cell.named_assertion}</p>
          <p><span class="chip ${chip}">${rc}</span> <span class="chip ${outcomeChip}">${cell.application_outcome}</span></p>
          ${idx === 0 && (hero.fault_label || run.intake && run.intake.fault_label) ? `<p class="injected">${hero.fault_label || run.intake.fault_label}</p>` : ""}
        </div>`;
      }).join("");
      const strip = v.status_strip;
      const findings = v.findings.map((f) => `<details class="finding panel"${f.open ? " open" : ""}>
        <summary>${f.case_id} · ${f.result_class} · ${f.application_outcome}</summary>
        <p>Expected: ${f.expected}</p>
        <p>Observed: ${f.observed}</p>
        <p>Violated invariant: ${f.violated_invariant}</p>
        <p class="unbound">Evidence: ${f.evidence_link}</p>
        <p>Next action: ${f.next_action}</p>
      </details>`).join("");
      const log = (v.event_log || []).map((e) => `${e.time}  ${e.owner}  ${e.message}`).join("\n");
      const cmp = run.comparison;
      let bake = "";
      if (cmp) {
        const inv = cmp.invariant || {};
        const weak = cmp.weak_control || {};
        const cap = cmp.capable_agent || {};
        bake = `<div class="bakeoff">
          <div class="panel"><h3>Weak control</h3><p>Labeled weak. False-accepts original duplicate: ${weak.false_acceptance_of_original_bug}</p></div>
          <div class="panel"><h3>Invariant</h3><p>Origin: <span class="badge">${inv.interpret_origin || run.interpret_origin || ""}</span> / <span class="badge">${inv.generation_origin || ""}</span></p><p>Pack valid: ${inv.pack_valid}</p></div>
          <div class="panel"><h3>Capable agent</h3><p>Status: ${cap.status || "unfinished"}</p><p>${cap.reason || cap.provider || ""}</p></div>
        </div>`;
      }
      const use = run.usefulness || (cmp && cmp.usefulness);
      const usePanel = use ? `<div class="panel"><p class="eyebrow">// Usefulness</p>
        <p>Reviewer: ${use.reviewer} (${use.reviewer_kind || "author"})</p>
        <p>Clock stop: ${use.clock_stop}</p>
        <p>${use.invariant_minutes}</p>
        <p>Superiority claim: ${use.superiority_claim}</p>
      </div>` : "";
      root.innerHTML = `${cells ? `<div class="compare">${cells}</div>` : ""}
        ${bake}
        ${usePanel}
        <div class="strip">
          <span class="chip">verification execution: ${strip.verification_execution}</span>
          <span class="chip">application correctness: ${strip.application_correctness}</span>
          <span class="chip unk">unresolved evidence: ${strip.unresolved_evidence}</span>
          <span class="chip">publication: ${strip.publication}</span>
        </div>
        ${findings}
        <details style="margin-top:12px"><summary>Event log</summary><pre class="log">${log}</pre></details>`;
      return;
    }
    const p = run.publish || {};
    root.innerHTML = `<div class="panel">
      <p class="eyebrow">// Publish</p>
      <p>Slack reply: <span class="mono">${p.slack_reply_ts || "—"}</span> (${p.slack_reply_status || "unknown"})</p>
      <p>Linear comment: <span class="mono">${p.linear_comment_id || "—"}</span> (${p.linear_comment_status || "unknown"})</p>
      <p>GitHub PR: ${run.evidence_links.github ? `<a href="${run.evidence_links.github}">${run.evidence_links.github}</a>` : "—"} (${p.github_pr_status || "unknown"})</p>
      <p class="unbound">CI: ${run.evidence_links.ci.reason}${run.evidence_links.ci.url ? ` · <a href="${run.evidence_links.ci.url}">${run.evidence_links.ci.url}</a>` : ""}</p>
      <p>Slack: ${run.evidence_links.slack || "deferred"} · Linear: ${run.evidence_links.linear || "deferred"}</p>
      <p>Injected AUT faults are not live Slack. Unknown publication is not published. Local journal objects only until a service is configured.</p>
    </div>`;
  }

  function bindDetail() {
    const id = param("id");
    const run = data.runs.find((r) => r.run_id === id) || data.runs[0];
    if (!run) {
      $("#stage-panel").innerHTML = "<p>No run records. Run <span class='mono'>python -m invariant.evaluate</span>.</p>";
      return;
    }
    $("#run-title").textContent = run.incident_title;
    $("#run-id").textContent = run.run_id;
    $("#aut-rev").textContent = run.aut_revision;
    $("#test-hash").textContent = run.generated_test_hash;
    $("#origin-badge").textContent = run.interpret_origin || run.test_origin;
    document.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => copyText(run[btn.dataset.copy] || btn.dataset.copyValue || ""));
    });
    $("#copy-run").addEventListener("click", () => copyText(run.run_id));
    $("#copy-sha").addEventListener("click", () => copyText(run.aut_revision));
    $("#copy-hash").addEventListener("click", () => copyText(run.generated_test_hash));
    const pipe = $("#pipeline");
    pipe.innerHTML = STAGES.map((s, i) => `<button type="button" class="stage${i === 3 ? " selected" : ""}" data-stage="${s}">
      <div class="name">${s[0].toUpperCase() + s.slice(1)}</div>
      <div class="pips"><span class="pip ${pipClass(run.stages[s])}">${pipMark(run.stages[s])}</span></div>
      <div class="viewing${i === 3 ? "" : " hidden"}">· viewing</div>
    </button>`).join("");
    let current = "verify";
    function select(name) {
      current = name;
      pipe.querySelectorAll(".stage").forEach((el) => {
        const on = el.dataset.stage === name;
        el.classList.toggle("selected", on);
        el.querySelector(".viewing").classList.toggle("hidden", !on);
      });
      renderStage(run, name);
    }
    pipe.querySelectorAll(".stage").forEach((el) => el.addEventListener("click", () => select(el.dataset.stage)));
    $("#refresh").addEventListener("click", () => location.reload());
    select(current);
  }

  window.InvariantConsole = { bindRuns, bindDetail };
})();
