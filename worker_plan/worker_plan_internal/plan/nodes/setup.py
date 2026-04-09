"""SetupTask - Convert plan_raw.json into the plan.txt used by the pipeline."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum
from worker_plan_api.plan_file import PlanFile


class SetupTask(PlanTask):
    """Read plan_raw.json and produce plan.txt from the template."""
    def output(self):
        return self.local_target(FilenameEnum.INITIAL_PLAN)

    def run(self):
        raw_path = self.run_id_dir / FilenameEnum.INITIAL_PLAN_RAW.value
        if not raw_path.exists():
            raise FileNotFoundError(
                f"Before starting the pipeline the '{FilenameEnum.INITIAL_PLAN_RAW.value}' file "
                f"must be present in the run_id_dir: {self.run_id_dir!r}"
            )
        plan_file = PlanFile.load(str(raw_path))
        plan_text = plan_file.to_plan_text()
        with open(self.output().path, "w", encoding="utf-8") as f:
            f.write(plan_text)
