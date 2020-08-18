#!/Volumes/MoviablesX/VMs/tools/bin/python
import os
import stat
import subprocess
import sys

ORIG_MODE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH


def kill_all_instances() -> None:
    ps_out = subprocess.check_output(['ps', 'auxwww'], stderr=subprocess.PIPE).decode('utf-8')
    pids = []
    for line in [l for l in ps_out.splitlines() if 'java' in l and 'Minecraft' in l]:
        pid = int(line.split()[1])
        pids.append(pid)
        os.kill(pid, 15)
        print('{} ({}) killed (15)'.format(line, pid))


def main(argv: list = sys.argv[1:]) -> int:
    launcher = '/Applications/Minecraft.app/Contents/MacOS/launcher'
    if len(argv) == 0:
        print('Specify either on or off')
        return 1
    if argv[0] == 'on':
        # chmod 755 /Applications/Minecraft.app/Contents/MacOS/launcher
        os.chmod(launcher, ORIG_MODE)
    elif argv[0] == 'off':
        # chmod 000 /Applications/Minecraft.app/Contents/MacOS/launcher
        os.chmod(launcher, 0)
        kill_all_instances()
    else:
        print('Please, specify on or off')
    return 0


if __name__ == '__main__':
    sys.exit(main())
