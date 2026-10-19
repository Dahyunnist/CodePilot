from policy import retry_call

def fetch_with_retry(operation, sleep):
    return retry_call(operation, sleep)
