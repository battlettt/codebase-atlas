from inventory.models import Item
from inventory.store import low_stock


def test_low_stock():
    items = [Item("a", "A", 1.0, 2), Item("b", "B", 1.0, 9)]
    assert [item.sku for item in low_stock(items)] == ["a"]
