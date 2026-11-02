package rates

import (
	"encoding/json"
	"math"
	"os"
)

// LoadTable reads a JSON rate table from disk.
func LoadTable(path string) ([]Rate, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var table []Rate
	err = json.Unmarshal(data, &table)
	return table, err
}

func roundCents(v float64) float64 {
	return math.Round(v*100) / 100
}
