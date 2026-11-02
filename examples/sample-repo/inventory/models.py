"""Data models for inventory items."""
from dataclasses import dataclass


@dataclass
class Item:
    """A stocked product with a unit price and a quantity on hand."""

    sku: str
    name: str
    price: float
    quantity: int

    def total_value(self):
        """Return price times quantity."""
        return self.price * self.quantity


def make_item(raw):
    return Item(
        sku=raw["sku"],
        name=raw["name"],
        price=float(raw["price"]),
        quantity=int(raw["quantity"]),
    )
