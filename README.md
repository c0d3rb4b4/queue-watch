# Azure Service Bus Monitor

> Real-time terminal monitor for Azure Service Bus queue and topic subscription depth.

![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

Watch active message counts, dead-letter counts, per-poll trend, and an adaptive rolling rate — all from a single terminal window. No Azure CLI required.

```
Azure Service Bus Monitor
----------------------------------------
Namespace: sbus-int-prod
Topic: customeraccount  Subscription: customeraccountcreatioSubscription
Time: 14:22:07
Active Messages: 84 (+12) ↑
Dead Letters:    0
Rate (47-poll):  +0.83 msg/s  [47/200 polls]
Poll interval:   3.0s
```

---

## Features

| | |
|---|---|
| 📊 **Live depth** | Active and dead-letter message counts, updated every poll |
| 📈 **Trend arrow** | ↑ growing · ↓ shrinking · → no change, colour-coded |
| ⚡ **Rolling rate** | msgs/sec calculated over up to 200 polls; shown from poll 20 onwards |
| 🔄 **Adaptive polling** | Backs off exponentially (×1.5 per idle poll, max 60 s) when count is unchanged; snaps back immediately on any change |
| 🔐 **Browser auth** | `InteractiveBrowserCredential` — one browser login, token cached and silently refreshed for the session |
| 🖥️ **Cross-platform** | macOS, Linux, Windows |

---

## Requirements

- Python 3.8+
- An Azure account with **Reader** access to the Service Bus namespace

---

## Setup

```bash
# clone / download the repo, then:
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> **Windows — execution policy**  
> If PowerShell blocks the activate script:  
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## Usage

### Monitor a queue

```bash
python queue_watch.py \
  --sub 00000000-0000-0000-0000-000000000000 \
  --rg my-resource-group \
  --namespace my-servicebus \
  --queue my-queue
```

### Monitor a topic subscription

```bash
python queue_watch.py \
  --sub 00000000-0000-0000-0000-000000000000 \
  --rg my-resource-group \
  --namespace my-servicebus \
  --topic my-topic \
  --sub-name my-subscription
```

### Custom poll interval

```bash
python queue_watch.py ... --interval 5
```

Press **Ctrl+C** to stop.

---

## Arguments

| Argument | Alias | Required | Default | Description |
|---|---|:---:|:---:|---|
| `--subscription` | `--sub` | ✅ | | Azure subscription ID |
| `--resource-group` | `--rg` | ✅ | | Resource group of the namespace |
| `--namespace` | | ✅ | | Service Bus namespace name |
| `--queue` | | ¹ | | Queue name to monitor |
| `--topic` | | ¹ | | Topic name to monitor |
| `--sub-name` | | ² | | Topic subscription name |
| `--interval` | | | `3` | Base poll interval in seconds |

¹ Specify exactly one of `--queue` or `--topic`.  
² Required when `--topic` is used.

---

## How adaptive polling works

When the active message count is **unchanged**, the poll interval grows exponentially:

$$t_n = t_{\text{base}} \times 1.5^n \quad \text{(capped at 60 s)}$$

The first poll that shows a **change** resets the interval back to `--interval` immediately. This keeps the terminal responsive during activity while being gentle on the API during quiet periods.

---

## Dependencies

```
azure-identity>=1.15.0
colorama>=0.4.6
requests>=2.31.0
```

---

## Ideas for extension

- Monitor multiple queues / subscriptions simultaneously
- Log counts to CSV for later analysis
- Alert (desktop notification / webhook) when dead-letter count rises
- Add throughput/sec sparkline

