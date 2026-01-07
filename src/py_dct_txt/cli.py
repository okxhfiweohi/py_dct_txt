"""Console script for py_dct_txt."""

import typer
from rich.console import Console

from py_dct_txt import utils

app = typer.Typer()
console = Console()


@app.command()
def main():
    """Console script for py_dct_txt."""
    console.print("Replace this message by putting your code into "
               "py_dct_txt.cli.main")
    console.print("See Typer documentation at https://typer.tiangolo.com/")
    utils.do_something_useful()


if __name__ == "__main__":
    app()
