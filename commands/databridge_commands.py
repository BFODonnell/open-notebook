from surreal_commands import CommandInput, CommandOutput, command


class ImportDatasetInput(CommandInput):
    job_id: str


class ImportDatasetOutput(CommandOutput):
    success: bool
    job_id: str


@command("import_dataset", app="open_notebook", retry={"max_attempts": 1})
async def import_dataset_command(input_data: ImportDatasetInput) -> ImportDatasetOutput:
    from open_notebook.databridge.ingestion.service import process

    return ImportDatasetOutput(
        success=await process(input_data.job_id), job_id=input_data.job_id
    )
