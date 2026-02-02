# Validating Guide

Welcome! This guide will help you set up and run a BitAds validator on Bittensor Subnet 16. Validators play a crucial role in the network by evaluating miner performance and distributing rewards.

## What Does a Validator Do?

As a validator, you'll:
- **Collect data**: Gather miner performance metrics (sales, revenue, refunds)
- **Calculate scores**: Use the scoring algorithm to evaluate each miner
- **Submit weights**: Send calculated scores to the Bittensor network
- **Distribute rewards**: Help ensure miners are rewarded fairly based on performance

## Prerequisites

### Register Your Hotkey on the Subnet

Before you can start validating, you must register your hotkey on the BitAds subnet using the Bittensor CLI:

**For Mainnet (finney)**:
```sh
btcli subnet register --netuid 16
```

**For Testnet (test)**:
```sh
btcli subnet register --netuid 368
```

This command will register your hotkey on the subnet, allowing you to participate as a validator. Make sure you have sufficient TAO in your wallet to cover the registration fee.

## 🟢 Quick Start: Docker Setup (Recommended)

The easiest way to run a validator is using Docker Compose. This method handles updates automatically and is the recommended approach.

### Step 1: Create a Directory

Create a new folder for your validator:

```sh
mkdir bitads
cd bitads
```

### Step 2: Get the Configuration File

Download the `docker-compose.yml` file:

```sh
curl -L -o docker-compose.yml https://raw.githubusercontent.com/FirstTensorLabs/BitAds/refs/heads/main/docker-compose.yml
```

**Alternative**: If you prefer to clone the repository:

```sh
git clone https://github.com/FirstTensorLabs/BitAds.git
cd BitAds
```

### Step 3: Start the Validator

Start the validator in the background:

```sh
docker compose up -d
```

