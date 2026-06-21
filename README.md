<div align="center">

# 💾 StorageTierIQ

### Stop paying premium prices to store data nobody uses.

*An open-source engine that finds your cold cloud data and moves it to cheaper tiers — cutting storage bills and CO₂ automatically.*

[![CI](https://github.com/nazarovh018e-ux/storagetieriq/actions/workflows/ci.yml/badge.svg)](https://github.com/nazarovh018e-ux/storagetieriq/actions)
![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue?logo=python&logoColor=white)
![AWS S3](https://img.shields.io/badge/AWS-S3-FF9900?logo=amazons3&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Open Source](https://img.shields.io/badge/open%20source-%E2%9D%A4-red)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)

</div>

---

## 🧊 The Problem — You're paying first-class for empty seats

Most organizations keep the **majority** of their data on fast, expensive, energy-hungry SSD storage — even data that hasn't been touched in months.

> 📉 **Industry research (IDC and others) shows that 60–80% of enterprise data is "cold"** — rarely or never accessed.

Yet it sits on the most expensive tier, as if every byte were urgent. The result:

- 💸 **Wasted money** — companies overpay for storage they don't use.
- 🌍 **Wasted energy** — always-on SSD burns far more electricity than cold archives, inflating the carbon footprint.

With the cloud storage market heading toward **~$800B by 2034** and data volumes growing ~20% a year, this waste compounds every single month.

---

## ✅ The Solution — Put every file where it actually belongs

**StorageTierIQ** analyzes your **real access patterns** and assigns every object to the tier that minimizes its true expected cost — then reports the money saved **and** the CO₂ avoided.

| Tier | Backing storage | Best for | Relative cost |
|------|-----------------|----------|---------------|
| 🔥 **HOT** | SSD / NVMe | Frequently accessed | 💰💰💰 |
| 🌤️ **WARM** | Object storage (S3-IA) | Occasional access | 💰💰 |
| 🧊 **COLD** | Glacier / Archive | Rarely or never accessed | 💰 |

The key difference from legacy tools: **StorageTierIQ decides from measured usage, not file age.** A six-month-old file accessed daily stays hot; a brand-new file nobody opens goes cold. No guesswork.

---

## 🚀 Core Features

- 📈 **Usage-aware tiering** — classifies data from real S3 server access logs, not crude age heuristics.
- 🧠 **Cost-optimal engine** — assigns each object to the tier with the lowest expected total cost (storage + retrieval over a planning horizon).
- 💵🌱 **Cost & CO₂ dashboard** — quantifies both the dollars and the carbon you save, in one view.
- 🤖 **Automatic, safe migration** — generates a migration plan and can execute it against AWS S3. Defaults to a **dry-run** so nothing moves until you approve.
- 🔒 **Privacy-first by design** — runs entirely in **your** environment. It reads metadata and logs locally; **your data never leaves your account.**
- 🧩 **Pluggable & open-source** — clean, modular architecture with automated tests and CI passing on Python 3.10–3.12.

---

## 🏗️ How It Works

StorageTierIQ plugs into your existing AWS S3 setup and runs a simple, transparent pipeline:

```
                        YOUR AWS ENVIRONMENT
   ┌─────────────────────────────────────────────────────────────┐
   │                                                               │
   │   ☁️  S3 Bucket  ──────────────┐                              │
   │   (objects + sizes)            │                              │
   │                                ▼                              │
   │   📜 S3 Access Logs ──▶  [ 1. INGEST ]  read usage + metadata │
   │                                │                              │
   │                                ▼                              │
   │                         [ 2. CLASSIFY ]  cost-optimal engine  │
   │                                │         HOT / WARM / COLD     │
   │                                ▼                              │
   │                         [ 3. REPORT ]   cost + CO₂ dashboard  │
   │                                │                              │
   │                                ▼                              │
   │                         [ 4. MIGRATE ]  dry-run → execute     │
   │                                │         (S3 storage classes) │
   │                                ▼                              │
   │   ☁️  S3 Bucket  ◀── objects moved to the right tier          │
   │                                                               │
   └─────────────────────────────────────────────────────────────┘
```

Every step is auditable, and migration is **opt-in** — you see the plan before a single object moves.

<div align="center">

![StorageTierIQ Dashboard](docs/dashboard.png)

*The cost & CO₂ dashboard generated on real AWS data.*

</div>

---

## 📊 Initial Test Results (Case Study)

We validated StorageTierIQ on **real Amazon S3 data** — a live bucket with server access logging enabled, classified from genuine usage patterns (not synthetic assumptions).

| Metric | Naive (age-based) | **StorageTierIQ (cost-optimal)** |
|--------|------------------|----------------------------------|
| 💸 Storage cost reduction | 20% | **57%** |
| 🌍 CO₂ footprint reduction | ~20% | **56%** |
| 🎯 Hot data correctly identified | mixed | **13% hot · 87% cold** |

> 💡 **The intelligence matters:** the cost-optimal engine delivered **~3× more savings** than a naive age-based rule — because it decided from *measured access*, not file age.

### 📈 Projected at enterprise scale

Applying the same logic to a **1 PB** workload (≈70% cold, per industry norms):

| | Per year |
|---|---|
| 💰 Cost saved | **~$630,000** |
| 🌱 CO₂ avoided | **~16 tonnes** |

> **Savings scale with how cold your data is** — typically **30–90%**. Archive-heavy workloads (backups, media, compliance data) sit at the top of that range; the more cold data you have, the more you save.

---

## ⚙️ Installation & Setup

### Prerequisites

- Python **3.10+**
- An AWS account with an **S3 bucket** and (for real usage data) **S3 server access logging** enabled
- AWS credentials configured (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`)

### 1. Install

```bash
git clone https://github.com/nazarovh018e-ux/storagetieriq.git
cd storagetieriq
pip install -e ".[viz,aws]"
```

### 2. Try it instantly (synthetic data — no AWS needed)

```bash
storagetieriq --strategy cost-optimal
```

### 3. Run on your real AWS data

Export your bucket's metadata and access logs into the analysis format:

```bash
python tools/s3_export.py \
  --bucket YOUR_BUCKET \
  --access-logs-bucket YOUR_LOG_BUCKET \
  --access-logs-prefix logs/ \
  --out storage_records.csv
```

Then analyze, see your savings, and preview a migration plan:

```bash
storagetieriq --input storage_records.csv --strategy cost-optimal --plan-migration
```

That's it — you'll get a cost & CO₂ report, a dashboard, and a dry-run migration plan. Nothing moves until you say so.

---

## 💰 Commercial Model — Gain Share

We only win when **you** win. No upfront license. No risk.

| | Details |
|---|---|
| 🎁 **Month 1** | **Free.** We analyze your storage and show you exactly what you'd save. |
| 🤝 **After that** | You pay a **percentage of the savings we deliver** — verified against your real bill. |
| ✅ **Why it works** | If we don't cut your costs, you don't pay. Incentives fully aligned. |

The open-source core is, and will remain, **free**. Paid enterprise offerings add managed migration, multi-cloud support, and dedicated support.

---

## 🗺️ Roadmap

- [ ] ML-based access prediction (forecast future usage, not just past)
- [ ] Multi-cloud support (Google Cloud Storage, Azure Blob)
- [ ] Hysteresis guard to prevent tier "thrashing"
- [ ] Hosted enterprise dashboard

---

## 🤝 Contributing

Contributions are welcome! Open an issue or a pull request. The codebase is modular and fully tested — a great place to build.

## 📄 License

Released under the **MIT License**. See [`LICENSE`](LICENSE) for details.

<div align="center">

**StorageTierIQ** — *Cost down. Carbon down. Zero guesswork.*

⭐ Star this repo if cheaper, greener cloud storage sounds good to you.

</div>
