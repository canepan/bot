#!/bin/bash
# tool to start/stop a service. Workflow is:
#  * get config from git
#  * backup current config (with timestamp) if different
#  * apply config
#  * check if primary (VRRP IP)
#  * start as a primary or (if possible) as secondary
import filecmp
import logging
import os
import subprocess
import typing
from datetime import datetime
from tempfile import TemporaryDirectory

import attr
import click


def are_files_equal(file_list: list, dir1: str, dir2: str) -> bool:
    log = logging.getLogger(__name__)
    (_, mismatch, errors) = filecmp.cmpfiles(
        dir1, dir2, file_list, shallow=False
    )
    if len(mismatch) > 0 or len(errors) > 0:
        log.debug(f"Mismatch: {mismatch}")
        log.debug(f"Errors: {errors}")
        return False
    return True


def are_dir_trees_equal(dir1, dir2):
    """
    Compare two directories recursively. Files in each directory are
    assumed to be equal if their names and contents are equal.

    @param dir1: First directory path
    @param dir2: Second directory path

    @return: True if the directory trees are the same and
        there were no errors while accessing the directories or files,
        False otherwise.
    """

    log = logging.getLogger(__name__)
    dirs_cmp = filecmp.dircmp(dir1, dir2)
    if (
        len(dirs_cmp.left_only) > 0
        or len(dirs_cmp.right_only) > 0
        or len(dirs_cmp.funny_files) > 0
    ):
        log.debug(f"Left: {dirs_cmp.left_only}")
        log.debug(f"Right: {dirs_cmp.right_only}")
        log.debug(f"Funny: {dirs_cmp.funny_files}")
        return False
    if not are_files_equal(dirs_cmp.common_files, dir1, dir2):
        return False
    for common_dir in dirs_cmp.common_dirs:
        new_dir1 = os.path.join(dir1, common_dir)
        new_dir2 = os.path.join(dir2, common_dir)
        if not are_dir_trees_equal(new_dir1, new_dir2):
            return False
    return True


@attr.s
class ServiceCatalog(object):
    SERVICES = {
        "bind9": {
            "git_repo": "cfengine/services/bind/phoenix",
            "config_dir": "/etc/bind",
        },
    }

    @classmethod
    def get_service(cls, service_name: str) -> "KeepalivedService":
        s = cls.SERVICES[service_name]
        return KeepalivedService(repo_path=s["git_repo"], config_dir=s["config_dir"])


@attr.s
class KeepalivedService(object):
    # git_base = "git@bigbang-01.canne:repos/"
    git_base = "http://git.canne/repos/"
    log = logging.getLogger(__name__)
    _repo_path: str = attr.ib()
    _config_dir: str = attr.ib()
    _config_files: typing.List[str] = attr.ib(factory=list)
    _backup_dir: str = attr.ib(default=os.environ["HOME"])

    def _run(self, cmd) -> str:
        try:
            return subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            self.log.exception(e.output)
            raise

    def git_pull(self):
        tmp_dir = TemporaryDirectory()
        # not thread safe
        os.chdir(tmp_dir.name)
        repo_name, repo_sub = self._repo_path.split("/", 1)
        self._run(["git", "clone", "-n", "--depth=1", "--filter=tree:0", f"{self.git_base}{repo_name}", tmp_dir.name])
        os.chdir(self._repo_path)

    def _config_changed(self) -> bool:
        return (
            not are_files_equal(self._config_files, ".", self._config_dir)
            or not are_dir_trees_equal(".", self._config_dir)
        )

    def backup_config(self):
        if self._config_changed():
            datenow = datetime.now().strftime('%Y%m%d%H%M%S')
            backup_file = os.path.join(self._backup_dir, f"{self._repo_path.replace('/', '_')}-{datenow}.tar.gz")
            self.log.debug(f"Backing up {self._config_dir} to {backup_file}")
            self._run(["tar", "-zcf", backup_file, self._config_dir] + self._config_files)

    def apply_config(self):
        if self._config_changed():
            print("Config changed")

    def start_pri_or_sec(self, primary: bool):
        pass

    def stop_pri_or_sec(self, primary: bool):
        pass


@click.group()
@click.option("--service", "-s", default="bind9")
@click.option("--verbose/--quiet", "-v/-q", default=None)
@click.pass_context
def main(ctx: click.Context, service:str, verbose: bool):
    ctx.ensure_object(dict)
    ctx.obj["kaservice"] = ServiceCatalog.get_service(service)
    logging.basicConfig()
    if verbose:
        logging.getLogger(__name__).setLevel(logging.DEBUG)
    elif verbose is False:
        logging.getLogger(__name__).setLevel(logging.CRITICAL)


@main.command()
@click.pass_context
def start(ctx: click.Context):
    ks = ctx.obj["kaservice"]
    ks.git_pull()
    ks.backup_config()
    ks.apply_config()
    ks.start_pri_or_sec(primary=True)


@main.command()
@click.pass_context
def stop(ctx: click.Context):
    ks = ctx.obj["kaservice"]
    ks.stop_pri_or_sec(primary=True)


if __name__ == "__main__":
    main()
