//! Crate-level docs use inner doc comments.
//! One sentence per line keeps diffs reviewable.

/// # Examples
///
/// ```
/// let x = read_all();
/// assert!(x.is_empty());
/// ```
///
/// Fenced code above is never checked, and this closing sentence is fine.
pub fn read_all() {}
