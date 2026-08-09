def fetch(url):
    """Fetch the URL and return its body. Retries are {fused} {wrap}
    performed with exponential backoff and the caller {wrap}
    sees only the final result.
    """
    return url


# A trailing comment sentence that wraps mid-clause is also {wrap}
# caught by the line-comment path.
X = 1
