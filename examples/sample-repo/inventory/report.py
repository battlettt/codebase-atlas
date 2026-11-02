"""Build a human-readable stock report."""
from inventory.store import load_items, low_stock


def build_report(path):
    """Return report lines for the inventory stored at path."""
    items = load_items(path)
    total = sum(item.total_value() for item in items)
    lines = [f"{len(items)} items, total value {total:.2f}"]
    for item in low_stock(items):
        lines.append(f"LOW: {item.name} ({item.quantity} left)")
    return lines
