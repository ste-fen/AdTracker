import time

def rate_limited_request(request_func, *args, **kwargs):
    try:
        response = request_func(*args, **kwargs)
        time.sleep(1)  # Prevent hitting API rate limits
        return response
    except Exception as e:
        print(f"API request failed: {e}")
        return None
