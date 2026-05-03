"""InitialPlanRawTask - ExternalTask exposing the user-supplied plan_raw.json."""
from pathlib import Path
import luigi
from worker_plan_api.filenames import FilenameEnum


class InitialPlanRawTask(luigi.ExternalTask):
    """The user-supplied plan_raw.json that must exist before the pipeline starts.

    Tasks that want the bare prompt (rather than SetupTask's
    formatted plan.txt) require this and read it via PlanFile.
    """
    run_id_dir = luigi.Parameter()

    def output(self):
        return luigi.LocalTarget(str(Path(self.run_id_dir) / FilenameEnum.INITIAL_PLAN_RAW.value))
