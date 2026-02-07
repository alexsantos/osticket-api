from typing import List, Optional
from urllib.parse import urlencode

from fastapi import Query, Request, HTTPException


def make_url(request: Request, limit: int, offset: int) -> str:
    """Helper function to rebuild the URL with a new offset."""
    query_params = dict(request.query_params)
    query_params['limit'] = str(limit)
    query_params['offset'] = str(offset)
    base_url = str(request.url).split('?')[0]
    return f"{base_url}?{urlencode(query_params)}"


def CommaSeparatedInts(param_name: str) -> List[int]:
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