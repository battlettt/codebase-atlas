package rates

import "testing"

func TestQuotePicksCheapest(t *testing.T) {
	table := []Rate{{Carrier: "A", PerKg: 2}, {Carrier: "B", PerKg: 1}}
	if got := Quote(table, 3); got.Carrier != "B" {
		t.Fatalf("expected B, got %s", got.Carrier)
	}
}
