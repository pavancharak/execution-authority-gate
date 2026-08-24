const SERIES = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5", "--series-6", "--series-7"];
const STATUS = { BLOCK: "--status-critical", FLAG: "--status-warning", ALLOW: "--status-good" };

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function fmtPct(x) {
  return `${(x * 100).toFixed(1)}%`;
}

function fmtMoney(x) {
  return `$${Number(x).toFixed(2)}`;
}

function fmtCost(x) {
  const n = Number(x);
  return n > 0 && n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = String(s);
  return div.innerHTML;
}

function statTile(label, value, cls = "", tooltip = "") {
  return `<div class="stat-tile"${tooltip ? ` title="${esc(tooltip)}"` : ""}>
    <div class="stat-label">${esc(label)}</div>
    <div class="stat-value ${cls}">${value}</div>
  </div>`;
}

/** rows: [{ name, value, max, colorVar }] */
function barChart(rows, { valueFmt = (v) => v } = {}) {
  const max = Math.max(...rows.map((r) => r.max ?? r.value), 1);
  const bars = rows
    .map((r) => {
      const pct = Math.max((r.value / max) * 100, r.value > 0 ? 1.5 : 0);
      const color = cssVar(r.colorVar);
      return `<div class="bar-row">
        <div class="bar-name">${esc(r.name)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%; background:${color}"></div></div>
        <div class="bar-value">${valueFmt(r.value)}</div>
      </div>`;
    })
    .join("");
  return `<div class="bar-chart">${bars}</div>`;
}

function legend(items) {
  return `<div class="legend">${items
    .map((it) => `<span class="legend-item"><span class="swatch" style="background:${cssVar(it.colorVar)}"></span>${esc(it.label)}</span>`)
    .join("")}</div>`;
}

function badge(decision) {
  const cls = decision.toLowerCase();
  return `<span class="badge ${cls}">${esc(decision)}</span>`;
}

function renderOverview(data) {
  const sim = data.simulation;
  const detect = data.detect.metrics;
  const pipeline = data.pipeline;
  const verification = data.verification;
  const api = data.api_activity.summary;

  const totalTx = sim.good_transaction_count + sim.fraud_transaction_count;

  const decisionRows = ["BLOCK", "FLAG", "ALLOW"].map((d) => ({
    name: d,
    value: pipeline.decision_counts[d] || 0,
    max: pipeline.total,
    colorVar: STATUS[d],
  }));

  return `
    <div class="section">
      <h1>Parmana Authority Gate</h1>
      <p>Two layer fraud defense: a transaction is only allowed through when the <strong>detect</strong> layer scores it as low risk <em>and</em> the <strong>mandate</strong> layer confirms it's actually authorized against the customer's own history. Every final decision is signed by an external authority before it counts.</p>
    </div>

    <div class="section">
      <h2>This run</h2>
      <div class="stat-row">
        ${statTile("Transactions processed", totalTx.toLocaleString())}
        ${statTile("Fraud caught", fmtPct(detect.fraud_caught_rate), "good")}
        ${statTile("False positive rate", fmtPct(detect.false_positive_rate))}
        ${statTile("Decisions signed", pipeline.total.toLocaleString())}
        ${statTile(
          "Signatures verified",
          `${verification.verified}/${verification.total}`,
          verification.all_verified ? "good" : "critical"
        )}
      </div>
    </div>

    <div class="section">
      <div class="card">
        <h3>Final decisions</h3>
        ${barChart(decisionRows)}
        ${legend(decisionRows.map((r) => ({ label: r.name, colorVar: r.colorVar })))}
      </div>
    </div>

    <div class="section">
      <div class="card">
        <h3>Generation layer, OpenAI API activity</h3>
        ${
          api.total_calls > 0
            ? `<div class="stat-row">
                ${statTile("Calls", api.total_calls.toLocaleString())}
                ${statTile("Tokens", api.total_tokens.toLocaleString())}
                ${statTile("Cost", fmtCost(api.total_cost_usd))}
                ${statTile("Avg latency", `${api.avg_latency_ms}ms`)}
              </div>`
            : `<p>No API calls recorded yet. Agents 1, 2, 4, and 7 call the real OpenAI API. Set <code>OPENAI_API_KEY</code> in a repo root <code>.env</code> and run the generate layer to populate this.</p>`
        }
      </div>
    </div>
  `;
}

