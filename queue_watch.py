import argparse
import time
import os
from collections import deque
from datetime import datetime
from typing import Optional
import requests
from azure.identity import InteractiveBrowserCredential
from colorama import Fore, Style, init

# --- Init colorama (important for Windows) ---
init(autoreset=True)

# --- Auth ---
_credential: Optional[InteractiveBrowserCredential] = None


def _get_token() -> str:
    """Return a Bearer token, re-using the credential across polls."""
    global _credential
    if _credential is None:
        _credential = InteractiveBrowserCredential()
    token = _credential.get_token("https://management.azure.com/.default")
    return f"Bearer {token.token}"


# --- Helpers ---
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def get_counts(subscription_id: str, resource_group: str, namespace: str,
               queue_name: Optional[str], topic_name: Optional[str], sub_name: Optional[str]):
    try:
        if topic_name:
            url = (
                f"https://management.azure.com/subscriptions/{subscription_id}"
                f"/resourceGroups/{resource_group}"
                f"/providers/Microsoft.ServiceBus/namespaces/{namespace}"
                f"/topics/{topic_name}/subscriptions/{sub_name}"
                f"?api-version=2021-11-01"
            )
        else:
            url = (
                f"https://management.azure.com/subscriptions/{subscription_id}"
                f"/resourceGroups/{resource_group}"
                f"/providers/Microsoft.ServiceBus/namespaces/{namespace}"
                f"/queues/{queue_name}"
                f"?api-version=2021-11-01"
            )
        r = requests.get(url, headers={"Authorization": _get_token()}, timeout=10)
        r.raise_for_status()
        details = r.json()["properties"]["countDetails"]
        return details["activeMessageCount"], details["deadLetterMessageCount"]
    except Exception as e:
        return None, str(e)


def get_trend(current, previous):
    if previous is None:
        return "→", Fore.YELLOW, 0

    delta = current - previous

    if delta > 0:
        return "↑", Fore.RED, delta    # growing = bad
    elif delta < 0:
        return "↓", Fore.GREEN, delta  # shrinking = good
    else:
        return "→", Fore.YELLOW, 0


def get_rate_value(history: deque):
    """Return msgs/sec as a float, or None if fewer than 20 polls accumulated."""
    if len(history) < 20:
        return None
    oldest_count, oldest_ts = history[0]
    newest_count, newest_ts = history[-1]
    elapsed = (newest_ts - oldest_ts).total_seconds()
    if elapsed <= 0:
        return None
    return (newest_count - oldest_count) / elapsed


def get_rate(history: deque) -> str:
    """Return formatted msgs/sec string, or '-' if not yet available."""
    rate = get_rate_value(history)
    return "-" if rate is None else f"{rate:+.2f} msg/s"


def get_eta(active: int, history: deque) -> str:
    """Return estimated time to drain to zero based on current rate.

    Only meaningful when the rate is negative (queue shrinking).
    Returns '-' when rate is unavailable, '∞' when rate is zero or positive.
    """
    rate = get_rate_value(history)
    if rate is None:
        return "-"
    if rate >= 0:
        return "∞" if rate == 0 else "∞ (growing)"
    seconds = active / abs(rate)
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes:02d}m"


