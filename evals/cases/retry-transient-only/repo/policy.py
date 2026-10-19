def retry_call(operation, sleep):
    try:
        return operation()
    except Exception:
        sleep(0)
        return operation()
