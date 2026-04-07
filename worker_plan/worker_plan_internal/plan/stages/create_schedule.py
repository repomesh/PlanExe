"""CreateScheduleTask - Builds the project schedule and exports Gantt charts."""
import json
from datetime import date, datetime
from typing import Any
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.schedule.project_schedule_populator import ProjectSchedulePopulator
from worker_plan_internal.schedule.schedule import ProjectSchedule
from worker_plan_internal.schedule.export_gantt_dhtmlx import ExportGanttDHTMLX
from worker_plan_internal.schedule.export_gantt_csv import ExportGanttCSV
from worker_plan_internal.wbs.wbs_task import WBSProject
from worker_plan_internal.wbs.wbs_task_tooltip import WBSTaskTooltip
from worker_plan_internal.plan.pipeline_config import PIPELINE_CONFIG
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.start_time import StartTimeTask
from worker_plan_internal.plan.stages.create_wbs_level1 import CreateWBSLevel1Task
from worker_plan_internal.plan.stages.identify_task_dependencies import IdentifyTaskDependenciesTask
from worker_plan_internal.plan.stages.estimate_task_durations import EstimateTaskDurationsTask
from worker_plan_internal.plan.stages.wbs_project_level1_level2_level3 import WBSProjectLevel1AndLevel2AndLevel3Task


class CreateScheduleTask(PlanTask):
    """Build the project schedule and generate Gantt charts."""

    def output(self):
        return {
            'dhtmlx_html': self.local_target(FilenameEnum.SCHEDULE_GANTT_DHTMLX_HTML),
            'machai_csv': self.local_target(FilenameEnum.SCHEDULE_GANTT_MACHAI_CSV)
        }

    def requires(self):
        return {
            'start_time': self.clone(StartTimeTask),
            'wbs_level1': self.clone(CreateWBSLevel1Task),
            'dependencies': self.clone(IdentifyTaskDependenciesTask),
            'durations': self.clone(EstimateTaskDurationsTask),
            'wbs_project123': self.clone(WBSProjectLevel1AndLevel2AndLevel3Task)
        }

    def run_inner(self):
        # For the report title, use the 'project_title' of the WBS Level 1 result.
        with self.input()['wbs_level1']['project_title'].open("r") as f:
            title = f.read()
        with self.input()['dependencies'].open("r") as f:
            dependencies_dict = json.load(f)
        with self.input()['durations'].open("r") as f:
            duration_list: list[dict[str, Any]] = json.load(f)
        wbs_project_path = self.input()['wbs_project123']['full'].path
        with open(wbs_project_path, "r") as f:
            wbs_project_dict = json.load(f)
        wbs_project = WBSProject.from_dict(wbs_project_dict)

        # Read the start time from the StartTimeTask to get the actual pipeline start date
        with self.input()['start_time'].open("r") as f:
            start_time_dict = json.load(f)

        # The start_time.server_iso_utc is in format "YYYY-MM-DDTHH:MM:SSZ"
        utc_timestamp = start_time_dict.get('server_iso_utc') or start_time_dict.get('utc_timestamp', '')
        # The 'Z' suffix for UTC is not supported by fromisoformat() in Python < 3.11. Replace, ensures compatibility.
        project_start_dt: datetime = datetime.fromisoformat(utc_timestamp.replace('Z', '+00:00'))
        project_start: date = project_start_dt.date()

        # logger.debug(f"dependencies_dict {dependencies_dict}")
        # logger.debug(f"duration_list {duration_list}")
        # logger.debug(f"wbs_project {wbs_project.to_dict()}")

        # Tooltips with a detailed description of each task.
        task_id_to_html_tooltip_dict: dict[str, str] = WBSTaskTooltip.html_tooltips(wbs_project)
        task_id_to_text_tooltip_dict: dict[str, str] = WBSTaskTooltip.text_tooltips(wbs_project)

        project_schedule: ProjectSchedule = ProjectSchedulePopulator.populate(
            wbs_project=wbs_project,
            duration_list=duration_list
        )

        # Export the Gantt chart to CSV.
        # Always run the CSV export so that the code gets exercised, otherwise the code will rot.
        csv_data: str = ExportGanttCSV.to_gantt_csv(
            project_schedule=project_schedule,
            project_start=project_start,
            task_id_to_tooltip_dict=task_id_to_text_tooltip_dict
        )
        if PIPELINE_CONFIG.enable_csv_export == False:
            # When disabled, then hide the "Export to CSV" button and don't embed the CSV data in the html report.
            csv_data = None

        ExportGanttCSV.save(
            project_schedule=project_schedule,
            path=self.output()['machai_csv'].path,
            project_start=project_start,
            task_id_to_tooltip_dict=task_id_to_text_tooltip_dict
        )

        # Identify the tasks that should be treated as project activities.
        task_ids_to_treat_as_project_activities = wbs_project.task_ids_with_one_or_more_children()

        # Export the Gantt chart to Frappe.
        # I'm disappointed by Frappe, it lacks a lot of features that are present in DHTMLX.
        # ExportGanttFrappe.save(
        #     project_schedule=project_schedule,
        #     path=self.output()['frappe_html'].path,
        #     project_start=project_start,
        #     task_ids_to_treat_as_project_activities=task_ids_to_treat_as_project_activities
        # )

        # Export the Gantt chart to DHTMLX.
        ExportGanttDHTMLX.save(
            project_schedule=project_schedule,
            path=self.output()['dhtmlx_html'].path,
            project_start=project_start,
            task_ids_to_treat_as_project_activities=task_ids_to_treat_as_project_activities,
            task_id_to_tooltip_dict=task_id_to_html_tooltip_dict,
            title=title,
            csv_data=csv_data
        )
