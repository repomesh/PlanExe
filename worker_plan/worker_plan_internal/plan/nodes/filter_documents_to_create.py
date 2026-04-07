"""FilterDocumentsToCreateTask - Narrows down documents to create to a relevant subset."""
import json
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.document.filter_documents_to_create import FilterDocumentsToCreate
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.nodes.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.nodes.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.nodes.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.nodes.project_plan import ProjectPlanTask
from worker_plan_internal.plan.nodes.identify_documents import IdentifyDocumentsTask


class FilterDocumentsToCreateTask(PlanTask):
    """Narrow the documents-to-create list to the most relevant ones for the current plan."""
    def output(self):
        return {
            "raw": self.local_target(FilenameEnum.FILTER_DOCUMENTS_TO_CREATE_RAW),
            "clean": self.local_target(FilenameEnum.FILTER_DOCUMENTS_TO_CREATE_CLEAN)
        }

    def requires(self):
        return {
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'identified_documents': self.clone(IdentifyDocumentsTask),
        }

    def run_with_llm(self, llm: LLM) -> None:
        # Read inputs from required tasks.
        with self.input()['identify_purpose']['raw'].open("r") as f:
            identify_purpose_dict = json.load(f)
        with self.input()['strategic_decisions_markdown']['markdown'].open("r") as f:
            strategic_decisions_markdown = f.read()
        with self.input()['scenarios_markdown']['markdown'].open("r") as f:
            scenarios_markdown = f.read()
        with self.input()['consolidate_assumptions_markdown']['short'].open("r") as f:
            assumptions_markdown = f.read()
        with self.input()['project_plan']['markdown'].open("r") as f:
            project_plan_markdown = f.read()
        with self.input()['identified_documents']['documents_to_create'].open("r") as f:
            documents_to_create = json.load(f)

        # Build the query.
        process_documents, integer_id_to_document_uuid = FilterDocumentsToCreate.process_documents_and_integer_ids(documents_to_create)
        query = (
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{assumptions_markdown}\n\n"
            f"File 'project-plan.md':\n{project_plan_markdown}\n\n"
            f"File 'documents.json':\n{process_documents}"
        )

        # Invoke the LLM.
        filter_documents = FilterDocumentsToCreate.execute(
            llm=llm,
            user_prompt=query,
            identified_documents_raw_json=documents_to_create,
            integer_id_to_document_uuid=integer_id_to_document_uuid,
            identify_purpose_dict=identify_purpose_dict
        )

        # Save the results.
        filter_documents.save_raw(self.output()["raw"].path)
        filter_documents.save_filtered_documents(self.output()["clean"].path)