function renderAttacks(data) {
  const attacks = data.attacks;
  const breakdown = data.simulation.attack_type_breakdown;
  const idToColor = {};
  attacks.forEach((a, i) => (idToColor[a.id] = SERIES[i % SERIES.length]));

  const breakdownRows = attacks
    .filter((a) => breakdown[a.id] !== undefined)
    .map((a) => ({ name: a.name, value: breakdown[a.id] || 0, colorVar: idToColor[a.id] }));

  const cards = attacks
    .map((a, i) => {
      const color = cssVar(SERIES[i % SERIES.length]);
      return `<div class="card attack-card">
        <div class="attack-stripe" style="background:${color}"></div>
        <div>
          <h2>${esc(a.name)}</h2>
          <p><strong>Where:</strong> ${esc(a.stage)}</p>
          <p><strong>Why it's hard to catch:</strong> ${esc(a.why_hard_to_catch)}</p>
          <p><strong>Damage:</strong> ${esc(a.damage)}</p>
          <div class="attack-meta">
            <span class="pill">${esc(a.simulated_by)}</span>
            ${a.real_llm_calls ? '<span class="pill">real OpenAI calls</span>' : '<span class="pill">local / no LLM</span>'}
          </div>
        </div>
      </div>`;
    })
    .join("");

  return `
    <div class="section">
      <h1>Attack taxonomy</h1>
      <p>Seven ways AI commits payment fraud. Six are actively simulated by bounded agents in <code>generate/src/fraud_agents.py</code>; one (feedback loop poisoning) is an honest, documented gap.</p>
    </div>

    ${
      breakdownRows.length
        ? `<div class="section"><div class="card"><h3>Generated fraud transactions by attack type</h3>${barChart(breakdownRows)}</div></div>`
        : ""
    }

    <div class="section">${cards}</div>
  `;
}

