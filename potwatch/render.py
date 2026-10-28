"""Render a check result as text, Prometheus exposition format, or a self-contained HTML page."""
from __future__ import annotations

import datetime as dt
import html

SEV_COLOR = {"ok": "#1a7f37", "info": "#0969da", "warn": "#9a6700", "crit": "#cf222e"}
SEV_NUM = {"ok": 0, "info": 0, "warn": 1, "crit": 2}


def _ts(ms: int | None) -> str:
    if not ms:
        return "n/a"
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def text(result: dict) -> str:
    s = result["snapshot"]["substrate"]
    lines = [f"[{result['overall'].upper()}] {result['snapshot']['network']} at {_ts(result['snapshot']['taken_at_ms'])}"]
    if s.get("ok"):
        lines.append(f"  chain={s['chain']} spec={s['spec']['name']}/{s['spec']['version']} best=#{s['best']} "
                     f"finalized=#{s['finalized']} head_time={_ts(s['head_timestamp_ms'])} peers={s['health']['peers']} "
                     f"validators={len(s['validators'])} rpc={s['latency_ms']:.0f}ms")
    h = result.get("history")
    if h and h.get("blocks", 0) > 1:
        bt = h["block_time_s"]
        lines.append(f"  last {h['blocks']} blocks: median {bt['median']} s, p95 {bt['p95']} s, max {bt['max']} s, "
                     f"slot fill {h['slot_fill_rate']}, authors " +
                     ", ".join(f"#{a['authority_index']}={a['blocks']}" for a in h["by_author"]))
    for x in result["findings"]:
        lines.append(f"  - {x['severity'].upper():4} {x['code']}: {x['message']}")
        if x.get("hint"):
            lines.append(f"         hint: {x['hint']}")
    return "\n".join(lines)


def prometheus(result: dict) -> str:
    net = result["snapshot"]["network"]
    lab = f'network="{net}"'
    s = result["snapshot"]["substrate"]
    out = [
        "# HELP potwatch_up 1 if the Substrate RPC answered.", "# TYPE potwatch_up gauge",
        f"potwatch_up{{{lab}}} {1 if s.get('ok') else 0}",
        "# HELP potwatch_status 0 ok, 1 warn, 2 crit.", "# TYPE potwatch_status gauge",
        f"potwatch_status{{{lab}}} {SEV_NUM[result['overall']]}",
    ]
    if s.get("ok"):
        age = (result["snapshot"]["taken_at_ms"] - s["head_timestamp_ms"]) / 1000
        for name, val, help_ in [
            ("best_block", s["best"], "Best block number."),
            ("finalized_block", s["finalized"], "Finalized block number."),
            ("finality_lag_blocks", s["best"] - s["finalized"], "Best minus finalized."),
            ("head_age_seconds", round(age, 1), "Seconds since the best block's timestamp."),
            ("peers", s["health"]["peers"], "Peers of the RPC node."),
            ("validators", len(s["validators"]), "Active session validators."),
            ("rpc_latency_ms", round(s["latency_ms"], 1), "Latency of system_chain."),
        ]:
            out += [f"# HELP potwatch_{name} {help_}", f"# TYPE potwatch_{name} gauge", f"potwatch_{name}{{{lab}}} {val}"]
    h = result.get("history")
    if h and h.get("blocks", 0) > 1:
        out += ["# HELP potwatch_block_time_median_seconds Median block interval in the sampled window.",
                "# TYPE potwatch_block_time_median_seconds gauge",
                f"potwatch_block_time_median_seconds{{{lab}}} {h['block_time_s']['median']}",
                "# HELP potwatch_authored_blocks Blocks authored per BABE authority in the sampled window.",
                "# TYPE potwatch_authored_blocks gauge"]
        for a in h["by_author"]:
            out.append(f'potwatch_authored_blocks{{{lab},authority="{a["authority"]}"}} {a["blocks"]}')
    for x in result["findings"]:
        out.append(f'potwatch_finding{{{lab},code="{x["code"]}",severity="{x["severity"]}"}} 1')
    return "\n".join(out) + "\n"


def _bars(values: list[float], width: int = 640, height: int = 120, color: str = "#0969da") -> str:
    if not values:
        return ""
    vmax = max(values) or 1
    bw = width / len(values)
    rects = "".join(
        f'<rect x="{i*bw:.2f}" y="{height - v/vmax*height:.2f}" width="{max(bw-0.5, 0.5):.2f}" '
        f'height="{v/vmax*height:.2f}" fill="{color}"><title>{v:.1f}s</title></rect>' for i, v in enumerate(values))
    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">{rects}</svg>'


def html_page(results: list[dict], intervals: dict[str, list[float]] | None = None) -> str:
    intervals = intervals or {}
    cards = []
    for r in results:
        s = r["snapshot"]["substrate"]
        color = SEV_COLOR[r["overall"]]
        rows = "".join(
            f'<tr><td style="color:{SEV_COLOR[x["severity"]]};font-weight:600">{x["severity"].upper()}</td>'
            f'<td><code>{html.escape(x["code"])}</code></td><td>{html.escape(x["message"])}'
            + (f'<br><small>{html.escape(x["hint"])}</small>' if x.get("hint") else "") + "</td></tr>"
            for x in r["findings"])
        stats = ""
        if s.get("ok"):
            stats = (f"<p>chain <b>{html.escape(s['chain'])}</b> · spec {html.escape(str(s['spec']['name']))}/{s['spec']['version']} · "
                     f"best <b>#{s['best']}</b> · finalized <b>#{s['finalized']}</b> · head time {_ts(s['head_timestamp_ms'])} · "
                     f"peers {s['health']['peers']} · validators {len(s['validators'])} · RPC {s['latency_ms']:.0f} ms</p>")
        h = r.get("history")
        hist = ""
        if h and h.get("blocks", 0) > 1:
            bt = h["block_time_s"]
            authors = "".join(f"<li><code>{html.escape(a['authority'])}</code>: {a['blocks']} blocks ({a['share']*100:.1f}%)</li>"
                              for a in h["by_author"])
            hist = (f"<h3>Last {h['blocks']} blocks (#{h['from_block']}–#{h['to_block']})</h3>"
                    f"<p>block time median {bt['median']} s · p95 {bt['p95']} s · max {bt['max']} s · slot fill {h['slot_fill_rate']} "
                    f"· missed slots {h['slots_missed']}</p>"
                    + _bars(intervals.get(r["snapshot"]["network"], [])) + f"<ul>{authors}</ul>")
        cards.append(f'<section style="border-left:6px solid {color};padding:0 1em;margin:1.5em 0">'
                     f'<h2>{html.escape(r["snapshot"]["network"])} <span style="color:{color}">{r["overall"].upper()}</span></h2>'
                     f'<p><small>checked {_ts(r["snapshot"]["taken_at_ms"])}</small></p>{stats}'
                     f'<table cellpadding="6" style="border-collapse:collapse">{rows}</table>{hist}</section>')
    return ("<!doctype html><html><head><meta charset='utf-8'><title>potwatch</title>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;padding:0 1em;color:#1f2328}"
            "td{border-top:1px solid #d0d7de;vertical-align:top}code{font-size:.9em}</style></head><body>"
            "<h1>potwatch · Portaldot network health</h1>"
            "<p>Read-only checks against public RPC endpoints. No keys, no transactions.</p>"
            + "".join(cards) + "</body></html>")
