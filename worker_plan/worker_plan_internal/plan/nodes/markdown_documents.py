"""MarkdownWithDocumentsToCreateAndFindTask - Creates markdown with documents to create and find."""
import json
from worker_plan_internal.plan.run_plan_pipeline import PlanTask
from worker_plan_internal.document.markdown_with_document import markdown_rows_with_document_to_create, markdown_rows_with_document_to_find
from worker_plan_api.filenames import FilenameEnum
from worker_plan_internal.plan.nodes.draft_documents_to_create import DraftDocumentsToCreateTask
from worker_plan_internal.plan.nodes.draft_documents_to_find import DraftDocumentsToFindTask


class MarkdownWithDocumentsToCreateAndFindTask(PlanTask):
    """Format drafted documents into a structured markdown with roles, templates, and approval steps."""
    def output(self):
        return self.local_target(FilenameEnum.DOCUMENTS_TO_CREATE_AND_FIND_MARKDOWN)

    def requires(self):
        return {
            'draft_documents_to_create': self.clone(DraftDocumentsToCreateTask),
            'draft_documents_to_find': self.clone(DraftDocumentsToFindTask),
        }

    def run_inner(self):
        # Read inputs from required tasks.
        with self.input()['draft_documents_to_create'].open("r") as f:
            documents_to_create = json.load(f)
        with self.input()['draft_documents_to_find'].open("r") as f:
            documents_to_find = json.load(f)

        accumulated_rows = []
        accumulated_rows.append("# Documents to Create")
        for index, document in enumerate(documents_to_create, start=1):
            rows = markdown_rows_with_document_to_create(index, document)
            accumulated_rows.extend(rows)

        accumulated_rows.append("\n\n# Documents to Find")
        for index, document in enumerate(documents_to_find, start=1):
            rows = markdown_rows_with_document_to_find(index, document)
            accumulated_rows.extend(rows)

        markdown_representation = "\n".join(accumulated_rows)

        # Write the markdown to the output file.
        output_file_path = self.output().path
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(markdown_representation)