function renderDetect(data) {
  const m = data.detect.metrics;
  const cm = m.confusion_matrix;

  const signalRows = m.top_signals.map((s) => ({
    name: s.feature.replace(/_/g, " "),
    value: s.importance,
    max: m.top_signals[0].importance,
    colorVar: "--series-1",
  }));

  const totalFraud = cm.true_positive + cm.false_negative;
  const totalLegit = cm.true_negative + cm.false_positive;
  const totalFlagged = cm.true_positive + cm.false_positive;

  return `
    <div class="section">
      <h1>Detection layer</h1>
      <p>A RandomForest classifier trained on six transaction features, proposing BLOCK / FLAG / ALLOW by fraud score. This layer only proposes. Nothing here is final until the mandate and sign layers run too.</p>
    </div>

    <div class="section">
      <div class="stat-row">
        ${statTile(
          "Fraud caught",
          fmtPct(m.fraud_caught_rate),
          "good",
          `Catches ${cm.true_positive} of ${totalFraud} fraud cases in the test set`
        )}
        ${statTile(
          "False positive rate",
          fmtPct(m.false_positive_rate),
          "",
          `Flags ${cm.false_positive} of ${totalLegit} legitimate transactions`
        )}
        ${statTile(
          "Precision",
          fmtPct(m.precision),
          "",
          `Of ${totalFlagged} transactions flagged, ${cm.true_positive} are real fraud. The detect layer's job is recall, not precision; see note below`
        )}
      </div>
    </div>

    <div class="grid-2 section">
      <div class="card">
        <h3>Confusion matrix (test set)</h3>
        <div class="confusion-grid">
          <div class="confusion-cell"><div class="n">${cm.true_negative}</div><div class="label">True negative</div></div>
          <div class="confusion-cell"><div class="n">${cm.false_positive}</div><div class="label">False positive</div></div>
          <div class="confusion-cell"><div class="n">${cm.false_negative}</div><div class="label">False negative</div></div>
          <div class="confusion-cell"><div class="n">${cm.true_positive}</div><div class="label">True positive</div></div>
        </div>
      </div>
      <div class="card">
        <h3>Top signals (feature importance)</h3>
        ${barChart(signalRows, { valueFmt: (v) => v.toFixed(3) })}
      </div>
    </div>

    <div class="section">
      <div class="card">
        <h3>Why precision looks low</h3>
        <p>
          Fraud is rare here (${totalFraud} cases out of ${(totalFraud + totalLegit).toLocaleString()} transactions,
          about 2%). Tuning a classifier to catch ${fmtPct(m.fraud_caught_rate)} of that rare an event means it has
          to flag aggressively, which produces false positives. It is the same tradeoff airport security makes to catch
          most weapons at the cost of flagging some harmless bags.
        </p>
        <p>
          Precision (${fmtPct(m.precision)}) measures the <em>detect layer alone</em>, in isolation, on this
          held out test set. It is not the system's real world false accusation rate: nothing here is auto executed
          off a detect layer flag. A flag still has to clear the <strong>mandate</strong> layer's independent,
          rule based check before anything is blocked, and every final decision, ALLOW or BLOCK, is signed and
          auditable. See <code>docs/JUDGES_GUIDE.md</code> for the full breakdown.
        </p>
      </div>
    </div>
  `;
}

function renderMandate(data) {
  const md = data.mandate;
  const attrRows = [
    { name: "Detect caught it", value: md.block_attribution.detect_only, colorVar: "--series-1" },
    { name: "Mandate caught it", value: md.block_attribution.mandate_only, colorVar: "--series-2" },
    { name: "Both caught it", value: md.block_attribution.both, colorVar: "--series-3" },
  ];
  const maxAttr = Math.max(...attrRows.map((r) => r.value), 1);
  attrRows.forEach((r) => (r.max = maxAttr));

  const ruleLabels = {
    spending_limit: "Spending limit",
    merchant_whitelist: "Merchant whitelist",
    time_restriction: "Time of day window",
    velocity: "Daily velocity",
  };
  const ruleRows = Object.entries(md.rule_violation_counts).map(([rule, count]) => ({
    name: ruleLabels[rule] || rule,
    value: count,
    colorVar: "--series-1",
  }));

  const sampleRows = md.sample_mandate_only_blocks
    .map((e) => {
      const d = e.decision;
      const violated = d.violated_mandate_rules.map((r) => ruleLabels[r] || r).join(", ");
      return `<tr>
        <td class="mono">${esc(d.transaction_id)}</td>
        <td>${fmtMoney(e.ground_truth.amount)}</td>
        <td>${esc(e.ground_truth.merchant)}</td>
        <td>${esc(violated)}</td>
        <td>${esc(e.ground_truth.attack_type)}</td>
      </tr>`;
    })
    .join("");

  return `
    <div class="section">
      <h1>Mandate layer</h1>
      <p>Deterministic authorization rules, independent of the fraud score. Each customer's mandate, spending limit, allowed merchants, allowed hours, daily transaction count, is derived from their own known good transaction history, not hand authored.</p>
    </div>

    <div class="section">
      <div class="stat-row">
        ${statTile("Customer mandates derived", md.mandates_derived.toLocaleString())}
        ${statTile("Blocks from mandate alone", md.block_attribution.mandate_only.toLocaleString(), "good")}
      </div>
    </div>

    <div class="grid-2 section">
      <div class="card">
        <h3>Who caught each block</h3>
        ${barChart(attrRows)}
        ${legend(attrRows.map((r) => ({ label: r.name, colorVar: r.colorVar })))}
      </div>
      <div class="card">
        <h3>Mandate rule violations</h3>
        ${ruleRows.some((r) => r.value > 0) ? barChart(ruleRows) : `<p>No mandate violations in this run.</p>`}
      </div>
    </div>

    ${
      sampleRows
        ? `<div class="section">
            <div class="card">
              <h3>Fraud the detector missed, mandate caught</h3>
              <div class="table-wrap">
                <table>
                  <thead><tr><th>Transaction</th><th>Amount</th><th>Merchant</th><th>Violated rule</th><th>Attack type</th></tr></thead>
                  <tbody>${sampleRows}</tbody>
                </table>
              </div>
            </div>
          </div>`
        : ""
    }
  `;
}

/** Shared render for a full pipeline outcome, used by both the Attack
 * Walkthrough (precomputed, real, already signed decisions) and the
 * Live Test Harness (a decision computed live, right now, by this
 * request). txSummaryRows: [{label, value}]. */
function renderDecisionCard(txSummaryRows, decision, mandateChecks, verified) {
  const ruleLabels = {
    spending_limit: "Spending limit",
    merchant_whitelist: "Merchant whitelist",
    time_restriction: "Time of day window",
    velocity: "Daily velocity",
  };

  const txRows = txSummaryRows
    .map((r) => `<div class="kv-row"><span class="kv-key">${esc(r.label)}</span><span class="kv-value">${esc(r.value)}</span></div>`)
    .join("");

  const mandateRows = mandateChecks
    .map(
      (c) => `<tr>
        <td>${ruleLabels[c.rule] || c.rule}</td>
        <td>${c.passed ? '<span class="dot good"></span> pass' : '<span class="dot critical"></span> fail'}</td>
        <td>${esc(c.reason)}</td>
      </tr>`
    )
    .join("");

  return `
    <div class="pipeline-steps">
      <div class="card pipeline-step">
        <h3>Step 1 &middot; Detection</h3>
        <div class="stat-row">
          ${statTile("Fraud score", decision.fraud_score.toFixed(4))}
          ${statTile("Detect layer proposes", badge(decision.detect_decision))}
        </div>
        <p>${(decision.reasons || []).filter((r) => r.startsWith("detect:")).map((r) => esc(r.replace("detect: ", ""))).join(", ") || "no single dominant signal"}</p>
      </div>

      <div class="card pipeline-step">
        <h3>Step 2 &middot; Mandate</h3>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Rule</th><th>Result</th><th>Reason</th></tr></thead>
            <tbody>${mandateRows}</tbody>
          </table>
        </div>
      </div>

      <div class="card pipeline-step">
        <h3>Step 3 &middot; Signing</h3>
        <div class="sig-line">
          <span class="dot ${verified ? "good" : "critical"}"></span>
          <strong>${verified ? "Signature verifies" : "Signature does NOT verify"}</strong>
        </div>
        <div class="kv-block"><span class="kv-key">Ed25519 signature</span><span class="kv-value mono">${esc(decision.signature.slice(0, 32))}&hellip;</span></div>
        <div class="kv-block"><span class="kv-key">Signed by</span><span class="kv-value">${esc(decision.signer)}</span></div>
      </div>

      <div class="card pipeline-step">
        <h3>Step 4 &middot; Authority (final decision)</h3>
        <div class="sig-line" style="margin-bottom:12px">${badge(decision.final_decision)}</div>
        <p>${
          decision.final_decision === "BLOCK"
            ? (!decision.mandate_allowed
                ? `Mandate layer rejected it (${decision.violated_mandate_rules.map((r) => ruleLabels[r] || r).join(", ")}), blocked regardless of the detect score.`
                : `Detect layer scored it high risk (${decision.fraud_score.toFixed(2)}), blocked even though the mandate layer had no objection.`)
            : decision.final_decision === "FLAG"
            ? `Detect layer is unsure (${decision.fraud_score.toFixed(2)}) and the mandate layer has no objection, flagged for review, not auto blocked.`
            : `Low risk (${decision.fraud_score.toFixed(2)}) and every mandate rule passed, allowed.`
        }</p>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3>Transaction</h3>
      <div class="kv-grid">${txRows}</div>
    </div>
  `;
}

function renderWalkthrough(data, scenarios) {
  if (!scenarios || !scenarios.length) {
    return `<div class="section"><h1>Attack walkthrough</h1><p class="error-inline">Couldn't load data/attack_scenarios.json.</p></div>`;
  }

  const buttons = scenarios
    .map(
      (s, i) => `<button class="scenario-btn" data-scenario-id="${esc(s.id)}" data-index="${i}">
        <span class="scenario-name">${esc(s.name)}</span>
        ${badge(s.example.decision.final_decision)}
      </button>`
    )
    .join("");

  return `
    <div class="section">
      <h1>Attack walkthrough</h1>
      <p>Pick a real attack type below to see one actual, already signed decision from this repo's own pipeline run: the detect score, the mandate rules it hit, the signature, and why the final decision came out the way it did.</p>
    </div>

    <div class="section">
      <div class="scenario-picker">${buttons}</div>
    </div>

    <div class="section" id="walkthrough-detail"></div>
  `;
}

