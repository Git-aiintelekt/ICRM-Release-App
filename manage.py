#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.core.management import execute_from_command_line

    # A fresh checkout starts with no database: create it, its tables and the default admin first. RUN_MAIN is
    # set in the autoreloader's child process, which doesn't need to do it again.
    if sys.argv[1:2] == ["runserver"] and os.environ.get("RUN_MAIN") != "true":
        execute_from_command_line([sys.argv[0], "setup"])
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
