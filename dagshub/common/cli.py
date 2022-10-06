import sys
import click

import dagshub.auth
from dagshub.common import config


@click.group()
@click.option("--host", default=config.host, help="Hostname of DagsHub instance")
@click.pass_context
def cli(ctx, host):
    ctx.obj = {"host": host.strip("/")}


@cli.command()
@click.argument("project_root", default=".")
@click.option("--repo_url", help="URL of the repo hosted on DagsHub")
@click.option("--branch", help="Repository's branch")
@click.option("--username", help="User's username")
@click.option("--password", help="User's password")
@click.option(
    "--debug", default=False, type=bool, help="Run fuse in foreground"
)
@click.pass_context
def mount(ctx, **kwargs):
    """
    Mount a DagsHub Storage folder via FUSE
    """
    # Since pyfuse can crash on init-time, import it here instead of up top
    from dagshub.streaming import mount

    if not kwargs["debug"]:
        # Hide tracebacks of errors, display only error message
        sys.tracebacklimit = 0
    mount(**kwargs)


@cli.command()
@click.option("--token", help="Login using a specified token")
@click.option("--host", help="DagsHub instance to which you want to login")
@click.pass_context
def login(ctx, token, host):
    host = host or ctx.obj["host"]
    if token is not None:
        dagshub.auth.add_app_token(token, host)
        print("Token added successfully")
    else:
        dagshub.auth.add_oauth_token(host)
        print("OAuth token added")


@cli.command()
@click.argument("filename", help="Path the file you want to upload")
@click.argument("--target", help="Where should the file be saved inside the repository")
@click.option("--repo", help="Full name of DagsHub repository, i.e: nirbarazida/yolov6")
@click.option("--branch", help="Repository's branch")
@click.option("--username", help="Username")
@click.option("--password", help="Password or Token")
@click.pass_context
def upload(ctx, **kwargs):
    """
    Upload a single file using the upload API to any location on a DagsHub repository, including DVC directories.
    """
    from dagshub.upload import Repo
    repo = Repo("idonov8", "baby-yoda-segmentation-dataset", username="<username>" password="<access token OR password>")
    repo.upload(file="image.png", path="images/category1/my-new-image.png", "Added new image to category 1")

    if not kwargs["debug"]:
        # Hide tracebacks of errors, display only error message
        sys.tracebacklimit = 0
    mount(**kwargs)


if __name__ == "__main__":
    cli()