# --- Main loop ---
def main():
    parser = argparse.ArgumentParser(
        description="Monitor Azure Service Bus queue or topic subscription depth in real time.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor a queue
  python queue_watch.py \\
    --sub 00000000-0000-0000-0000-000000000000 \\
    --rg my-resource-group \\
    --namespace my-servicebus \\
    --queue my-queue

  # Monitor a topic subscription
  python queue_watch.py \\
    --sub 00000000-0000-0000-0000-000000000000 \\
    --rg my-resource-group \\
    --namespace my-servicebus \\
    --topic my-topic \\
    --sub-name my-subscription

  # Custom poll interval
  python queue_watch.py \\
    --sub 00000000-0000-0000-0000-000000000000 \\
    --rg my-resource-group \\
    --namespace my-servicebus \\
    --queue my-queue \\
    --interval 5
        """,
    )
    parser.add_argument("--subscription", "--sub", required=True,
                        help="Azure subscription ID")
    parser.add_argument("--resource-group", "--rg", required=True,
                        help="Resource group containing the Service Bus namespace")
    parser.add_argument("--namespace", required=True,
                        help="Service Bus namespace name")
    parser.add_argument("--queue", default=None,
                        help="Queue name to monitor")
    parser.add_argument("--topic", default=None,
                        help="Topic name to monitor")
    parser.add_argument("--sub-name", dest="sub_name", default=None,
                        help="Topic subscription name (required with --topic)")
    parser.add_argument("--interval", type=float, default=3,
                        help="Poll interval in seconds (default: 3)")
    args = parser.parse_args()

    if args.queue and args.topic:
        parser.error("Specify either --queue or --topic/--sub-name, not both.")
    if not args.queue and not args.topic:
        parser.error("Specify either --queue or --topic with --sub-name.")
    if args.topic and not args.sub_name:
        parser.error("--sub-name is required when using --topic.")

    if args.topic:
        entity_label = f"Topic: {args.topic}  Subscription: {args.sub_name}"
    else:
        entity_label = f"Queue: {args.queue}"

    prev_active = None
    history: deque = deque(maxlen=200)  # (active_count, timestamp) pairs; rate shown from 20, full window at 200
    backoff = 1.0          # multiplier; resets to 1.0 on any change
    BACKOFF_FACTOR = 1.5   # exponential growth factor per unchanged poll
    MAX_INTERVAL = 60.0    # hard cap in seconds

    while True:
        now = datetime.now()
        active, dead = get_counts(
            args.subscription, args.resource_group, args.namespace,
            args.queue, args.topic, args.sub_name
        )

        clear_screen()

        print("Azure Service Bus Monitor")
        print("-" * 40)
        print(f"Namespace: {args.namespace}")
        print(f"{entity_label}")
        print(f"Time: {now.strftime('%H:%M:%S')}")

        if isinstance(active, int):
            history.append((active, now))
            arrow, color, delta = get_trend(active, prev_active)

            # Adaptive interval: back off when idle, snap back on change
            if prev_active is not None and active == prev_active:
                backoff = min(backoff * BACKOFF_FACTOR, MAX_INTERVAL / args.interval)
            else:
                backoff = 1.0
            current_interval = args.interval * backoff

            delta_str = f"{delta:+}" if prev_active is not None else "N/A"
            rate_str = get_rate(history)
            rate_color = (
                Fore.RED if rate_str.startswith("+") and rate_str != "+0.00 msg/s"
                else Fore.GREEN if rate_str.startswith("-")
                else Fore.YELLOW
            )

            print(
                f"Active Messages: "
                f"{color}{active} ({delta_str}) {arrow}{Style.RESET_ALL}"
            )
            print(f"Dead Letters:    {dead}")
            n = len(history)
            poll_label = f"{n}/200 polls" if n < 200 else "200-poll window"
            print(
                f"Rate ({n}-poll):  "
                f"{rate_color}{rate_str}{Style.RESET_ALL}"
                f"  [{poll_label}]"
            )
            eta_str = get_eta(active, history)
            eta_color = Fore.GREEN if not eta_str.startswith("∞") and eta_str != "-" else Fore.YELLOW
            print(f"ETA to empty:    {eta_color}{eta_str}{Style.RESET_ALL}")
            interval_note = f"  (backing off ×{backoff:.1f})" if backoff > 1.0 else ""
            print(f"Poll interval:   {current_interval:.1f}s{interval_note}")

            prev_active = active

        else:
            current_interval = args.interval
            # error case
            print(Fore.RED + "Error fetching queue data:")
            print(dead)  # contains error message

        print("\nPress Ctrl+C to stop")
        time.sleep(current_interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")