function renderScenarioDetail(scenario) {
  const ex = scenario.example;
  const gt = ex.ground_truth;
  return `
    <div class="card" style="margin-bottom:14px">
      <h3>${esc(scenario.name)}</h3>
      <p><strong>Where:</strong> ${esc(scenario.stage)}</p>
      <p><strong>Why it's hard to catch:</strong> ${esc(scenario.why_hard_to_catch)}</p>
    </div>
    ${renderDecisionCard(
      [
        { label: "Amount", value: fmtMoney(gt.amount) },
        { label: "Merchant", value: gt.merchant },
        { label: "Currency", value: gt.currency },
        { label: "Ground truth", value: gt.is_fraud ? "Actually fraud" : "Actually legitimate" },
      ],
      ex.decision,
      ex.mandate_checks,
      ex.verified
    )}
  `;
}

function renderLiveTest(data, customersData) {
  const customers = (customersData && customersData.customers) || [];
  const merchants = (customersData && customersData.merchants) || [];

  if (!customers.length) {
    return `<div class="section"><h1>Live test harness</h1><p class="error-inline">Couldn't load data/demo_customers.json.</p></div>`;
  }

  const customerOptions = customers
    .map((c) => `<option value="${esc(c.customer_id)}">${esc(c.customer_name)} (${esc(c.customer_id)})</option>`)
    .join("");
  const merchantOptions = merchants.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");

  return `
    <div class="section">
      <h1>Live test harness</h1>
      <p>Submit a transaction and it runs through the real pipeline right now: the actual trained detector, the actual mandate rules derived from that customer's history, and a real Ed25519 signature from this deployment's own authority key.</p>
    </div>

    <div class="section">
      <div class="card">
        <form id="live-test-form" class="live-form">
          <label>Customer
            <select name="customer_id" required>${customerOptions}</select>
          </label>
          <label>Amount (USD)
            <input type="number" name="amount" min="0.01" max="1000000" step="0.01" value="50.00" required>
          </label>
          <label>Merchant
            <input list="merchant-list" name="merchant" value="${esc(merchants[0] || "")}" required>
            <datalist id="merchant-list">${merchantOptions}</datalist>
          </label>
          <label>Hour of day (0 to 23)
            <input type="number" name="hour_of_day" min="0" max="23" value="12" required>
          </label>
          <label>AI generated signal (0 to 1)
            <input type="number" name="ai_generated_signal" min="0" max="1" step="0.01" value="0.1" required>
          </label>
          <button type="submit" class="submit-btn">Run transaction</button>
        </form>
        <p class="form-hint">Each customer's mandate (spending limit, allowed merchants, allowed hours) was derived from their own real transaction history. Try an unlisted merchant or an odd hour to see the mandate layer object on its own.</p>
      </div>
    </div>

    <div class="section" id="live-test-result"></div>
  `;
}

