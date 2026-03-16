import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from log_config import get_logger

log = get_logger("email_notifier")


class EmailNotifier:
    def __init__(self):
        self.host = os.environ.get("SMTP_HOST", "")
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")
        to_raw = os.environ.get("SMTP_TO", "")
        self.recipients = [r.strip() for r in to_raw.split(",") if r.strip()]

        if not all([self.host, self.user, self.password, self.recipients]):
            log.warning(
                "EmailNotifier: missing SMTP config — emails will be skipped "
                "(need SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_TO)"
            )
        else:
            log.debug(
                "EmailNotifier initialised: host=%s:%d user=%s recipients=%s",
                self.host,
                self.port,
                self.user,
                self.recipients,
            )

    def _configured(self):
        return all([self.host, self.user, self.password, self.recipients])

    # ------------------------------------------------------------------
    # HTML builder
    # ------------------------------------------------------------------

    def _render_html(
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
        buys = actions.get("buys", [])
        sells = actions.get("sells", [])
        dividends = actions.get("dividends", [])
        newly_entered = window_deltas.get("newly_entered", [])
        newly_exited = window_deltas.get("newly_exited", [])
        max_pos = config["portfolio"].get("max_positions", 20)
        buy_before = config["strategy"]["buy_before"]
        sell_after = config["strategy"]["sell_after"]

        pos_color = "#2ecc71" if summary["return_pct"] >= 0 else "#e74c3c"
        accent = "#2c3e50"

        def section(title, body_html, title_color="#2c3e50"):
            return f"""
            <tr><td style="padding:18px 24px 0">
              <p style="margin:0 0 8px;font-size:13px;font-weight:700;
                         text-transform:uppercase;letter-spacing:1px;
                         color:{title_color}">{title}</p>
              {body_html}
            </td></tr>
            <tr><td style="padding:0 24px">
              <hr style="border:none;border-top:1px solid #ecf0f1;margin:12px 0 0">
            </td></tr>
            """

        def pill(text, bg="#ecf0f1", fg="#2c3e50"):
            return (
                f'<span style="background:{bg};color:{fg};padding:2px 8px;'
                f'border-radius:12px;font-size:12px;font-weight:600">{text}</span>'
            )

        def row_style(i):
            return "background:#f9f9f9" if i % 2 == 0 else "background:#ffffff"

        # ── Header ──────────────────────────────────────────────────────
        header_html = f"""
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="padding:24px;background:{accent};border-radius:8px 8px 0 0">
              <p style="margin:0;font-size:20px;font-weight:700;color:#ffffff">
                📈 Daily Digest — {date_str}
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 24px;background:#f4f6f8;border-bottom:1px solid #dde1e5">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <p style="margin:0;font-size:22px;font-weight:700;color:{pos_color}">
                      ${summary["total_value"]:,.2f}
                      <span style="font-size:14px;color:{pos_color}">
                        {summary["return_pct"]:+.2f}% since inception
                      </span>
                    </p>
                  </td>
                </tr>
                <tr><td style="padding-top:6px">
                  <span style="font-size:13px;color:#666">
                    💵 Cash: <strong>${summary["cash"]:,.2f}</strong>
                    &nbsp;·&nbsp;
                    Positions: <strong>{summary["holdings_count"]}/{max_pos}</strong>
                    &nbsp;·&nbsp;
                    Invested: <strong>${summary["holdings_value"]:,.2f}</strong>
                  </span>
                </td></tr>
              </table>
            </td>
          </tr>
        </table>
        """

        sections_html = ""

        # ── Trades today ─────────────────────────────────────────────────
        if buys:
            rows = "".join(
                f"""<tr style="{row_style(i)}">
                  <td style="padding:6px 8px;font-weight:600">{b["ticker"]}</td>
                  <td style="padding:6px 8px">{b["shares"]:.4f} sh</td>
                  <td style="padding:6px 8px">${b["price"]:,.2f}</td>
                  <td style="padding:6px 8px">{b["days_to_div"]}d</td>
                  <td style="padding:6px 8px;font-weight:600">${b["cost"]:,.2f}</td>
                </tr>"""
                for i, b in enumerate(buys)
            )
            body = f"""
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="font-size:13px;border-collapse:collapse">
              <tr style="background:#d5f5e3;color:#1e8449">
                <th style="padding:6px 8px;text-align:left">Ticker</th>
                <th style="padding:6px 8px;text-align:left">Shares</th>
                <th style="padding:6px 8px;text-align:left">Price</th>
                <th style="padding:6px 8px;text-align:left">Div in</th>
                <th style="padding:6px 8px;text-align:left">Cost</th>
              </tr>
              {rows}
            </table>"""
            sections_html += section("🟢 Bought Today", body, "#1e8449")

        if sells:
            rows = "".join(
                f"""<tr style="{row_style(i)}">
                  <td style="padding:6px 8px;font-weight:600">{s["ticker"]}</td>
                  <td style="padding:6px 8px">{s["shares"]:.4f} sh</td>
                  <td style="padding:6px 8px;color:{"#1e8449" if s["total_pnl"] >= 0 else "#c0392b"};font-weight:600">
                    ${s["total_pnl"]:+,.2f}
                  </td>
                  <td style="padding:6px 8px">{s["total_pnl_pct"]:+.1f}%</td>
                </tr>"""
                for i, s in enumerate(sells)
            )
            body = f"""
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="font-size:13px;border-collapse:collapse">
              <tr style="background:#fadbd8;color:#922b21">
                <th style="padding:6px 8px;text-align:left">Ticker</th>
                <th style="padding:6px 8px;text-align:left">Shares</th>
                <th style="padding:6px 8px;text-align:left">PnL</th>
                <th style="padding:6px 8px;text-align:left">Return</th>
              </tr>
              {rows}
            </table>"""
            sections_html += section("🔴 Sold Today", body, "#922b21")

        if dividends:
            rows = "".join(
                f"""<tr style="{row_style(i)}">
                  <td style="padding:6px 8px;font-weight:600">{d["ticker"]}</td>
                  <td style="padding:6px 8px">{d["shares"]:.4f} sh</td>
                  <td style="padding:6px 8px">${d["per_share"]:.4f}/sh</td>
                  <td style="padding:6px 8px;font-weight:600;color:#1e8449">${d["amount"]:,.2f}</td>
                </tr>"""
                for i, d in enumerate(dividends)
            )
            body = f"""
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="font-size:13px;border-collapse:collapse">
              <tr style="background:#fef9e7;color:#9a7d0a">
                <th style="padding:6px 8px;text-align:left">Ticker</th>
                <th style="padding:6px 8px;text-align:left">Shares</th>
                <th style="padding:6px 8px;text-align:left">Per Share</th>
                <th style="padding:6px 8px;text-align:left">Received</th>
              </tr>
              {rows}
            </table>"""
            sections_html += section("💰 Dividends Received", body, "#9a7d0a")

        if not buys and not sells and not dividends:
            sections_html += section(
                "💤 No Trades Today",
                '<p style="margin:0;font-size:13px;color:#666">'
                "No executions — see positions and deltas below.</p>",
            )

        # ── Window deltas ────────────────────────────────────────────────
        delta_body = ""
        if newly_entered:
            pills = " ".join(pill(t, "#d6eaf8", "#1a5276") for t in newly_entered)
            delta_body += (
                f'<p style="margin:0 0 6px;font-size:12px;color:#666;font-weight:600">'
                f'ENTERED WINDOW</p><p style="margin:0 0 10px">{pills}</p>'
            )
        if newly_exited:
            pills = " ".join(pill(t, "#f2f3f4", "#555") for t in newly_exited)
            delta_body += (
                f'<p style="margin:0 0 6px;font-size:12px;color:#666;font-weight:600">'
                f'LEFT WINDOW</p><p style="margin:0">{pills}</p>'
            )
        if not delta_body:
            delta_body = (
                '<p style="margin:0;font-size:13px;color:#666">'
                "No tickers entered or left the buy window today.</p>"
            )
        sections_html += section("🔔 Buy Window Changes", delta_body)

        # ── Current positions ────────────────────────────────────────────
        if holdings_detail:
            sorted_h = sorted(
                holdings_detail,
                key=lambda h: h.get("expected_exit") or "9999-99-99",
            )
            rows = "".join(
                f"""<tr style="{row_style(i)}">
                  <td style="padding:6px 8px;font-weight:600">{h["ticker"]}</td>
                  <td style="padding:6px 8px">{h["shares"]:.4f}</td>
                  <td style="padding:6px 8px">{h.get("exdiv_date") or "?"}</td>
                  <td style="padding:6px 8px">{h.get("expected_exit") or "?"}</td>
                  <td style="padding:6px 8px;font-weight:600;
                     color:{"#1e8449" if h["unrealized_pnl"] >= 0 else "#c0392b"}">
                    ${h["unrealized_pnl"]:+,.2f}
                    {f"<span style='font-size:11px;color:#1e8449'> +div ${h['div_captured']:,.2f}</span>" if h["div_captured"] else ""}
                  </td>
                </tr>"""
                for i, h in enumerate(sorted_h)
            )
            body = f"""
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="font-size:13px;border-collapse:collapse">
              <tr style="background:#eaf2ff;color:#1a5276">
                <th style="padding:6px 8px;text-align:left">Ticker</th>
                <th style="padding:6px 8px;text-align:left">Shares</th>
                <th style="padding:6px 8px;text-align:left">Ex-Div</th>
                <th style="padding:6px 8px;text-align:left">Exit ≈</th>
                <th style="padding:6px 8px;text-align:left">PnL</th>
              </tr>
              {rows}
            </table>"""
        else:
            body = (
                '<p style="margin:0;font-size:13px;color:#666">No open positions.</p>'
            )
        sections_html += section(
            f"📂 Current Positions ({len(holdings_detail)}/{max_pos})", body
        )

        # ── Watching ─────────────────────────────────────────────────────
        if watching:
            pills = " ".join(
                pill(f"{w['ticker']} {w['days_to_div']}d", "#f0f0f0", "#333")
                for w in watching[:10]
            )
            suffix = (
                f'<span style="font-size:12px;color:#999"> '
                f"…and {len(watching) - 10} more</span>"
                if len(watching) > 10
                else ""
            )
            sections_html += section(
                "👀 Watching (in window, not held)",
                f'<p style="margin:0">{pills}{suffix}</p>',
            )

        # ── Upcoming ex-dates ────────────────────────────────────────────
        if upcoming:
            rows = "".join(
                f"""<tr style="{row_style(i)}">
                  <td style="padding:5px 8px;font-weight:600">{u["ticker"]}</td>
                  <td style="padding:5px 8px">{u["days_to_div"]}d</td>
                  <td style="padding:5px 8px">
                    {
                    pill("✓ held", "#d5f5e3", "#1e8449")
                    if u["held"]
                    else (
                        pill("🎯 in window", "#d6eaf8", "#1a5276")
                        if u["in_window"]
                        else ""
                    )
                }
                  </td>
                </tr>"""
                for i, u in enumerate(upcoming[:12])
            )
            body = f"""
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="font-size:13px;border-collapse:collapse">
              <tr style="background:#f4f6f8;color:#555">
                <th style="padding:5px 8px;text-align:left">Ticker</th>
                <th style="padding:5px 8px;text-align:left">Days</th>
                <th style="padding:5px 8px;text-align:left">Status</th>
              </tr>
              {rows}
            </table>"""
            sections_html += section("📅 Upcoming Ex-Dates (next 14 days)", body)

        # ── Footer ───────────────────────────────────────────────────────
        footer_html = f"""
        <tr><td style="padding:16px 24px;background:#f4f6f8;
                        border-radius:0 0 8px 8px;border-top:1px solid #dde1e5">
          <p style="margin:0;font-size:11px;color:#999;text-align:center">
            B{buy_before}/S{sell_after} · LoyalDividendCapture
            · $200B+ universe · 5% per position
            · Mirror at your own discretion
          </p>
        </td></tr>
        """

        # ── Assemble ─────────────────────────────────────────────────────
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f0f2f5;font-family:
             -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08)">
        <tr><td>{header_html}</td></tr>
        {sections_html}
        {footer_html}
      </table>
    </td></tr>
  </table>
</body>
</html>"""
        return html

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

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
        if not self._configured():
            log.warning("Email skipped — SMTP not configured")
            return

        log.info(
            "Sending daily digest email to %d recipient(s): %s",
            len(self.recipients),
            self.recipients,
        )

        html_body = self._render_html(
            date_str,
            summary,
            actions,
            holdings_detail,
            window_deltas,
            watching,
            upcoming,
            config,
        )

        subject_prefix = config.get("notifications", {}).get(
            "email_subject_prefix", "Dividend Digest"
        )
        ret_sign = "+" if summary["return_pct"] >= 0 else ""
        subject = (
            f"{subject_prefix} — {date_str} · "
            f"${summary['total_value']:,.0f} ({ret_sign}{summary['return_pct']:.2f}%)"
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = ", ".join(self.recipients)
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.host, self.port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.user, self.password)
                server.sendmail(self.user, self.recipients, msg.as_string())
            log.info("Email sent successfully: %s", subject)
        except Exception as e:
            log.error("Email send failed: %s", e)
