"""SetupTask - Convert plan_raw.json into the plan.txt used by the pipeline."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum
from worker_plan_api.plan_file import PlanFile
from worker_plan_internal.plan.nodes.initial_plan_raw import InitialPlanRawTask


class SetupTask(PlanTask):
    """Read plan_raw.json and produce plan.txt from the template."""
    def requires(self):
        return self.clone(InitialPlanRawTask)

    def output(self):
        return self.local_target(FilenameEnum.INITIAL_PLAN)

    def run(self):
        plan_file = PlanFile.load(self.input().path)
        plan_text = plan_file.to_plan_text()
        with open(self.output().path, "w", encoding="utf-8") as f:
            f.write(plan_text)
