// Command shipper prints the cheapest shipping offer for a parcel weight.
package main

import (
	"fmt"
	"os"
	"strconv"

	"example.com/shipping/internal/rates"
)

func main() {
	weight, err := strconv.ParseFloat(os.Args[1], 64)
	if err != nil {
		fmt.Println("weight must be a number")
		os.Exit(1)
	}
	table, err := rates.LoadTable("rates.json")
	if err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
	offer := rates.Quote(table, weight)
	fmt.Printf("%s: %.2f\n", offer.Carrier, offer.Price)
}
