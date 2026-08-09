def sample():
    """Summary line is checked normally.

    >>> sample() # doctest lines are skipped. Even with two sentences.
    'x'

        indented example block with no punctuation at all
        and a lowercase continuation that must stay invisible

    ```
    fenced example with no punctuation at all
    ```

    Closing sentence after the examples is checked again.
    """
    return "x"


def fence_one_liner():
    """```"""
    # This comment sits directly after a one-line docstring with a fence marker.
    # It must be extracted as prose, and it is clean.
    return 1


def pre_one_liner():
    """<pre>"""
    # This comment sits directly after a one-line docstring with a pre marker.
    # It must be extracted as prose, and it is clean.
    return 2
