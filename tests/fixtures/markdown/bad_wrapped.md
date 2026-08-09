# Worker pool

The pool starts one worker per configured slot and hands each submission to {wrap}
the first idle worker. A submission that arrives while every worker is busy {fused} {wrap}
blocks until a slot frees.
