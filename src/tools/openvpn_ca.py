import os
import click
import subprocess
import shutil

EASYRSA_DIR = os.getcwd()
PKI_DIR = os.path.join(EASYRSA_DIR, 'pki')

def run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, cwd=cwd or EASYRSA_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"Error: {result.stderr}")
        return False
    click.echo(result.stdout)
    return True

def menu(title, options):
    click.echo(f"\n=== {title} ===")
    for i, opt in enumerate(options, 1):
        click.echo(f"{i}) {opt[0]}")
    click.echo("0) Exit")
    return click.prompt("Select option", type=int, default=0)

@click.group()
def cli():
    pass

@cli.command()
def init():
    """Initialize EasyRSA PKI"""
    click.echo("Initializing PKI...")
    run_cmd("easyrsa init-pki")

@cli.command()
def build_ca():
    """Build root CA"""
    click.echo("Building root CA...")
    run_cmd("easyrsa build-ca")

@cli.command()
@click.option('--name', default='server', help='Common name for server certificate')
def gen_req(name):
    """Generate certificate request"""
    run_cmd(f"easyrsa gen-req {name}")

@cli.command()
@click.option('--name', default='server', help='Certificate common name')
def sign_req(name):
    """Sign a certificate request"""
    run_cmd(f"easyrsa sign-req {name}")

@cli.command()
def revoke():
    """Revoke a certificate"""
    name = click.prompt("Client name to revoke")
    run_cmd(f"easyrsa revoke {name}")
    run_cmd("easyrsa gen-crl")

@cli.command()
def list_certs():
    """List all certificates"""
    crl_file = os.path.join(PKI_DIR, 'crl.pem')
    if os.path.exists(crl_file):
        click.echo("CRL generated")
    
    keys_dir = os.path.join(PKI_DIR, 'private')
    if os.path.exists(keys_dir):
        click.echo("\nPrivate keys:")
        for f in os.listdir(keys_dir):
            if f.endswith('.key'):
                click.echo(f"  - {f}")

@cli.command()
@click.option('--name', default='client', help='Client name')
def build_client(name):
    """Build client certificate and config"""
    click.echo(f"Building client: {name}")
    run_cmd(f"easyrsa build-client-full {name}")

@cli.command()
def build_server():
    """Build server certificate"""
    run_cmd("easyrsa build-server-full server")

@cli.command()
def gen_dh():
    """Generate Diffie-Hellman parameters"""
    run_cmd("easyrsa gen-dh")

@cli.command()
def menu_mode():
    """Interactive menu mode"""
    while True:
        choice = menu("OpenVPN CA Management", [
            ("Initialize PKI", init),
            ("Build Root CA", build_ca),
            ("Generate DH Params", gen_dh),
            ("Build Server Cert", build_server),
            ("Build Client Cert", build_client),
            ("Sign Request", sign_req),
            ("Revoke Certificate", revoke),
            ("List Certificates", list_certs),
        ])
        
        if choice == 0:
            click.echo("Goodbye!")
            break
        elif 1 <= choice <= 8:
            options = [
                ("Initialize PKI", ["init"]),
                ("Build Root CA", ["build-ca"]),
                ("Generate DH Params", ["gen-dh"]),
                ("Build Server Cert", ["build-server-full", "server"]),
                (lambda: click.prompt("Client name", default="client"), ["build-client-full"]),
                (lambda: click.prompt("Common name", default="client"), ["sign-req"]),
                (lambda: click.prompt("Client to revoke", default="client"), ["revoke"]),
                ("List Certificates", ["list-certs"]),
            ]
            opt = options[choice - 1]
            if callable(opt[0]):
                name = opt[0]()
                run_cmd(f"easyrsa {opt[1][0]} {name}")
            else:
                if len(opt) == 2 and isinstance(opt[1], list):
                    cmd = f"easyrsa {opt[1][0]}"
                    if len(opt[1]) > 1:
                        cmd += f" {opt[1][1]}"
                    run_cmd(cmd)

if __name__ == '__main__':
    cli()