"""
PROMPT> python -m worker_plan_api.plan_file
"""
import json
from datetime import datetime
from dataclasses import dataclass


PLAN_TEMPLATE = "Plan:\n{plan_prompt}\n\nToday's date:\n{pretty_date}\n\nProject start ASAP"


@dataclass
class PlanFile:
    plan_prompt: str
    pretty_date: str

    @classmethod
    def create(cls, vague_plan_description: str, start_time: datetime) -> "PlanFile":
        pretty_date = start_time.strftime("%Y-%b-%d")
        return cls(plan_prompt=vague_plan_description, pretty_date=pretty_date)

    def to_dict(self) -> dict:
        return {
            "plan_prompt": self.plan_prompt,
            "pretty_date": self.pretty_date,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanFile":
        return cls(plan_prompt=data["plan_prompt"], pretty_date=data["pretty_date"])

    @classmethod
    def load(cls, file_path: str) -> "PlanFile":
        with open(file_path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_plan_text(self) -> str:
        return PLAN_TEMPLATE.format(plan_prompt=self.plan_prompt, pretty_date=self.pretty_date)


if __name__ == "__main__":
    start_time: datetime = datetime.now().astimezone()
    plan = PlanFile.create(vague_plan_description="My plan is here!", start_time=start_time)
    print(json.dumps(plan.to_dict(), indent=2))
    print("---")
    print(plan.to_plan_text())
