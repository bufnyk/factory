from pydantic import BaseModel 

class Label(BaseModel):
    name: str

class Issue(BaseModel):
    repository_url: str
    title: str
    body: str
    id: int

class Github(BaseModel):
    action: str
    issue: Issue
    labels: list[Label]

