#!/mnt/opt/nicola/media/bin/python
import os
import random
import re
import sys
# TODO: use this
# from configparser import ConfigParser
from pathlib import Path

import click
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


def is_valid(file_path: Path, valid_extensions) -> bool:
    return file_path.name.endswith(tuple(valid_extensions)) and not file_path.name.startswith(("inkyframe", "frame"))


@click.command()
@click.option("--input-dirs", "-i", type=str, multiple=True, default=(Path(".").absolute(),), help="One or more directory or @file containing a list of dirs")
@click.option("--output-dir", "-o", type=Path, default=Path(".").absolute())
@click.option("--dry-run", "-d", is_flag=True, envvar="DRYRUN")
@click.option("--extensions", "-e", type=str, multiple=True, default=VALID_EXTS)
def app(input_dirs: list[str], output_dir: Path, dry_run: bool, extensions: tuple[str]):
    if dry_run:
        os.environ["DRYRUN"] = "1"
    os.chdir(output_dir)
    choices = []
    input_dirs_list = set()
    for input_dir in input_dirs:
        if input_dir.startswith('@'):
            file_path = Path(input_dir[1:])  # Remove the @ prefix

            if not file_path.is_file():
                typer.echo(f"Error: File not found: {file_path}", err=True)
                raise typer.Exit(code=1)

            # Read directories from file
            with open(file_path, 'r') as f:
                input_dirs_list.update(Path(line.strip()) for line in f if line.strip() and not line.startswith('#'))
        else:
            input_dirs_list.add(Path(input_dir))

    for input_dir in input_dirs_list:
        for file_path in [fp for fp in input_dir.iterdir() if is_valid(fp, extensions)]:
            choices.append(file_path)
    convert(random.choices(choices, k=4))
    Path("index.html").open("w").write(create_html_index())


def needs_rotate(screen_ratio, image_ratio) -> bool:
    return (screen_ratio > 1 and image_ratio < 1) or (screen_ratio < 1 and image_ratio > 1)


def all_numbers(text: str) -> bool:
    if re.match(r"[-_0-9 .]*$", text):
        return True
    return False


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
        title_file = input_file.with_suffix("")
        while all_numbers(title_file.name) and not title_file.is_mount():
            title_file = title_file.parent
        if title_file.is_mount():
            title_file = input_file
        title = re.sub(r"(^[0-9]*[- _.]|[-_.])", " ", title_file.name).title().strip()
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


def create_html_index(img_dir="."):
    """
    Create an HTML index for the indexed images.

    Returns:
        str: HTML content as a string.
    """
    html = "<html><body><h1>Indexed Images</h1>"

    # List of files and their corresponding paths
    file_list = []
    for root, dirs, files in Path(img_dir).walk():
        for file in files:
            if file.endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(root, file)
                # resized_path = resize_image(file_path)
                # file_list.append((file_path, resized_path))
                file_list.append((file_path, file_path))

    # Sort the list by file size (largest first)
    file_list.sort(key=lambda x: os.path.getsize(x[1]), reverse=True)

    # Create HTML content
    for i, (file_path, resized_path) in enumerate(file_list):
        html += f"<p><img src='{resized_path}' width='50%' height='auto'></p>"

    # Close the HTML body and document
    html += "</body></html>"

    return html


if __name__ == "__main__":
    app()

