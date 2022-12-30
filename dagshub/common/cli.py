import os
import sys
import tempfile

import click
import logging
import git
import zipfile
import tarfile
from pathlib import Path
from os.path import exists
from http import HTTPStatus
from urllib.parse import urlparse

import dagshub.auth
import dagshub.common.logging
from dagshub.common import config
from dagshub.upload import create_repo
from dagshub.auth.token_auth import HTTPBearerAuth
from dagshub.common.helpers import http_request, get_project_root
from dagshub.upload.wrapper import add_dataset_to_repo, DEFAULT_DATA_DIR_NAME


@click.group()
@click.option("--host", default=config.host, help="Hostname of DagsHub instance")
@click.pass_context
def cli(ctx, host):
    dagshub.common.logging.init_logger()
    ctx.obj = {"host": host.strip("/")}


@cli.command()
@click.argument("project_root", default=".")
@click.option("--repo_url", help="URL of the repo hosted on DagsHub")
@click.option("--branch", help="Repository's branch")
@click.option("-v", "--verbose", default=0, count=True, help="Verbosity level")
@click.option(
    "--debug", default=False, type=bool, help="Run fuse in foreground"
)
# todo: add log level
@click.pass_context
def mount(ctx, verbose, **kwargs):
    """
    Mount a DagsHub Storage folder via FUSE
    """
    # Since pyfuse can crash on init-time, import it here instead of up top
    from dagshub.streaming import mount

    logger = logging.getLogger()
    logger.setLevel(to_log_level(verbose))

    if not kwargs["debug"]:
        # Hide tracebacks of errors, display only error message
        sys.tracebacklimit = 0
    mount(**kwargs)


@cli.command()
@click.option("--repo_name", help="The repository name to set up")
@click.option("--repo_owner", help="The organization under which the repository needs to be set up")
@click.option("--url", help="DagsHub remote url; either provide --url or repo_name and repo_owner")
@click.option("--host", default=config.DEFAULT_HOST, help="DagsHub instance to which you want to login")
@click.option("--mlflow", default=True, is_flag=True, help="Set up MLFlow environment with DagsHub remote")
@click.option("--dvc", default=False, is_flag=True, help="Set up DVC with DagsHub remote")
@click.pass_context
def init(ctx, repo_name, repo_owner, url, host, mlflow, dvc):
    _init(repo_name, repo_owner, url, host, mlflow, dvc)


def _init(repo_name=None, repo_owner=None, url=None, root=None,
          host=config.DEFAULT_HOST, mlflow=True, dvc=False):
    from ..upload.wrapper import create_repo
    import urllib

    # Setup required variables
    root = root or get_project_root(Path(os.path.abspath('.')))

    if url and (repo_name or repo_owner):
        repo_name, repo_owner = None, None

    if not url:
        if repo_name is not None and repo_owner is not None:
            url = urllib.parse.urljoin(host, f'{repo_owner}/{repo_name}')
        else:
            with open(root / '.git' / 'config', 'r') as cfg:
                for line in cfg.readlines():
                    if host in line:
                        url = line.split()[-1][:-4]
                        break
    elif url[-4] == '.':
        url = url[:-4]

    if not (repo_name and repo_owner):
        splitter = lambda x: (x[-1], x[-2])
        repo_name, repo_owner = splitter(url.split('/'))

    if None in [repo_name, repo_owner, url]:
        raise ValueError('Host not found; please specify the remote url with --url')

    # Setup authentication
    username = config.username
    password = config.password
    if username is not None and password is not None:
        auth = username, password
    else:
        token = config.token or dagshub.auth.get_token()
        if token is not None:
            auth = token, token
            bearer = HTTPBearerAuth(token)

    # Configure repository
    res = http_request("GET", urllib.parse.urljoin(host, config.REPO_INFO_URL.format(
        owner=repo_owner,
        reponame=repo_name)), auth=bearer or auth)
    if res.status_code == 404:
        create_repo(repo_name)

    # Configure MLFlow
    if mlflow:
        os.environ['MLFLOW_TRACKING_URI'] = f'{url}.mlflow'
        os.environ['MLFLOW_TRACKING_USERNAME'] = auth[0]
        os.environ['MLFLOW_TRACKING_PASSWORD'] = auth[1]

    # Configure DVC
    if dvc:
        remote = 'origin'
        flag = exists(root / '.dvc' / 'config')
        Path(root / '.dvc').mkdir(parents=True, exist_ok=True)
        with open(root / '.dvc' / 'config', 'a+') as cfg, open(root / '.dvc' / 'config.local', 'a+') as cfg_local:
            if not flag:
                cfg.write(config.CONFIG_CORE)
            else:
                cfg.seek(0)
                flag = False

            lines = iter(cfg.readlines())
            for line in lines:
                if remote in line:
                    if host in next(lines):
                        flag = True
                        break
                    else:
                        remote = 'dagshub'
                        flag = False

            if not flag:
                cfg.write(config.CONFIG_REMOTE.format(remote=remote, url=url))
                cfg_local.write(config.CONFIG_LOCAL.format(remote=remote, token=auth[1]))
                print(f'Added new remote "{remote}" with url = {url}')

        if not exists(root / '.dvc' / '.gitignore'):
            with open(root / '.dvc' / '.gitignore', 'w') as ign:
                ign.write(config.CONFIG_GITIGNORE)

    print('Repository initialized!')


