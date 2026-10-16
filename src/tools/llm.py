#!/usr/bin/env python3
import sys
import json
import click
from ollama import Ollama, OllamaError

@click.command()
@click.option("-H", "--host", default="http://localhost:11434", show_default=True, help="Ollama host URL")
@click.option("-m", "--model", default="llama2", show_default=True, help="Model name to use")
@click.option("-f", "--file", type=click.Path(exists=True), help="Read prompt from file (otherwise reads stdin)")
@click.option("--stream/--no-stream", default=True, show_default=True, help="Use streaming output")
def main(host, model, file, stream):
    client = Ollama(base_url=host) if host else Ollama()
    if file:
        with open(file, "r", encoding="utf-8") as fh:
            prompt = fh.read()
    else:
        prompt = sys.stdin.read()
    if not prompt or not prompt.strip():
        click.echo("No prompt provided", err=True)
        sys.exit(2)

    messages = [{"role": "user", "content": prompt}]
    try:
        if stream:
            # chat_stream yields chunks (depends on client version—adapt if needed)
            with client.chat_stream(model=model, messages=messages) as stream_iter:
                for chunk in stream_iter:
                    # chunk may be dict-like with text fields; handle common shapes
                    if isinstance(chunk, str):
                        sys.stdout.write(chunk); sys.stdout.flush()
                        continue
                    text = (
                        chunk.get("output")
                        or chunk.get("text")
                        or (chunk.get("choices") and chunk["choices"][0].get("delta", {}).get("content"))
                        or ""
                    )
                    if text:
                        sys.stdout.write(text)
                        sys.stdout.flush()
        else:
            resp = client.chat(model=model, messages=messages)
            # resp may contain 'text' or 'output' or choices
            text = (
                resp.get("output")
                or resp.get("text")
                or (resp.get("choices") and resp["choices"][0].get("message", {}).get("content"))
                or ""
            )
            sys.stdout.write(text)
    except OllamaError as e:
        click.echo(f"Ollama error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

