# Fences that close nothing

A fence is closed only by a run of its own mark, at least as long as its own.

```
~~~~~~~
```

```swift
struct Qux {
  let quux: Int
}
```

A fence long enough to quote a shorter one is not closed by the one it quotes.

````markdown
```
struct Corge {
  let grault: Int
}
```
````

Prose after all of it is still measured,
so neither rule switches the checker off for the rest of the file.
