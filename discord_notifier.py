import requests
import os

COLORS = {
    "blue": 3447003,
    "green": 3066993,
    "orange": 15158332,
    "red": 15548997,
    "purple": 10181046,
}


class DiscordNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def _post(self, payload):
        if not self.webhook_url:
            print("Discord: No webhook URL configured — skipping.")
            return
        try:
            r = requests.post(self.webhook_url, json=payload, timeout=10)
            if r.status_code not in [200, 204]:
                print(f"Discord error: {r.status_code} {r.text}")
        except Exception as e:
            print(f"Discord exception: {e}")

    def send_daily_signal(self, date_str, summary, actions, upcoming_list):
        """
        Sends a rich embedded daily signal message to Discord.
        actions: dict with keys 'buys', 'sells', 'dividends'
        """
        buys = actions.get("buys", [])
        sells = actions.get("sells", [])
        dividends = actions.get("dividends", [])

        fields = []

        if buys:
            buy_lines = "\n".join(
                f"• **{b['ticker']}** — Div in {b['days_to_div']}d · {b['alloc_pct']:.0f}% · ${b['cost']:,.0f}"
                for b in buys
            )
            fields.append({"name": "🟢 BUY TODAY", "value": buy_lines, "inline": False})

        if sells:
            sell_lines = "\n".join(
                f"• **{s['ticker']}** — PnL: ${s['total_pnl']:+,.2f} ({s['total_pnl_pct']:+.1f}%)"
                for s in sells
            )
            fields.append(
                {"name": "🔴 SELL TODAY", "value": sell_lines, "inline": False}
            )

        if dividends:
            div_lines = "\n".join(
                f"• **{d['ticker']}** — ${d['amount']:,.2f} (${d['per_share']:.4f}/share × {d['shares']} shares)"
                for d in dividends
            )
            fields.append(
                {"name": "💰 DIVIDENDS RECEIVED", "value": div_lines, "inline": False}
            )

        if not (buys or sells or dividends):
            fields.append(
                {
                    "name": "😴 No Actions Today",
                    "value": "All positions are in their hold window. No trades required.",
                    "inline": False,
                }
            )

        if upcoming_list:
            fields.append(
                {
                    "name": "📅 Upcoming (next 7 days)",
                    "value": "\n".join(f"• {u}" for u in upcoming_list[:8]),
                    "inline": False,
                }
            )

        return_color = "green" if summary["return_pct"] >= 0 else "red"

        description = (
            f"**💼 Portfolio:** ${summary['total_value']:,.2f} "
            f"(**{summary['return_pct']:+.2f}%** since inception)\n"
            f"**💵 Cash:** ${summary['cash']:,.2f}  |  "
            f"**Positions:** {summary['holdings_count']}/20\n"
            f"📊 [Full Report](https://clates.github.io/dividend-analysis/signal/)"
        )

        embed = {
            "title": f"📈 Dividend Signal — {date_str}",
            "description": description,
            "color": COLORS["green"] if summary["return_pct"] >= 0 else COLORS["red"],
            "fields": fields,
            "footer": {
                "text": (
                    "Virtual portfolio starting at $10,000 · B35/S45 strategy · "
                    "Mirror at your own discretion · 5% allocation per position"
                )
            },
        }
        self._post({"embeds": [embed]})

    def send_weekly_recap(self, week_str, summary, week_actions, next_week_preview):
        """
        Sends a weekly recap message every Saturday.
        """
        buys = week_actions.get("buys", [])
        sells = week_actions.get("sells", [])
        dividends = week_actions.get("dividends", [])

        week_pnl = sum(s["total_pnl"] for s in sells)
        week_div = sum(d["amount"] for d in dividends)

        fields = []

        # Week summary stats
        fields.append(
            {
                "name": "📊 Week in Numbers",
                "value": (
                    f"Trades: {len(buys) + len(sells)} ({len(buys)} buys, {len(sells)} sells)\n"
                    f"Dividends Received: ${week_div:,.2f}\n"
                    f"Realised PnL: ${week_pnl:+,.2f}"
                ),
                "inline": False,
            }
        )

        if sells:
            sell_lines = "\n".join(
                f"• **{s['ticker']}** — ${s['total_pnl']:+,.2f} ({s['total_pnl_pct']:+.1f}%)"
                for s in sells
            )
            fields.append(
                {"name": "🔴 Closed This Week", "value": sell_lines, "inline": False}
            )

        if next_week_preview:
            fields.append(
                {
                    "name": "🗓 Next Week Preview",
                    "value": "\n".join(f"• {item}" for item in next_week_preview[:10]),
                    "inline": False,
                }
            )

        embed = {
            "title": f"📊 Weekly Recap — {week_str}",
            "description": (
                f"**💼 Portfolio:** ${summary['total_value']:,.2f} "
                f"(**{summary['return_pct']:+.2f}%** since inception)\n"
                f"📊 [Full Report](https://clates.github.io/dividend-analysis/signal/)"
            ),
            "color": COLORS["purple"],
            "fields": fields,
            "footer": {
                "text": "Virtual portfolio · B35/S45 · Mirror at your own discretion"
            },
        }
        self._post({"embeds": [embed]})
