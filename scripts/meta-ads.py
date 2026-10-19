#!/usr/bin/env python3
"""Check and manage the Iguana Comedy Meta ads account from the command line.

Operator tool, run by hand from the dev box. It reads the system-user token from
~/.credentials/meta/iguanacomedy/token (never from the repo, never from config.py: no deployed
service calls this). Set META_TOKEN_FILE to point somewhere else.

    scripts/meta-ads.py status                 account standing, money, what is actually delivering
    scripts/meta-ads.py campaigns --days 90    campaigns that spent in the window, with cost per result
    scripts/meta-ads.py daily --days 30        spend per day
    scripts/meta-ads.py pixels                 pixels and when each last received an event
    scripts/meta-ads.py pause <campaign_id>    pause a campaign (asks first unless --yes)
    scripts/meta-ads.py resume <campaign_id>   set a campaign back to ACTIVE (asks first unless --yes)

"Active" in Meta's UI does not mean spending: a campaign stays ACTIVE forever while its ad sets
ran out of schedule years ago. `status` reports what is *delivering*, meaning an ad set that is
active and whose end_time has not passed, and it cross-checks that against real spend.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://graph.facebook.com/v21.0"
AD_ACCOUNT = "act_178760798664478"          # IGUANA, MXN, business IguanaComedy
PAGE_ID = "122106930026005410"              # Iguana Comedy Productions
INSTAGRAM_ID = "17841461594533193"          # @iguanacomedy
TOKEN_FILE = os.environ.get("META_TOKEN_FILE", "~/.credentials/meta/iguanacomedy/token")

# Meta reports money in the account currency's minor unit for budgets, but insights come back as
# decimal strings. Budgets are centavos here because the account is MXN.
CENTAVOS = 100


def token() -> str:
    path = pathlib.Path(TOKEN_FILE).expanduser()
    try:
        value = path.read_text().strip()
    except OSError as exc:
        # Fail loudly: an empty token turns every call into an opaque 190 instead of naming the cause.
        sys.exit(f"cannot read the Meta token from {path}: {exc}")
    if not value:
        sys.exit(f"{path} is empty; put the system-user token there (chmod 600)")
    return value


def get(path: str, **params) -> dict:
    params["access_token"] = token()
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            message = json.loads(body)["error"]["message"]
        except Exception:
            message = body[:300]
        sys.exit(f"Graph API {exc.code} on {path}: {message}")


def post(path: str, **params) -> dict:
    params["access_token"] = token()
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", data=data), timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            message = json.loads(body)["error"]["message"]
        except Exception:
            message = body[:300]
        sys.exit(f"Graph API {exc.code} on {path}: {message}")


def pages(path: str, **params):
    """Yield every row across Graph's cursor pagination."""
    params.setdefault("limit", 100)
    while True:
        payload = get(path, **params)
        yield from payload.get("data", [])
        after = payload.get("paging", {}).get("cursors", {}).get("after")
        if not after or "next" not in payload.get("paging", {}):
            return
        params["after"] = after


def money(value) -> str:
    return f"{float(value or 0):,.2f}"


def window(days: int) -> str:
    until = dt.date.today()
    since = until - dt.timedelta(days=days)
    return json.dumps({"since": since.isoformat(), "until": until.isoformat()})


def results_of(row: dict) -> tuple[str, int, float]:
    """Pick the result Meta itself would show: purchases, then leads, then link clicks."""
    actions = {a["action_type"]: int(float(a["value"])) for a in row.get("actions", [])}
    costs = {c["action_type"]: float(c["value"]) for c in row.get("cost_per_action_type", [])}
    for key in ("purchase", "onsite_conversion.purchase", "lead", "link_click"):
        if actions.get(key):
            return key, actions[key], costs.get(key, 0.0)
    return "none", 0, 0.0


def cmd_status(args) -> None:
    account = get(
        AD_ACCOUNT,
        fields="name,account_status,disable_reason,currency,funding_source_details,spend_cap,amount_spent,min_daily_budget",
    )
    funding = account.get("funding_source_details") or {}
    standing = {1: "ACTIVE", 2: "DISABLED", 3: "UNSETTLED", 7: "PENDING_RISK_REVIEW", 9: "IN_GRACE_PERIOD", 101: "CLOSED"}
    print(f"account   {account['name']} ({AD_ACCOUNT}) {account['currency']}")
    state = standing.get(account["account_status"], account["account_status"])
    if account.get("disable_reason"):
        state += f", disable_reason={account['disable_reason']}"
    print(f"standing  {state}")
    print(f"paying    {funding.get('display_string', 'NO PAYMENT METHOD')}")
    print(f"spent     {money(int(account['amount_spent']) / CENTAVOS)} lifetime"
          f"   min daily budget {money(int(account['min_daily_budget']) / CENTAVOS)}")

    print("\nspend")
    for label, days in (("today", 0), ("last 7 days", 7), ("last 30 days", 30)):
        rows = get(AD_ACCOUNT + "/insights", time_range=window(days), fields="spend,impressions,clicks").get("data", [])
        if not rows:
            print(f"  {label:13} nothing delivered")
            continue
        row = rows[0]
        print(f"  {label:13} {money(row.get('spend')):>10}   impressions {int(row.get('impressions', 0)):>8,}"
              f"   clicks {int(row.get('clicks', 0)):>6,}")

    today = dt.date.today().isoformat()
    live, expired, adless = [], 0, []
    for adset in pages(AD_ACCOUNT + "/adsets", fields="id,name,effective_status,end_time,campaign{name},"
                       "ads.limit(50){effective_status}", effective_status='["ACTIVE"]'):
        end = (adset.get("end_time") or "")[:10]
        ads = [ad["effective_status"] for ad in (adset.get("ads") or {}).get("data", [])]
        if end and end < today:
            expired += 1
        elif "ACTIVE" not in ads:
            # An ACTIVE ad set whose ads are all paused or in review spends nothing (2026-10-19: the English open
            # mic ran eight days like that while this line listed it as delivering).
            adless.append((adset, ads))
        else:
            live.append(adset)

    print(f"\ndelivering: {len(live)} ad set(s)")
    for adset in live:
        campaign = adset.get("campaign", {}).get("name", "")
        end = (adset.get("end_time") or "")[:10] or "no end date"
        print(f"  {adset['id']}  ends {end:11}  {campaign[:38]:38}  {adset['name'][:34]}")
    if expired:
        print(f"  ({expired} more ad set(s) say ACTIVE but their schedule already ended, so they spend nothing)")
    for adset, ads in adless:
        print(f"  NOT delivering: {adset['name'][:50]} is ACTIVE but has no active ad"
              f" ({', '.join(sorted(set(ads))) or 'no ads'})")