> ⚠️ **Important**: By default, the validator uses wallet name `default` and hotkey `default`. You should configure your own wallet for security. See the [Wallet Customization](#-wallet-customization) section below.

### Step 4: Check Status

View the validator logs to make sure everything is running:

```sh
docker compose logs -f validator
```

You should see logs showing the validator syncing with the network and processing campaigns.

---

## 🖥️ Hardware Requirements

Make sure your server meets these specifications:

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 1 core @ 2.6 GHz | 2 cores @ 2.6 GHz |
| **RAM** | 2 GB | 4 GB |

### Supported Platforms

| Platform | Status | Examples |
|----------|--------|----------|
| ARM64 | ✅ Supported | Apple Silicon, Ampere® |
| x86/x86_64 | ✅ Supported | Intel, AMD processors |

---

## 🛑 Running Without Docker (Advanced)

> 💡 **Note**: Docker is recommended because it handles automatic updates. Only use this method if you have a specific need to run outside Docker.

> ⚠️ **Important**: When running manually (without Docker), the `.env` file configuration does not work. You must pass all parameters via command-line arguments.

If you need to run the validator directly on your system:

### Step 1: Install Dependencies

```sh
git clone https://github.com/FirstTensorLabs/BitAds
cd BitAds

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### Step 2: Run the Validator

Choose the command based on which network you want to use:

| Network | NETUID | Network Name | Use Case |
|---------|--------|--------------|----------|
| **Mainnet** | 16 | `finney` | Production use |
| **Testnet** | 368 | `test` | Testing and development |

**For Mainnet (Production)**:
```sh
python neurons/validator.py \
  --netuid 16 \
  --subtensor.network finney \
  --wallet.name <YOUR_WALLET_NAME> \
  --wallet.hotkey <YOUR_HOTKEY>
```

**For Testnet (Testing)**:
```sh
python neurons/validator.py \
  --netuid 368 \
  --subtensor.network test \
  --wallet.name <YOUR_WALLET_NAME> \
  --wallet.hotkey <YOUR_HOTKEY>
```

Replace `<YOUR_WALLET_NAME>` and `<YOUR_HOTKEY>` with your actual Bittensor wallet credentials.

---

## ⚙️ Wallet Customization

You need to configure your Bittensor wallet for the validator to work. Here are two easy ways to do it:

> ⚠️ **Note**: The `.env` file method only works with Docker Compose. If you're running the validator manually, you must use command-line arguments (see Method 2).

### Method 1: Using a `.env` File (Docker Only)

This is the recommended method for Docker users because your settings are saved and easy to manage.

1. **Copy the example file**:
   ```sh
   cp env.example .env
   ```

2. **Edit the `.env` file** with your favorite text editor:

   | Variable | Mainnet Value | Testnet Value | Description |
   |----------|---------------|---------------|-------------|
   | `NETUID` | `16` | `368` | Subnet identifier |
   | `SUBTENSOR_NETWORK` | `finney` | `test` | Network name |
   | `WALLET_NAME` | `my_wallet` | `my_wallet` | Your wallet name |
   | `WALLET_HOTKEY` | `my_hotkey` | `my_hotkey` | Your hotkey name |
   | `LOGGING_LEVEL` | `info` | `info` | Log verbosity |
   | `AXON_PORT` | `9100` | `9100` | Axon / metrics port (optional) |

   Example `.env` file for mainnet:
   ```env
   NETUID=16
   SUBTENSOR_NETWORK=finney
   WALLET_NAME=my_wallet
   WALLET_HOTKEY=my_hotkey
   LOGGING_LEVEL=info
   AXON_PORT=9100
   ```

   Replace `my_wallet` and `my_hotkey` with your actual wallet name and hotkey.

3. **Start the validator**:
   ```sh
   docker compose up -d
   ```

   The validator will automatically use the settings from your `.env` file.

### Method 2: Command Line Arguments

#### For Docker Users

You can set variables directly when starting Docker (alternative to `.env` file):

**For Mainnet**:
```sh
WALLET_NAME=my_wallet \
WALLET_HOTKEY=my_hotkey \
NETUID=16 \
SUBTENSOR_NETWORK=finney \
docker compose up -d
```

**For Testnet**:
```sh
WALLET_NAME=my_wallet \
WALLET_HOTKEY=my_hotkey \
NETUID=368 \
SUBTENSOR_NETWORK=test \
docker compose up -d
```

#### For Manual Startup

> ⚠️ **Important**: When running manually, `.env` files are not used. You must pass all parameters via command-line arguments.

**For Mainnet**:
```sh
python neurons/validator.py \
  --netuid 16 \
  --subtensor.network finney \
  --wallet.name my_wallet \
  --wallet.hotkey my_hotkey
```

**For Testnet**:
```sh
python neurons/validator.py \
  --netuid 368 \
  --subtensor.network test \
  --wallet.name my_wallet \
  --wallet.hotkey my_hotkey
```

> 💡 **Tip**: For Docker users, Method 1 (`.env` file) is easier to manage and less error-prone.

---

## How the Validator Works

### The Validation Cycle

Once running, your validator continuously:

1. **Syncs with the network**: Connects to Bittensor and gets the latest state
2. **Checks timing**: Determines when it's time to update weights (based on subnet tempo)
3. **Processes campaigns**: For each active campaign:
   - Fetches miner statistics (sales, revenue, refunds)
   - Calculates P95 percentiles for normalization
   - Computes scores for all miners
   - Submits weights to the Bittensor network
4. **Updates metrics**: Refreshes percentile calculations after each cycle
5. **Waits**: Sleeps until the next update cycle

### Weight Distribution

When submitting weights:
- A percentage is burned (sent to UID 0, the subnet owner)
- The remaining percentage is distributed to miners based on their scores
- Higher scores = higher weights = more rewards

---

## 📊 Monitoring Your Validator

### Viewing Logs

Check what your validator is doing in real-time:

```sh
docker compose logs -f validator
```

Press `Ctrl+C` to exit the log viewer.

### Log File Location

Logs are also saved to your local filesystem:
```
~/.bittensor/wallets/{wallet_name}/{hotkey}/netuid{netuid}/validator/
```

### What to Monitor

Keep an eye on these metrics:

| Metric | Description | What to Look For |
|--------|-------------|------------------|
| **Campaigns processed** | Number of campaigns handled | Should match active campaigns |
| **Miners scored** | How many miners received scores | Should include all active miners |
| **Weight submissions** | Success rate of weight updates | Should be 100% or close to it |
| **Errors** | Any issues that need attention | Should be minimal or zero |
| **P95 values** | Current percentile thresholds | Should update regularly |

### Prometheus Metrics (Recommended)

The validator exposes Prometheus metrics for monitoring validator status, performance, and version information. This is **highly recommended** for production deployments.

#### Enabling Metrics

Metrics are enabled by default and exposed on `config.axon.port` (default `9100`). You can customize this port via the axon configuration:

**In `.env` file (Docker)** (recommended):
```env
AXON_PORT=9100
```

**Via command line (Docker)**:
```sh
AXON_PORT=9100 docker compose up -d
```

**Via command line (Manual)**:
```sh
python neurons/validator.py --netuid 16 --subtensor.network finney --axon.port 9100 ...
```

#### Exposing the Metrics Port

**For Docker Compose**: The metrics / axon port is automatically exposed in the `docker-compose.yml` file. If you need to change the port, update both the `AXON_PORT` environment variable and the port mapping in `docker-compose.yml`:

```yaml
ports:
  - "${AXON_PORT:-9100}:${AXON_PORT:-9100}"
```

**For Manual Setup**: Ensure the port is accessible. You may need to:
- Open the port in your firewall
- Configure port forwarding if behind a router
- Use a reverse proxy if needed

#### Available Metrics

The validator exposes the following Prometheus metrics:

| Metric Name | Type | Description | Labels |
|-------------|------|-------------|--------|
| `validator_version` | Gauge | Validator version as integer (converted from semantic version) | `hotkey`, `version_string` |
| `validator_loop_iterations_total` | Counter | Total number of main loop iterations | `hotkey` |
| `validator_sync_and_process_duration_seconds` | Histogram | Duration of sync and process cycle | `hotkey` |
| `validator_last_process_success` | Gauge | 1 if last cycle succeeded, 0 otherwise | `hotkey` |
| `validator_active_campaigns` | Gauge | Number of active campaigns processed | `hotkey` |
| `validator_weights_sets_total` | Counter | Total successful weight-setting operations | `hotkey`, `scope` |
| `validator_weights_errors_total` | Counter | Total errors during weight-setting | `hotkey`, `scope` |

#### Accessing Metrics

Once the validator is running, you can access metrics at:

```
http://localhost:9100/metrics
```

Or from another machine:
```
http://<validator-ip>:9100/metrics
```

#### Example Metrics Output

```
# Validator version (recommended to monitor for version tracking)
validator_version{hotkey="5F3sa2TJAWMqDhXG6jhV4N8ko9SxwGy8TpaNS1repo5EYjQX",version_string="0.0.1"} 1

# Loop iterations
validator_loop_iterations_total{hotkey="5F3sa2TJAWMqDhXG6jhV4N8ko9SxwGy8TpaNS1repo5EYjQX"} 42

# Process duration
validator_sync_and_process_duration_seconds_bucket{hotkey="5F3sa2TJAWMqDhXG6jhV4N8ko9SxwGy8TpaNS1repo5EYjQX",le="5.0"} 40

# Last process success
validator_last_process_success{hotkey="5F3sa2TJAWMqDhXG6jhV4N8ko9SxwGy8TpaNS1repo5EYjQX"} 1

# Active campaigns
validator_active_campaigns{hotkey="5F3sa2TJAWMqDhXG6jhV4N8ko9SxwGy8TpaNS1repo5EYjQX"} 3
```

#### Setting Up Prometheus Scraping

To scrape these metrics with Prometheus, add a job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'bitads-validator'
    static_configs:
      - targets: ['<validator-ip>:9100']
        labels:
          instance: 'my-validator'
          network: 'mainnet'
```

#### Disabling Metrics

If you need to disable metrics (not recommended), you can:

**Via command line**:
```sh
python neurons/validator.py --disable-telemetry --netuid 16 ...
```

When telemetry is disabled, the validator will **not start the metrics server or serve an axon**, so it will not accept incoming RPC requests from miners.

**Note**: Metrics are valuable for monitoring validator health and version tracking. We strongly recommend keeping them enabled in production.

---

## 🔧 Troubleshooting

| Problem | Symptoms | Solutions |
|---------|----------|-----------|
| **No Miner Statistics Found** | Warnings about empty miner stats | • Check data source accessibility<br>• Verify campaign configuration<br>• Ensure statistics API is responding<br>• Check network connection |
| **Weight Submission Fails** | Errors when submitting weights | • Verify wallet has enough TAO<br>• Check internet connection stability<br>• Verify mechanism ID (mech_id) configuration<br>• Confirm Bittensor network status |
| **Can't Connect to Network** | Connection errors to Subtensor or data sources | • Test internet connection<br>• Verify RPC endpoints are reachable<br>• Check firewall rules<br>• Review network configuration |

---

## 💡 Best Practices

| Category | Practice | Why It Matters |
|----------|----------|----------------|
| **Keep It Running** | Monitor logs daily | Catch issues early before they become problems |
| | Set up alerts | Get notified immediately if validator stops |
| | Track metrics over time | Understand performance trends |
| **Stay Updated** | Use Docker (automatic updates) | Watchtower handles updates seamlessly |
| | Test on testnet first | Verify updates work before mainnet |
| | Read changelogs | Know what changed before updating |
| **Protect Your Setup** | Backup wallet files | Prevent loss of access |
| | Save configuration | Easy to restore or migrate |
| | Test recovery procedures | Ensure backups actually work |

---

## 📚 Additional Resources

- **Scoring Details**: Check the [Core Library documentation](https://pypi.org/project/bitads-v3-core/) for algorithm details
- **Mining Guide**: Learn about [mining](mining.md) in the BitAds network
- **Community Support**: Reach out to the community if you need help

---

## 🎯 Next Steps

Now that your validator is running:

1. ✅ Monitor the logs to ensure everything is working
2. ✅ Set up alerts for critical issues
3. ✅ Review the [mining guide](mining.md) to understand how miners are scored
4. ✅ Join the community to share experiences and get help

Happy validating! 🚀
