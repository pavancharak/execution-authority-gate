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
      <h1>Execution Authority Gate</h1>
      <p>Dual-layer fraud defense: a transaction is only allowed through when the <strong>detect</strong> layer scores it as low risk <em>and</em> the <strong>mandate</strong> layer confirms it's actually authorized against the customer's own history. Every final decision is signed by an external authority before it counts.</p>
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
        <h3>Generation layer — OpenAI API activity</h3>
        ${
          api.total_calls > 0
            ? `<div class="stat-row">
                ${statTile("Calls", api.total_calls.toLocaleString())}
                ${statTile("Tokens", api.total_tokens.toLocaleString())}
                ${statTile("Cost", fmtCost(api.total_cost_usd))}
                ${statTile("Avg latency", `${api.avg_latency_ms}ms`)}
              </div>`
            : `<p>No API calls recorded yet. Agents 1, 2, 4, and 7 call the real OpenAI API — set <code>OPENAI_API_KEY</code> in a repo-root <code>.env</code> and run the generate layer to populate this.</p>`
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
      <p>Seven ways AI commits payment fraud. Six are actively simulated by bounded agents in <code>generate/src/fraud_agents.py</code>; one (feedback-loop poisoning) is an honest, documented gap.</p>
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
      <p>A RandomForest classifier trained on six transaction features, proposing BLOCK / FLAG / ALLOW by fraud score. This layer only proposes — nothing here is final until the mandate and sign layers run too.</p>
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
          `Of ${totalFlagged} transactions flagged, ${cm.true_positive} are real fraud — the detect layer's job is recall, not precision; see note below`
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
          to flag aggressively, which produces false positives — the same trade-off airport security makes to catch
          most weapons at the cost of flagging some harmless bags.
        </p>
        <p>
          Precision (${fmtPct(m.precision)}) measures the <em>detect layer alone</em>, in isolation, on this
          held-out test set. It is not the system's real-world false-accusation rate: nothing here is auto-executed
          off a detect-layer flag. A flag still has to clear the <strong>mandate</strong> layer's independent,
          rule-based check before anything is blocked, and every final decision — ALLOW or BLOCK — is signed and
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
    time_restriction: "Time-of-day window",
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
      <p>Deterministic authorization rules, independent of the fraud score. Each customer's mandate — spending limit, allowed merchants, allowed hours, daily transaction count — is derived from their own known-good transaction history, not hand-authored.</p>
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
      <p>Every final decision is signed with Ed25519 by an external authority — neither the detector nor the mandate checker holds a private key. Anyone can verify a signature independently using only the public key on disk, with no access to any private key.</p>
    </div>

    <div class="section">
      <div class="card">
        <div class="sig-line">
          <span class="dot ${v.all_verified ? "good" : "critical"}"></span>
          <strong>${v.verified}/${v.total}</strong>&nbsp;signed decisions verify independently
        </div>
        <p>Verification uses only <code>sign/tokens/authority_public_key.pem</code> — a script that can verify a signature cannot forge one.</p>
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

const RENDERERS = {
  overview: renderOverview,
  attacks: renderAttacks,
  detect: renderDetect,
  mandate: renderMandate,
  proof: renderProof,
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

  const panels = {};
  for (const name of Object.keys(RENDERERS)) {
    panels[name] = RENDERERS[name](data);
  }

  app.innerHTML = Object.entries(panels)
    .map(([name, html], i) => `<div class="panel${i === 0 ? " active" : ""}" data-panel="${name}">${html}</div>`)
    .join("");

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
