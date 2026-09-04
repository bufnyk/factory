from pydantic import BaseModel 

class Label(BaseModel):
    name: str

class Issue(BaseModel):
    repository_url: str
    title: str
    body: str
    number: int
    id: int
    labels: list[Label]

class Github(BaseModel):
    action: str
    issue: Issue
    