function renderProof(data) {
  const v = data.verification;
  const sample = data.pipeline.sample_decisions.find((e) => e.decision.final_decision === "BLOCK") || data.pipeline.sample_decisions[0];

  const rows = data.pipeline.sample_decisions
    .slice(0, 12)
    .map((e) => {
      const d = e.decision;
      return `<tr>
        <td class="mono">${esc(d.transaction_id)}</td>
        <td>${d.fraud_score}</td>
        <td>${badge(d.final_decision)}</td>
        <td class="mono">${esc(d.signature.slice(0, 24))}&hellip;</td>
      </tr>`;
    })
    .join("");

  return `
    <div class="section">
      <h1>Proof</h1>
      <p>Every final decision is signed with Ed25519 by an external authority. Neither the detector nor the mandate checker holds a private key. Anyone can verify a signature independently using only the public key on disk, with no access to any private key.</p>
    </div>

    <div class="section">
      <div class="card">
        <div class="sig-line">
          <span class="dot ${v.all_verified ? "good" : "critical"}"></span>
          <strong>${v.verified}/${v.total}</strong>&nbsp;signed decisions verify independently
        </div>
        <p>Verification uses only <code>sign/tokens/authority_public_key.pem</code>. A script that can verify a signature cannot forge one.</p>
      </div>
    </div>

    ${
      sample
        ? `<div class="section">
            <div class="card">
              <h3>Example signed envelope</h3>
              <pre class="envelope">${esc(JSON.stringify(sample.decision, null, 2))}</pre>
            </div>
          </div>`
        : ""
    }

    <div class="section">
      <div class="card">
        <h3>Sample signed decisions</h3>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Transaction</th><th>Fraud score</th><th>Decision</th><th>Signature</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

async function fetchJsonSafe(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`Couldn't load ${url}: ${err.message}`);
    return null;
  }
}

