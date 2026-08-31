"""
Enrich existing datasets in the database with missing information.

This script:
1. Identifies datasets with evaluations that are missing descriptions, paper URLs, or HF URLs
2. Uses step_3 (information gathering) to find missing information
3. Updates the datasets in the database with the gathered information

Usage:
```bash
# Enrich all datasets missing information (dry-run by default)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py

# Enrich specific datasets by ID
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --dataset_ids 31 33 74

# Actually apply the updates (not dry-run)
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --apply

# Limit to top N datasets by evaluation count
uv run --env-file backend/keys.env extract_evaluation_results/enrich_datasets.py --limit 10 --apply
```
"""

import argparse
import asyncio
import json
import logging
from typing import Optional

from pydantic import BaseModel

from extract_evaluation_results.step_base import AgentStep
from extract_evaluation_results.tools import get_tasks_by_area, find_dataset
from backend.database.connection import db_manager
from backend.models.database import Dataset, Evaluation
from backend.models.evaluations import DatasetUpdateRequest
from backend.services.dataset_service import DatasetService
from sqlalchemy import func, or_

logger = logging.getLogger(__name__)


class DatasetEnrichmentInfo(BaseModel):
    """Information gathered to enrich a dataset."""

    description: Optional[str] = None
    full_name: Optional[str] = None
    hf_url: Optional[str] = None
    paper_url: Optional[str] = None


class EnrichDatasetInput(BaseModel):
    """Input for enriching a single dataset."""

    dataset_id: int
    dataset_name: str
    missing_fields: list[str]
    existing_info: dict


class EnrichDatasetOutput(BaseModel):
    """Output from enriching a dataset."""

    enrichment_info: DatasetEnrichmentInfo


dataset_enrichment_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape.

## Task

You need to enrich an existing dataset in our database by finding missing information.

The dataset is already in our database and is used in evaluation leaderboards, but some information is missing.
Your task is to search the web and Hugging Face to find:
- Description (if missing)
- Full name (if missing)
- Hugging Face URL (if missing)
- Paper URL/ArXiv URL (if missing)

## Dataset Information

You will be provided with:
- The dataset name (from our database)
- The dataset ID
- Any existing information we already have
- Which fields are missing

**IMPORTANT**: Only find information for the missing fields. Do NOT provide information for fields that already exist.

## Output format

```python
from pydantic import BaseModel

class DatasetEnrichmentInfo(BaseModel):
    description: Optional[str] = None
    full_name: Optional[str] = None
    hf_url: Optional[str] = None
    paper_url: Optional[str] = None
```

Return ONLY the missing fields. For example, if we already have a description, return description=None.
Do not make up information - only use verified information from your searches.

