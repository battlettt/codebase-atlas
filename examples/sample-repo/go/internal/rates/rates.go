// Package rates computes shipping offers from a rate table.
package rates

// Rate is the price per kilogram for one carrier.
type Rate struct {
	Carrier string
	PerKg   float64
}

// Offer is a priced quote for one parcel.
type Offer struct {
	Carrier string
	Price   float64
}

// Quote returns the cheapest offer for the given weight.
func Quote(table []Rate, weight float64) Offer {
	best := table[0]
	for _, r := range table[1:] {
		if r.PerKg < best.PerKg {
			best = r
		}
	}
	return Offer{Carrier: best.Carrier, Price: price(best, weight)}
}

func price(r Rate, weight float64) float64 {
	return roundCents(r.PerKg * weight)
}
