# Titanium-Agentic — System Guide
### How it works, why it works, and what to do when things happen

*Plain language. No stats degree required.*

---

## The One-Line Summary

> **The system scans live betting markets, filters out the noise using a set of hard rules (kill switches), scores what's left on a 0–100 scale (sharp score), and shows you the bets worth considering — ranked best to worst.**

That's it. Everything below is just explaining those four steps in more detail.

---

## ELI5: What Actually Happens When You Open the App?

```
ODDS API POLL (every ~5 min)
      │
      ▼
Raw odds from 5–15 sportsbooks
      │
      ▼
COLLAR FILTER  ─── Removes extreme prices
      │           (only -180 to +150 accepted)
      ▼
EDGE CALCULATION
      │    Is the consensus "fair price" better
      │    than what one book is offering?
      │    Requires: at least 2 books, ≥3.5% edge
      ▼
KILL SWITCHES  ─── Disqualify automatically
      │           (back-to-back NBA, NHL starter unknown,
      │            NFL wind >20mph, surface mismatch, etc.)
      ▼
SHARP SCORE (0–100)
      │    Combines: edge strength, RLM signal,
      │    team efficiency gap, situational factors
      ▼
CANDIDATES (sorted by sharp score)
```

You see the output of that pipeline. Every bet that reaches your screen has already been through all those filters.

---

## Frequently Asked Questions

---

### Q: What is the "collar"? Why do some bets get rejected before I even see them?

The collar is a price filter. The system only accepts standard American odds between **-180 and +150**.

**Why?** Anything below -180 means you're risking a lot to win a little — the math gets very unfavorable very fast. Anything above +150 on a 2-way market usually means something is off with the line (a blowout in progress, stale data, or a trap). Soccer 3-way markets get a wider collar (-250 to +400) because home/draw/away splits naturally produce more extreme prices.

You don't see collar rejects — they're silently filtered before the list populates.

---

### Q: What is "edge" and how is it calculated?

Edge = the gap between the price you can get and the "fair" price the market implies.

**Example:**
- 3 sportsbooks offer: Team A at -115, -112, -108
- No-vig consensus fair probability = ~53.2%
- Book X is offering -108 → implied probability = 51.9%
- Edge = 53.2% - 51.9% = **1.3% raw**

The minimum edge threshold is **3.5%**. Anything below that is likely noise (juice, rounding, market efficiency). Only bets with ≥3.5% edge proceed to kill switch evaluation.

---

### Q: What are kill switches?

Kill switches are automatic disqualifiers. If a condition fires, the bet is killed — **even if the edge and price are great**.

| Sport | Kill Condition | Why |
|-------|---------------|-----|
| NBA | Road back-to-back with <8% edge | Fatigue destroys road B2B teams in late-game execution |
| NBA | PDO regression signal | Teams running unsustainably hot/cold on luck will regress — bet against them |
| NFL | Wind >20mph | High wind wrecks passing game → totals models break down |
| NFL | Backup QB | Win probability models trained on starters are invalid |
| NHL | Starting goalie unconfirmed | Goalie is 85%+ of NHL variance — unknown starter = don't bet |
| Tennis | Surface mismatch | Clay specialist on grass, grass specialist on clay → model stats meaningless |
| Soccer | Dead rubber | Team already eliminated/promoted → effort level drops to zero |
| NCAAB | 3PT reliance >40% (road) | 3PT shooting is the highest-variance stat — road teams regress hard |

Kill switches do not negotiate. There are no overrides. If you disagree with a kill, the model disagrees with you until the data proves otherwise.

---

### Q: What is the Sharp Score (0–100)?

It's the system's overall confidence rating for a bet. Think of it as: *"how much does every signal agree this is a good bet?"*

**How it's calculated:**

| Component | Max Points | What it measures |
|-----------|-----------|-----------------|
| Edge strength | 40 | How much you're beating the fair price |
| RLM (Reverse Line Movement) | 25 | Did sharp money confirm the direction? |
| Team efficiency gap | 20 | How much better is one team than the other, really? |
| Situational factors | 15 | Rest, travel, injury boost, matchup grade |
| **Total** | **100** | |

**Score → Signal grade:**
- **45–59**: LEAN — minimum threshold. Small position or skip.
- **60–89**: STANDARD — solid bet. This is where most bets live.
- **90+**: NUCLEAR — rare. Requires RLM confirmation + injury boost to reach. Bet full size.

A score of 90 is only mathematically reachable if: edge gives you ~35+ points, RLM fires (+25), AND an opposing star player is injured (+5 bonus). Without all three, 90 is the ceiling — not a floor.

---

### Q: What is RLM (Reverse Line Movement)?

When betting lines move in the *opposite direction* of where most public bets are going.

**Example:**
- 70% of tickets are on Team A (public is betting Team A)
- Line moves from Team A -3.5 to Team A -3 (books are giving you a better price on Team A)
- Normally, when 70% bets on Team A, books would move the line AGAINST them (to A -4.5)
- But the line went the other way — that means sharp (professional) money is on Team B

RLM = sharp bettors are on the other side of the public. The system treats this as the strongest single signal.

**In the app:** RLM fires on the *second poll cycle* after a line move. The first poll sets the open price. Any future move against public is measured against that baseline.

---

### Q: What is CLV (Closing Line Value)?

CLV measures whether you beat the final odds before the game started.

**Formula:**
```
CLV = (your price implied probability) - (closing price implied probability)
      ─────────────────────────────────────────────────────────────────────
                         closing price implied probability
```

