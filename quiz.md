# Quiz — Amazon Aurora

Test what you picked up from the README. No peeking — answers are collapsed below each question.

---

## Q1. How is Aurora storage different from a traditional database's storage?

A. It lives on the same disk as the compute instance
B. It is a shared cluster volume, decoupled from compute, replicated 6 ways across 3 AZs and auto-scaling to 128 TiB
C. It only stores data in a single AZ and relies on snapshots for durability
D. It requires you to pre-provision the full 128 TiB up front

<details>
<summary>Answer</summary>

**B.** Storage is decoupled from compute. The cluster volume replicates your data 6 ways across 3 Availability Zones, repairs itself, and grows automatically from 10 GiB to 128 TiB. Adding a read replica never copies data — it just attaches to the same volume.
</details>

---

## Q2. Your Aurora writer fails over to a reader. Which endpoint keeps your application working with zero code changes?

A. The old writer's instance endpoint
B. The cluster endpoint — it always points at the current writer
C. The reader endpoint — it becomes the writer automatically
D. The custom endpoint you made for analytics

<details>
<summary>Answer</summary>

**B.** The **cluster endpoint** always resolves to the current writer. After failover (typically under 30 seconds) it points at the promoted reader. Never hard-code a writer's instance DNS name — it goes stale the moment a failover happens.
</details>

---

## Q3. When is Aurora I/O-Optimized cheaper than Aurora Standard?

A. Always — it has a lower hourly instance price
B. Never — it is a premium tier for performance only
C. When I/O charges make up roughly 25% or more of your total Aurora bill, because I/O-Optimized removes per-I/O charges
D. Only for clusters smaller than 10 GiB

<details>
<summary>Answer</summary>

**C.** I/O-Optimized charges a higher instance rate but **zero per-I/O fees**. The break-even is roughly when I/O is ~25% of the bill. I/O-heavy workloads (lots of small reads/writes) save money; quiet workloads pay more.
</details>

---

## Q4. A developer runs a bad migration and drops the wrong table 2 hours ago. What is the fastest way back — and what is its limit?

A. Restore the latest snapshot (limit: snapshots are hourly)
B. Aurora Backtrack — rewind the cluster to a point in time (limit: 72-hour backtrack window)
C. Clone the cluster (limit: clones only go forward in time)
D. Fail over to a reader (limit: readers don't keep old data)

<details>
<summary>Answer</summary>

**B.** **Backtrack** rewinds the whole cluster to any second in the last **72 hours** — no snapshot restore, no new cluster. The 72-hour window is the limit: beyond that you need a point-in-time restore from the continuous backup (up to 35 days).
</details>

---

## Q5. You need a full copy of the production database for a developer to test a risky schema change. What do you use, and why is it cheap?

A. A snapshot restore — cheap because snapshots are incremental
B. Aurora cloning — copy-on-write, so the clone shares the same storage pages until data diverges; it takes minutes and costs almost nothing extra
C. A read replica — cheap because it shares the writer's compute
D. Export to S3 and re-import — cheap because S3 storage is nearly free

<details>
<summary>Answer</summary>

**B.** **Cloning** is copy-on-write: the clone points at the same storage pages as the source. You only pay for pages that change after the clone is made. A full production copy appears in minutes, and deleting it is instant.
</details>

---

**Score yourself:** 5/5 — Aurora pro. 3–4 — solid, re-read the Global Database and endpoints sections. 0–2 — re-read the README, then try again tomorrow.
