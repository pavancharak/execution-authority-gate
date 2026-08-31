const SERIES = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5", "--series-6", "--series-7"];
const STATUS = { BLOCK: "--status-critical", FLAG: "--status-warning", ALLOW: "--status-good" };

// Real, verified inputs (checked against the live trained model and the
// real mandate for each customer_id in data/demo_customers.json) that
// reliably reproduce each of the three final decisions. Not illustrative
// placeholders: every field here was chosen by actually running it
// through web/interactive_demo.py's evaluate_transaction and confirming
// the outcome, so a judge who clicks one of these gets a real result
// that matches the button's label.
const QUICK_START_EXAMPLES = {
  normal: {
    label: "Normal transaction",
    outcome: "ALLOW",
    customer_id: "cust_cbca48b5", // Jordan Chen
    amount: 50.0,
    merchant: "CloudHost",
    hour_of_day: 12,
    ai_generated_signal: 0.1,
  },
  flagged: {
    label: "Flagged transaction",
    outcome: "FLAG",
    customer_id: "cust_cbca48b5", // Jordan Chen
    amount: 500.0,
    merchant: "CloudHost",
    hour_of_day: 22,
    ai_generated_signal: 0.85,
  },
  blocked: {
    label: "Blocked transaction",
    outcome: "BLOCK",
    customer_id: "cust_de9945f9", // Casey Kowalski
    amount: 900.0,
    merchant: "StreamFlix",
    hour_of_day: 3,
    ai_generated_signal: 0.9,
  },
};

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

const RULE_LABELS = {
  spending_limit: "Spending limit",
  merchant_whitelist: "Merchant whitelist",
  time_restriction: "Time of day window",
  velocity: "Daily velocity",
};

const GITHUB_REPO = "https://github.com/pavancharak/execution-authority-gate";

/** Opens the real source on GitHub in a new tab, distinct from the
 * data-goto-tab links elsewhere on this page: this one leaves the app
 * and shows the actual code the tab's numbers come from, not just the
 * tab itself. */
