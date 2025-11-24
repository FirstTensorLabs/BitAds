<div align="center">

![BitAds Logo](https://raw.githubusercontent.com/FirstTensorLabs/BitAds-Assets/main/Logo-white-green-black.png)

# BitAds V3

BitAds V3 is a Bittensor subnet that validates and rewards miners for providing ad campaign services. The system uses a sophisticated scoring algorithm to evaluate miner performance based on sales, revenue, and refund metrics.

**Website**: [bitads.ai](https://bitads.ai)

</div>

## What is BitAds V3?

BitAds V3 is a specialized Bittensor subnet that:
- Rewards miners for providing ad campaign services
- Validates miner performance using sales, revenue, and refund metrics
- Distributes rewards based on computed scores
- Supports multiple campaigns with different scoring scopes

## How It Works

### For Miners

Miners provide ad campaign services and earn rewards based on:
- **Sales**: Number of successful ad campaign sales
- **Revenue**: Total revenue generated in USD
- **Refunds**: Number of refund orders (lower is better)

See [Mining Guide](docs/mining.md) for details.

### For Validators

Validators collect miner performance data, calculate scores, and submit weights to the Bittensor network. The scoring algorithm evaluates miners using:

1. **Refund Rate**: $\text{ref}_i = \min(1, \frac{{\text{refund}\_\text{orders}}_i}{\max(1, \text{sales}_i)})$
2. **Sales Normalization**: Square root normalization against P95 percentile
3. **Revenue Normalization**: Logarithmic normalization against P95 percentile
4. **Base Score**: $40\%$ sales + $60\%$ revenue
5. **Final Score**: $\text{score}_i = \text{base}_i \times (1 - \text{ref}_i)$

See [Validating Guide](docs/validating.md) for setup instructions.

## Scoring Algorithm

### BitAds Miner Score

**Purpose**: Compute a bounded score in $[0,1]$ per miner for the last 30 days, combining:
- Sales volume (weight 40%)
- Revenue in USD (weight 60%)
- Refund rate as a multiplicative penalty

This is outlier-resistant, easy to implement, and aligned with merchant value.

### Inputs (per miner i, last 30 days)

- `sales_i` (integer ≥ 0): number of verified orders (post-webhook truth)
- `rev_i` (float ≥ 0): sum of verified revenue in USD
- `refund_orders_i` (integer ≥ 0): number of refunded orders among the verified ones

**Derived**:
- $\text{ref}_i = \frac{{\text{refund}\_\text{orders}}_i}{\max(1, \text{sales}_i)}$ (refund rate in $[0,1]$)

> **Note**: If `sales_i = 0`, the score will be 0 regardless of refunds, which is intended.

### Network Reference Values (for normalization)

Compute across all active miners in the same 30-day window (or campaign-level):
- $P95_{\text{sales}}$ = 95th percentile of $\{\text{sales}_j\}$
- $P95_{\text{rev}}$ = 95th percentile of $\{\text{rev}_j\}$

**Why percentiles?** P95 provides a robust scale that ignores extreme whales (top 5%). It adapts automatically as the network performance changes.

**Indexing**: For $N$ miners sorted ascending, P95 is value at index $\lceil 0.95 \times N \rceil$ (1-indexed).

### Normalization with Diminishing Returns

We compress extremes (many sales or huge revenue) to keep the score fair.

Let $\varepsilon = 10^{-9}$ (to avoid division by zero) and define:

$${\text{sales}\_\text{norm}}_i = \min\left(1, \frac{\sqrt{\text{sales}_i}}{\max(\sqrt{P95_{\text{sales}}}, \varepsilon)}\right)$$

$${\text{rev}\_\text{norm}}_i = \min\left(1, \frac{\ln(1 + \text{rev}_i)}{\max(\ln(1 + P95_{\text{rev}}), \varepsilon)}\right)$$

- $\sqrt{\cdot}$ rewards volume while reducing dominance of very high counts
- $\ln(1+\cdot)$ rewards revenue while compressing very large tickets
- Each normalized component is in $[0,1]$ by construction

### Weights (fixed)

- $w_{\text{sales}} = 0.40$
- $w_{\text{rev}} = 0.60$

Compute the base (pre-refund) score:

$$\text{base}_i = w_{\text{sales}} \times {\text{sales}\_\text{norm}}_i + w_{\text{rev}} \times {\text{rev}\_\text{norm}}_i$$

$\text{base}_i \in [0,1]$

### Refund Penalty (multiplicative)

Given your requirement: if 10% refunds, multiply score by 0.90.

General rule:

$${\text{refund}\_\text{multiplier}}_i = 1 - \text{ref}_i \quad \text{(in } [0,1] \text{)}$$

**Example**: $\text{ref}_i = 0.25$ → multiplier = $0.75$ ($-25\%$ to score)

### Final Score (bounded)

$$\text{score}_i = \text{base}_i \times {\text{refund}\_\text{multiplier}}_i$$

Result is guaranteed in $[0,1]$.

### Worked Examples

#### Example A (balanced high performer)

- **Network**: $P95_{\text{sales}} = 60$, $P95_{\text{rev}} = 4,000$
- **Miner A** (last 30d):
  - $\text{sales}_i = 48$
  - $\text{rev}_i = 2,300$
  - ${\text{refund}\_\text{orders}}_i = 6$ → $\text{ref}_i = \frac{6}{48} = 0.125$ → mult = $0.875$

**Compute**:
$$\text{sales}\_\text{norm} = \frac{\sqrt{48}}{\sqrt{60}} = \frac{6.928}{7.746} \approx 0.894$$

$$\text{rev}\_\text{norm} = \frac{\ln(2301)}{\ln(4001)} = \frac{7.741}{8.294} \approx 0.933$$

$$\text{base} = 0.40 \times 0.894 + 0.60 \times 0.933 = 0.358 + 0.560 = 0.918$$

$$\text{score} = 0.918 \times 0.875 = 0.802$$

#### Example B (few sales, higher $ per sale)

- **Same network P95s**
- **Miner B**:
  - $\text{sales}_i = 10$
  - $\text{rev}_i = 3,000$
  - ${\text{refund}\_\text{orders}}_i = 1$ → $\text{ref}_i = 0.10$ → mult = $0.90$

$$\text{sales}\_\text{norm} = \frac{\sqrt{10}}{\sqrt{60}} = \frac{3.162}{7.746} \approx 0.408$$

$$\text{rev}\_\text{norm} = \frac{\ln(3001)}{\ln(4001)} = \frac{8.007}{8.294} \approx 0.965$$

$$\text{base} = 0.40 \times 0.408 + 0.60 \times 0.965 = 0.163 + 0.579 = 0.742$$

$$\text{score} = 0.742 \times 0.90 = 0.668$$

A wins on volume and slightly better refund rate; B is very strong on revenue.

#### Example C (no sales)

- **Miner C**: $\text{sales}_i = 0$, $\text{rev}_i = 0$, ${\text{refund}\_\text{orders}}_i = 0$ → $\text{score} = 0$

### Edge Cases & Guardrails

- **Zero P95s** (tiny networks or new epoch): Use $\max(\sqrt{P95_{\text{sales}}}, \varepsilon)$ and $\max(\ln(1+P95_{\text{rev}}), \varepsilon)$; with $\varepsilon = 10^{-9}$ the expression remains safe.

- **Sales < 3 floor (optional)**: To avoid 1-sale flukes, you can soft-cap:
  ```python
  if sales_i < 3:
      score_i *= 0.3  # only 30% credit until 3 sales
  ```
  (Not required by the spec, but commonly used.)

- **Refunds > sales** (data noise): Clamp: $\text{ref}_i = \min(1, \frac{{\text{refund}\_\text{orders}}_i}{\max(1, \text{sales}_i)})$.

- **Campaign vs. global P95**: Preferred: compute per-campaign P95 to keep things fair across low-ticket vs high-ticket campaigns. For a global leaderboard, average per-campaign scores with weights = campaign budget or impressions.

- **Smoothing P95 (optional)**: To avoid jumps between epochs:
  $$P95_{\text{sales},t} = \alpha \times P95_{\text{sales},\text{cur}} + (1-\alpha) \times P95_{\text{sales},\text{prev}}$$
  $$P95_{\text{rev},t} = \alpha \times P95_{\text{rev},\text{cur}} + (1-\alpha) \times P95_{\text{rev},\text{prev}}$$
  with $\alpha \in [0.3, 0.5]$.

- **Data integrity**: Only include webhook-verified sales/revenue and confirmed refunds/chargebacks in the 30-day window.

### Implementation

The scoring algorithm is implemented in the `bitads-v3-core` library:
- Pure, deterministic, and unit-testable
- No external dependencies
- Available on PyPI: [bitads-v3-core](https://pypi.org/project/bitads-v3-core/)

## Burn Mechanism

The burn mechanism automatically adjusts the percentage of emissions that are burned to prevent miners from becoming over-profitable when emissions exceed the value they generate.

### The Problem

When emissions (paid in TAO) are worth more than the sales value miners generate, miners become over-profitable. This creates sell pressure as miners convert excess TAO to USDC, which can hurt the subnet's TAO price.

**Example**: Miners generate $10,000 in sales, but emissions are worth $30,000. The excess $20,000 creates over-profitability and sell pressure.

### How It Works

The burn mechanism automatically calculates and applies a burn percentage based on the relationship between sales and emissions:

1. **Get total emissions** for the period (in TAO)
2. **Convert to USD**: Multiply by current TAO/USD price
3. **Get total sales**: Sum of actual sales generated by miners (in USD)
4. **Get target ratio**: Fetch the target sales-to-emission ratio from external API
   - `1.0` = 1:1 ratio (miners earn what they generate)
   - `1.5` = 1.5:1 ratio (miners can earn up to 1.5× their sales)
   - `2.0` = 2:1 ratio (more generous, but more burn needed if sales fall behind)
5. **Calculate burn percentage**:
   - If emissions ≤ sales × ratio: burn = 0%
   - Otherwise: burn = (emissions - sales × ratio) / emissions × 100%

### Formula

$$\text{burn}\_\text{percentage} = \max\left(0, \frac{{\text{emission}\_\text{usd}} - {\text{sales}\_\text{usd}} \times {\text{target}\_\text{ratio}}}{{\text{emission}\_\text{usd}}} \times 100\right)$$

The result is clamped to $[0.0, 100.0]\%$.

### Examples

#### Example 1: No Burn Needed

- **Emissions**: $10,000 USD
- **Sales**: $10,000 USD
- **Target ratio**: 1.0 (1:1)

$$\text{burn} = \frac{10,000 - 10,000 \times 1.0}{10,000} \times 100 = 0\%$$

No burn needed since emissions match sales at the target ratio.

#### Example 2: Burn Required

- **Emissions**: $15,000 USD
- **Sales**: $10,000 USD
- **Target ratio**: 1.0 (1:1)

$$\text{burn} = \frac{15,000 - 10,000 \times 1.0}{15,000} \times 100 \approx 33.3\%$$

Approximately 33% of emissions need to be burned to maintain the 1:1 ratio.

#### Example 3: With 1.5:1 Ratio

- **Emissions**: $20,000 USD
- **Sales**: $10,000 USD
- **Target ratio**: 1.5 (1.5:1)

Expected emissions at 1.5:1 ratio: $10,000 × 1.5 = $15,000

$$\text{burn} = \frac{20,000 - 15,000}{20,000} \times 100 = 25\%$$

25% burn needed since emissions exceed the more generous 1.5:1 ratio.

### Automatic Operation

The burn percentage is calculated automatically by validators:

1. **Periodic calculation**: Validators recalculate the burn percentage every X hours/days
2. **Data fetching**: Validators fetch:
   - Total emissions in TAO (from chain)
   - TAO/USD price (from price oracle)
   - Total sales in USD (from sales API)
   - Target sales-to-emission ratio (from configuration API)
3. **Weight application**: The calculated burn percentage is applied by sending that percentage of weights to the subnet creator's hotkey (UID 0)
4. **Automatic burning**: Emissions sent to the creator hotkey are automatically burned by the chain

No manual configuration or validator updates are required—the system adjusts automatically based on current sales and emissions data.

## Documentation

- [Mining Guide](docs/mining.md) - Guide for miners
- [Validating Guide](docs/validating.md) - Guide for validators

