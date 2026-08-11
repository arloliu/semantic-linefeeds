# Code written as HTML

A proposal that writes its examples as HTML rather than as a fence.

<pre>
struct Foo {
  let bar: Int
  func baz() -&gt; Int {
    return bar
  }
}
</pre>

Prose after the block is still measured,
so the rule does not switch the checker off for the rest of the file.
