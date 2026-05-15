"""
Check that Pydantic can be used to parse LLM "structured output".

PROMPT> python experiments/standalone_experiments/run_pydantic.py
"""
from pydantic import BaseModel

class MyStruct(BaseModel):
    weather: str = "sunshine"
    count: str = "999"
    state: str = "start"

json_data = {
    "weather": "rain",
    "count": "42",
    "state": "halted"
}

my_struct = MyStruct(**json_data)
print(my_struct)
