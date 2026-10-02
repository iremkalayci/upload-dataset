
from pydantic import Field
from typing import Optional, Union, Literal

from sdks.novavision.src.base.model import (
    Package,
    Inputs,
    Configs,
    Outputs,
    Response,
    Request,
    Output,
    Input,
    Config,
)


class InputImage(Input):
    name: Literal["inputImage"] = "inputImage"
    value: str
    type: Literal["object"] = "object"

    class Config:
        title = "Image"


class OutputImage(Output):
    name: Literal["outputImage"] = "outputImage"
    value: str
    type: Literal["object"] = "object"

    class Config:
        title = "Image"


class ConfigDataset(Config):
    """Select a dataset from the current workspace."""

    name: Literal["configDataset"] = "configDataset"
    value: str
    type: Literal["string"] = "string"
    field: Literal["widget"] = "widget"

    class Config:
        title = "Dataset"
        json_schema_extra = {
            "shortDescription": "Dataset Picker",
            "class": "\\novavision\\data\\widgets\\DatasetPicker",
        }


class ConfigFrameInterval(Config):
    """Save one frame for every N incoming frames."""

    name: Literal["FrameInterval"] = "FrameInterval"
    value: int = Field(default=5, ge=1)
    type: Literal["number"] = "number"
    field: Literal["textInput"] = "textInput"
    placeHolder: Literal["1, 2, 5, ..."] = "1, 2, 5, ..."

    class Config:
        title = "Frame Sampling Interval"
        json_schema_extra = {
            "shortDescription": "Save one frame for every N frames"
        }


class UploadDatasetInputs(Inputs):
    inputImage: InputImage


class UploadDatasetConfigs(Configs):
    dataset: ConfigDataset
    frameInterval: ConfigFrameInterval


class UploadDatasetOutputs(Outputs):
    outputImage: OutputImage


class UploadDatasetRequest(Request):
    inputs: Optional[UploadDatasetInputs] = None
    configs: UploadDatasetConfigs

    class Config:
        json_schema_extra = {
            "target": "configs"
        }


class UploadDatasetResponse(Response):
    outputs: UploadDatasetOutputs


class UploadDatasetExecutor(Config):
    """
    Select and prepare video frames for dataset upload.
    """

    name: Literal["UploadDataset"] = "UploadDataset"
    value: Union[UploadDatasetRequest, UploadDatasetResponse]
    type: Literal["object"] = "object"
    field: Literal["option"] = "option"

    class Config:
        title = "Upload Dataset"
        json_schema_extra = {
            "target": {
                "value": 0
            }
        }


class ConfigExecutor(Config):
    name: Literal["ConfigExecutor"] = "ConfigExecutor"
    value: Union[UploadDatasetExecutor]
    type: Literal["executor"] = "executor"
    field: Literal["dependentDropdownlist"] = "dependentDropdownlist"

    class Config:
        title = "Task"
        json_schema_extra = {
            "target": "value"
        }


class PackageConfigs(Configs):
    executor: ConfigExecutor


class PackageModel(Package):
    configs: PackageConfigs
    type: Literal["component"] = "component"
    name: Literal["UploadDataset"] = "UploadDataset"
