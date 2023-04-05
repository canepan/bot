import json
import os
from collections import defaultdict

import click
import requests


MY_ZONES = {
    "<zone.tld>": {
        "id": "<cloudflare_id>",
        "token": "<cloudflare_key>",
        "www.nicolacanepa.net": "<zone_id>",
        "data": {"type": "A", "name": "<fqdn>", "proxied": True, "ttl": 1},
    },
}


def show_records(cf_dict: dict):
    zones = defaultdict(list)
    for record in cf_dict["result"]:
        zones[record["zone_id"]].append({k: record[k] for k in ("id", "name", "type", "content")})
    click.echo(json.dumps(zones, indent=2))


@click.group()
@click.option("--zone", default="nicolacanepa.net")
@click.pass_context
def main(ctx, zone: str):
    ctx.ensure_object(dict)
    with open(os.path.join(os.environ["HOME"], ".cloudflare.cfg"), "r") as f:
        MY_ZONES.update(json.load(f))
    ctx.obj["zone"] = zone
    zone_id = MY_ZONES.get(zone, {}).get("id", None)
    ctx.obj["base_url"] = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    auth_token = MY_ZONES.get(zone, {}).get("token", None)
    ctx.obj["headers"] ={"Content-Type": "application/json", "Authorization": f"Bearer {auth_token}"}


@main.command("list")
@click.pass_context
def records(ctx):
    url = ctx.obj["base_url"]
    headers = ctx.obj["headers"]
    response = requests.get(url, headers=headers)
    response_json = response.json()
    if response_json["success"]:
        show_records(response_json)
    else:
        for message in ("errors", "messages"):
            click.echo(response_json[message])


@main.command()
@click.argument("ip_address")
@click.option("--fqdn", default=None)
@click.pass_context
def update(ctx, ip_address: str, fqdn: str):
    if fqdn is None:
        fqdn = f"www.{ctx.obj['zone']}"
    my_zone = MY_ZONES.get(ctx.obj["zone"], {})
    record_id = my_zone.get(fqdn, None)
    url = f"{ctx.obj['base_url']}/{record_id}"
    headers = ctx.obj["headers"]
    record_data = my_zone["data"].copy()
    record_data["content"] = ip_address
    response = requests.put(url, headers=headers, json=record_data)
    response_json = response.json()
    if response_json["success"]:
        show_records(response_json)
    else:
        for message in ("errors", "messages"):
            click.echo(response_json[message])


if __name__ == "__main__":
    main()