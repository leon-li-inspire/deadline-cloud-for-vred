# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from deadline.client.submitter_api import SubmitterAPI, SubmitterSettings


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
        import vrFileIO  # type: ignore[import]
        import vrRenderSettings  # type: ignore[import]

        settings = VREDSubmitterSettings()

        scene_file = vrFileIO.getFileIOFilePath() or ""
        settings.name = os.path.basename(scene_file) if scene_file else "Untitled"
        settings.project_path = os.path.dirname(scene_file) if scene_file else ""
        settings.input_filenames = [scene_file] if scene_file else []

        render_settings = vrRenderSettings.getRenderSettings()
        if render_settings:
            settings.image_width = render_settings.getWidth()
            settings.image_height = render_settings.getHeight()

            output_path = render_settings.getFilename()
            if output_path:
                settings.output_path = os.path.dirname(output_path)
                settings.output_directories = [settings.output_path]

        start_frame = vrRenderSettings.getStartFrame()
        end_frame = vrRenderSettings.getEndFrame()
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
        import yaml
        from pathlib import Path

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
        import vrFileIO  # type: ignore[import]

        scene_file = vrFileIO.getFileIOFilePath() or ""

        parameter_values: list[dict[str, Any]] = [
            {"name": "VREDSceneFile", "value": scene_file},
            {"name": "Frames", "value": settings.frame_list},
            {"name": "deadline:priority", "value": settings.priority},
            {"name": "deadline:targetTaskRunStatus", "value": settings.initial_status},
            {"name": "deadline:maxFailedTasksCount", "value": settings.max_failed_tasks_count},
            {"name": "deadline:maxRetriesPerTask", "value": settings.max_retries_per_task},
        ]

        if isinstance(settings, VREDSubmitterSettings):
            parameter_values.append({"name": "RenderMode", "value": settings.render_mode})
            parameter_values.append({"name": "ImageWidth", "value": settings.image_width})
            parameter_values.append({"name": "ImageHeight", "value": settings.image_height})

        parameter_values.extend(
            {"name": param["name"], "value": param["value"]} for param in queue_parameters
        )

        return parameter_values

    def get_asset_references(self, settings: SubmitterSettings) -> dict[str, Any]:
        from deadline.client.job_bundle.submission import AssetReferences

        asset_refs = AssetReferences(
            input_filenames=set(settings.input_filenames),
            input_directories=set(settings.input_directories),
            output_directories=set(settings.output_directories),
        )
        return asset_refs.to_dict()
