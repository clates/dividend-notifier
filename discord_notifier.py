import requests
import os


class DiscordNotifier:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send_daily_signal(self, date_str, summary, actions, upcoming):
        """Sends a formatted daily signal message."""
        if not self.webhook_url:
            print("No Discord webhook URL configured.")
            return

        # Format actions
        buys = [a for a in actions if "BUY" in a]
        sells = [a for a in actions if "SELL" in a]
        divs = [a for a in actions if "DIVIDEND" in a]

        description = f"**💼 Portfolio Value:** ${summary['total_value']:,.2f} ({summary['return_pct']:+.2f}%)\n"
        description += f"**💵 Cash Available:** ${summary['cash']:,.2f} | **Holdings:** {summary['holdings_count']}/20\n\n"

        if buys:
            description += (
                "🟢 **EXECUTE TODAY — BUY**\n"
                + "\n".join(f"• {b}" for b in buys)
                + "\n\n"
            )
        if sells:
            description += (
                "🔴 **EXECUTE TODAY — SELL**\n"
                + "\n".join(f"• {s}" for b in sells)
                + "\n\n"
            )
        if divs:
            description += (
                "💰 **DIVIDENDS RECEIVED**\n"
                + "\n".join(f"• {d}" for d in divs)
                + "\n\n"
            )

        if not (buys or sells or divs):
            description += "😴 *No actions required today.*\n\n"

        embed = {
            "title": f"📈 Dividend Signal — {date_str}",
            "description": description,
            "color": 3447003,  # Blue
            "fields": [
                {
                    "name": "📅 Upcoming Dividends (next 7 days)",
                    "value": "\n".join(upcoming[:10]) if upcoming else "None tracked",
                    "inline": False,
                }
            ],
            "footer": {
                "text": "Mirror these trades at your own discretion. Proportional allocation (5%) recommended."
            },
            "url": "https://clates.github.io/dividend-analysis/signal/",
        }

        payload = {"embeds": [embed]}
        try:
            requests.post(self.webhook_url, json=payload)
        except Exception as e:
            print(f"Error sending Discord notification: {e}")

    def send_weekly_recap(self, recap_data):
        # Implementation for weekly recap
        pass
