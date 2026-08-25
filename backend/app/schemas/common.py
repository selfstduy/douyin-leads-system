from typing import Any, Optional
from pydantic import BaseModel


class ResponseModel(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None


class PageResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None
    total: int = 0
    page: int = 1
    page_size: int = 20
