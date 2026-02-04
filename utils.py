from urllib.parse import urlencode
from fastapi import Request

def make_url(request: Request, limit: int, new_offset: int) -> str:
    """
    Rebuilds the current request's URL with a new offset for pagination.

    Args:
        request: The incoming FastAPI request object.
        limit: The current page limit.
        new_offset: The new offset to use for the next/previous page.

    Returns:
        The full URL for the new page.
    """
    query_params = dict(request.query_params)
    query_params['limit'] = str(limit)
    query_params['offset'] = str(new_offset)
    
    base_url = str(request.url).split('?')[0]
    return f"{base_url}?{urlencode(query_params)}"
