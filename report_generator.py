import pandas as pd
import os
from datetime import datetime
from jinja2 import Template


class ReportGenerator:
    def __init__(self, state_dir="state"):
        self.state_dir = state_dir

    def _base_styles(self):
        return """
        body { padding: 30px; background-color: #f8f9fa; font-family: sans-serif; }
        .metric-card { padding: 20px; background: white; border-radius: 10px; text-align: center;
                       box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #dee2e6; }
        .metric-value { font-size: 26px; font-weight: bold; color: #0d6efd; }
        .metric-label { font-size: 11px; color: #6c757d; text-transform: uppercase; font-weight: bold; }
        .card { margin-bottom: 20px; border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .buy-row { background-color: #d1e7dd !important; }
        .sell-row { background-color: #f8d7da !important; }
        .div-row { background-color: #e0f2fe !important; }
        th, td { text-align: left !important; }
        .badge-strategy { background-color: #6c757d; color: white; padding: 3px 8px;
                          border-radius: 4px; font-size: 12px; }
        """

    def generate_daily_html(
        self,
        date_str,
        summary,
        actions,
        upcoming_list,
        signal_log_path,
        holdings_detail=None,
    ):
        buys = actions.get("buys", [])
        sells = actions.get("sells", [])
        dividends = actions.get("dividends", [])

        # Recent trades table
        trades_html = ""
        if os.path.exists(signal_log_path):
            df_log = pd.read_csv(signal_log_path)
            recent = df_log.tail(50).iloc[::-1]
            trades_html = self._format_trades_table(recent)

        # Holdings table
        holdings_html = ""
        if holdings_detail:
            hdf = pd.DataFrame(holdings_detail)
            hdf = hdf.round(2)
            holdings_html = hdf.to_html(
                classes="table table-sm table-striped", index=False
            )

        return_color = "green" if summary["return_pct"] >= 0 else "red"

        template_str = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dividend Signal Feed</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>{{ styles }}</style>
        </head>
        <body>
            <div class="container">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <div>
                        <h1 class="mb-1">📈 Dividend Signal Feed</h1>
                        <span class="badge-strategy">B35/S45 · LoyalDividendCapture · IRA/401k</span>
                    </div>
                    <span class="text-muted small">Last updated: {{ date_str }}</span>
                </div>

                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="metric-card">
                            <div class="metric-label">Portfolio Value</div>
                            <div class="metric-value">${{ "{:,.2f}".format(summary.total_value) }}</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="metric-card">
                            <div class="metric-label">Total Return</div>
                            <div class="metric-value" style="color: {{ return_color }}">
                                {{ "{:+.2f}".format(summary.return_pct) }}%
                            </div>
                            <small class="text-muted">since {{ summary.inception_date }}</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="metric-card">
                            <div class="metric-label">Cash Reserves</div>
                            <div class="metric-value text-secondary">${{ "{:,.2f}".format(summary.cash) }}</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="metric-card">
                            <div class="metric-label">Positions</div>
                            <div class="metric-value">{{ summary.holdings_count }}<span class="text-muted fs-5">/20</span></div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header bg-primary text-white fw-bold">Today's Signals — {{ date_str }}</div>
                    <div class="card-body">
                        {% if buys or sells or dividends %}
                            {% if buys %}
                                <h6 class="text-success">🟢 BUY</h6>
                                <ul>{% for b in buys %}<li><strong>{{ b.ticker }}</strong> — Div in {{ b.days_to_div }} days · Allocate {{ b.alloc_pct }}% (~${{ "{:,.0f}".format(b.cost) }})</li>{% endfor %}</ul>
                            {% endif %}
                            {% if sells %}
                                <h6 class="text-danger">🔴 SELL</h6>
                                <ul>{% for s in sells %}<li><strong>{{ s.ticker }}</strong> — PnL: ${{ "{:+,.2f}".format(s.total_pnl) }} ({{ "{:+.1f}".format(s.total_pnl_pct) }}%)</li>{% endfor %}</ul>
                            {% endif %}
                            {% if dividends %}
                                <h6 class="text-info">💰 DIVIDENDS RECEIVED</h6>
                                <ul>{% for d in dividends %}<li><strong>{{ d.ticker }}</strong> — ${{ "{:,.2f}".format(d.amount) }} (${{ "%.4f"|format(d.per_share) }}/share × {{ d.shares }} shares)</li>{% endfor %}</ul>
                            {% endif %}
                        {% else %}
                            <p class="text-muted">😴 No actions required today. All positions are within their hold window.</p>
                        {% endif %}
                    </div>
                </div>

                <div class="row">
                    <div class="col-md-5">
                        <div class="card">
                            <div class="card-header bg-dark text-white">📅 Upcoming Dividends (7 days)</div>
                            <div class="card-body" style="max-height: 350px; overflow-y: auto;">
                                <ul class="list-group list-group-flush">
                                {% for item in upcoming %}<li class="list-group-item small">{{ item }}</li>{% endfor %}
                                </ul>
                            </div>
                        </div>
                    </div>
                    {% if holdings_html %}
                    <div class="col-md-7">
                        <div class="card">
                            <div class="card-header bg-secondary text-white">📂 Current Holdings</div>
                            <div class="card-body p-0" style="max-height: 350px; overflow-y: auto;">{{ holdings_html }}</div>
                        </div>
                    </div>
                    {% endif %}
                </div>

                <div class="card mt-4">
                    <div class="card-header bg-dark text-white">📋 Recent Transactions</div>
                    <div class="card-body p-0" style="max-height: 400px; overflow-y: auto;">{{ trades_html }}</div>
                </div>

                <p class="text-center text-muted small mt-4">
                    Virtual portfolio starting at ${{ "{:,.0f}".format(summary.initial_cash) }} · 
                    Strategy: B35/S45 Loyal Dividend Capture · 
                    Mirror trades at your own discretion · 5% allocation per position
                </p>
            </div>
        </body>
        </html>
        """
        t = Template(template_str)
        return t.render(
            styles=self._base_styles(),
            date_str=date_str,
            summary=type("S", (), summary)(),  # convert dict to object for dot access
            return_color=return_color,
            buys=buys,
            sells=sells,
            dividends=dividends,
            upcoming=upcoming_list,
            holdings_html=holdings_html,
            trades_html=trades_html,
        )

    def generate_weekly_html(
        self, week_str, summary, week_actions, next_week_preview, signal_log_path
    ):
        buys = week_actions.get("buys", [])
        sells = week_actions.get("sells", [])
        dividends = week_actions.get("dividends", [])

        week_pnl = sum(s.get("total_pnl", 0) for s in sells)
        week_div = sum(d.get("amount", 0) for d in dividends)

        trades_html = ""
        if os.path.exists(signal_log_path):
            df_log = pd.read_csv(signal_log_path)
            df_log["Date"] = pd.to_datetime(df_log["Date"])
            week_start = df_log["Date"].max() - pd.Timedelta(days=7)
            week_trades = df_log[df_log["Date"] >= week_start].iloc[::-1]
            trades_html = self._format_trades_table(week_trades)

        return_color = "green" if summary["return_pct"] >= 0 else "red"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Weekly Recap — {week_str}</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>{self._base_styles()}</style>
        </head>
        <body>
            <div class="container">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h1>📊 Weekly Recap</h1>
                    <span class="text-muted small">{week_str}</span>
                </div>

                <div class="row mb-4">
                    <div class="col-md-3"><div class="metric-card"><div class="metric-label">Portfolio Value</div><div class="metric-value">${summary["total_value"]:,.2f}</div></div></div>
                    <div class="col-md-3"><div class="metric-card"><div class="metric-label">Total Return</div><div class="metric-value" style="color: {return_color}">{summary["return_pct"]:+.2f}%</div></div></div>
                    <div class="col-md-3"><div class="metric-card"><div class="metric-label">Week Realised PnL</div><div class="metric-value" style="color: {"green" if week_pnl >= 0 else "red"}">${week_pnl:+,.2f}</div></div></div>
                    <div class="col-md-3"><div class="metric-card"><div class="metric-label">Dividends This Week</div><div class="metric-value text-info">${week_div:,.2f}</div></div></div>
                </div>

                <div class="row">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header bg-primary text-white">Week Summary</div>
                            <div class="card-body">
                                <p>Trades: <strong>{len(buys) + len(sells)}</strong> ({len(buys)} buys, {len(sells)} sells)</p>
                                <p>Dividends collected: <strong>${week_div:,.2f}</strong></p>
                                <p>Realised PnL from sells: <strong>${week_pnl:+,.2f}</strong></p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header bg-dark text-white">🗓 Next Week Preview</div>
                            <div class="card-body">
                                <ul class="list-group list-group-flush">
                                {"".join(f"<li class='list-group-item small'>{item}</li>" for item in next_week_preview)}
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card mt-4">
                    <div class="card-header bg-secondary text-white">Transactions This Week</div>
                    <div class="card-body p-0">{trades_html}</div>
                </div>
            </div>
        </body>
        </html>
        """
        return html

    def _format_trades_table(self, df):
        """Renders a trades DataFrame as a color-coded HTML table."""
        if df.empty:
            return "<p class='text-muted p-3'>No transactions yet.</p>"

        rows = []
        for _, row in df.iterrows():
            action = row.get("Action", "")
            if action == "BUY":
                cls = "buy-row"
            elif action == "SELL":
                cls = "sell-row"
            elif action == "DIVIDEND":
                cls = "div-row"
            else:
                cls = ""

            def fmt(val):
                if pd.isnull(val):
                    return "-"
                if isinstance(val, float):
                    return f"${val:,.2f}"
                return str(val)

            cells = "".join(f"<td>{fmt(v)}</td>" for v in row)
            rows.append(f"<tr class='{cls}'>{cells}</tr>")

        headers = "".join(f"<th>{c}</th>" for c in df.columns)
        return (
            f'<table class="table table-sm table-hover" style="font-size: 12px;">'
            f'<thead class="table-dark"><tr>{headers}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table>"
        )
