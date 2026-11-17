# Snack Counter — Design

## Problem

Two offices (Oslo, Bengaluru) keep a snack box stocked by volunteers who pay out of pocket and claim through HR. Informal chat is causing empty boxes, double purchases, uneven load, slow reimbursement, and no spending picture.

## What “automate” means here

We do **not** replace HR or the chat tool. We add a small coordinator that:

1. Turns “the box is empty” into **one** tracked refill per office.
2. **Assigns** a buyer instead of waiting for a volunteer (kills the bystander effect).
3. Lets only that person **commit**, atomically (kills double purchase).
4. **Reassigns** if they do not act in time (hybrid / leave / visiting).
5. **Checks budget** at purchase, files the HR claim, and produces **one monthly report**.

Empty is reported by a person in chat (`/snacks empty`). We deliberately skip IoT sensors: they are expensive, fail, and still need a human to buy.

## Lifecycle: empty → reimbursed

```
report empty → OPEN
     │  assign eligible volunteer (in office today, not on leave)
     ▼
 ASSIGNED  ──timeout / decline──► reassign (new ASSIGNED)
     │  assignee commits “I will buy”
     ▼
 COMMITTED ──timeout with no receipt──► release + reassign
     │  amount + receipt + snack note
     ▼
 PURCHASED  (box is full; a new empty-report may start)
     │  create HR claim (amount, currency, description, receipt, employee id)
     ▼
 CLAIM_SUBMITTED ──HR approve (1–10 days)──► REIMBURSED
                  └──HR reject──► surface in chat; volunteer resubmits
```

Payroll currency is the office currency (NOK / INR). We send HR that currency. Visiting employees are reimbursed in **their** payroll currency; if they buy for the host office we still record spend against the **host office budget** in the host currency (assumption, flagged below).

## Main parts and data

| Part | Responsibility | Data it keeps |
|---|---|---|
| **Coordinator** (this service) | Lifecycle, assignment, budget, reports | Offices, volunteers, refills, presence/leave, FX rates |
| **Chat adapter** | DMs + office channel | None (pass-through). Fake in tests. |
| **HR adapter** | Create claim, poll status | None. Fake in tests. |
| **Clock** | Timeouts | Injected so tests can advance time |

**Office:** id, monthly budget, currency.  
**Volunteer:** employee id, home office, visit windows, leave days, in-office days (hybrid).  
**Refill:** id, office, status, assignee, timestamps, amount, receipt ref, snack note, HR claim id.  
**At most one “box still empty” refill per office** (`OPEN` / `ASSIGNED` / `COMMITTED`).

Assignment: eligible = (home office **or** currently visiting) **and** in office that day **and** not on leave. Pick the person with the fewest completed refills this month, then oldest last-buy (fairness). If nobody is eligible, post in the office channel.

Timeouts (assumptions): **4 hours** to commit, **24 hours** after commit to upload a receipt.

## How the listed problems are prevented

| Problem | Control |
|---|---|
| Box empty for days | System assigns; channel ping; reassignment on timeout |
| Two people buy the same day | One active refill; `commit` is a compare-and-swap under a lock |
| Same few people + slow payback | Fair rotation; claim filed immediately at purchase |
| No spend / no “what was eaten” | Monthly report (both currencies + EUR total); optional snack note on the receipt, not a SKU catalogue |

## Monthly report

Each office is shown in its own currency vs its budget. Totals use **finance-supplied FX to EUR** (not live market). We never mix NOK and INR in one arithmetic line.

## Trade-offs and what we would not build

- **Chat-first, no extra app.** Everyone already has login + chat. A portal can wait.
- **No automatic grocery order.** Vendors, dietary needs, and “what people actually eat” differ by office; a human still walks to the store.
- **No weight sensors / cameras.** High cost, privacy, still need a buyer.
- **No full inventory.** A free-text snack note is enough to learn preferences.
- **No real Slack/HR clients in this exercise** — protocols + fakes, as requested.
- **Hard budget cap on purchase**, not a vague warning. Overspend needs an explicit override we did not implement (ask finance).
- **Once purchased, we do not auto-reassign.** They may already be at the shop; we nag in chat instead.

## Assumptions we would confirm

1. One box per office.  
2. Volunteer roster is maintained by office managers.  
3. “In office today” can be a simple daily check-in or calendar; we model it as a date set.  
4. Visiting buyer: spend hits **host** budget; reimbursement uses **home** payroll currency — HR must accept a claim currency that may differ from the receipt. If HR cannot, visitors should not buy.  
5. FX for the EUR total comes from finance each month.

## Run

```text
pip install -e ".[dev]"
pytest -q
python -m snack_counter.demo
```
