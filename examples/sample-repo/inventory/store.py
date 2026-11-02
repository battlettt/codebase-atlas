"""Load and save inventory items from JSON files."""
import json
from pathlib import Path

from .models import Item, make_item


def load_items(path):
    """Read items from a JSON file and return a list of Item objects."""
    # TODO: validate that every record has a sku before building items
    with open(path, encoding="utf-8") as handle:
        records = json.load(handle)
    return [make_item(record) for record in records]


def save_items(path, items: list[Item]):
    """Write items back to a JSON file."""
    data = [item.__dict__ for item in items]
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def low_stock(items, threshold=5):
    """Return items whose quantity is below the threshold."""
    return [item for item in items if item.quantity < threshold]
