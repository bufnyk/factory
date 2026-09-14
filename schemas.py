from pydantic import BaseModel 

class Label(BaseModel):
    name: str

class Issue(BaseModel):
    title: str
    body: str
    number: int
    id: int
    labels: list[Label]

class repo(BaseModel):
    html_url: str

class Github(BaseModel):
    action: str
    issue: Issue
    repository: repo
    