function wireWalkthrough(scenarios) {
  const picker = document.querySelector('.panel[data-panel="walkthrough"] .scenario-picker');
  const detail = document.getElementById("walkthrough-detail");
  if (!picker || !detail || !scenarios) return;

  picker.addEventListener("click", (e) => {
    const btn = e.target.closest(".scenario-btn");
    if (!btn) return;
    picker.querySelectorAll(".scenario-btn").forEach((b) => b.classList.toggle("active", b === btn));
    const scenario = scenarios[Number(btn.dataset.index)];
    detail.innerHTML = renderScenarioDetail(scenario);
  });

  // Show the first scenario by default.
  const firstBtn = picker.querySelector(".scenario-btn");
  if (firstBtn) {
    firstBtn.classList.add("active");
    detail.innerHTML = renderScenarioDetail(scenarios[0]);
  }
}

function wireLiveTest() {
  const form = document.getElementById("live-test-form");
  const result = document.getElementById("live-test-result");
  if (!form || !result) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const submitBtn = form.querySelector(".submit-btn");
    submitBtn.disabled = true;
    submitBtn.textContent = "Running…";
    result.innerHTML = `<div class="loading">Running the live pipeline&hellip;</div>`;

    const fd = new FormData(form);
    const body = {
      customer_id: fd.get("customer_id"),
      amount: Number(fd.get("amount")),
      merchant: fd.get("merchant"),
      hour_of_day: Number(fd.get("hour_of_day")),
      ai_generated_signal: Number(fd.get("ai_generated_signal")),
    };

    try {
      const res = await fetch("api/demo/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`);

      const tx = payload.transaction;
      result.innerHTML = renderDecisionCard(
        [
          { label: "Customer", value: `${tx.customer_name} (${tx.customer_id})` },
          { label: "Amount", value: fmtMoney(tx.amount) },
          { label: "Merchant", value: tx.merchant },
          { label: "Hour of day", value: tx.hour_of_day },
          { label: "AI generated signal", value: tx.ai_generated_signal },
        ],
        payload.decision,
        payload.mandate_checks,
        payload.verified
      );
    } catch (err) {
      result.innerHTML = `<div class="error-inline">Couldn't run the live pipeline: ${esc(err.message)}.<br>The Live Test Harness needs the Flask server (<code>python web/server.py</code>). It isn't available under <code>python -m http.server</code>.</div>`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Run transaction";
    }
  });
}

