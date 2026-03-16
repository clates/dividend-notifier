import requests
import os
from log_config import get_logger

log = get_logger("discord_notifier")

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
        if not webhook_url:
            log.warning(
                "DiscordNotifier initialised WITHOUT a webhook URL — all messages will be skipped"
            )
        else:
            log.debug("DiscordNotifier initialised (webhook URL configured)")

    def _post(self, payload):
        if not self.webhook_url:
            log.warning("Discord: No webhook URL configured — skipping post")
            return
        embed_title = payload.get("embeds", [{}])[0].get("title", "(no title)")
        log.info("Posting to Discord: %s", embed_title)
        try:
            r = requests.post(self.webhook_url, json=payload, timeout=10)
            if r.status_code in [200, 204]:
                log.info("Discord post successful (HTTP %d)", r.status_code)
            else:
                log.error("Discord post FAILED: HTTP %d — %s", r.status_code, r.text)
        except Exception as e:
            log.error("Discord post raised exception: %s", e)

    def send_daily_signal(
        self,
        date_str,
        summary,
        actions,
        holdings_detail,
        window_deltas,
        watching,
        upcoming,
        config,
    ):
        """
        Sends the full daily digest embed to Discord.

        Sections:
          1. Portfolio snapshot (description)
          2. Trades today — executed buys, sells, dividends received
          3. Deltas — tickers that newly entered or left the buy window
          4. Current positions — held tickers with unrealised PnL + days to next div
          5. Watching — in-window but not held (position cap or no cash)
          6. Upcoming ex-dates (next 14 days)
        """
        buys = actions.get("buys", [])
        sells = actions.get("sells", [])
        dividends = actions.get("dividends", [])
        newly_entered = window_deltas.get("newly_entered", [])
        newly_exited = window_deltas.get("newly_exited", [])
        max_pos = config["portfolio"].get("max_positions", 20)

        log.info(
            "Building daily digest for %s — buys=%d, sells=%d, divs=%d, "
            "new_entries=%d, exits=%d, watching=%d, upcoming=%d",
            date_str,
            len(buys),
            len(sells),
            len(dividends),
            len(newly_entered),
            len(newly_exited),
            len(watching),
            len(upcoming),
        )

        fields = []

        # ── Section 1: Trades today ──────────────────────────────────────
        if buys:
            lines = "\n".join(
                f"• **{b['ticker']}** — {b['shares']:.4f} sh @ ${b['price']:,.2f}"
                f" · div in {b['days_to_div']}d · cost ${b['cost']:,.2f}"
                for b in buys
            )
            fields.append({"name": "🟢 BOUGHT TODAY", "value": lines, "inline": False})

        if sells:
            lines = "\n".join(
                f"• **{s['ticker']}** — {s['shares']:.4f} sh"
                f" · PnL ${s['total_pnl']:+,.2f} ({s['total_pnl_pct']:+.1f}%)"
                for s in sells
            )
            fields.append({"name": "🔴 SOLD TODAY", "value": lines, "inline": False})

        if dividends:
            lines = "\n".join(
                f"• **{d['ticker']}** — ${d['amount']:,.2f}"
                f" (${d['per_share']:.4f}/sh × {d['shares']:.4f} sh)"
                for d in dividends
            )
            fields.append(
                {"name": "💰 DIVIDENDS RECEIVED", "value": lines, "inline": False}
            )

        if not buys and not sells and not dividends:
            fields.append(
                {
                    "name": "💤 No Trades Today",
                    "value": "No executions — see positions and deltas below.",
                    "inline": False,
                }
            )

        # ── Section 2: Window deltas ─────────────────────────────────────
        delta_lines = []
        if newly_entered:
            delta_lines.append(
                "**Entered window today:**\n"
                + "\n".join(f"• **{t}**" for t in newly_entered)
            )
        if newly_exited:
            delta_lines.append(
                "**Left window today:**\n" + "\n".join(f"• {t}" for t in newly_exited)
            )
        if delta_lines:
            fields.append(
                {
                    "name": "🔔 BUY WINDOW CHANGES",
                    "value": "\n\n".join(delta_lines),
                    "inline": False,
                }
            )
        else:
            fields.append(
                {
                    "name": "🔔 BUY WINDOW CHANGES",
                    "value": "No tickers entered or left the buy window today.",
                    "inline": False,
                }
            )

        # ── Section 3: Current positions ─────────────────────────────────
        if holdings_detail:
            # Sort by expected_exit ascending so soonest-to-exit is first
            sorted_holdings = sorted(
                holdings_detail,
                key=lambda h: h.get("expected_exit") or "9999-99-99",
            )
            pos_lines = "\n".join(
                f"• **{h['ticker']}** — {h['shares']:.4f} sh"
                f" · ex {h['exdiv_date'] or '?'}"
                f" · exit ≈{h['expected_exit'] or '?'}"
                f" · PnL ${h['unrealized_pnl']:+,.2f}"
                + (f" +div ${h['div_captured']:,.2f}" if h["div_captured"] else "")
                for h in sorted_holdings
            )
            fields.append(
                {
                    "name": f"📂 CURRENT POSITIONS ({len(holdings_detail)}/{max_pos})",
                    "value": pos_lines,
                    "inline": False,
                }
            )
        else:
            fields.append(
                {
                    "name": f"📂 CURRENT POSITIONS (0/{max_pos})",
                    "value": "No open positions.",
                    "inline": False,
                }
            )

        # ── Section 4: Watching (in window, not held) ────────────────────
        if watching:
            watch_lines = "\n".join(
                f"• **{w['ticker']}** — div in {w['days_to_div']}d"
                for w in watching[:10]
            )
            suffix = f"\n_…and {len(watching) - 10} more_" if len(watching) > 10 else ""
            fields.append(
                {
                    "name": "👀 WATCHING (in window, not held)",
                    "value": watch_lines + suffix,
                    "inline": False,
                }
            )

        # ── Section 5: Upcoming ex-dates ─────────────────────────────────
        if upcoming:
            up_lines = "\n".join(
                f"• **{u['ticker']}** — {u['days_to_div']}d"
                + (" ✓ held" if u["held"] else "")
                + (" 🎯 in window" if u["in_window"] and not u["held"] else "")
                for u in upcoming[:12]
            )
            suffix = f"\n_…and {len(upcoming) - 12} more_" if len(upcoming) > 12 else ""
            fields.append(
                {
                    "name": "📅 UPCOMING EX-DATES (next 14 days)",
                    "value": up_lines + suffix,
                    "inline": False,
                }
            )

        # ── Embed wrapper ────────────────────────────────────────────────
        pos_color = "green" if summary["return_pct"] >= 0 else "red"
        description = (
            f"**💼 Value:** ${summary['total_value']:,.2f}"
            f" · **{summary['return_pct']:+.2f}%** since inception\n"
            f"**💵 Cash:** ${summary['cash']:,.2f}"
            f" · **Positions:** {summary['holdings_count']}/{max_pos}"
            f" · **Invested:** ${summary['holdings_value']:,.2f}\n"
            f"📊 [Full Report](https://clates.github.io/dividend-analysis/signal/)"
        )

        embed = {
            "title": f"📈 Daily Digest — {date_str}",
            "description": description,
            "color": COLORS[pos_color],
            "fields": fields,
            "footer": {
                "text": (
                    f"B{config['strategy']['buy_before']}/"
                    f"S{config['strategy']['sell_after']}"
                    f" · LoyalDividendCapture · $200B+ universe"
                    f" · 5% per position · mirror at your own discretion"
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

        log.info(
            "Building weekly recap embed for %s — buys=%d, sells=%d, dividends=%d, "
            "week_pnl=$%.2f, week_div=$%.2f",
            week_str,
            len(buys),
            len(sells),
            len(dividends),
            week_pnl,
            week_div,
        )

        fields = []

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
