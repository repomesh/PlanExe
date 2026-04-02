"""StartTimeTask - The timestamp when the pipeline was started."""
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_api.filenames import FilenameEnum


class StartTimeTask(PlanTask):
    """The timestamp when the pipeline was started."""
    def output(self):
        return self.local_target(FilenameEnum.START_TIME)

    def run(self):
        # The Gradio/Flask app that starts the luigi pipeline, must first create the `START_TIME` file inside the `run_id_dir`.
        # This code will ONLY run if the Gradio/Flask app *failed* to create the file.
        raise AssertionError(f"This code is not supposed to be run. Before starting the pipeline the '{FilenameEnum.START_TIME.value}' file must be present in the `run_id_dir`: {self.run_id_dir!r}")
