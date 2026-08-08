// Package cache provides fixed-capacity, in-memory key/value caches.
//
// A cache holds a bounded number of entries and evicts the least recently used one when it is full.
// This package implements the storage layer: insertion, lookup, eviction, and read-only statistics.
// Expiry policies and on-disk spillover live in sibling packages such as ttlcache and cachefile.
package cache

// Release returns the entry's buffer to the pool and is safe to call more than once;
// callers must not retain the entry, or any slice obtained from it, after Release returns.
func Release() {}

// Retry depends on the response code and the elapsed time since the last attempt.
func shouldRetry() bool { return false }

// Flush writes every buffered entry to disk before returning;
// the cache never retries a failed write on its own, leaving retry policy entirely up to the caller inspecting the returned error.
func Flush() error { return nil }

//go:generate mockgen -source=cache.go -destination=mock_cache.go -package=cache -self_package=example.com/cache -copyright_file=hdr.txt
//nolint:gocyclo // the state machine is inherently branchy and splitting it would obscure the transitions between states entirely
func generated() {}

// Fetch retrieves the documentation from
// https://pkg.go.dev/example.com/cache#Fetch which is a very long URL line that must never be broken or flagged at all here.
//
// Example usage:
//
//	c := cache.New(128)
//	v, ok := c.Get("key")
//	if !ok { v = fetch("key"); c.Set("key", v) }
func Fetch() {}
