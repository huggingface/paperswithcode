from pathlib import Path
from typing import Optional
import aiofiles


async def async_export_txt(
    *, filename: str, value: str, arxiv_id: Optional[str] = None
) -> None:
    """Asynchronously write a string to a txt file for debugging purposes.

    Args:
        filename: Name of the file (without .txt extension)
        value: Content to write to the file
        arxiv_id: If provided, writes to backend/outputs/evaluation_results/{arxiv_id}/
                 If None, writes to backend/outputs/ (for backwards compatibility)
    """
    if arxiv_id:
        output_dir = (
            Path(__file__).parent.parent / "outputs" / "evaluation_results" / arxiv_id
        )
    else:
        output_dir = Path(__file__).parent.parent / "outputs"

    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{filename}.txt"
    async with aiofiles.open(output_path, "w") as file:
        await file.write(value)
