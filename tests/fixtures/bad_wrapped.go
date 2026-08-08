// Package cache provides fixed-capacity, in-memory key/value caches. A cache
// holds a bounded number of entries and evicts the least recently used one
// when it is full. This package implements the storage layer: insertion,
// lookup, eviction, and read-only statistics. Expiry policies and on-disk
// spillover live in sibling packages such as ttlcache and cachefile.
package cache