def cmd_campaigns(args) -> None:
    rows = get(
        AD_ACCOUNT + "/insights",
        level="campaign",
        time_range=window(args.days),
        fields="campaign_id,campaign_name,spend,impressions,clicks,ctr,cpc,actions,cost_per_action_type",
        limit=200,
    ).get("data", [])
    rows.sort(key=lambda r: -float(r.get("spend", 0)))
    if not rows:
        print(f"no campaign spent anything in the last {args.days} days")
        return
    total = sum(float(r["spend"]) for r in rows)
    print(f"{'spend':>10}  {'ctr':>5} {'cpc':>5}  {'result':>16}  {'cost/result':>11}  campaign")
    for row in rows:
        kind, count, cost = results_of(row)
        label = f"{count} {kind.replace('onsite_conversion.', '')}" if count else "-"
        print(f"{money(row['spend']):>10}  {row.get('ctr', '0')[:5]:>5} {row.get('cpc', '0')[:5]:>5}"
              f"  {label:>16}  {money(cost) if cost else '-':>11}  {row.get('campaign_name', '')[:40]}")
    print(f"{money(total):>10}  total over {args.days} days, {len(rows)} campaign(s) with delivery")


def cmd_daily(args) -> None:
    rows = get(AD_ACCOUNT + "/insights", time_range=window(args.days), time_increment=1,
               fields="spend,impressions,clicks,actions", limit=400).get("data", [])
    if not rows:
        print(f"nothing delivered in the last {args.days} days")
        return
    for row in rows:
        kind, count, _ = results_of(row)
        print(f"  {row['date_start']}  {money(row['spend']):>9}   impressions {int(row.get('impressions', 0)):>7,}"
              f"   clicks {int(row.get('clicks', 0)):>5,}   {count} {kind if count else ''}")
    print(f"  total {money(sum(float(r['spend']) for r in rows))} over {len(rows)} day(s) with delivery")


def cmd_pixels(args) -> None:
    for pixel in pages(AD_ACCOUNT + "/adspixels", fields="id,name,last_fired_time,creation_time"):
        fired = pixel.get("last_fired_time")
        if fired:
            age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(fired)).days
            state = f"last event {fired[:10]} ({age} days ago)"
        else:
            state = "NEVER received an event"
        print(f"  {pixel['id']}  {pixel.get('name', ''):24} {state}")


def _confirm(action: str, campaign_id: str, assume_yes: bool) -> None:
    campaign = get(campaign_id, fields="name,effective_status,daily_budget,lifetime_budget")
    print(f"{action} {campaign_id}: {campaign.get('name')} (now {campaign.get('effective_status')})")
    if assume_yes:
        return
    if input("type yes to continue: ").strip().lower() != "yes":
        sys.exit("cancelled")


def cmd_pause(args) -> None:
    _confirm("pause", args.campaign_id, args.yes)
    print(post(args.campaign_id, status="PAUSED"))


def cmd_resume(args) -> None:
    _confirm("resume", args.campaign_id, args.yes)
    print(post(args.campaign_id, status="ACTIVE"))
    print("note: a campaign only spends again if its ad sets' schedules have not already ended")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="account standing, spend, what is delivering").set_defaults(func=cmd_status)

    campaigns = sub.add_parser("campaigns", help="campaigns that spent, with cost per result")
    campaigns.add_argument("--days", type=int, default=90)
    campaigns.set_defaults(func=cmd_campaigns)

    daily = sub.add_parser("daily", help="spend per day")
    daily.add_argument("--days", type=int, default=30)
    daily.set_defaults(func=cmd_daily)

    sub.add_parser("pixels", help="pixels and when each last received an event").set_defaults(func=cmd_pixels)

    for name, handler, helptext in (("pause", cmd_pause, "pause a campaign"), ("resume", cmd_resume, "reactivate a campaign")):
        command = sub.add_parser(name, help=helptext)
        command.add_argument("campaign_id")
        command.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
        command.set_defaults(func=handler)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
