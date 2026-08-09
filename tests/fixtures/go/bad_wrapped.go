// Package cache provides fixed-capacity, in-memory key/value caches. A cache {fused} {wrap}
// holds a bounded number of entries and evicts the least recently used one
// when it is full. This package implements the storage layer: insertion, {fused}
// lookup, eviction, and read-only statistics. Expiry policies and on-disk {fused} {wrap}
// spillover live in sibling packages such as ttlcache and cachefile.
package cache
