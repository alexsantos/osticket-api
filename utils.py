from typing import List, Optional, Callable
from urllib.parse import urlencode

from fastapi import Query, Request, HTTPException


def make_url(request: Request, limit: int, offset: int) -> str:
    """
    Helper function to rebuild the URL with a new offset.

    Prefers X-Forwarded-Proto/X-Forwarded-Host over request.url, since behind
    a gateway (e.g. Cloud Run fronted by an API facade) the ASGI scope only
    sees the internal host, not the one the client actually called.
    """
    query_params = dict(request.query_params)
    query_params['limit'] = str(limit)
    query_params['offset'] = str(offset)

    scheme = request.headers.get('x-forwarded-proto', request.url.scheme)
    host = request.headers.get('x-forwarded-host', request.url.netloc)
    base_url = f"{scheme}://{host}{request.url.path}"

    return f"{base_url}?{urlencode(query_params)}"


def build_pagination_urls(request: Request, limit: int, offset: int, total: int) -> tuple[Optional[str], Optional[str]]:
    """Builds the 'next' and 'previous' pagination URLs for a paginated response."""
    next_url = None
    if offset + limit < total:
        next_url = make_url(request, limit, offset + limit)

    previous_url = None
    if offset > 0:
        previous_url = make_url(request, limit, max(0, offset - limit))

    return next_url, previous_url


def CommaSeparatedInts(param_name: str) -> Callable[..., Optional[List[int]]]:
    """
    A dependency that parses a comma-separated list of integers from a query parameter.
    It also gracefully handles repeated query parameters (e.g., ?id=1&id=2).
    """
    def parse(q: Optional[List[str]] = Query(None, alias=param_name)) -> Optional[List[int]]:
        if not q:
            return None
        
        # Flatten the list in case of both comma-separated and repeated params
        flat_list = [item for sublist in [i.split(',') for i in q] for item in sublist]
        
        try:
            return [int(i.strip()) for i in flat_list if i.strip()]
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid integer value in list for parameter '{param_name}'")
            
    return parse