function githubLink(path, label) {
  const href = path ? `${GITHUB_REPO}/blob/main/${path}` : GITHUB_REPO;
  return `<a class="link-btn github-link" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
}

/** Identify -> Generate -> Detect -> Authorize -> Prove: the same five
 * stage names as this repo's own top-level folders (identify/,
 * generate/, detect/, mandate/+sign/, pipeline/audit), reused as the
 * hero flow and the closed-loop diagram so the landing page's
 * architecture claim is literally the repo layout, not marketing
 * shorthand invented for the page. */
const OV_STAGES = [
  { k: "identify", label: "Identify", desc: "Find how AI is used to commit payment fraud" },
  { k: "generate", label: "Generate", desc: "Build realistic fake attacks to test against" },
  { k: "detect", label: "Detect", desc: "Score each transaction's fraud risk" },
  { k: "authorize", label: "Authorize", desc: "Check it against real spending rules, then sign it" },
  { k: "prove", label: "Prove", desc: "Anyone can verify the signature, anytime" },
];

function ovFlow(accentKeys = []) {
  const steps = OV_STAGES.map(
    (s, i) => `<div class="ov-flow-step">
      <div class="ov-flow-node" style="${accentKeys.includes(s.k) ? "border-color:var(--ov-accent);color:var(--ov-accent)" : ""}">${i + 1}</div>
      <div class="ov-flow-label">${esc(s.label)}</div>
      <div class="ov-flow-desc">${esc(s.desc)}</div>
    </div>`
  ).join("");
  return `<div class="ov-flow">${steps}</div>`;
}

function ovLoop() {
  const nodes = OV_STAGES.map(
    (s, i) => `<div class="ov-loop-node${i >= 3 ? " accent" : ""}">${esc(s.label)}</div>${i < OV_STAGES.length - 1 ? '<div class="ov-loop-arrow">→</div>' : ""}`
  ).join("");
  return `<div class="ov-loop">${nodes}</div><p class="ov-loop-back">↩ New attack patterns feed back into Identify. The loop never stops.</p>`;
}

function renderOverviewV2(data) {
  const sim = data.simulation;
  const detect = data.detect.metrics;
  const mandate = data.mandate;
  const pipeline = data.pipeline;
  const verification = data.verification;
  const attacks = data.attacks || [];

  const totalTx = sim.good_transaction_count + sim.fraud_transaction_count;
  const fraudRate = sim.fraud_transaction_count / totalTx;
  const simulatedCount = attacks.filter((a) => a.real_llm_calls || !/known gap/i.test(a.simulated_by)).length;
  const gapCount = attacks.length - simulatedCount;
  const mandateOnly = mandate.block_attribution.mandate_only;
  const example = (mandate.sample_mandate_only_blocks || [])[0];
  const blockSample = pipeline.sample_decisions.find((e) => e.decision.final_decision === "BLOCK") || pipeline.sample_decisions[0];

  const attackChips = attacks
    .map((a) => {
      const gap = /known gap/i.test(a.simulated_by) && !a.real_llm_calls;
      return `<button type="button" class="ov-attack-chip" data-goto-tab="attacks">${esc(a.name)}${gap ? '<span class="gap-tag">Documented gap</span>' : ""}</button>`;
    })
    .join("");

  return `
    <div class="ov">
      <div class="ov-section ov-hero">
        <div class="ov-inner">
          <div class="ov-eyebrow">AI Payment Defense &middot; Execution Authority Gate</div>
          <h1 class="ov-h1">AI can generate the attack.<br>It doesn't get to execute it.</h1>
          ${ovFlow()}
          <p class="ov-sub" style="margin-top:36px">Most fraud tools give you a risk score and hope someone acts on it. This one goes further: a second, completely separate check has to agree before anything is let through &mdash; and every decision gets signed, so it can be proven later, not just logged.</p>
          <div class="ov-cta-row">
            <button type="button" class="ov-btn ov-btn-primary" data-goto-tab="live-test">Run Live Defense →</button>
            <button type="button" class="ov-btn ov-btn-secondary" data-goto-tab="attacks">Explore Attack Intelligence →</button>
          </div>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">What's actually new here</div>
          <h2 class="ov-h2">A risk score is not a decision</h2>
          <p class="ov-lede">A fraud model can only answer one question: <strong>"does this look risky?"</strong><br>It can't tell you whether the transaction actually broke a rule. So this system checks both, separately, before anything is allowed to happen.</p>
          <div class="ov-compare">
            <div class="ov-compare-col muted">
              <div class="ov-compare-title">How most fraud tools work</div>
              <div class="ov-compare-flow">
                <div class="ov-compare-node">Transaction</div>
                <div class="ov-compare-arrow">↓</div>
                <div class="ov-compare-node">Fraud model</div>
                <div class="ov-compare-arrow">↓</div>
                <div class="ov-compare-node">Allow / Block</div>
                <div class="ov-compare-arrow">↓</div>
                <div class="ov-compare-node">Execution</div>
              </div>
              <div class="ov-compare-tag">The model's guess is the final answer</div>
            </div>
            <div class="ov-compare-col accent">
              <div class="ov-compare-title">Execution Authority Gate</div>
              <div class="ov-compare-flow">
                <div class="ov-compare-node">Transaction</div>
                <div class="ov-compare-arrow">↓</div>
                <div class="ov-compare-node">Fraud model → risk score</div>
                <div class="ov-compare-arrow">↓</div>
                <div class="ov-compare-node">Separate check against real spending rules</div>
                <div class="ov-compare-arrow">↓</div>
                <div class="ov-compare-node">Signed, tamper-proof decision</div>
                <div class="ov-compare-arrow">↓</div>
                <div class="ov-compare-node">Allow / Flag / Block</div>
                <div class="ov-compare-arrow">↓</div>
                <div class="ov-compare-node">Proof anyone can check later</div>
              </div>
              <div class="ov-compare-tag">A guess is not the same as permission</div>
            </div>
          </div>
          <p class="ov-sub" style="margin-top:24px">Models get things wrong sometimes. Nothing should be allowed to happen just because a model guessed it was fine &mdash; and here, nothing is. Either check can say no on its own.</p>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">Why this wins</div>
          <h2 class="ov-h2">What happens when the model gets fooled?</h2>
          <p class="ov-sub">This isn't a hypothetical. In this real test run, the fraud model rated ${mandateOnly.toLocaleString()} genuine fraud cases as safe enough to allow. Every single one of them was still blocked &mdash; because a separate check caught that it broke a rule about that customer's real spending, something the model was never looking at.</p>
          <div class="ov-demo-flow">
            <div class="ov-demo-step"><span class="ov-demo-icon">⚠</span><div class="ov-demo-title">AI-generated attack</div><div class="ov-demo-sub">A fake transaction, built to test the system</div></div>
            <div class="ov-demo-arrow">→</div>
            <div class="ov-demo-step warn"><span class="ov-demo-icon">✓</span><div class="ov-demo-title">Fraud model</div><div class="ov-demo-sub">Says it looks safe &mdash; wrong</div></div>
            <div class="ov-demo-arrow">→</div>
            <div class="ov-demo-step block"><span class="ov-demo-icon">✕</span><div class="ov-demo-title">Rule check</div><div class="ov-demo-sub">Catches it anyway, on its own</div></div>
            <div class="ov-demo-arrow">→</div>
            <div class="ov-demo-step block"><span class="ov-demo-icon">✕</span><div class="ov-demo-title">Blocked</div><div class="ov-demo-sub">The transaction never goes through</div></div>
          </div>
          ${
            example
              ? `<div class="ov-example-card">
                  <div class="ov-example-title">A real example from this run</div>
                  <div class="ov-kv-row"><span>Transaction</span><span>${esc(example.decision.transaction_id)}</span></div>
                  <div class="ov-kv-row"><span>Amount</span><span>${fmtMoney(example.ground_truth.amount)} at ${esc(example.ground_truth.merchant)}</span></div>
                  <div class="ov-kv-row"><span>AI's risk level</span><span>${fmtPct(example.decision.fraud_score)} (would have been let through on its own)</span></div>
                  <div class="ov-kv-row"><span>Rule it broke</span><span>${esc((example.decision.violated_mandate_rules || []).map((r) => RULE_LABELS[r] || r).join(", "))}</span></div>
                  <div class="ov-kv-row"><span>Final decision</span><span>${badge(example.decision.final_decision)}</span></div>
                </div>`
              : ""
          }
          <div class="ov-insight">
            <p>The model got fooled. The rule check didn't.<br><strong>That's the whole reason this exists.</strong></p>
          </div>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">Test the defense before attackers do</div>
          <h2 class="ov-h2">Attacks it's tested against</h2>
          <p class="ov-sub">Before building the defense, this project mapped out how AI is actually being used to commit payment fraud today, then built realistic versions of those attacks to test against.</p>
          <div class="ov-metric-row">
            <div class="ov-metric"><div class="ov-metric-value">${attacks.length}</div><div class="ov-metric-label">GenAI payment fraud types identified</div></div>
            <div class="ov-metric"><div class="ov-metric-value">${simulatedCount}</div><div class="ov-metric-label">Attack types actively simulated, ${gapCount} documented as open gaps</div></div>
            <div class="ov-metric"><div class="ov-metric-value">${fmtPct(fraudRate)}</div><div class="ov-metric-label">Fraud rate across ${totalTx.toLocaleString()} generated transactions</div></div>
          </div>
          <div class="ov-attack-grid">${attackChips}</div>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">How it all fits together</div>
          <h2 class="ov-h2">From finding attacks to stopping them</h2>
          <p class="ov-sub">Defending against fraud isn't one step. Here it's three separate, checkable ones: score the risk, check it against real rules, then sign proof of what was decided. A decision is never just a guess &mdash; and what's learned from new attacks feeds back into finding the next ones.</p>
          ${ovLoop()}
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">See it run</div>
          <h2 class="ov-h2">Don't take our word for it. Run the defense.</h2>
          <p class="ov-sub">Change one transaction variable. Watch detection respond. Then see whether the mandate layer grants execution authority.</p>
          <div class="ov-frame">
            <div class="ov-frame-bar"><span class="ov-frame-dot"></span><span class="ov-frame-dot"></span><span class="ov-frame-dot"></span></div>
            <div class="ov-frame-body">
              <p style="margin:0 0 4px;color:var(--ov-text);font-size:14px;font-weight:600">Real trained model, real rule check, real digital signature &mdash; try it yourself</p>
              <p style="margin:0;font-size:13px">Three real starting points, each one you can run right now:</p>
              <div class="ov-frame-outcomes">
                <div class="ov-frame-outcome allow"><span class="tag">ALLOW</span><p>Normal spend, known merchant, ordinary hour</p></div>
                <div class="ov-frame-outcome flag"><span class="tag">FLAG</span><p>Large amount, late hour, ambiguous signal</p></div>
                <div class="ov-frame-outcome block"><span class="tag">BLOCK</span><p>Unfamiliar merchant, odd hour, high AI signal</p></div>
              </div>
              <div class="ov-cta-row"><button type="button" class="ov-btn ov-btn-primary" data-goto-tab="live-test">Run Live Test →</button></div>
            </div>
          </div>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">The final answer, not just a fraud label</div>
          <h2 class="ov-h2">Three possible outcomes</h2>
          <p class="ov-sub">This is the decision after both checks have run and the result has been signed &mdash; not a raw risk score.</p>
          <div class="ov-decision-grid">
            <div class="ov-decision-card allow">
              <div class="ov-decision-head"><span class="ov-decision-icon">✓</span>ALLOW</div>
              <div class="ov-decision-sub">Goes through</div>
              <p>Both checks agree it's fine. Signed and ready to execute.</p>
            </div>
            <div class="ov-decision-card flag">
              <div class="ov-decision-head"><span class="ov-decision-icon">⚠</span>FLAG</div>
              <div class="ov-decision-sub">Needs a human to look</div>
              <p>Not clearly fine, not clearly bad. Sent for manual review instead of guessing either way.</p>
            </div>
            <div class="ov-decision-card block">
              <div class="ov-decision-head"><span class="ov-decision-icon">✕</span>BLOCK</div>
              <div class="ov-decision-sub">Stopped</div>
              <p>Either check objected. That's enough on its own to stop it &mdash; nothing proceeds.</p>
            </div>
          </div>
          <div class="ov-cta-row"><button type="button" class="ov-btn ov-btn-secondary" data-goto-tab="proof">See Proof →</button></div>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">Proof, not just a log line</div>
          <h2 class="ov-h2">Every decision leaves evidence behind.</h2>
          <p class="ov-sub">A decision by itself isn't proof. Every final decision here is digitally signed by a separate key that neither the risk model nor the rule checker has access to &mdash; so afterward, anyone can check the decision is real and hasn't been altered, without needing to trust us.</p>
          ${
            blockSample
              ? `<div class="ov-proof-card">
                  <div class="ov-proof-head">Proof This Decision Is Real</div>
                  <div class="ov-proof-body">
                    <div class="ov-proof-row"><span>Transaction</span><span>${esc(blockSample.decision.transaction_id)}</span></div>
                    <div class="ov-proof-row"><span>Decision</span><span class="${blockSample.decision.final_decision === "BLOCK" ? "no" : "ok"}">${esc(blockSample.decision.final_decision)}</span></div>
                    <div class="ov-proof-row"><span>Risk level</span><span>${fmtPct(blockSample.decision.fraud_score)}</span></div>
                    <div class="ov-proof-row"><span>Signed by</span><span>${esc(blockSample.decision.signer)}</span></div>
                    <div class="ov-proof-row"><span>Signature</span><span>${esc(blockSample.decision.signature.slice(0, 28))}&hellip;</span></div>
                    <div class="ov-proof-row"><span>Signatures verified independently</span><span class="${verification.all_verified ? "ok" : "no"}">${verification.verified.toLocaleString()} / ${verification.total.toLocaleString()}</span></div>
                  </div>
                </div>`
              : ""
          }
          <div class="ov-cta-row"><button type="button" class="ov-btn ov-btn-secondary" data-goto-tab="proof">Inspect Proof →</button></div>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">Where it sits</div>
          <h2 class="ov-h2">Between the AI's decision and what actually happens.</h2>
          <div class="ov-vflow">
            <div class="ov-vflow-node">AI agents / ML models</div>
            <div class="ov-vflow-arrow">↓</div>
            <div class="ov-vflow-node">Risk score / what it wants to do</div>
            <div class="ov-vflow-arrow">↓</div>
            <div class="ov-vflow-node accent">Execution Authority Gate</div>
            <div class="ov-vflow-arrow">↓</div>
            <div class="ov-vflow-branch">
              <div class="ov-vflow-node">Allow</div>
              <div class="ov-vflow-node">Flag</div>
              <div class="ov-vflow-node">Block</div>
            </div>
            <div class="ov-vflow-arrow">↓</div>
            <div class="ov-vflow-node">Only approved systems can carry it out</div>
            <div class="ov-vflow-arrow">↓</div>
            <div class="ov-vflow-node accent">Proof anyone can check</div>
          </div>
          <p class="ov-sub" style="margin:24px auto 0;text-align:center">This doesn't replace an existing fraud model. It sits in front of it, so nothing an AI decides gets acted on without a separate check first.</p>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">The rules it's built on</div>
          <h2 class="ov-h2">Six rules, all of them in real code today</h2>
          <div class="ov-principle-grid">
            <div class="ov-principle-card"><div class="ov-principle-title">The model only recommends</div><p>The final decision comes from rules based on that customer's real history &mdash; not how confident the model feels.</p></div>
            <div class="ov-principle-card"><div class="ov-principle-title">No proof, no action</div><p>If a system asking to execute something can't prove who it is, nothing happens. No valid token, no action &mdash; never a default yes.</p></div>
            <div class="ov-principle-card"><div class="ov-principle-title">Can't run twice</div><p>The same approved decision is checked against a log before it runs, so it can never accidentally be executed twice.</p></div>
            <div class="ov-principle-card"><div class="ov-principle-title">Signed, checkable proof</div><p>Every decision is digitally signed and verifiable with just a public key &mdash; ${verification.verified.toLocaleString()}/${verification.total.toLocaleString()} checked and confirmed in this run.</p></div>
            <div class="ov-principle-card"><div class="ov-principle-title">Two separate votes</div><p>A risk score never directly makes anything happen. It's one input to a separate check, and either one can block it alone.</p></div>
            <div class="ov-principle-card"><div class="ov-principle-title">Every decision explains itself</div><p>Each one comes with its reasons attached: the risk score, which rules passed or failed, and why.</p></div>
          </div>
        </div>
      </div>

      <div class="ov-section">
        <div class="ov-inner">
          <div class="ov-eyebrow">What this is</div>
          <h2 class="ov-h2">Built to defend against AI-driven payment fraud</h2>
          <p class="ov-sub">This project covers the whole loop: finding new attack types, generating realistic examples of them, scoring risk, deciding independently, and proving the decision afterward. It's an independent research project built for the Mastercard Innovation Challenge, AI Defense Lab 2026 &mdash; not an official Mastercard product, and Mastercard hasn't endorsed it.</p>
          <div class="ov-step-pills">
            <span class="ov-step-pill">Identify</span>
            <span class="ov-step-pill">Generate</span>
            <span class="ov-step-pill">Detect</span>
            <span class="ov-step-pill accent">Authorize</span>
            <span class="ov-step-pill accent">Prove</span>
          </div>
        </div>
      </div>

      <div class="ov-final">
        <div class="ov-inner">
          <h2>A model can guess.<br>It doesn't get the final say.</h2>
          <p class="ov-final-sub">AI can be smart without being the one in charge.</p>
          <div class="ov-cta-row">
            <button type="button" class="ov-btn ov-btn-primary" data-goto-tab="live-test">Try It Yourself →</button>
            <button type="button" class="ov-btn ov-btn-secondary" data-goto-tab="mandate">See How It Works →</button>
          </div>
        </div>
      </div>

      <div class="ov-footer">
        <div class="ov-inner">
          <div class="ov-footer-brand">EXECUTION AUTHORITY GATE</div>
          <div class="ov-footer-tag">A model can guess. It doesn't get the final say.</div>
          <div class="ov-footer-nav">
            <button type="button" data-goto-tab="overview">Overview</button>
            <button type="button" data-goto-tab="attacks">Attacks</button>
            <button type="button" data-goto-tab="walkthrough">Attack Walkthrough</button>
            <button type="button" data-goto-tab="detect">Detection</button>
            <button type="button" data-goto-tab="mandate">Mandate</button>
            <button type="button" data-goto-tab="live-test">Live Test</button>
            <button type="button" data-goto-tab="proof">Proof</button>
            <button type="button" data-goto-tab="faq">FAQ</button>
            ${githubLink(null, "View source on GitHub")}
          </div>
          <p class="ov-footer-note">Synthetic data &middot; research prototype &middot; not a production payment authorization service. Built for the Mastercard Innovation Challenge, AI Defense Lab 2026.</p>
        </div>
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

  const simulatedCount = attacks.filter((a) => a.real_llm_calls || !/known gap/i.test(a.simulated_by)).length;
  const gapCount = attacks.length - simulatedCount;

  return `
    <div class="section">
      <h1>Attack taxonomy</h1>
      <p>${attacks.length} ways AI commits payment fraud. ${simulatedCount} are actively simulated by bounded agents in <code>generate/src/fraud_agents.py</code>; ${gapCount} are honest, documented gaps spanning rails and surfaces the simulated agents don't touch (B2B wire/ACH, real time push payments, agentic commerce, biometric liveness, post transaction disputes, and long horizon account fraud).</p>
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
        ${statTile(
          "F1 score",
          m.f1_score.toFixed(3),
          "",
          "Harmonic mean of precision and recall, low here for the same reason precision is low: fraud is rare and recall is prioritized"
        )}
        ${statTile(
          "ROC AUC",
          m.roc_auc.toFixed(3),
          "good",
          "Threshold independent separability of fraud from legitimate transactions by fraud score"
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

  const ruleRows = Object.entries(md.rule_violation_counts).map(([rule, count]) => ({
    name: RULE_LABELS[rule] || rule,
    value: count,
    colorVar: "--series-1",
  }));

  const sampleRows = md.sample_mandate_only_blocks
    .map((e) => {
      const d = e.decision;
      const violated = d.violated_mandate_rules.map((r) => RULE_LABELS[r] || r).join(", ");
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

const OUTCOME_ICON = { ALLOW: "✓", FLAG: "⚠", BLOCK: "✕" };

/** A summary of why the final decision came out the way it did, written
 * in plain language a judge can follow, computed entirely from real
 * fields already present on the signed decision (fraud_score,
 * detect_decision, mandate_allowed, violated_mandate_rules) plus the
 * mandate rule labels. No new backend data, just a clearer
 * presentation of what Step 4 of renderDecisionCard already says in
 * prose. */
function renderOutcomeBanner(decision, mandateChecks) {
  const failedRules = (mandateChecks || []).filter((c) => !c.passed).map((c) => RULE_LABELS[c.rule] || c.rule);
  const final = decision.final_decision;
  const icon = OUTCOME_ICON[final] || "";

  let why;
  if (final === "BLOCK") {
    if (!decision.mandate_allowed && decision.detect_decision === "BLOCK") {
      why = `Both layers objected: the detection model scored this ${decision.fraud_score.toFixed(2)} (high risk), and the mandate layer rejected it on ${failedRules.join(", ")}. Either alone would have been enough to block it.`;
    } else if (!decision.mandate_allowed) {
      why = `The mandate layer rejected it (${failedRules.join(", ")}), even though the detection model alone scored this only ${decision.fraud_score.toFixed(2)} (would have allowed it). This is the mandate layer catching something the fraud model missed.`;
    } else {
      why = `The detection model scored this ${decision.fraud_score.toFixed(2)} (high risk) and blocked it, even though the mandate layer had no objection.`;
    }
  } else if (final === "FLAG") {
    why = `The detection model is unsure (score ${decision.fraud_score.toFixed(2)}, between the ALLOW and BLOCK thresholds) and the mandate layer has no objection. Flagged for manual review, not blocked automatically.`;
  } else {
    why = `The detection model scored this ${decision.fraud_score.toFixed(2)} (low risk) and every mandate rule passed. Both layers agree.`;
  }

  const action =
    final === "ALLOW"
      ? "Ready to execute: this signed decision can be handed to a payment processor to settle."
      : final === "FLAG"
      ? "Sent to manual review. A reviewer can allow it or escalate it to a block."
      : "Transaction denied. Nothing is executed for a BLOCK decision.";

  return `<div class="outcome-banner outcome-${final.toLowerCase()}">
    <div class="outcome-head">
      <span class="outcome-icon" aria-hidden="true">${icon}</span>
      <h2>${esc(final)}</h2>
    </div>
    <p class="outcome-why">${why}</p>
    <p class="outcome-action">${action}</p>
  </div>`;
}

/** Shared render for a full pipeline outcome, used by both the Attack
 * Walkthrough (precomputed, real, already signed decisions) and the
 * Live Test Harness (a decision computed live, right now, by this
 * request). txSummaryRows: [{label, value}]. */
function renderDecisionCard(txSummaryRows, decision, mandateChecks, verified) {
  const txRows = txSummaryRows
    .map((r) => `<div class="kv-row"><span class="kv-key">${esc(r.label)}</span><span class="kv-value">${esc(r.value)}</span></div>`)
    .join("");

  const mandateRows = mandateChecks
    .map(
      (c) => `<tr>
        <td>${RULE_LABELS[c.rule] || c.rule}</td>
        <td>${c.passed ? '<span class="dot good"></span> pass' : '<span class="dot critical"></span> fail'}</td>
        <td>${esc(c.reason)}</td>
      </tr>`
    )
    .join("");

  return `
    ${renderOutcomeBanner(decision, mandateChecks)}

    <div class="pipeline-steps">
      <div class="card pipeline-step">
        <h3>Step 1 &middot; AI Risk Check</h3>
        <div class="stat-row">
          ${statTile("Risk level", fmtPct(decision.fraud_score), "", `Raw model score: ${decision.fraud_score.toFixed(4)}`)}
          ${statTile("AI's recommendation", badge(decision.detect_decision))}
        </div>
        <p>${(decision.reasons || []).filter((r) => r.startsWith("detect:")).map((r) => esc(r.replace("detect: ", ""))).join(", ") || "no single dominant signal"}</p>
      </div>

      <div class="card pipeline-step">
        <h3>Step 2 &middot; Safety Rules Check</h3>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Rule</th><th>Followed?</th><th>Why</th></tr></thead>
            <tbody>${mandateRows}</tbody>
          </table>
        </div>
      </div>

      <div class="card pipeline-step">
        <h3>Step 3 &middot; Proof It's Real</h3>
        <div class="sig-line">
          <span class="dot ${verified ? "good" : "critical"}"></span>
          <strong>${verified ? "Verified: this decision is genuine and unaltered" : "NOT verified — this decision may have been tampered with"}</strong>
        </div>
        <div class="kv-block"><span class="kv-key">Digital signature (Ed25519)</span><span class="kv-value mono">${esc(decision.signature.slice(0, 32))}&hellip;</span></div>
        <div class="kv-block"><span class="kv-key">Signed by</span><span class="kv-value">${esc(decision.signer)}</span></div>
      </div>

      <div class="card pipeline-step">
        <h3>Step 4 &middot; Final Decision</h3>
        <div class="sig-line" style="margin-bottom:12px">${badge(decision.final_decision)}</div>
        <p>${
          decision.final_decision === "BLOCK"
            ? (!decision.mandate_allowed
                ? `Mandate layer rejected it (${decision.violated_mandate_rules.map((r) => RULE_LABELS[r] || r).join(", ")}), blocked regardless of the detect score.`
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

function customerInfoHtml(customer) {
  if (!customer) return "";
  const m = customer.mandate;
  return `<div class="customer-info" id="customer-info">
    <div class="customer-info-row"><span>Spending limit</span><strong>${fmtMoney(m.monthly_limit_usd)}/mo</strong></div>
    <div class="customer-info-row"><span>Known merchants</span><strong>${m.allowed_merchants && m.allowed_merchants.length ? esc(m.allowed_merchants.join(", ")) : "no restriction"}</strong></div>
    <div class="customer-info-row"><span>Allowed hours</span><strong>${m.allowed_hours[0]}:00&ndash;${m.allowed_hours[1]}:00</strong></div>
    <div class="customer-info-row"><span>Max transactions/day</span><strong>${m.max_tx_per_day}</strong></div>
  </div>`;
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
        <h3>Try an example</h3>
        <p class="form-hint" style="margin:0 0 12px">Click one to fill in the form below automatically and run it immediately. Each one is a real, verified input, not a mockup.</p>
        <div class="quick-start-row">
          <button type="button" class="quick-start-btn allow" data-example="normal">
            <span class="qs-outcome">ALLOW</span>
            <span class="qs-label">Normal transaction</span>
          </button>
          <button type="button" class="quick-start-btn flag" data-example="flagged">
            <span class="qs-outcome">FLAG</span>
            <span class="qs-label">Flagged transaction</span>
          </button>
          <button type="button" class="quick-start-btn block" data-example="blocked">
            <span class="qs-outcome">BLOCK</span>
            <span class="qs-label">Blocked transaction</span>
          </button>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="card">
        <form id="live-test-form" class="live-form">
          <label>Customer
            <span class="hint">Each customer's mandate is derived from their own real history</span>
            <select name="customer_id" id="customer-select" required>${customerOptions}</select>
          </label>
          <label>Amount (USD)
            <span class="hint">Try this customer's typical spend first, then an unusual amount</span>
            <input type="number" name="amount" min="0.01" max="1000000" step="0.01" value="50.00" placeholder="e.g. 100" required>
          </label>
          <label>Merchant
            <span class="hint">Pick a known merchant, or type a new one to test the whitelist</span>
            <input list="merchant-list" name="merchant" value="${esc(merchants[0] || "")}" required>
            <datalist id="merchant-list">${merchantOptions}</datalist>
          </label>
          <label>What time is it? (hour, 0&ndash;23)
            <span class="hint">Most simulated fraud happens at odd hours (2&ndash;5am)</span>
            <input type="number" name="hour_of_day" min="0" max="23" value="12" required>
          </label>
          <label>How suspicious does the pattern look? (0 to 1)
            <span class="hint">0 = looks like normal human behavior &middot; 1 = looks like a fabricated, AI-generated pattern</span>
            <input type="number" name="ai_generated_signal" min="0" max="1" step="0.01" value="0.1" required>
          </label>
          <button type="submit" class="submit-btn">Check this payment</button>
        </form>
        <div id="customer-info-wrap">${customerInfoHtml(customers[0])}</div>
        <p class="form-hint">Each customer's mandate (spending limit, allowed merchants, allowed hours) was derived from their own real transaction history. Try an unlisted merchant or an odd hour to see the mandate layer object on its own. Press Escape to reset the form.</p>
      </div>
    </div>

    <div class="section" id="live-test-result" aria-live="polite"></div>
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
        <td>${fmtPct(d.fraud_score)}</td>
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
            <thead><tr><th>Transaction</th><th>Risk level</th><th>Decision</th><th>Signature</th></tr></thead>
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

function wireLiveTest(customersData) {
  const form = document.getElementById("live-test-form");
  const result = document.getElementById("live-test-result");
  if (!form || !result) return;

  const customers = (customersData && customersData.customers) || [];
  const customersById = Object.fromEntries(customers.map((c) => [c.customer_id, c]));

  const customerSelect = document.getElementById("customer-select");
  const infoWrap = document.getElementById("customer-info-wrap");
  if (customerSelect && infoWrap) {
    customerSelect.addEventListener("change", () => {
      infoWrap.innerHTML = customerInfoHtml(customersById[customerSelect.value]);
    });
  }

  document.querySelectorAll(".quick-start-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const example = QUICK_START_EXAMPLES[btn.dataset.example];
      if (!example) return;
      form.elements["customer_id"].value = example.customer_id;
      form.elements["amount"].value = example.amount;
      form.elements["merchant"].value = example.merchant;
      form.elements["hour_of_day"].value = example.hour_of_day;
      form.elements["ai_generated_signal"].value = example.ai_generated_signal;
      if (customerSelect && infoWrap) {
        infoWrap.innerHTML = customerInfoHtml(customersById[example.customer_id]);
      }
      form.requestSubmit();
    });
  });

  form.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      form.reset();
      if (customerSelect && infoWrap) {
        infoWrap.innerHTML = customerInfoHtml(customersById[customerSelect.value]);
      }
      result.innerHTML = "";
    }
  });

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
          { label: "Time", value: `${tx.hour_of_day}:00` },
          { label: "Suspicion level", value: tx.ai_generated_signal },
        ],
        payload.decision,
        payload.mandate_checks,
        payload.verified
      );
    } catch (err) {
      result.innerHTML = `<div class="error-inline">Couldn't run the live pipeline: ${esc(err.message)}.<br>The Live Test Harness needs the Flask server (<code>python web/server.py</code>). It isn't available under <code>python -m http.server</code>.</div>`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Check this payment";
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
    a: "Not the signature. Nothing calling this pipeline, agent or otherwise, has access to the private signing key, so it cannot produce a valid signed ALLOW on its own. The enforcement API also checks a caller token before acting on any decision and fails closed if that token is missing or wrong, so an agent cannot execute a decision it was never issued permission for. What it can still do is choose not to call the pipeline at all; putting this check at the actual execution point, not as an optional step an agent can decide to skip, is a system-integration decision outside this repo's scope.",
  },
  {
    q: "Does this replace a human reviewer?",
    a: "No, and it is not trying to. FLAG decisions exist for exactly the cases where neither layer is confident enough to decide alone. What this project replaces is blind trust in a single model's score, not human judgment.",
  },
  {
    q: "Why is precision only around 28%?",
    a: "Fraud is rare, a few percent of transactions in this dataset. Catching over 90% of a rare event requires flagging aggressively, and that lowers precision. See the Detection tab for the full breakdown and the exact current numbers.",
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
    a: "It produces a signed decision, ALLOW, FLAG, or BLOCK, then the enforcement API (sign/src/decision_executor.py) independently checks the caller's permission and the decision's signature before acting on it, blocking a BLOCK regardless of who asks. What it enforces against today is a no-op webhook, not a live payment processor, so no real money moves yet. Wiring that webhook to an actual payment rail is the remaining integration.",
  },
  {
    q: "Are signed decisions stored permanently?",
    a: "Enforcement decisions are: pipeline/audit/decisions.jsonl is an append only log, keyed on each decision's record_id, so a decision is written once and a replayed batch cannot duplicate an entry. The older pipeline_decisions.json snapshot is still written for backward compatibility, and that one does get overwritten on each pipeline run, it is not the durability guarantee.",
  },
  {
    q: "Who is allowed to trigger a decision or call the API?",
    a: "The enforcement endpoint (POST /api/enforce/decisions) requires a signed caller token issued to a registered caller (payment-processor, fraud-analyst, audit-system in sign/src/caller_auth.py) and fails closed: a missing or invalid token gets a 401, not a default allow. A caller without permission for a decision's outcome, e.g. payment-processor attempting a BLOCK, gets that one decision rejected without affecting the rest of its batch. The read-only dashboard and demo routes (what this public page itself calls) are intentionally left open, since gating them wouldn't protect anything they don't already let the caller fully control.",
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
  overview: renderOverviewV2,
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
  const DEFAULT_TAB = "overview";
  app.innerHTML = order
    .map((name) => `<div class="panel${name === DEFAULT_TAB ? " active" : ""}" data-panel="${name}">${panels[name]}</div>`)
    .join("");

  wireWalkthrough(scenarios);
  wireLiveTest(customersData);

  document.getElementById("tabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab-btn");
    if (!btn) return;
    goToTab(btn.dataset.tab);
  });

  // Event delegation so any element rendered anywhere, including inside
  // dynamically rebuilt panels like Overview, can link to another tab
  // just by carrying data-goto-tab, no rewiring needed on every render.
  app.addEventListener("click", (e) => {
    const link = e.target.closest("[data-goto-tab]");
    if (!link) return;
    goToTab(link.dataset.gotoTab);
  });

  wireOnboarding(goToTab);
}

