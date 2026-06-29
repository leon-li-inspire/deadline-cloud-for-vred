# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

import vrFileIO  # type: ignore[import]
import vrRenderSettings  # type: ignore[import]

from deadline.client.job_bundle.submission import AssetReferences
from deadline.client.submitter_api import SubmitterAPI, SubmitterSettings

# Template defaults for StartFrame/EndFrame (see default_vred_job_template.yaml);
# used when settings.frame_list is empty or cannot be parsed.
_DEFAULT_START_FRAME = 0
_DEFAULT_END_FRAME = 20


def _frame_range_from_settings(settings: SubmitterSettings) -> tuple[int, int]:
    """Derive integer (start_frame, end_frame) from settings.frame_list.

    The job template declares StartFrame/EndFrame as INT parameters (consumed by
    an INT task-parameter range expression), so the emitted values must be ints.
    settings.frame_list is a string such as "1-20" or "5"; falls back to the
    template defaults when it is empty or unparseable.
    """
    frame_list = (settings.frame_list or "").strip()
    if not frame_list:
        return _DEFAULT_START_FRAME, _DEFAULT_END_FRAME
    try:
        if "-" in frame_list.lstrip("-"):
            # Split on the range separator, preserving a leading sign on the start frame.
            sign = "-" if frame_list.startswith("-") else ""
            start_str, end_str = frame_list.lstrip("-").split("-", 1)
            return int(sign + start_str), int(end_str)
        single = int(frame_list)
        return single, single
    except ValueError:
        return _DEFAULT_START_FRAME, _DEFAULT_END_FRAME


@dataclass
class VREDSubmitterSettings(SubmitterSettings):
    """VRED-specific submission settings."""

    render_mode: str = "image"
    image_width: int = 1920
    image_height: int = 1080
    description: str = ""


class VREDSubmitterAPI(SubmitterAPI):
    """SubmitterAPI implementation for VRED submissions."""

    def get_settings(self) -> VREDSubmitterSettings:
        settings = VREDSubmitterSettings()

        scene_file = vrFileIO.getFileIOFilePath() or ""
        settings.name = os.path.basename(scene_file) if scene_file else "Untitled"
        settings.project_path = os.path.dirname(scene_file) if scene_file else ""
        settings.input_filenames = [scene_file] if scene_file else []

        # vrRenderSettings exposes module-level getters (there is no
        # getRenderSettings() object in VRED 2025/2026); use them directly.
        settings.image_width = vrRenderSettings.getRenderPixelWidth()
        settings.image_height = vrRenderSettings.getRenderPixelHeight()

        output_path = vrRenderSettings.getRenderFilename()
        if output_path:
            settings.output_path = os.path.dirname(output_path)
            settings.output_directories = [settings.output_path]

        start_frame = vrRenderSettings.getRenderStartFrame()
        end_frame = vrRenderSettings.getRenderStopFrame()
        if end_frame > start_frame:
            settings.frame_list = f"{start_frame}-{end_frame}"
        else:
            settings.frame_list = str(start_frame)

        return settings

    def get_job_template(
        self,
        settings: SubmitterSettings,
        host_requirements: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        template_path = Path(__file__).parent / "default_vred_job_template.yaml"
        with open(template_path) as fh:
            job_template = yaml.safe_load(fh)

        job_template["name"] = settings.name

        if isinstance(settings, VREDSubmitterSettings) and settings.description:
            job_template["description"] = settings.description

        if host_requirements:
            for step in job_template.get("steps", []):
                step["hostRequirements"] = host_requirements

        return job_template

    def get_parameter_values(
        self,
        settings: SubmitterSettings,
        queue_parameters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        scene_file = vrFileIO.getFileIOFilePath() or ""

        start_frame, end_frame = _frame_range_from_settings(settings)

        parameter_values: list[dict[str, Any]] = [
            {"name": "SceneFile", "value": scene_file},
            # OutputDir is a required template parameter with no default, so it
            # must always be emitted, otherwise CreateJob rejects the job:
            # "No parameter value provided for Job Template parameter OutputDir".
            {"name": "OutputDir", "value": settings.output_path},
            {"name": "StartFrame", "value": start_frame},
            {"name": "EndFrame", "value": end_frame},
            {"name": "deadline:priority", "value": settings.priority},
            {"name": "deadline:targetTaskRunStatus", "value": settings.initial_status},
            {"name": "deadline:maxFailedTasksCount", "value": settings.max_failed_tasks_count},
            {"name": "deadline:maxRetriesPerTask", "value": settings.max_retries_per_task},
        ]

        if isinstance(settings, VREDSubmitterSettings):
            # ImageWidth/ImageHeight are INT template parameters; vrRenderSettings
            # returns floats (e.g. 800.0) which fail INT validation (the value
            # regex "^[-]?(0|[1-9][0-9]*)$" does not match "800.0"). Coerce to int.
            parameter_values.append({"name": "ImageWidth", "value": int(settings.image_width)})
            parameter_values.append({"name": "ImageHeight", "value": int(settings.image_height)})

        parameter_values.extend(
            {"name": param["name"], "value": param["value"]} for param in queue_parameters
        )

        return parameter_values

    def get_asset_references(self, settings: SubmitterSettings) -> dict[str, Any]:
        asset_refs = AssetReferences(
            input_filenames=set(settings.input_filenames),
            input_directories=set(settings.input_directories),
            output_directories=set(settings.output_directories),
        )
        return asset_refs.to_dict()
