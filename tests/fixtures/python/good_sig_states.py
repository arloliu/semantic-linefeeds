def one_liner(): pass


for item in [1]:
    """this string follows a for loop. It must not be treated as a docstring."""


def with_comment():  # pragma: no cover
    """A real docstring despite the trailing comment on the signature.
    It is checked and it is clean.
    """


def multi_line(
    a,
    b,
):
    """Docstrings after multi-line signatures are found too.
    Both sentences here are clean.
    """
