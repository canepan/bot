#!/mnt/opt/nicola/tools/bin/python
import json
import os
import typing
from collections import defaultdict

import click
import requests


MY_ZONES = {
    "<zone.tld>": {
        "id": "<zone_id>",
        "token": "<cloudflare_key>",
        "www.nicolacanepa.net": {"id": "<record_id>", "type": "A", "name": "<fqdn>", "proxied": True, "ttl": 1},
    },
}
TEMPLATE = {"type": "A", "proxied": False, "ttl": 1}


class Echo(object):
    def __init__(self, verbose: bool, quiet: bool):
        self.verbose = verbose
        self.quiet = quiet

    def info(self, *args, **kwargs):
        if not self.quiet:
            return click.echo(*args, **kwargs)

    def debug(self, *args, **kwargs):
        if self.verbose:
            return click.echo(*args, **kwargs)


def show_records(cf_dict: dict):
    zones = defaultdict(list)
    for record in cf_dict["result"]:
        zones[record["zone_id"]].append(
            {k: record[k] for k in ("id", "name", "type", "content", "comment") if record.get(k, None)}
        )
    click.echo(json.dumps(zones, indent=2))


@click.group()
@click.option("--zone", default="nicolacanepa.net")
@click.option("--verbose/--quiet", "-v/-q", default=None)
@click.pass_context
def main(ctx, zone: str, verbose: bool):
    ctx.ensure_object(dict)
    with open(os.path.join(os.environ["HOME"], ".cloudflare.cfg"), "r") as f:
        MY_ZONES.update(json.load(f))
    ctx.obj["zone"] = zone
    zone_id = MY_ZONES.get(zone, {}).get("id", None)
    ctx.obj["base_url"] = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    auth_token = MY_ZONES.get(zone, {}).get("token", None)
    ctx.obj["headers"] = {"Content-Type": "application/json", "Authorization": f"Bearer {auth_token}"}
    quiet = verbose is False
    verbose = verbose or False
    ctx.obj["echo"] = Echo(verbose=verbose, quiet=quiet)


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
            ctx.obj["echo"].info(response_json[message])


@main.command()
@click.argument("ip_address")
@click.option("--fqdns", "-F", default=None, multiple=True)
@click.option("--unsafe", "-U", is_flag=True, default=False)
@click.pass_context
def add(ctx, ip_address: str, fqdns: typing.Iterable[str], unsafe: bool):
    headers = ctx.obj["headers"]
    my_zone = MY_ZONES.get(ctx.obj["zone"], {})
    echo = ctx.obj["echo"]

    fqdns = fqdns or (f"www.{ctx.obj['zone']}",)

    for fqdn in fqdns:
        click.echo(fqdn)
        record_data = my_zone.get(fqdn, my_zone.get("template", TEMPLATE))
        url = f"{ctx.obj['base_url']}/"
        echo.debug(f"About to post {record_data}")
        record_data["content"] = ip_address
        record_data["name"] = fqdn
        if unsafe:
            response = requests.post(url, headers=headers, json=record_data)
            response_json = response.json()
            echo.debug(response_json)
            if response_json.get("success", False):
                echo.info(response_json["result"])
            else:
                for message in ("errors", "messages"):
                    echo.info(response_json[message])
        else:
            echo.info(f"Would PUT: {url}, with headers=(hidden), json={record_data}")


@main.command()
@click.argument("ip_address")
@click.option("--fqdns", "-F", default=None, multiple=True)
@click.option("--all-records", "-A", is_flag=True, default=False)
@click.option("--unsafe", "-U", is_flag=True, default=False)
@click.pass_context
def update(ctx, ip_address: str, fqdns: typing.Iterable[str], all_records: bool, unsafe: bool):
    headers = ctx.obj["headers"]
    my_zone = MY_ZONES.get(ctx.obj["zone"], {})
    echo = ctx.obj["echo"]

    if all_records:
        url = ctx.obj['base_url']
        response = requests.get(url, headers=headers).json()
        zones = defaultdict(list)
        for record in response["result"]:
            if record["comment"] == "Donomore":
                echo.debug(f"Adding {record['name']}")
                local_record = record.copy()
                my_zone[local_record["name"]] = local_record
                fqdns = fqdns + (local_record["name"],)
    else:
        fqdns = fqdns or (f"www.{ctx.obj['zone']}",)
        for fqdn in fqdns:
            echo.debug(f"Checking {fqdn}")
            record_id = my_zone[fqdn]["id"]
            url = f"{ctx.obj['base_url']}/{record_id}"
            response = requests.get(url, headers=headers).json()
            my_zone[fqdn] = response["result"][0]

    for fqdn in fqdns:
        click.echo(fqdn)
        record_data = my_zone[fqdn]
        click.echo(record_data)
        record_id = record_data["id"]
        url = f"{ctx.obj['base_url']}/{record_id}"
        if ip_address == record_data.get("content", None):
            echo.info(f"{fqdn} already points to {ip_address}")
            continue
        record_data["content"] = ip_address
        if unsafe:
            response = requests.put(url, headers=headers, json=record_data)
            response_json = response.json()
            if response_json["success"]:
                echo.info(response_json)
            else:
                for message in ("errors", "messages"):
                    echo.info(response_json[message])
        else:
            echo.info(f"Would PUT: {url}, with headers=(hidden), json={record_data}")


if __name__ == "__main__":
    main()
