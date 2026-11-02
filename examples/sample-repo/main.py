"""Command line entry point for the sample shop inventory report."""
import sys

from inventory import report


def main(argv):
    """Print the inventory report for the JSON file given on the command line."""
    path = argv[1] if len(argv) > 1 else "data/items.json"
    for line in report.build_report(path):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
