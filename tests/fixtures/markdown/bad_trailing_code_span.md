# Trailing code spans

The compiler will assume all functions provide an `ABIInternal` {wrap}
implementation.

One incompatibility is changing `testing.Cover.CoveredPackages` {wrap}
field type, but the rest of the package is covered.

The clause boundary in front of the span is still a boundary:

method: `window/collectInput`
params: `FormField[]`

A line that is nothing but a code span ends where it ends:

`type [T] type Vector []T`
and the syntax described above is preferred.
