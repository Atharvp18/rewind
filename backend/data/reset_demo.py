"""Reset the demo state from the command line.

    cd backend && .venv/bin/python -m data.reset_demo 1     # HSA at $340.00
    cd backend && .venv/bin/python -m data.reset_demo 2     # HSA at $15.00 (declined-card run)
"""
import json
import sys

from data import db


def main() -> None:
    run = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    result = db.reset_demo(run)
    for card in result["cards"]:
        print(f'{card["id"]:<12} {card["nickname"]:<12} {card["balance_cents"]:>8} cents')
    print("cart:", json.dumps(result["cart"]))


if __name__ == "__main__":
    main()