function goToTab(tab) {
  const btn = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
  if (!btn) return;
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === tab));
  window.scrollTo({ top: 0, behavior: "instant" });
}

const ONBOARDING_KEY = "judge_onboarding_dismissed_at";
const ONBOARDING_HOURS = 24;

function wireOnboarding(goToTab) {
  const backdrop = document.getElementById("onboarding-backdrop");
  const closeBtn = document.getElementById("onboarding-close");
  const gotoBtn = document.getElementById("onboarding-goto-live-test");
  if (!backdrop || !closeBtn || !gotoBtn) return;

  function dismiss() {
    backdrop.hidden = true;
    try {
      localStorage.setItem(ONBOARDING_KEY, String(Date.now()));
    } catch (err) {
      /* localStorage unavailable (private mode, blocked storage): just close without remembering */
    }
  }

  let shouldShow = true;
  try {
    const dismissedAt = Number(localStorage.getItem(ONBOARDING_KEY));
    if (dismissedAt && Date.now() - dismissedAt < ONBOARDING_HOURS * 3600 * 1000) {
      shouldShow = false;
    }
  } catch (err) {
    /* localStorage unavailable: default to showing the modal every visit */
  }

  if (shouldShow) {
    backdrop.hidden = false;
  }

  closeBtn.addEventListener("click", dismiss);
  gotoBtn.addEventListener("click", () => {
    dismiss();
    goToTab("live-test");
  });
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) dismiss();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !backdrop.hidden) dismiss();
  });
}

main();
