#!/ur/bin/env python3
import os
import sys


def duplicates(base_dir: str):
    result_lines = list()
    for root_dir, files, subdirs in os.walk(base_dir):
        print(root_dir, files, subdirs)
    return result_lines


def main(argv=sys.argv[1:]):
    for base_dir in argv or [os.path.abspath(os.path.curdir)]:
        result_text = "\n".join(duplicates(base_dir))
        print(result_text)


if __name__ == "__main__":
    main()
