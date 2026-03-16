import pandas as pd
import os
import json
from jinja2 import Template


class ReportGenerator:
    def __init__(self, state_dir="state"):
        self.state_dir = state_dir

    def generate_daily_html(
        self, date_str, summary, actions, upcoming, signal_log_path
    ):
        # Load full history for charting
        df_log = pd.read_csv(signal_log_path)
        # We need to compute an equity curve from the log if we want to show it.
        # For simplicity in this first version, we'll just show current status and recent trades.

        recent_trades = df_log.tail(50).iloc[::-1]
        trades_html = recent_trades.to_html(
            classes="table table-striped table-hover", index=False
        )

        template_str = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Live Dividend Signals</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 30px; background-color: #f8f9fa; }
                .card { margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: none; }
                .metric-card { text-align: center; padding: 20px; background: white; border-radius: 10px; }
                .metric-value { font-size: 28px; font-weight: bold; color: #0d6efd; }
                .buy-row { background-color: #d1e7dd !important; }
                .sell-row { background-color: #f8d7da !important; }
                .div-row { background-color: #e0f2fe !important; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="mb-4">📈 Dividend Strategy Signal Feed</h1>
                
                <div class="row mb-4">
                    <div class="col-md-4">
                        <div class="card metric-card">
                            <div class="text-muted small text-uppercase fw-bold">Portfolio Value</div>
                            <div class="metric-value">${{ "{:,.2f}".format(summary['total_value']) }}</div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card metric-card">
                            <div class="text-muted small text-uppercase fw-bold">Total Return</div>
                            <div class="metric-value" style="color: {{ 'green' if summary['return_pct'] >= 0 else 'red' }}">
                                {{ "{:+.2f}".format(summary['return_pct']) }}%
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card metric-card">
                            <div class="text-muted small text-uppercase fw-bold">Cash Reserves</div>
                            <div class="metric-value text-secondary">${{ "{:,.2f}".format(summary['cash']) }}</div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header bg-primary text-white">Today's Signals ({{ date_str }})</div>
                    <div class="card-body">
                        {% if actions %}
                            <ul class="list-group">
                            {% for action in actions %}
                                <li class="list-group-item">{{ action }}</li>
                            {% endfor %}
                            </ul>
                        {% else %}
                            <p class="text-muted">No actions required today.</p>
                        {% endif %}
                    </div>
                </div>

                <div class="row">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header bg-dark text-white">Upcoming Dividends (7 Days)</div>
                            <div class="card-body" style="max-height: 400px; overflow-y: auto;">
                                <ul class="list-group list-group-flush">
                                {% for item in upcoming %}
                                    <li class="list-group-item small">{{ item }}</li>
                                {% endfor %}
                                </ul>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header bg-secondary text-white">Recent Transactions</div>
                            <div class="card-body p-0" style="max-height: 400px; overflow-y: auto;">
                                {{ trades_html }}
                            </div>
                        </div>
                    </div>
                </div>

                <div class="text-center mt-4 text-muted small">
                    <p>This is a virtual portfolio starting at $10,000 on 2026-03-16.<br>
                    Strategy: Loyal Dividend Capture (B35/S45)</p>
                </div>
            </div>
        </body>
        </html>
        """

        template = Template(template_str)
        return template.render(
            date_str=date_str,
            summary=summary,
            actions=actions,
            upcoming=upcoming,
            trades_html=trades_html,
        )
