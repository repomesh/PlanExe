"""FilterDocumentsToFindTask - Narrows down documents to find to a relevant subset."""
import json
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.document.filter_documents_to_find import FilterDocumentsToFind
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.identify_documents import IdentifyDocumentsTask


class FilterDocumentsToFindTask(PlanTask):
    """
    The "documents to find" may be a long list of documents, some duplicates, irrelevant, not needed at an early stage of the project.
    This task narrows down to a handful of relevant documents.
    """
    def output(self):
        return {
            "raw": self.local_target(FilenameEnum.FILTER_DOCUMENTS_TO_FIND_RAW),
            "clean": self.local_target(FilenameEnum.FILTER_DOCUMENTS_TO_FIND_CLEAN)
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
        with self.input()['identified_documents']['documents_to_find'].open("r") as f:
            documents_to_find = json.load(f)

        # Build the query.
        process_documents, integer_id_to_document_uuid = FilterDocumentsToFind.process_documents_and_integer_ids(documents_to_find)
        query = (
            f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
            f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
            f"File 'assumptions.md':\n{assumptions_markdown}\n\n"
            f"File 'project-plan.md':\n{project_plan_markdown}\n\n"
            f"File 'documents.json':\n{process_documents}"
        )

        # Invoke the LLM.
        filter_documents = FilterDocumentsToFind.execute(
            llm=llm,
            user_prompt=query,
            identified_documents_raw_json=documents_to_find,
            integer_id_to_document_uuid=integer_id_to_document_uuid,
            identify_purpose_dict=identify_purpose_dict
        )

        # Save the results.
        filter_documents.save_raw(self.output()["raw"].path)
        filter_documents.save_filtered_documents(self.output()["clean"].path)