@cli.command()
@click.option("--token", help="Login using a specified token")
@click.option("--host", help="DagsHub instance to which you want to login")
@click.pass_context
def login(ctx, token, host):
    """
    Initiate an Oauth authentication process. This process will generate and cache a short-lived token in your
    local machine, to allow you to perform actions that require authentication. After running `dagshub login` you can
    use data streaming and upload files without providing authentication info.
    """
    host = host or ctx.obj["host"]
    if token is not None:
        dagshub.auth.add_app_token(token, host)
        print("Token added successfully")
    else:
        dagshub.auth.add_oauth_token(host)
        print("OAuth token added")


def validate_repo(ctx, param, value):
    parts = value.split("/")
    if len(parts) != 2:
        raise click.BadParameter("repo needs to be in the format <repo-owner>/<repo-name>")
    return tuple(parts)


def to_log_level(verbosity):
    if verbosity == 0:
        return logging.WARN
    elif verbosity == 1:
        return logging.INFO
    elif verbosity >= 2:
        return logging.DEBUG


@cli.command()
@click.argument("repo", callback=validate_repo)
@click.argument("filename", type=click.Path(exists=True))
@click.argument("target")
@click.option("-m", "--message", help="Commit message for the upload")
@click.option("-b", "--branch", help="Branch to upload the file to")
@click.option("--update", is_flag=True, help="Force update an existing file")
@click.option("-v", "--verbose", default=0, count=True, help="Verbosity level")
@click.pass_context
def upload(ctx,
           filename,
           target,
           repo,
           message,
           branch,
           verbose,
           update,
           **kwargs):
    """
    Upload FILENAME to REPO at location TARGET.
    REPO should be of the form <owner>/<repo-name>, i.e nirbarazida/yolov6.
    TARGET should include the full path inside the repo, including the filename itself.
    """
    from dagshub.upload import Repo
    logger = logging.getLogger()
    logger.setLevel(to_log_level(verbose))

    owner, repo_name = repo
    repo = Repo(owner=owner, name=repo_name, branch=branch)
    repo.upload(file=filename, path=target, commit_message=message, force=update)


@cli.group()
def repo():
    """
    Operations on repo: currently only 'create'
    """
    pass


@repo.command()
@click.argument("repo_name")
@click.option("-u", "--upload-data", help="Upload data from specified url to new repository")
@click.option("-c", "--clone", is_flag=True,  help="Clone repository locally")
@click.option("-v", "--verbose", default=0, count=True, help="Verbosity level")
@click.pass_context
def create(ctx,
           repo_name,
           upload_data,
           clone,
           verbose):
    """
    create a repo and:\n
    optional- upload files to 'data' dir,
     .zip and .tar files are extracted, other formats copied as is.
    optional- clone repo locally.\n
    example 1:  dagshub repo-create mytutorial -u "http://example.com/data.csv" --clone\n
    example 2:  dagshub --host "https://www.dagshub.com"
    repo-create mytutorial2 -u "http://0.0.0.0:8080/index.html" --clone --verbose
    """

    logger = logging.getLogger()
    logger.setLevel(to_log_level(verbose))

    with tempfile.TemporaryDirectory() as tmp_dir:

        # override default host if provided by --host
        host = ctx.obj["host"]

        # create remote repo
        repo = create_repo(repo_name, host=host)
        logger.info(f"Created repo: {host}/{repo.owner}/{repo.name}.git")

        if upload_data:
            # get the data
            res = http_request("GET", upload_data)
            if res.status_code != HTTPStatus.OK:
                raise RuntimeError(f"Could not get file from source (response: {res.status_code}), repo created")

            downloaded_file_name = os.path.basename(urlparse(upload_data).path)

            # save to disk
            with open(downloaded_file_name, 'wb') as fh:
                fh.write(res.content)

            logger.info(f"Downloaded and saved {downloaded_file_name}")

            # extract to data dir or move there
            if zipfile.is_zipfile(downloaded_file_name):
                with zipfile.ZipFile(downloaded_file_name, 'r') as zip_ref:
                    zip_ref.extractall(tmp_dir)
            elif tarfile.is_tarfile(downloaded_file_name):
                with tarfile.TarFile(downloaded_file_name, 'r') as tar_ref:
                    tar_ref.extractall(tmp_dir)
            else:
                os.rename(downloaded_file_name, f"{tmp_dir}/{downloaded_file_name}")

            # upload data dir as DVC to repo
            add_dataset_to_repo(repo, tmp_dir, DEFAULT_DATA_DIR_NAME)
            logger.info("Data uploaded to repo")

        if clone:
            # make local repo
            git.Git(repo.name).clone(f"{host}/{repo.owner}/{repo.name}.git")
            logger.info(f"Cloned repo to folder {repo.name}")

            # move the data to it,
            # now the local repo resembles the remote but with copy of data
            if upload_data:
                os.rename(tmp_dir, f"{repo.name}/{DEFAULT_DATA_DIR_NAME}")
                logger.info(f"files moved to {repo.name}/{DEFAULT_DATA_DIR_NAME}")

    # clean tmp file/dir if exists
    if os.path.exists(downloaded_file_name):
        os.remove(downloaded_file_name)


if __name__ == "__main__":
    cli()
