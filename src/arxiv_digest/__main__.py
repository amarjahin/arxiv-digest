"""Enable `python -m arxiv_digest`, used as a PATH-independent fallback by the
scheduler when the console script isn't available."""

from .cli import main

if __name__ == "__main__":
    main()
