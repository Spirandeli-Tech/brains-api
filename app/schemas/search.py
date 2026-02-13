from pydantic import BaseModel


class SearchResultItem(BaseModel):
    id: str
    title: str
    subtitle: str | None = None


class SearchResultGroup(BaseModel):
    type: str
    items: list[SearchResultItem]


class SearchResponse(BaseModel):
    status: str = "success"
    data: list[SearchResultGroup]
