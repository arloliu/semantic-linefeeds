# Worker pool

The pool starts one worker per configured slot and hands each submission to
the first idle worker. A submission that arrives while every worker is busy
blocks until a slot frees.
