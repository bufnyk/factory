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

def construct_claude_prompt(payload: Github):
    return f'''
You are an agent assigned to resolve a certain issue. Here is a tile of this isse: {payload.issue.title} and its description: {payload.issue.body} 
Your job is to resolve the task. YOU MUST NOT CREATE ANY UNITEST
'''

def construct_codex_prompt(payload: Github):
    return f'''
You are an agent assigned to resolve a certain issue. Here is a tile of this isse: {payload.issue.title} and its description: {payload.issue.body} 
Your job is to check if the issue/task has been solved. Create unitest and do a code review
'''
    

