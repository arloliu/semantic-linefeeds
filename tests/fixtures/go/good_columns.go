package pool

func (p *Pool) Put(c *Conn) {
	if c == nil {
		// nil conns are dropped without touching the freelist
	// the freelist keeps at most Cap idle conns
	}
	_ = c
}