**Why it matters:** If you consistently beat the closing line, you will be profitable long-term — regardless of short-term win/loss variance. The closing price is the most efficient price (all sharp money has had time to move it). If you beat it, you had an edge.

Positive CLV = you got better odds than where the market settled. This is the gold standard for validating a betting system.

---

### Q: What is the calibration gate? Why does it say "30 bets required"?

The model's self-validation features are intentionally locked until you have enough real bet data to evaluate.

With fewer than 30 graded bets:
- Your sample is too small to distinguish luck from edge
- Correlations are meaningless (one hot/cold streak distorts everything)
- Any "insight" from the data would be confirmation bias, not signal

At 30 graded bets, these unlock:
- **Sharp Score ROI correlation** — do higher sharp scores actually win more?
- **RLM lift analysis** — do RLM-confirmed bets outperform non-RLM bets?
- **CLV beat rate** — what % of your bets beat the closing line?
- **Equity curve** — P&L over time (shows if you're running above/below expected value)

**The calibration gate protects you from making decisions on noise.**

---

### Q: What is PDO regression (NBA)?

PDO = Points Scored % + Points Allowed % (both measured as a proportion of total points in the game).

A team's "true" PDO over a long season trends toward 100. Teams above 105 are getting lucky (opponents hitting unusual shot rates against them). Teams below 95 are getting unlucky.

The system identifies:
- **REGRESS**: Team is running at PDO >102. If they're favored in a matchup, fade them (bet against).
- **RECOVER**: Team is running at PDO <98. If they're an underdog, back them (bet for).

This is a pure mean-reversion signal. The model has no opinion — it's just math.

---

### Q: Why won't the system let me bet on tennis without an API?

The system never uses api-tennis.com or any unofficial tennis data source. **Permanently.**

Surface win rates are pre-loaded for 90 ATP/WTA players from public historical data. This covers ~80% of all ATP Tour and WTA Tour match candidates. If a player isn't in the database, the tennis kill switch treats the matchup as incomplete data and returns no signal (not a kill — just silence).

---

### Q: The analytics page shows "sample guard" warnings everywhere. Is it broken?

No. This is intentional.

The analytics page shows a data wall until you have 30 graded bets. This is not a bug. It's a feature that prevents you from looking at meaningless charts and making decisions based on 5-10 bets of noise.

**To unlock it:** Log and grade 30 bets via Bet Tracker. The gate drops automatically.

---

### Q: What is the Trinity simulation?

The Trinity simulation (used in the Simulator tab and internally for live candidates) is a Monte Carlo model that estimates cover probability for a given bet.

It uses three approaches and weights them:
- **20%**: Consensus probability from market prices
- **20%**: First-principles probability from team efficiency data
- **60%**: Monte Carlo simulation (runs 10,000+ simulated outcomes)

The "mean" input must always be the **efficiency gap** — how much better one team is than the other in points per possession, converted to an expected point margin. It is never the raw market spread.

This is why a +4.5 underdog can have a 47% cover probability even though the market implies 45% — the efficiency data disagrees with the market, and the simulation reflects that disagreement.

---

### Q: How do I know if the model is working?

After 30+ graded bets, look at three things in order:

1. **CLV beat rate > 50%** — you're beating the closing line more than half the time. Edge is real.
2. **Sharp score ROI correlation positive** — higher sharp scores are producing higher returns. The ranking system is working.
3. **RLM lift > 0%** — RLM-confirmed bets are outperforming non-RLM bets. The signal adds value.

If all three are positive after 100+ bets, the model is validated. If any are negative, something needs adjustment. The calibration system will tell you what.

---

### Q: What tabs are in the app and what do they each do?

| Tab | What it does |
|-----|-------------|
| 📖 Guide | You are here. Live session workflow, field glossary, kill switch reference. |
| 📊 Live Lines | The main event. Live bet candidates, ranked by sharp score. Log bets from here. |
| 📈 Analysis | KPI summary, P&L history, edge/CLV histograms, line pressure charts. |
| 📉 Line History | How each line has moved over time. RLM seed table (set open prices). |
| 📝 Bet Tracker | Log new bets. Grade existing bets. CLV tracker. P&L summary. |
| 🧪 R&D Output | Math validation dashboard — tests the model's pure math without live data. |
| 🎮 Simulator | Interactive Trinity game simulator. Set your own inputs, see cover probabilities. |
| 📊 Analytics | Advanced performance analytics. **Locked until 30 graded bets.** |

---

## The Live Session Checklist (print this out)

```
□  Open terminal → streamlit run app.py --server.port 8504
□  Go to http://localhost:8504
□  Wait for first scheduler poll (~5 min after app loads)
□  Live Lines: review candidates sorted by sharp score
□  Find a bet you like → review math breakdown
□  Log Bet: fill required fields + analytics metadata
   □  Sharp Score (copy from card)
   □  Line (the spread/total value)
   □  Book (where you're placing it)
   □  RLM Confirmed (was there an RLM signal?)
   □  Days to Game (0 = today)
   □  Signal (what triggered this? e.g. "sharp", "rlm_confirmed")
   □  Tags (e.g. "nba,home_dog")
□  After game: grade the bet in Bet Tracker → Grade Bet
   □  Win / Loss / Void
   □  Actual stake
   □  Closing price (for CLV calculation)
□  Repeat until 30 graded bets → Analytics page unlocks
```

---

*Built by Titanium-Agentic (experimental sandbox). Math > Narrative. Always.*
