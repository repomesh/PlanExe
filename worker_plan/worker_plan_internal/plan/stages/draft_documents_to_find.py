"""DraftDocumentsToFindTask - Drafts bullet points for documents to find."""
import json
import logging
from llama_index.core.llms.llm import LLM
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.document.draft_document_to_find import DraftDocumentToFind
from worker_plan_internal.llm_util.llm_executor import LLMExecutor, PipelineStopRequested
from worker_plan_api.filenames import FilenameEnum
from worker_plan_api.speedvsdetail import SpeedVsDetailEnum
from worker_plan_internal.plan.stages.identify_purpose import IdentifyPurposeTask
from worker_plan_internal.plan.stages.strategic_decisions_markdown import StrategicDecisionsMarkdownTask
from worker_plan_internal.plan.stages.scenarios_markdown import ScenariosMarkdownTask
from worker_plan_internal.plan.stages.consolidate_assumptions_markdown import ConsolidateAssumptionsMarkdownTask
from worker_plan_internal.plan.stages.project_plan import ProjectPlanTask
from worker_plan_internal.plan.stages.filter_documents_to_find import FilterDocumentsToFindTask

logger = logging.getLogger(__name__)


class DraftDocumentsToFindTask(PlanTask):
    """Draft content specs for each document to find: essential info, risks, and scenarios."""
    def output(self):
        return self.local_target(FilenameEnum.DRAFT_DOCUMENTS_TO_FIND_CONSOLIDATED)

    def requires(self):
        return {
            'identify_purpose': self.clone(IdentifyPurposeTask),
            'strategic_decisions_markdown': self.clone(StrategicDecisionsMarkdownTask),
            'scenarios_markdown': self.clone(ScenariosMarkdownTask),
            'consolidate_assumptions_markdown': self.clone(ConsolidateAssumptionsMarkdownTask),
            'project_plan': self.clone(ProjectPlanTask),
            'filter_documents_to_find': self.clone(FilterDocumentsToFindTask),
        }

    def run_inner(self):
        llm_executor: LLMExecutor = self.create_llm_executor()

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
        with self.input()['filter_documents_to_find']['clean'].open("r") as f:
            documents_to_find = json.load(f)

        accumulated_documents = documents_to_find.copy()

        logger.info(f"DraftDocumentsToFindTask.speedvsdetail: {self.speedvsdetail}")
        if self.speedvsdetail == SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS:
            logger.info("FAST_BUT_SKIP_DETAILS mode, truncating to 2 chunks for testing.")
            documents_to_find = documents_to_find[:2]
        else:
            logger.info("Processing all chunks.")

        for index, document in enumerate(documents_to_find):
            logger.info(f"Document-to-find: Drafting document {index+1} of {len(documents_to_find)}...")

            # Build the query.
            query = (
                f"File 'strategic_decisions.md':\n{strategic_decisions_markdown}\n\n"
                f"File 'scenarios.md':\n{scenarios_markdown}\n\n"
                f"File 'assumptions.md':\n{assumptions_markdown}\n\n"
                f"File 'project-plan.md':\n{project_plan_markdown}\n\n"
                f"File 'document.json':\n{document}"
            )

            # IDEA: If the document already exist, then there is no need to run the LLM again.
            def execute_draft_document_to_find(llm: LLM) -> DraftDocumentToFind:
                return DraftDocumentToFind.execute(llm=llm, user_prompt=query, identify_purpose_dict=identify_purpose_dict)

            try:
                draft_document = llm_executor.run(execute_draft_document_to_find)
            except PipelineStopRequested:
                # Re-raise PipelineStopRequested without wrapping it
                raise
            except Exception as e:
                logger.error(f"Document-to-find {index+1} LLM interaction failed.", exc_info=True)
                raise ValueError(f"Document-to-find {index+1} LLM interaction failed.") from e

            json_response = draft_document.to_dict()

            # Write the raw JSON for this document using the FilenameEnum template.
            raw_filename = FilenameEnum.DRAFT_DOCUMENTS_TO_FIND_RAW_TEMPLATE.value.format(index+1)
            raw_chunk_path = self.run_id_dir / raw_filename
            with open(raw_chunk_path, 'w') as f:
                json.dump(json_response, f, indent=2)

            # Merge the draft document into the original document.
            document_updated = document.copy()
            for key in draft_document.response.keys():
                document_updated[key] = draft_document.response[key]
            accumulated_documents[index] = document_updated

        # Write the accumulated documents to the output file.
        with self.output().open("w") as f:
            json.dump(accumulated_documents, f, indent=2)
