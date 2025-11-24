# Mining Guide

This guide is for miners who want to participate in the BitAds V3 subnet and earn rewards based on their performance.

## What is Mining?

Mining in BitAds V3 involves providing ad campaign services on the Bittensor network. Miners earn rewards based on their performance metrics:

- **Sales**: Number of successful ad campaign sales
- **Revenue**: Total revenue generated in USD
- **Refunds**: Number of refund orders (lower is better)

## Prerequisites

### Register Your Hotkey on the Subnet

Before you can start mining, you must register your hotkey on the BitAds V3 subnet using the Bittensor CLI:

**For Mainnet (finney)**:
```sh
btcli subnet register --netuid 16
```

**For Testnet (test)**:
```sh
btcli subnet register --netuid 368
```

This command will register your hotkey on the subnet, allowing you to participate and receive rewards. Make sure you have sufficient TAO in your wallet to cover the registration fee.

## How Scoring Works

Your score is calculated by validators using the following algorithm:

### Step 1: Refund Rate
```
refund_rate = min(1, refund_orders / max(1, sales))
```

### Step 2: Sales Normalization
```
sales_norm = min(1, sqrt(sales) / max(sqrt(p95_sales), eps))
```
Normalized against the 95th percentile of all miners.

### Step 3: Revenue Normalization
```
rev_norm = min(1, ln(1 + revenue) / max(ln(1 + p95_revenue), eps))
```
Normalized against the 95th percentile of all miners.

### Step 4: Base Score
```
base = 0.40 * sales_norm + 0.60 * rev_norm
```
Weighted combination: 40% sales, 60% revenue.

### Step 5: Final Score
```
score = (1 - refund_rate) * base
```
Applies refund multiplier.

### Step 6: Soft Cap (if enabled)
If `sales < 3`:
```
score = score * 0.30
```

## Maximizing Your Score

### Increase Sales

- Provide high-quality ad campaign services
- Maintain consistent performance over time
- Focus on customer satisfaction and retention
- Build a reputation for reliability

### Increase Revenue

- Offer premium services and packages
- Optimize pricing strategies
- Build long-term customer relationships
- Upsell and cross-sell opportunities

### Reduce Refunds

- Deliver on promises and commitments
- Provide excellent customer service
- Set realistic expectations
- Handle issues proactively before they become refunds

## Understanding Your Performance

### P95 Percentiles

Your performance is normalized against the 95th percentile of all miners:
- If you're at P95, your normalized score is 1.0
- If you're below P95, your normalized score is proportional
- P95 values are computed automatically from all miner statistics

### Soft Cap

Miners with sales < 3 receive a 0.30 multiplier on their score. This encourages consistent performance and discourages inactive miners.

### Refund Impact

High refund rates significantly reduce your score:
- Refund rate = refunds / sales
- Final score = base score × (1 - refund rate)
- Example: 20% refund rate reduces your score by 20%

## Performance Metrics

### Sales Count

The number of successful ad campaign sales you've completed in the rolling window (typically 30 days).

### Revenue in USD

The total revenue generated from your ad campaign services, measured in USD.

### Refund Orders

The number of refund orders processed. Lower is better.

## Monitoring Your Performance

### Check Your Stats

Monitor your performance metrics regularly:
- Track sales count over time
- Monitor revenue trends
- Keep refund rate as low as possible

### Track Your Score

Your score is computed by validators and submitted to the Bittensor network. You can check your weight in the metagraph to see your relative performance.

### Weight Distribution

Weights are distributed based on scores:
- Higher scores → Higher weights → More rewards
- Weights are normalized across all miners
- Burn percentage goes to UID 0 (subnet owner)

## Best Practices

### Consistency

- Maintain steady performance over time
- Avoid large fluctuations in sales or revenue
- Build a sustainable business model

### Quality

- Focus on delivering value to customers
- Prioritize quality over quantity
- Build a strong reputation

### Customer Service

- Minimize refunds through excellent service
- Respond quickly to customer issues
- Set clear expectations upfront

### Monitoring

- Track your metrics regularly
- Identify trends and patterns
- Adjust your strategy based on performance

## Common Pitfalls

### Low Sales Volume

- Problem: Sales < 3 triggers soft cap (0.30 multiplier)
- Solution: Focus on increasing sales volume consistently

### High Refund Rate

- Problem: High refunds significantly reduce score
- Solution: Improve service quality and customer satisfaction

### Inconsistent Performance

- Problem: Large fluctuations make it hard to maintain good scores
- Solution: Build sustainable, consistent operations

## Getting Help

- Review the [Core Library documentation](https://pypi.org/project/bitads-v3-core/) for detailed scoring formulas
- Check validator logs for scoring information
- Contact the community for support

## Next Steps

- [Validating Guide](validating.md) - Learn about running a validator
- Review the scoring algorithm in detail
- Monitor your performance metrics