Strategy: Start with 2-3 focused searches to gather the essential missing information. Be efficient.
**IMPORTANT CONSTRAINT**: You have a maximum of 15 turns. Prioritize finding the most critical missing information.
"""


class EnrichDatasetStep(AgentStep[EnrichDatasetInput, EnrichDatasetOutput]):
    """Agent-based step for enriching existing datasets with missing information."""

    input_model = EnrichDatasetInput
    output_model = EnrichDatasetOutput

    def __init__(self):
        super().__init__(
            name="EnrichDataset: Dataset Information Enrichment",
            description="Enriches existing datasets with missing information from web and HF",
            instructions=dataset_enrichment_prompt,
            tools=[
                find_dataset,
                get_tasks_by_area,
            ],  # Removed update_dataset - we'll call service directly
            agent_output_type=DatasetEnrichmentInfo,
            model="gpt-5-mini",
            mcp_servers=["exa", "huggingface"],  # Exa required, HF optional
        )

    async def build_agent_prompt(self, inputs: EnrichDatasetInput) -> str:
        """Build the agent prompt with dataset context."""
        dataset_id = inputs.dataset_id
        dataset_name = inputs.dataset_name
        missing_fields = inputs.missing_fields
        existing_info = inputs.existing_info

        prompt_parts = [
            f"Dataset ID: {dataset_id}",
            f"Dataset Name: {dataset_name}",
            f"\nMissing fields: {', '.join(missing_fields)}",
        ]

        if existing_info:
            prompt_parts.append("\nExisting information:")
            for key, value in existing_info.items():
                if value:
                    prompt_parts.append(f"  - {key}: {value}")

        prompt_parts.append("\nPlease find the missing information for this dataset.")

        return "\n".join(prompt_parts)

    async def process_agent_output(
        self, agent_output: DatasetEnrichmentInfo, inputs: EnrichDatasetInput
    ) -> EnrichDatasetOutput:
        """Process the agent output into the expected output format."""
        return EnrichDatasetOutput(enrichment_info=agent_output)

    async def format_instructions(self, inputs: EnrichDatasetInput) -> str:
        """Format instructions (no task list needed for enrichment)."""
        return self.instructions


def get_datasets_missing_info(
    dataset_ids: Optional[list[int]] = None, limit: Optional[int] = None
):
    """Get datasets with evaluations that are missing information.

    Args:
        dataset_ids: Optional list of specific dataset IDs to process
        limit: Optional limit on number of datasets to return (ordered by eval count)

    Returns:
        List of dataset dictionaries with metadata about missing fields
    """
    with db_manager.session_local() as db:
        query = db.query(Dataset).join(Evaluation, Dataset.id == Evaluation.dataset_id)

        if dataset_ids:
            query = query.filter(Dataset.id.in_(dataset_ids))
        else:
            query = query.filter(
                or_(
                    Dataset.description is None,
                    Dataset.description == "",
                    Dataset.paper_url is None,
                    Dataset.paper_url == "",
                    Dataset.hf_url is None,
                    Dataset.hf_url == "",
                )
            )

        query = query.group_by(Dataset.id).order_by(func.count(Evaluation.id).desc())

        if limit:
            query = query.limit(limit)

        datasets = query.all()

        results = []
        for dataset in datasets:
            eval_count = (
                db.query(func.count(Evaluation.id))
                .filter(Evaluation.dataset_id == dataset.id)
                .scalar()
            )

            missing_fields = []
            if not dataset.description or not dataset.description.strip():
                missing_fields.append("description")
            if not dataset.paper_url or not dataset.paper_url.strip():
                missing_fields.append("paper_url")
            if not dataset.hf_url or not dataset.hf_url.strip():
                missing_fields.append("hf_url")

            # Only include if there are missing fields (when not filtering by IDs)
            if dataset_ids or missing_fields:
                results.append(
                    {
                        "id": dataset.id,
                        "name": dataset.name,
                        "slug": dataset.slug,
                        "eval_count": eval_count,
                        "missing_fields": missing_fields,
                        "existing_info": {
                            "description": dataset.description,
                            "full_name": dataset.full_name,
                            "url": dataset.url,
                            "hf_url": dataset.hf_url,
                            "paper_url": dataset.paper_url,
                        },
                    }
                )

        return results


async def enrich_single_dataset(dataset_info: dict, dry_run: bool = True) -> dict:
    """Enrich a single dataset with missing information.

    Args:
        dataset_info: Dictionary containing dataset metadata
        dry_run: If True, only gather information without updating

    Returns:
        Dictionary with enrichment results
    """
    dataset_id = dataset_info["id"]
    dataset_name = dataset_info["name"]
    missing_fields = dataset_info["missing_fields"]

    if not missing_fields:
        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "success": True,
            "message": "No missing fields to enrich",
            "updated_fields": [],
        }

    print(f"\nEnriching dataset: {dataset_name} (ID: {dataset_id})")
    print(f"  Missing fields: {', '.join(missing_fields)}")

    agent = None
    try:
        # Run the agent to gather information
        agent = EnrichDatasetStep()
        inputs = EnrichDatasetInput(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            missing_fields=missing_fields,
            existing_info=dataset_info["existing_info"],
        )

        result = await agent.run(inputs)

        if not result.success:
            return {
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "success": False,
                "message": result.error_message or "Agent failed to gather information",
                "updated_fields": [],
            }

        # Extract the enrichment info
        enrichment_output: EnrichDatasetOutput = result.outputs
        enrichment_info: DatasetEnrichmentInfo = enrichment_output.enrichment_info

        # Prepare update data (only fields that were found and were missing)
        update_data = {}
        if "description" in missing_fields and enrichment_info.description:
            update_data["description"] = enrichment_info.description
        if "paper_url" in missing_fields and enrichment_info.paper_url:
            update_data["paper_url"] = enrichment_info.paper_url
        if "hf_url" in missing_fields and enrichment_info.hf_url:
            update_data["hf_url"] = enrichment_info.hf_url
        if enrichment_info.full_name and not dataset_info["existing_info"].get(
            "full_name"
        ):
            update_data["full_name"] = enrichment_info.full_name

        if not update_data:
            return {
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "success": False,
                "message": "Agent did not find any new information",
                "updated_fields": [],
            }

        print(f"  Found information for: {', '.join(update_data.keys())}")

        if dry_run:
            print(f"  [DRY RUN] Would update with: {json.dumps(update_data, indent=2)}")
            return {
                "dataset_id": dataset_id,
                "dataset_name": dataset_name,
                "success": True,
                "message": "Dry run - would update dataset",
                "updated_fields": list(update_data.keys()),
                "gathered_data": update_data,
            }
        else:
            # Actually update the dataset using the backend service
            try:
                with db_manager.session_local() as db:
                    service = DatasetService(db)
                    update_request = DatasetUpdateRequest(**update_data)
                    updated_dataset = service.update_dataset(dataset_id, update_request)

                    result_msg = f"✓ Successfully updated dataset: ID={updated_dataset.id}, Name={updated_dataset.name}"
                    print(f"  {result_msg}")

                    return {
                        "dataset_id": dataset_id,
                        "dataset_name": dataset_name,
                        "success": True,
                        "message": result_msg,
                        "updated_fields": list(update_data.keys()),
                        "gathered_data": update_data,
                    }
            except Exception as e:
                error_msg = f"✗ Failed to update dataset: {str(e)}"
                print(f"  {error_msg}")
                return {
                    "dataset_id": dataset_id,
                    "dataset_name": dataset_name,
                    "success": False,
                    "message": error_msg,
                    "updated_fields": [],
                }

    except Exception as e:
        logger.error(f"Error enriching dataset {dataset_name}: {e}", exc_info=True)
        return {
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "success": False,
            "message": f"Error: {str(e)}",
            "updated_fields": [],
        }
    finally:
        # Ensure MCP servers are cleaned up for this agent instance
        if agent is not None:
            try:
                if hasattr(agent, "_mcp_servers") and agent._mcp_servers is not None:
                    await agent._cleanup_mcp_servers()
                    agent._mcp_servers = None
            except Exception as cleanup_error:
                logger.debug(
                    f"MCP server cleanup error (non-critical): {cleanup_error}"
                )

        # Note: Small delay not needed in parallel processing mode
        pass


async def main():
    parser = argparse.ArgumentParser(
        description="Enrich existing datasets with missing information"
    )
    parser.add_argument(
        "--dataset_ids",
        type=int,
        nargs="+",
        help="Specific dataset IDs to enrich (optional)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of datasets to process (ordered by evaluation count)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply the updates (default is dry-run mode)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=3,
        help="Number of datasets to process concurrently (default: 3, recommended for 4GB RAM)",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    if dry_run:
        print("=" * 80)
        print("DRY RUN MODE - No actual updates will be made")
        print("Use --apply flag to actually update the database")
        print("=" * 80)

    # Get datasets that need enrichment
    print("\nFetching datasets that need enrichment...")
    datasets = get_datasets_missing_info(dataset_ids=args.dataset_ids, limit=args.limit)

    if not datasets:
        print("No datasets found that need enrichment.")
        return

    print(f"\nFound {len(datasets)} dataset(s) to enrich:")
    for idx, ds in enumerate(datasets, 1):
        print(
            f"{idx}. {ds['name']} (ID: {ds['id']}) - Missing: {', '.join(ds['missing_fields'])}"
        )

    print("\n" + "=" * 80)
    print("Starting enrichment process...")
    print(f"Processing in batches of {args.batch_size} to manage memory usage")
    print("=" * 80)

    # Process datasets in batches to avoid OOM on VPS
    all_results = []
    batch_size = args.batch_size

    for batch_start in range(0, len(datasets), batch_size):
        batch_end = min(batch_start + batch_size, len(datasets))
        batch = datasets[batch_start:batch_end]

        batch_num = (batch_start // batch_size) + 1
        total_batches = (len(datasets) + batch_size - 1) // batch_size

        print(
            f"\n--- Batch {batch_num}/{total_batches} (datasets {batch_start + 1}-{batch_end}) ---"
        )

        # Process this batch in parallel
        tasks = [
            enrich_single_dataset(dataset_info, dry_run=dry_run)
            for dataset_info in batch
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert any exceptions to error results
        for idx, result in enumerate(batch_results):
            if isinstance(result, Exception):
                dataset_info = batch[idx]
                all_results.append(
                    {
                        "dataset_id": dataset_info["id"],
                        "dataset_name": dataset_info["name"],
                        "success": False,
                        "message": f"Error: {str(result)}",
                        "updated_fields": [],
                    }
                )
            else:
                all_results.append(result)

        # Show batch progress
        batch_success = sum(
            1
            for r in batch_results
            if not isinstance(r, Exception)
            and (isinstance(r, dict) and r.get("success"))
        )
        print(f"Batch {batch_num} completed: {batch_success}/{len(batch)} successful")

        # Add delay between batches for memory cleanup (except after last batch)
        if batch_end < len(datasets):
            print("Waiting 3 seconds for memory cleanup before next batch...")
            await asyncio.sleep(3)

    results = all_results

    # Print summary
    print("\n" + "=" * 80)
    print("ENRICHMENT SUMMARY")
    print("=" * 80)

    success_count = sum(1 for r in results if r["success"])
    print(f"Successfully enriched: {success_count}/{len(results)} datasets")

    if dry_run:
        print(
            "\n[DRY RUN] No actual updates were made. Use --apply to update the database."
        )

    print("\nDetails:")
    for idx, result in enumerate(results, 1):
        status = "✓" if result["success"] else "✗"
        print(f"{idx}. {status} {result['dataset_name']} (ID: {result['dataset_id']})")
        if result["updated_fields"]:
            print(f"   Updated: {', '.join(result['updated_fields'])}")
        print(f"   {result['message']}")


if __name__ == "__main__":
    asyncio.run(main())
