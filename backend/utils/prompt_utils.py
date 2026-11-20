from pathlib import Path
import json
import os
import re
from typing import List, Dict, Any


ROOT_FOLDER = Path(__file__).resolve().parent.parent


class PromptTemplate:
    def __init__(
        self,
        template: str,
        input_variables: List[str],
        partial_variables: Dict[str, Any] = None,
    ):
        self.template = template
        self.input_variables = input_variables
        self.partial_variables = partial_variables or {}

    @classmethod
    def from_template(cls, template: str) -> "PromptTemplate":
        input_variables = cls._get_template_variables(template)
        return cls(template=template, input_variables=input_variables)

    @staticmethod
    def _get_template_variables(template: str) -> List[str]:
        return list(set(re.findall(r"\{(\w+)\}", template)))

    def format(self, **kwargs: Any) -> str:
        kwargs = {**self.partial_variables, **kwargs}
        return self.template.format(**kwargs)


def load_prompt(config_path: str, subfolder_name="templates") -> PromptTemplate:
    """
    Load a prompt template from a JSON file.

    Returns:
        PromptTemplate: A prompt template object.
    """
    config_file = ROOT_FOLDER / "prompts" / config_path
    with open(config_file, "r") as file:
        config = json.load(file)

    template_path = os.path.join(
        ROOT_FOLDER, "prompts", subfolder_name, config["template_path"]
    )
    with open(template_path, "r") as file:
        template = file.read()

    prompt_template = PromptTemplate.from_template(template)

    return prompt_template
