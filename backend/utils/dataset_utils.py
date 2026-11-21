"""
Utility functions for working with datasets, especially handling dataset splits and variants.
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session

from backend.models.database import Dataset as DBDataset

logger = logging.getLogger(__name__)


def find_dataset_by_name(
    db: Session, dataset_name: str, prefer_splits: bool = True
) -> Optional[DBDataset]:
    """
    Find a dataset by name, with smart matching for splits and variants.

    This function handles matching dataset names from legacy PapersWithCode data
    to our structured dataset system with splits and variants.

    Examples:
        - "COCO test-dev" → finds split with split_name='test-dev'
        - "COCO minival" → finds split with split_name='minival'
        - "MS COCO" → finds parent COCO dataset
        - "COCO-Stuff" → finds COCO-Stuff variant

    Args:
        db: Database session
        dataset_name: Name of the dataset from legacy data (e.g., "COCO minival")
        prefer_splits: If True, prefer matching splits over parent datasets

    Returns:
        DBDataset object or None if not found
    """
    if not dataset_name:
        return None

    dataset_name_lower = dataset_name.lower().strip()

    exact_match = db.query(DBDataset).filter(DBDataset.name.ilike(dataset_name)).first()

    if exact_match:
        logger.debug(f"Found exact match for '{dataset_name}': {exact_match.name}")
        return exact_match

    split_patterns = {
        "test-dev": ["test-dev", "testdev", "test dev"],
        "test-challenge": ["test-challenge", "test challenge", "testchallenge"],
        "minival": ["minival", "mini val", "mini-val"],
        "val2017": ["val2017", "val 2017", "2017 val"],
        "val": ["validation", " val ", " val", "val "],
        "test": ["test", " test", "test "],
        "train": ["train", "training"],
    }

    for split_name, patterns in split_patterns.items():
        for pattern in patterns:
            if pattern in dataset_name_lower:
                base_name = dataset_name_lower
                for p in patterns:
                    base_name = base_name.replace(p, "").strip()

                split_match = (
                    db.query(DBDataset)
                    .filter(
                        DBDataset.split_name == split_name,
                        DBDataset.name.ilike(f"%{base_name}%"),
                    )
                    .first()
                )

                if split_match:
                    logger.debug(
                        f"Found split match for '{dataset_name}': "
                        f"{split_match.name} (split={split_name})"
                    )
                    return split_match

    words = [w for w in dataset_name_lower.split() if len(w) > 2]
    if words:
        query = db.query(DBDataset)
        for word in words[:3]:
            query = query.filter(DBDataset.name.ilike(f"%{word}%"))

        fuzzy_match = query.first()
        if fuzzy_match:
            logger.debug(f"Found fuzzy match for '{dataset_name}': {fuzzy_match.name}")
            return fuzzy_match

    if not prefer_splits:
        base_keywords = ["coco", "imagenet", "pascal", "cifar", "mnist"]
        for keyword in base_keywords:
            if keyword in dataset_name_lower:
                parent_match = (
                    db.query(DBDataset)
                    .filter(
                        DBDataset.name.ilike(f"%{keyword}%"),
                        DBDataset.parent_dataset_id.is_(None),
                    )
                    .first()
                )
                if parent_match:
                    logger.debug(
                        f"Found parent dataset for '{dataset_name}': {parent_match.name}"
                    )
                    return parent_match

    logger.warning(f"No dataset match found for '{dataset_name}'")
    return None


def get_or_create_dataset_split(
    db: Session,
    parent_dataset: DBDataset,
    split_name: str,
    full_name: Optional[str] = None,
    description: Optional[str] = None,
) -> DBDataset:
    """
    Get or create a dataset split.

    If the split already exists, return it. Otherwise, create a new split entry.

    Args:
        db: Database session
        parent_dataset: Parent dataset object
        split_name: Name of the split (e.g., "test-dev", "minival")
        full_name: Optional full name for the split
        description: Optional description

    Returns:
        DBDataset object for the split
    """
    existing_split = (
        db.query(DBDataset)
        .filter(
            DBDataset.parent_dataset_id == parent_dataset.id,
            DBDataset.split_name == split_name,
        )
        .first()
    )

    if existing_split:
        return existing_split

    split_display_name = f"{parent_dataset.name} {split_name}"
    slug = split_display_name.lower().replace(" ", "-").replace("_", "-")

    new_split = DBDataset(
        name=split_display_name,
        slug=slug,
        full_name=full_name
        or f"{parent_dataset.full_name or parent_dataset.name} - {split_name} Split",
        description=description or f"{split_name} split of {parent_dataset.name}",
        parent_dataset_id=parent_dataset.id,
        variant_type="split",
        split_name=split_name,
        homepage=parent_dataset.homepage,
        url=parent_dataset.url,
        license_name=parent_dataset.license_name,
        license_url=parent_dataset.license_url,
        introduced_year=parent_dataset.introduced_year,
        modalities=parent_dataset.modalities,
    )

    db.add(new_split)
    db.commit()
    db.refresh(new_split)

    logger.info(f"Created new dataset split: {new_split.name} (ID: {new_split.id})")
    return new_split


def get_dataset_with_splits(db: Session, dataset_id: int) -> dict:
    """
    Get a dataset along with all its splits and variants.

    Args:
        db: Database session
        dataset_id: ID of the dataset

    Returns:
        Dictionary with dataset info and its children
    """
    dataset = db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
    if not dataset:
        return None

    splits = (
        db.query(DBDataset)
        .filter(
            DBDataset.parent_dataset_id == dataset_id, DBDataset.variant_type == "split"
        )
        .order_by(DBDataset.split_name)
        .all()
    )

    variants = (
        db.query(DBDataset)
        .filter(
            DBDataset.parent_dataset_id == dataset_id, DBDataset.variant_type != "split"
        )
        .order_by(DBDataset.name)
        .all()
    )

    return {
        "dataset": dataset,
        "splits": splits,
        "variants": variants,
        "total_children": len(splits) + len(variants),
    }
