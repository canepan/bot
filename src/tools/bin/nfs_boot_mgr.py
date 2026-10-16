import os

import attr
import click


@attr.s(repr=False)
class NfsManager(object):
    nfs_root: str = attr.ib()
    serials: dict = attr.ib(default={"031b3525": "RaspyKey", "a9b0a878": "RaspyM2", "9262480ae": "lheaven"})

    @property
    def nfs_paths(self):
        try:
            return self._nfs_paths
        except AttributeError:
            root, nfs_dirs, nfs_files = next(os.walk(self.nfs_root))
            self._nfs_paths = list(nfs_dirs)
        return self._nfs_paths

    def __repr__(self) -> str:
        return "\n".join(f"{nfs_dir}: {self.serials.get(nfs_dir, nfs_dir)}" for nfs_dir in self.nfs_paths if not os.path.islink(os.path.join(self.nfs_root, nfs_dir)))


@click.command()
@click.argument("nfs-root", default="/mnt/nfs/boot")
def cli(nfs_root: str):
    nfs_manager = NfsManager(nfs_root)
    # for nfs_path in nfs_manager.nfs_paths:
    #     print(nfs_path)
    click.echo(nfs_manager)


if __name__ == "__main__":
    cli()
