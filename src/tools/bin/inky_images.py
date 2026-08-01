#!/mnt/opt/nicola/media/bin/python
import os
import random
import sys
# TODO: use this
# from configparser import ConfigParser
from pathlib import Path

import typer
from PIL import Image

FORMATS = {
    # 640 x 400 (for 4.0")
    "inkyframe4": {"width": 640, "height": 400},
    # 600 x 448 pixels (for 5.7")
    "inkyframe5": {"width": 600, "height": 448},
    # 800 x 480 pixels (for 7.3")
    "inkyframe7": {"width": 800, "height": 480},
    # 1600 x 1200 pixels (for 13.3")
    "inkyframe13": {"width": 1600, "height": 1200},
}

VALID_EXTS = (".gif", ".jpg", ".png")

app = typer.Typer()


def is_valid(file_path: Path, valid_extensions) -> bool:
    return file_path.name.endswith(tuple(valid_extensions)) and not file_path.name.startswith(("inkyframe", "frame"))


@app.command()
def main(input_dirs: list[Path] = (Path(".").absolute(),), output_dir: Path = Path(".").absolute(), extensions: list[str] = VALID_EXTS):
    os.chdir(output_dir)
    choices = []
    for input_dir in input_dirs:
        for file_path in [fp for fp in input_dir.iterdir() if is_valid(fp, extensions)]:
            choices.append(file_path)
    convert(random.choices(choices, k=4))


def needs_rotate(screen_ratio, image_ratio) -> bool:
    return (screen_ratio > 1 and image_ratio < 1) or (screen_ratio < 1 and image_ratio > 1)


def dryrun(env: dict) -> bool:
    if env.get("DRYRUN"):
        return True
    return False


def convert(input_files: list):
    """Pass max 4 files to distribute (resized) to inkyframe<N>.jpg files"""
    if not input_files:
        print("Please specify at least one input file")
        sys.exit(1)
    for input_filename, inky_filename in zip(input_files, FORMATS):
        FORMATS[inky_filename]["input_file"] = Path(input_filename)
    for file_name, inky_format in FORMATS.items():
        input_file = inky_format.get("input_file", Path(input_files[-1]))
        title = input_file.stem.title().replace("-", " ").replace("_", " ")
        img = Image.open(input_file)
        if needs_rotate(inky_format["width"] / inky_format["height"], img.width / img.height):
            print(f"Rotating: {inky_format} -> ({img.width}, {img.height})")
            res = img.rotate(90)
        else:
            res = img
        res = res.resize((inky_format["width"], inky_format["height"]), resample=Image.LANCZOS)
        if dryrun(os.environ):
            print(f"Would save {file_name}.jpg with size {res.size} from {input_file} {img.size} and {title=} in {file_name}.txt")
        else:
            res.save(f"{file_name}.jpg")
            Path(f"{file_name}.txt").write_text(title)


if __name__ == "__main__":
    typer.run(main)