const FAQ_ITEMS = [
  {
    q: "What makes this different from a typical fraud detection system?",
    a: "Most fraud tools stop at a risk score. This project adds a second, independent layer that checks the transaction against that specific customer's own history instead of a model's guess, and neither layer is treated as final until a separate authority signs the combined result. A model being confident is not the same as a transaction being authorized, and this project keeps those two ideas apart on purpose.",
  },
  {
    q: "What does this system actually allow that a fraud score alone does not?",
    a: "It lets anyone, a judge, an auditor, another system, check afterward that a specific decision was really made, by which layers, and was not silently changed. A score alone cannot prove any of that. The signature and the mandate check are what turn a model's opinion into something you can point to later.",
  },
  {
    q: "Why does this fit naturally into agentic commerce?",
    a: "When an AI agent is the one deciding whether to complete a payment, the question stops being only whether a transaction looks like fraud and becomes whether that agent was actually authorized to do it. A risk score cannot answer the second question, because it is about permission, not detection. The mandate layer checks permission against the customer's real history, and the signature makes that permission check something the agent itself cannot forge or quietly skip, since it never holds the signing key.",
  },
  {
    q: "Could an AI agent fake or skip this check?",
    a: "Not the signature. Nothing calling this pipeline, agent or otherwise, has access to the private signing key, so it cannot produce a valid signed ALLOW on its own. It could still choose not to call the pipeline at all, which is why this belongs at the point where a transaction actually executes, not as an optional step an agent can decide to skip. Wiring it into that execution point is not done in this repo yet, see the enforcement question below.",
  },
  {
    q: "Does this replace a human reviewer?",
    a: "No, and it is not trying to. FLAG decisions exist for exactly the cases where neither layer is confident enough to decide alone. What this project replaces is blind trust in a single model's score, not human judgment.",
  },
  {
    q: "Why is precision only 21.1%?",
    a: "Fraud is rare, about 2% of transactions in this dataset. Catching 89.1% of a rare event requires flagging aggressively, and that lowers precision. See the Detection tab for the full breakdown.",
  },
  {
    q: "Does a low precision flag mean legitimate transactions get blocked?",
    a: "No. A detect layer flag alone does not block anything. The mandate layer also has to object before a transaction is BLOCKed. Try it yourself on the Live Test tab: a low risk transaction at an unfamiliar merchant still gets BLOCKed by the mandate layer alone.",
  },
  {
    q: "Are the numbers on this dashboard real?",
    a: "Yes. The transactions, the fraud rate, the detection metrics, and the signatures all come from this repo's own generation and pipeline code, including real OpenAI calls for several agents. Nothing here is hand authored sample data.",
  },
  {
    q: "What is the difference between Attack Walkthrough and Live Test?",
    a: "Attack Walkthrough shows five real, already signed decisions pulled from an actual past pipeline run, one per attack type. Live Test runs a brand new transaction through the real model and rule engine right now, using whatever you type in.",
  },
  {
    q: "Is the Live Test result actually computed live, or just looked up?",
    a: "Computed live. The trained model scores it, the mandate rules check it against that customer's real history, and the result gets a fresh Ed25519 signature that is verified in the same request.",
  },
  {
    q: "Does this system actually stop a transaction from going through?",
    a: "No, and this project is upfront about that. It produces a signed decision, ALLOW, FLAG, or BLOCK. It does not call a payment processor or move money. Wiring a signed decision to real enforcement is a separate integration this repo does not include yet.",
  },
  {
    q: "Are signed decisions stored permanently?",
    a: "Not yet, in a durable way. Right now decisions are written to a single local file that gets overwritten on the next pipeline run. Turning that into an append only or externally stored log is a known gap, not a finished feature.",
  },
  {
    q: "Who is allowed to trigger a decision or call the API?",
    a: "There is currently no caller authentication on the pipeline or its API. Every decision is signed by the same authority identity regardless of who asked for it. This is a working prototype, not a production access control system.",
  },
  {
    q: "Why does the mandate layer use a customer's own history instead of one fixed rule for everyone?",
    a: "One fixed spending limit would be too loose for small spenders and too tight for big ones. Deriving each customer's limit, merchants, hours, and daily count from their own past good transactions makes the check specific to them.",
  },
  {
    q: "What happens if I try a merchant or hour outside a customer's normal pattern on Live Test?",
    a: "The mandate layer objects on that rule even when the detection score is low. That is the point: the two layers check different things, and either one objecting is enough to block the transaction.",
  },
];

function renderFAQ(data) {
  const items = FAQ_ITEMS.map(
    (item) => `<div class="card faq-item">
      <h3>${esc(item.q)}</h3>
      <p>${esc(item.a)}</p>
    </div>`
  ).join("");

  return `
    <div class="section">
      <h1>FAQ</h1>
      <p>The questions judges and users ask most often about this project.</p>
    </div>
    <div class="section">${items}</div>
  `;
}

const RENDERERS = {
  overview: renderOverview,
  attacks: renderAttacks,
  detect: renderDetect,
  mandate: renderMandate,
  proof: renderProof,
  faq: renderFAQ,
};

async function main() {
  const app = document.getElementById("app");
  let data;
  try {
    const res = await fetch("data/dashboard.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (err) {
    app.innerHTML = `<div class="error">Couldn't load data/dashboard.json (${esc(err.message)}).<br>Run the pipeline layer first: <code>cd pipeline/src && python run_pipeline.py</code></div>`;
    return;
  }

  const [scenarios, customersData] = await Promise.all([
    fetchJsonSafe("data/attack_scenarios.json"),
    fetchJsonSafe("data/demo_customers.json"),
  ]);

  const panels = {};
  for (const name of Object.keys(RENDERERS)) {
    panels[name] = RENDERERS[name](data);
  }
  panels.walkthrough = renderWalkthrough(data, scenarios);
  panels["live-test"] = renderLiveTest(data, customersData);

  const order = ["overview", "attacks", "walkthrough", "detect", "mandate", "live-test", "proof", "faq"];
  const DEFAULT_TAB = "live-test";
  app.innerHTML = order
    .map((name) => `<div class="panel${name === DEFAULT_TAB ? " active" : ""}" data-panel="${name}">${panels[name]}</div>`)
    .join("");

  wireWalkthrough(scenarios);
  wireLiveTest();

  document.getElementById("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab-btn");
    if (!btn) return;
    const tab = btn.dataset.tab;
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === tab));
    window.scrollTo({ top: 0, behavior: "instant" });
  });
}

main();
