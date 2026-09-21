import argparse
from datetime import date

from .db import init_db
from .scraper import DouScraper
from .telegram import publish_pending_telegram


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    scrape = sub.add_parser("scrape")
    scrape.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    init_db()
    if args.command == "scrape":
        items = DouScraper().scrape(date.fromisoformat(args.date))
        sent = publish_pending_telegram()
        print(f"Encontradas {len(items)} publicações em {args.date}; enviadas ao Telegram: {sent}")


if __name__ == "__main__":
    main()
